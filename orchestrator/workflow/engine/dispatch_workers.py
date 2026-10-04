# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Refetch and process ordinary and cleanup work under the appropriate close scope.

Each worker entry takes the issue's writer claim before anything else, so its
refetch and observation scopes run under it and a contender leaves every
reading as it found it; the sequential loop's pass refetches under the claim
its own entry took. Workers retain their thread-local GitHub client and
optional semaphore. Closed readings and cleanup passes finish through their
observation contexts so a race or failed pass cannot discard the owed ending.
"""
from __future__ import annotations

import contextlib
import functools
from collections.abc import Callable

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import (
    cleanup_observation as _cleanup_observation,
    dispatch_closure as _dispatch_closure,
    issue_processing as _issue_processing,
    observations,
    poll_models as _poll_models,
)


def _polled_refetch(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    *,
    reading: _poll_models._PollReading,
) -> None:
    """Read one polled issue again under its writer claim, and dispatch that.

    The sequential entry took the claim after the poll did its reading, and
    another poller on this host may have advanced the issue in between: a
    handler routed off the enumeration's object would resume a stage that
    poller already left -- relabelling the issue back and handing it to an
    agent a second time. So the label a handler is chosen by is the one this
    read returns, as on every worker path.

    What the poll established is carried over that read only where it is a
    close. A CLOSED reading is held across the whole pass, refetch included,
    for the reason the worker paths hold theirs: nothing latched it, this pass
    is what would have acted on it, and neither a raise nor a pinned read the
    guard could not take may cost it. It is bound rather than re-read, so a
    reopen in between cannot turn it into an agent-spawning stage handler. An
    OPEN reading carries nothing, which makes the refetch the place a close
    can first exist, and the dispatch is wrapped in the hold one earns.

    Refetched on the caller's own client rather than through
    `_refetch_and_process`: nothing here crosses a thread, so what that mints
    a per-worker client for does not apply, while the read it takes does.
    """
    held = (
        _dispatch_closure._closed_reading(gh, spec, issue_number, reading.read_at)
        if reading.closed else contextlib.nullcontext()
    )
    with held:
        refetched = gh.get_issue(issue_number)
        with _dispatch_closure._refetched_close(gh, spec, refetched, reading):
            _issue_processing._process_issue(gh, spec, refetched, reading=reading)


def _refetch_and_process(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    *,
    semaphore_cm: contextlib.AbstractContextManager | None = None,
    reading: _poll_models._PollReading = _poll_models._POLLED_OPEN,
) -> None:
    """Mint a per-worker client, refetch the Issue, and run its handler.

    Only issue NUMBERS cross the thread boundary. PyGithub's ``Issue`` and
    the parent ``GitHubClient`` / ``Repository`` / ``Requester`` chain hold
    mutable per-request state that is not documented thread-safe, so each
    worker calls ``gh._for_worker_thread()`` to mint a fresh client and
    refetches its Issue against THAT client -- every in-flight HTTP call is
    then the sole consumer of its requester's state.

    ``semaphore_cm`` wraps the ``_process_issue`` call so the in-tick parallel
    path can thread the cross-repo ``global_semaphore`` through here; the
    scheduler path leaves it ``None`` (a no-op) because the scheduler owns
    the cross-repo cap itself.

    ``cleanup_only`` rides along because the refetch is exactly where a
    classification can go stale. A closed cleanup owner is submitted on its
    own cap-exempt terms, and a reopen between the poll and this call must not
    turn that submit into an agent-spawning stage handler running outside the
    caps -- so the route is carried rather than re-derived.

    Staleness runs the other way too, and that one is an OBSERVATION rather
    than a route: an issue open when it was listed can be closed by the time
    this reads it, and nothing in this process holds that reading. It is
    taken here, against the object the refetch just returned.

    The issue's writer claim is taken first, ahead of the refetch, and a
    contender returns having read nothing: the pass is retried on a later
    polling pass, and this one has nothing to keep.
    """
    with _issue_processing._writer_claim(gh, spec, issue_number) as held:
        if held:
            _refetched_pass(
                gh, spec, issue_number,
                semaphore_cm=semaphore_cm, reading=reading,
            )


def _refetched_pass(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    *,
    semaphore_cm: contextlib.AbstractContextManager | None,
    reading: _poll_models._PollReading,
) -> None:
    """The refetch and dispatch a worker runs once it holds the issue.

    Apart from its claim because the closed and cleanup passes take that claim
    outside the observation scope they wrap this in, and a second claim on the
    same issue would be refused by the first.
    """
    worker_gh = gh._for_worker_thread()
    worker_issue = worker_gh.get_issue(issue_number)
    cm = contextlib.nullcontext() if semaphore_cm is None else semaphore_cm
    with cm, _dispatch_closure._refetched_close(worker_gh, spec, worker_issue, reading):
        _issue_processing._process_issue(worker_gh, spec, worker_issue, reading=reading)


def _fanout_task(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    *,
    reading: _poll_models._PollReading,
    semaphore_cm: contextlib.AbstractContextManager | None = None,
) -> Callable[[], None]:
    """The callable one fan-out submit hands the scheduler.

    An ordinary issue is refetched and dispatched, and what it carries with it
    is the poll's own CLOSED reading: the worker refetches, so a human who
    reopens the issue in that window would otherwise have the fresh reading
    say open and a live late cycle resume against it. The reading is the
    poll's, so it is bound rather than re-derived.

    A cleanup carries an OBSERVATION as well as a turn, so it is wrapped in
    the settlement that observation is owed -- which is a thing only the
    worker can decide, since only the worker knows whether the pass ran.
    """
    if reading.cleanup_only:
        return functools.partial(
            _swept_for_cleanup, gh, spec, issue_number,
            semaphore_cm=semaphore_cm,
        )
    if reading.closed:
        return functools.partial(
            _closed_ordinary_pass, gh, spec, issue_number,
            reading=reading, semaphore_cm=semaphore_cm,
        )
    return functools.partial(
        _refetch_and_process, gh, spec, issue_number,
        semaphore_cm=semaphore_cm,
    )


def _closed_ordinary_pass(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    *,
    reading: _poll_models._PollReading,
    semaphore_cm: contextlib.AbstractContextManager | None = None,
) -> None:
    """Run a closed issue's ordinary pass, keeping the reading if it fails.

    The pass carries the poll's closed reading and is the only thing that
    will ever act on it: the enumeration latched it, and this task is what
    settles it. So a failure anywhere -- the refetch, the pinned read, the
    write that marks the cancellation -- has to leave the latch standing, or
    a human who reopens before the next poll takes the reading off the remote
    for good.

    Asked on the way OUT rather than only on a raise, because a pass can
    fail to spend the reading without failing at all: the pinned read the
    guard is built on answers a refusal of its own, so a tick that could not
    read the record refuses the issue and marks nothing. Settled the same way
    a refused submit settles one -- only where the record positively says
    there is nothing to end, which is exactly what a pass that DID mark it
    leaves behind.

    Held only where the enumeration kept a reading at all. It asked the same
    record already, and an issue it settled there is a closed one with no late
    cycle: asking again would spend a pinned read to reach the same answer,
    and re-latching in between would route an ordinary terminal through a
    cleanup pass on the tick after this one.

    The writer claim is taken outside that hold, because the hold's own exit
    reads the record and writes a receipt. A contender asks nothing, and the
    latch the enumeration took stays exactly as it was for the next poll.
    """
    with _issue_processing._writer_claim(gh, spec, issue_number) as held:
        if not held:
            return
        if not observations.close_observed(spec.slug, issue_number):
            _refetched_pass(
                gh, spec, issue_number, semaphore_cm=semaphore_cm, reading=reading,
            )
            return
        with _dispatch_closure._closed_reading(gh, spec, issue_number, reading.read_at):
            _refetched_pass(
                gh, spec, issue_number, semaphore_cm=semaphore_cm, reading=reading,
            )


def _swept_for_cleanup(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    *,
    semaphore_cm: contextlib.AbstractContextManager | None = None,
) -> None:
    """Take one latched close, and settle it only if the pass lands.

    Settled AFTER the pass rather than when the submit was accepted, because
    an accepted submit is not a cancellation persisted: the worker's own
    refetch is a GitHub read, and a read that fails leaves the cycle unmarked
    with nothing left saying a close was ever seen. A human reopening the
    issue before the next poll would then get ordinary workflow dispatch over
    a cycle a close already ended.

    So a pass that raises anywhere -- the refetch, the route, the sweep --
    hands the observation back, whether this worker was carrying one from an
    earlier tick or was the first to see the close. The next tick submits the
    cleanup again on the strength of it, and the sweep it reaches repeats
    whatever the failed pass did manage: every step of the ending is
    idempotent, and the mark itself is kept from its first stamp.

    The writer claim is taken outside the observation hold, since the hold
    reads the record on its way out. A contender never enters it: the latch it
    found is the latch it leaves, owed to the next poll, and nothing is asked
    of a record another poller is writing.
    """
    with _issue_processing._writer_claim(gh, spec, issue_number) as held:
        if not held:
            return
        with _cleanup_observation._cleanup_observation(gh, spec, issue_number):
            _refetched_pass(
                gh, spec, issue_number, semaphore_cm=semaphore_cm,
                reading=_poll_models._PollReading(cleanup_only=True, closed=True),
            )
