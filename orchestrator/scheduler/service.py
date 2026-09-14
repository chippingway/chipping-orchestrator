# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The concrete ``IssueScheduler`` and the layers it is built from.

The scheduler's responsibilities are split across four layers that only this
module composes: read-only state inspection plus temporary claims, atomic slot
admission and release, the reversible barrier that closes both admission paths
and waits the admitted work out, and worker dispatch with completion draining.
Callers import the composed ``IssueScheduler`` directly from this module.

What a refused submission MEANT is not one of them. A submission this
scheduler declines costs its caller a turn, and the caller decides what that
is worth -- a cleanup refused because a worker already holds the issue costs
an observation instead, and the workflow keeps that reading somewhere its own
stage handlers can reach it rather than here, where nothing above the slot
accounting could.

The one thing this scheduler answers about the whole host rather than about one
submission is whether it has gone quiet, and it answers it only while holding
admission closed: a caller that has to act on the absence of work needs the
absence to still be true one line later. What such a caller then DOES under
that hold is not one of the responsibilities either.
"""
from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from orchestrator.scheduler import models

log = logging.getLogger("orchestrator.scheduler")

# The exempt pool is sized independently of ``global_cap`` so a tight cap (e.g.
# ``global_cap=1``) does not transitively cap cap-exempt throughput across
# repos. The bound is deliberately generous: exempt handlers are fast label /
# dep-graph walks with no agent and no worktree.
_EXEMPT_POOL_WORKERS = 32

# What a submission refused by a held maintenance barrier is reported as. Kept
# apart from ``closed`` because the two cost the caller different things: a
# closed scheduler never admits anything again and its caller is on the way
# out, while this one is over as soon as the pass behind it is, and the next
# polling pass submits the same issue again.
_BARRED_SKIP_REASON = "maintenance"


class _SchedulerViewMixin:
    """Read-only scheduler state and temporary active tracking."""

    @property
    def global_cap(self) -> int:
        return self._global_cap

    @property
    def per_repo_cap(self) -> int:
        return self._per_repo_cap

    def active_count(self, repo_slug: str | None = None) -> int:
        """Return counted in-flight workers, globally or for one repo."""
        with self._lock:
            if repo_slug is None:
                return len(self._active)
            return self._per_repo_active.get(repo_slug, 0)

    def is_active(self, repo_slug: str, issue_number: int) -> bool:
        """Return whether a counted or tracked claim owns an issue key."""
        issue_key = (repo_slug, int(issue_number))
        with self._lock:
            return issue_key in self._active or issue_key in self._tracked

    def is_closed(self) -> bool:
        """Whether submission has been closed for good by a shutdown.

        The reading a caller holding a granted barrier comes back for. What the
        hold answered was true when it was given, and a signal landing a line
        later closes this scheduler while that answer is still in the caller's
        hand -- so anything acting on the quiet asks again as it goes.
        """
        with self._lock:
            return self._closed

    @contextlib.contextmanager
    def track_active(
        self,
        repo_slug: str,
        issue_number: int,
    ) -> Iterator[bool]:
        """Temporarily claim an issue without consuming a cap slot."""
        issue_key = (repo_slug, int(issue_number))
        claimed = False
        with self._lock:
            if self._claimable_locked(issue_key):
                self._tracked.add(issue_key)
                claimed = True
        try:
            yield claimed
        finally:
            if claimed:
                with self._lock:
                    self._tracked.discard(issue_key)
                    self._quiet.notify_all()

    def _claimable_locked(self, issue_key: tuple[str, int]) -> bool:
        """Whether a temporary claim may be admitted for this issue key.

        A held barrier refuses one exactly as a live claim on the same issue
        does, because the caller answers both the same way: it skips this
        iteration and the next polling pass takes the issue up again. Without
        that refusal a family bucket already running could claim an issue after
        the barrier had counted the claims and found none.
        """
        if self._barred:
            return False
        return issue_key not in self._active and issue_key not in self._tracked


class _SchedulerReservationMixin(_SchedulerViewMixin):
    """Atomic slot admission, logging, and release."""

    def _cap_skip_reason_locked(
        self,
        submission: models.Submission,
    ) -> str | None:
        if len(self._active) >= self._global_cap:
            return "global_cap"
        repo_active = self._per_repo_active.get(submission.repo_slug, 0)
        if repo_active >= submission.per_repo_cap:
            return "per_repo_cap"
        return None

    def _admission_skip_reason_locked(self) -> str | None:
        """Whether this scheduler is admitting anything at all right now.

        The two refusals that are about the scheduler rather than about the
        submission in hand, asked before any of the per-submission gates
        because neither one has to look at it to answer.
        """
        if self._closed:
            return "closed"
        return _BARRED_SKIP_REASON if self._barred else None

    def _skip_reason_locked(
        self,
        submission: models.Submission,
    ) -> str | None:
        admission_reason = self._admission_skip_reason_locked()
        if admission_reason is not None:
            return admission_reason
        if submission.key in self._active or submission.key in self._tracked:
            return "duplicate_active"
        if not submission.cap_exempt:
            cap_reason = self._cap_skip_reason_locked(submission)
            if cap_reason is not None:
                return cap_reason
        if (
            submission.family
            and submission.repo_slug in self._family_active_repos
        ):
            return "family_slot_held"
        return None

    def _log_skip_locked(
        self,
        submission: models.Submission,
        reason: str,
    ) -> None:
        if reason == "duplicate_active":
            log.debug(
                "scheduler skip repo=%s issue=#%s reason=duplicate_active",
                submission.repo_slug,
                submission.issue_number,
            )
            return
        if reason == "global_cap":
            log.info(
                "scheduler skip repo=%s issue=#%s reason=global_cap "
                "(active=%d cap=%d)",
                submission.repo_slug,
                submission.issue_number,
                len(self._active),
                self._global_cap,
            )
            return
        if reason == "per_repo_cap":
            log.info(
                "scheduler skip repo=%s issue=#%s reason=per_repo_cap "
                "(active=%d cap=%d)",
                submission.repo_slug,
                submission.issue_number,
                self._per_repo_active.get(submission.repo_slug, 0),
                submission.per_repo_cap,
            )
            return
        log.info(
            "scheduler skip repo=%s issue=#%s reason=%s",
            submission.repo_slug,
            submission.issue_number,
            reason,
        )

    def _reserve_slot_locked(
        self,
        submission: models.Submission,
    ) -> None:
        if submission.cap_exempt:
            self._tracked.add(submission.key)
        else:
            self._active.add(submission.key)
            self._per_repo_active[submission.repo_slug] += 1
        if submission.family:
            self._family_active_repos.add(submission.repo_slug)

    def _release_slot_locked(
        self,
        submission: models.Submission,
    ) -> None:
        if submission.cap_exempt:
            self._tracked.discard(submission.key)
        else:
            self._active.discard(submission.key)
            active_count = self._per_repo_active.get(submission.repo_slug, 0)
            if active_count <= 1:
                self._per_repo_active.pop(submission.repo_slug, None)
            else:
                self._per_repo_active[submission.repo_slug] = active_count - 1
        if submission.family:
            self._family_active_repos.discard(submission.repo_slug)
        # Every path a counted slot or an exempt claim is given back on ends
        # here, so this is the one place a barrier waiting for the host to go
        # quiet has to be woken from -- the completed worker, and the submit
        # whose executor would not take the work after the slot was reserved.
        self._quiet.notify_all()


class _SchedulerBarrierMixin(_SchedulerReservationMixin):
    """The reversible hold under which the host can be proved quiet.

    Two halves, and the second is worthless without the first: admission is
    closed for both kinds of claim, and only then is the work already admitted
    waited out. A caller that merely waited for the counters to reach zero
    would be told about a moment that had already passed by the time it acted.

    Nothing already running is cancelled or hurried. A worker mid-agent-run
    keeps its slot until it exits, which is why the wait is bounded and why
    failing it is an ordinary answer rather than an error: the caller does
    nothing this time and asks again later, and the host it declined to act on
    is one that was busy.

    Reversal is the invariant. The hold is taken and given back around one
    body, so a caller that raises, returns early, or is refused the quiet it
    asked for still leaves admission exactly as it found it.
    """

    @contextlib.contextmanager
    def maintenance_barrier(self, *, timeout: float) -> Iterator[bool]:
        """Close admission, and say whether the admitted work then drained.

        The answer is the whole contract: `True` is every counted worker and
        every tracked claim gone while this hold keeps new ones out, and
        `False` is a caller that may not act on the state of this host at all.
        A scheduler already closed answers `False` without taking the hold --
        a process on its way out has a drain of its own to run, and holding
        admission shut in front of it would only slow that down. So does a
        scheduler whose hold somebody else has: the pass under the first one
        owns that window, and a second hold given back on its way out would
        reopen this host underneath it.
        """
        with self._lock:
            held = not self._closed and not self._barred
            if held:
                self._barred = True
        try:
            yield held and self._quiesced(timeout)
        finally:
            if held:
                with self._lock:
                    self._barred = False

    def _pending_locked(self) -> bool:
        """Whether any counted worker or tracked claim is still in flight."""
        return bool(self._active or self._tracked)

    def _quiesced(self, timeout: float) -> bool:
        """Wait out the work already admitted, within one finite bound.

        Woken by each release rather than polling for it, so the common case --
        a host with nothing running -- costs one read, and a host that goes
        quiet mid-wait is acted on the moment it does.

        A shutdown arriving during the wait ends it as the timeout does. The
        caller is deferring either way, and a drain the process itself has
        started is not the quiet this hold was asked to establish.
        """
        deadline = time.monotonic() + timeout
        with self._lock:
            while self._pending_locked():
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._closed:
                    break
                self._quiet.wait(remaining)
            quiet = not self._pending_locked() and not self._closed
            if not quiet:
                self._log_barrier_timeout_locked(timeout)
            return quiet

    def _log_barrier_timeout_locked(self, timeout: float) -> None:
        log.info(
            "scheduler maintenance barrier found no quiet within %.0fs "
            "(workers=%d claims=%d closed=%s)",
            timeout,
            len(self._active),
            len(self._tracked),
            self._closed,
        )


class _SchedulerExecutionMixin(_SchedulerBarrierMixin):
    """Worker dispatch, completion draining, and shutdown coordination."""

    def submit(self, *args: Any, **kwargs: Any) -> bool:
        """Dispatch a typed request or the historical submit call shape."""
        request = models.bind_submission_request(args, kwargs)
        submission = models.normalize_submission(
            request,
            self._per_repo_cap,
        )
        with self._lock:
            skip_reason = self._skip_reason_locked(submission)
            if skip_reason is not None:
                self._log_skip_locked(submission, skip_reason)
                return False
            self._reserve_slot_locked(submission)
            return self._start_worker_locked(submission)

    def reap(self) -> int:
        """Drain completed futures and log worker exceptions."""
        with self._lock:
            drained_futures = self._completed
            self._completed = []
        for future in drained_futures:
            error = future.exception()
            if error is not None:
                log.error("scheduler worker raised", exc_info=error)
        return len(drained_futures)

    def shutdown(self, *, wait: bool = True) -> None:
        """Close submission, stop both executors, and drain completions."""
        with self._lock:
            self._closed = True
            # A barrier waiting for this host to go quiet is waiting for
            # something a closing scheduler will not give it, so the close is
            # what releases it rather than the bound it was given.
            self._quiet.notify_all()
        self._executor.shutdown(wait=wait)
        self._exempt_executor.shutdown(wait=wait)
        self.reap()

    def _start_worker_locked(
        self,
        submission: models.Submission,
    ) -> bool:
        executor = (
            self._exempt_executor
            if submission.cap_exempt
            else self._executor
        )
        try:
            future = executor.submit(submission.fn)
        except RuntimeError:
            self._release_slot_locked(submission)
            return False
        future.add_done_callback(
            lambda completed_future: self._on_worker_done(
                completed_future,
                submission,
            ),
        )
        return True

    def _on_worker_done(
        self,
        future: Future,
        submission: models.Submission,
    ) -> None:
        with self._lock:
            self._release_slot_locked(submission)
            self._completed.append(future)


class IssueScheduler(_SchedulerExecutionMixin):
    """Long-lived scheduler shared by every repository polling tick."""

    def __init__(
        self,
        *,
        global_cap: int,
        per_repo_cap: int,
        thread_name_prefix: str = "orch-worker",
    ) -> None:
        self._global_cap = max(1, int(global_cap))
        self._per_repo_cap = max(1, int(per_repo_cap))
        self._executor = ThreadPoolExecutor(
            max_workers=self._global_cap,
            thread_name_prefix=thread_name_prefix,
        )
        self._exempt_executor = ThreadPoolExecutor(
            max_workers=_EXEMPT_POOL_WORKERS,
            thread_name_prefix=f"{thread_name_prefix}-exempt",
        )
        self._lock = threading.RLock()
        # Signalled whenever a counted slot or a tracked claim is given back,
        # over the same lock every count is read under: a barrier is woken by
        # the release that made the host quiet, in the same critical section
        # that made it so, and cannot see a count that has moved since.
        self._quiet = threading.Condition(self._lock)
        self._active: set[tuple[str, int]] = set()
        self._tracked: set[tuple[str, int]] = set()
        self._per_repo_active: dict[str, int] = defaultdict(int)
        self._family_active_repos: set[str] = set()
        self._completed: list[Future] = []
        self._closed = False
        # Whether a maintenance barrier is holding admission closed. Read by
        # both admission paths -- the counted submit and the tracked claim --
        # since the pass behind it is entitled to the absence of both.
        self._barred = False


IssueScheduler.submit.__signature__ = models._SUBMIT_METHOD_SIGNATURE
