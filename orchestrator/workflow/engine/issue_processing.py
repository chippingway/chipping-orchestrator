# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Route one issue through cleanup or guarded stage dispatch and record evaluation timing.

The publication claim surrounds the handler, and evaluation analytics run
on both success and failure. Hard-skip controls preserve their observed
close exception before that processing begins.
"""
from __future__ import annotations

import logging
import time

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.workflow.engine import (
    dispatch_guards as _dispatch_guards,
    poll_models as _poll_models,
    poll_reading as _poll_reading,
    publication_holds as _publication_holds,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")


_TERMINAL_LABELS = (WorkflowLabel.DONE, WorkflowLabel.REJECTED)


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
