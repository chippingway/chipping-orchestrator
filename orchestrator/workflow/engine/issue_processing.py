# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Route one issue through cleanup or guarded stage dispatch and record evaluation timing.

Every dispatch seam enters an issue under its host-local writer claim, keyed
on the repository's canonical name and taken before the refetch and the close
recovery wrapped around this processing, and a contender skips the issue
whole, keeping only a closed reading in this process's latch. The publication
claim surrounds the handler, and evaluation analytics run on both success and
failure. Hard-skip controls preserve their observed close exception before
that processing begins.
"""
from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.scheduler import writer_claims as _writer_claims
from orchestrator.workflow.engine import (
    dispatch_guards as _dispatch_guards,
    observations as _observations,
    poll_models as _poll_models,
    poll_reading as _poll_reading,
    publication_holds as _publication_holds,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")


_TERMINAL_LABELS = (WorkflowLabel.DONE, WorkflowLabel.REJECTED)


@contextlib.contextmanager
def _writer_claim(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    *,
    keeps_close: bool = False,
    alongside: bool = False,
) -> Iterator[bool]:
    """Hold this issue's writer claim across one whole dispatch, or refuse it.

    The one claim every dispatch seam takes, and taken where the seam starts
    rather than around `_process_issue`: what the seam wraps around this
    processing -- the worker's refetch, the close a refetch establishes, the
    cleanup observation a sweep is held under, the closed reading an ordinary
    pass keeps -- reads the pinned record and writes receipts on the strength
    of it, so it is as much a writer as the handler is. A seam that took it
    later would let a contender decide on a record another poller is
    rewriting. The poll's own receipt for a close it observed is taken under
    it too, `alongside` whatever worker of this process holds the issue.

    Keyed on the client's `repo_slug`, the repository's canonical name, and
    never on `spec.slug`: an operator's spelling, or a renamed repository's
    old name, is a different file, and two pollers configured with two names
    for one repository would each hold "the" claim. Every caller hands in the
    client its tick or its worker was given, so the name is one GitHub
    already answered.

    A refusal is answered by doing nothing for the issue at all: no refetch,
    no guard, no recovery, no handler, no receipt, and no evaluation record.
    Whatever this process was holding for the issue -- a latched close, a
    publication hold the submit took -- is left exactly as it was, so the next
    polling pass finds the issue owed what it was owed and tries again. The
    scheduler's own guards are unchanged by it: an issue this process is
    already running is refused there first, and the claim is what answers for
    a process whose scheduler this one cannot read.

    `keeps_close` is a caller saying the poll read this issue CLOSED and would
    have held that reading across its pass. A refusal keeps it in the one
    place a contender may write, this process's latch: the pinned read that
    decides whether it is owed and the receipt that makes it durable are both
    the holder's record to touch, but a reading dropped here is gone once a
    human reopens the issue, and the stage handler its label names would then
    resume a cycle the close ended. A latch over an issue with no cycle costs
    the next tick one cleanup pass, under the claim, that settles it.
    """
    with _writer_claims.issue_writer(gh.repo_slug, issue_number, alongside=alongside) as held:
        if not held and keeps_close:
            _observations.observe_close(spec.slug, issue_number)
            log.info(
                "repo=%s issue=#%d observed closed, but its writer claim was "
                "refused; holding the observation and sweeping it on the "
                "next polling pass",
                spec.slug, issue_number,
            )
        yield held


def _route_issue_to_handler(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    *,
    reading: _poll_models._PollReading = _poll_models._POLLED_OPEN,
) -> None:
    """Dispatch one issue to its stage handler by workflow label.

    The module the table names is imported at call time and the handler read
    off it as an attribute, so the patch that intercepts a dispatch is the one
    against that module -- the stage's own handler owner.
    ``done`` / ``rejected`` are terminal no-ops; an unrecognized label is
    logged and left alone for a human. Timing and the ``stage_evaluation``
    analytics record stay in ``_process_issue``, which wraps this call in its
    try / except / finally.

    Two routes are taken ahead of the table. A closed issue on a cleanup-swept
    label goes to the sweep owner, because its label names a handler that would
    resume the workflow its close ended. And what the issue's own pinned
    comment records can stop the tick outright -- a restart an operator has
    authorized over a settled cancellation, a live adjudication the label was
    moved out from under, a snapshot this child was cut from and the remote no
    longer has, a cancelled cycle this owner has still to settle, or an
    unlabeled issue this orchestrator has already greeted once. The
    cleanup route comes first: that guard spends a pinned read to decide, and a
    closed owner is not dispatched on any of those answers.

    ``cleanup_only`` is that first route arriving as a decision rather than as
    a reading. It is set by the submit that a closed cleanup owner was
    classified into, and it BINDS: the worker refetches the issue after the
    classification, so a human who reopens one in that window would otherwise
    have the freshly-read label send it to the handler its cap-exempt submit
    was granted on the understanding it would never reach. What the sweep does
    with an issue that is open again is mark the cancellation the observed
    close already earned and stop there, leaving every external part of the
    ending to the guard that owns a reopened cancelled owner from the next
    tick.

    A control label the closed reading was let past is re-applied BEHIND the
    guard, because what that reading buys is the mark and nothing else: the
    park was waived so an observed close could be recorded before it was lost,
    and a record with no late cycle to mark has nothing to record -- so the
    stage handler below it would be the one reaction an operator's `paused`
    exists to prevent.
    """
    if reading.cleanup_only or _poll_reading._cleanup_sweep_only(issue, label):
        _stage_targets._call_handler(gh, spec, issue, _stage_targets._CLEANUP_SWEEP_TARGET)
        return
    if _dispatch_guards._pinned_state_refuses(
        gh, spec, issue, label, observed_closed=reading.closed,
    ):
        return
    if _dispatch_guards._parked_past_the_mark(spec, issue):
        return
    target = _stage_targets._STAGE_HANDLER_TARGETS.get(label)
    if target is not None:
        _stage_targets._call_handler(gh, spec, issue, target)
    elif label not in _TERMINAL_LABELS:
        log.warning(
            "repo=%s issue=#%s label=%r not implemented yet; leaving alone",
            spec.slug, issue.number, label,
        )


def _process_issue(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    *,
    reading: _poll_models._PollReading = _poll_models._POLLED_OPEN,
) -> None:
    # Postponed-task hold: applying `backlog` (or `paused`) parks the issue
    # outside the state machine entirely until the label is removed, so the
    # orchestrator never decomposes, spawns an agent, or otherwise reacts
    # while the operator is using the label as a "not yet" signal. Hard-skips
    # are NOT counted as a stage evaluation: no handler runs and there is
    # nothing to time.
    label = gh.workflow_label(issue)
    if _poll_reading._hard_skipped(spec, issue, label, reading):
        return
    log.info("repo=%s issue=#%s label=%r", spec.slug, issue.number, label)
    # Time the handler dispatch and append a single `stage_evaluation`
    # analytics record on exit. `evaluation_result` flips to "error" inside the
    # except clause so an unhandled exception still produces a timing
    # record before propagating -- the tick loop's per-issue try/except
    # already logs and isolates the failure, so re-raising here keeps
    # the existing dispatch / exception contract intact. The append
    # itself is internally hardened against OSError; an analytics
    # misconfiguration cannot stop the per-issue tick from advancing.
    start = time.monotonic()
    evaluation_result = "ok"
    try:
        # Advertised for the whole dispatch, so a close another thread
        # observes while this one is acting is not dropped again out from
        # under the barriers that read it. Those barriers stand immediately
        # before a push and the publications they guard carry no late cycle,
        # which is the one thing a poll drops a reading on. The drop is
        # postponed rather than refused: `observations` takes it again as the
        # window closes.
        with _publication_holds.publishing(spec.slug, issue.number):
            _route_issue_to_handler(gh, spec, issue, label, reading=reading)
    except Exception:
        evaluation_result = "error"
        raise
    finally:
        duration_s = round(time.monotonic() - start, 3)
        _recording_events.record_stage_evaluation(
            repo=getattr(gh, "_repo_slug", None) or "",
            issue=issue.number,
            stage=stage_name(label),
            duration_s=duration_s,
            result=evaluation_result,
        )
