# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a pending captured completion still answers what the issue is, read afresh over everything it stands on.

A capture is the record of one run's return, taken before that return could
be discarded, and what it may still become depends on everything that has
happened to the issue since. So nothing the dispatch already read is taken
on trust, and each reading is asked in turn, the cheapest first, until one
answers (`completion_recovery_models.Decision`).

The record comes first: the capture read back afresh through its own
checkpoint (`completion_checkpoint.read_back`), which admits the comment
again and binds it to the invocation's repository, issue, comment, and
cycle. That read-back -- of the confirmed capture, or of a write left
uncertain -- is the only thing recovery reads the capture from; no log,
analytics record, native session, trajectory, or host record is asked. A
capture of another record or of a cycle the record has left, and a capture or
cycle nobody can read, are damage; a comment that will not read, or no longer
reads as the one the dispatch read, holds.

The issue is fetched again next, for the labels and controls as they stand:
a control applied, or a label moved, during the dispatch holds the tick for
the next one to read. Then the road. Work that has ended -- the issue
closed, or labelled `done` or `rejected` -- and an issue moved onto any
other road than the one the capture reported on are past its output. A
dependency hold, the `ready` decision that answers it, and an issue a human
took the workflow label off are waited through instead: the capture is
neither handed on nor discarded there, and the stage runs as it would
without one -- beside an auto-rebase anchor too, since none of those labels
is one the base refresh drives, and the anchor's hold answers the anchor
there by a clear or a park that leaves the checkout where it stands. On the
capture's own road an anchor standing beside it is asked next: the branch is
mid-rewrite, and the anchor's recovery may reset or replace the commit the
report is about, so the capture is retired before that recovery runs
(`dispatch_guards._anchor_holds_the_tick` asks this ahead of the anchor's
hold). Then the records the road stands on: the pull request a pull-request
stage's report is owed to, the debt a rewritten-head refresh answers, the
adjudication a late revision answers, and the records its handoff was frozen
over -- one another road has moved since is past the run's output, where the
move still reads (`completion_prerequisites`).

The requirements are read off the issue as a developer prompt reads them
(`prompt_context._delivered_thread`), so the fingerprint is comparable with
the one the run was handed; an edit since -- the body, the title, or human
guidance on the thread -- leaves the report about requirements the issue no
longer has. Then the branch and the checkout it reported on
(`completion_sources`); then, for a run whose usage was captured unaccounted,
the receipt of it read back beside readable counters, without which the
capture is held; and last the pull request.

What a decision's effect stands on is read again behind the issue's last
fetch before it (`completion_effect`), so `live_issue` and the issue's own
readings (`issue_refusal`) are that owner's to ask a second time.

Nothing here writes, charges a run, clears a park, or grants an invocation.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github import issues as _issues, labels as _labels
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_commits as _commits,
    completion_prerequisites as _prerequisites,
    completion_records as _records,
    completion_recovery_models as _models,
    completion_sources as _sources,
    completion_state as _state,
    prompt_context as _prompt_context,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_Standing = _models.Standing
_Reason = _models.Reason

# The labels whose whole meaning is that this issue's work is over.
_TERMINAL_LABELS = frozenset((WorkflowLabel.DONE, WorkflowLabel.REJECTED))

# The stages a capture waits through: a dependency hold, and the decision
# that answers one and hands the issue back to its road.
_WAITING_LABELS = frozenset((WorkflowLabel.BLOCKED, WorkflowLabel.READY))

_DAMAGED = _models.Decision(_Standing.DAMAGED, _Reason.DAMAGED)

_RECORD_UNREAD = _models.Decision(_Standing.UNCERTAIN, _Reason.RECORD_UNREAD)

_ISSUE_UNREAD = _models.Decision(_Standing.UNCERTAIN, _Reason.ISSUE_UNREAD)

_ENDED = _models.Decision(_Standing.INVALID, _Reason.ENDED)

# What a read-back refused for says about the capture itself, where it says
# anything: every other refusal is a comment that would not read as current.
_REFUSED_AS = MappingProxyType({
    _commits.CheckpointRefusal.DAMAGED: _DAMAGED,
    _commits.CheckpointRefusal.FOREIGN: _models.Decision(_Standing.DAMAGED, _Reason.NOT_THIS_RECORD),
    _commits.CheckpointRefusal.OTHER_CYCLE: _models.Decision(_Standing.DAMAGED, _Reason.NOT_THIS_RECORD),
})


def decided(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: WorkflowLabel | None,
    state: PinnedState,
) -> _models.Decision:
    """What the pending capture `state` carries is owed, decided under the label the dispatch resolved.

    `state` is the dispatcher's admitted reading; the capture's read-back lays
    the comment's own capture back onto it, and a comment that moved since
    withholds it. Only an APPLICABLE answer carries the handoff.
    """
    capture = _state.read(state)
    refused = _record_refusal(gh, issue, state, capture)
    if refused is not None:
        return refused
    fresh = live_issue(gh, issue, label)
    if isinstance(fresh, _models.Decision):
        return fresh
    refused = (
        _road_refusal(fresh, label, state, capture)
        or _prerequisites.anchor_refusal(state)
        or _prerequisites.road_refusal(state, capture)
    )
    refused = refused or (
        _requirements_refusal(gh, fresh, state, capture)
        or _sources.checkout_refusal(spec, issue.number, state, capture)
        or _prerequisites.accounting_refusal(state, capture)
    )
    if refused is not None:
        return refused
    head = _sources.pull_request_head(gh, state, capture)
    if isinstance(head, _models.Decision):
        return head
    return _models.Decision(_Standing.APPLICABLE, admitted=_models.AdmittedCompletion(
        gh=gh, spec=spec, issue=fresh, label=label, state=state, capture=capture, pull_request_head=head,
    ))


def _record_refusal(
    gh: GitHubClient, issue: Issue, state: PinnedState, capture: object,
) -> _models.Decision | None:
    """Why the capture, read back afresh and bound to its invocation, is not a pending one to decide on; or None."""
    if not isinstance(capture, _records.CompletionCapture):
        return _DAMAGED
    answer = _checkpoint.read_back(gh, issue, state, capture.invocation)
    if answer.status is _commits.CheckpointStatus.REFUSED:
        return _REFUSED_AS.get(answer.refusal, _RECORD_UNREAD)
    if answer.stage is not _records.CaptureStage.PENDING or state.withheld:
        return _RECORD_UNREAD
    return None


def live_issue(gh: GitHubClient, issue: Issue, label: WorkflowLabel | None) -> Issue | _models.Decision:
    """The issue fetched afresh, where its controls and label still read as the dispatch resolved them.

    Asked once ahead of the road's readings, and again right before the
    effect a decision makes (`completion_effect`), since a control or a
    relabel can land while those readings are taken.
    """
    try:
        fresh = gh.get_issue(issue.number)
    except Exception:  # noqa: BLE001 - an issue nobody could fetch holds the capture, never invalidates it
        log.warning("issue=#%d could not be fetched again to admit its captured completion", issue.number)
        return _ISSUE_UNREAD
    if _labels.hard_skip_control_label(fresh) is not None or gh.workflow_label(fresh) != label:
        return _ISSUE_UNREAD
    return fresh


def issue_refusal(
    gh: GitHubClient, fresh: Issue, label: WorkflowLabel | None, state: PinnedState,
) -> _models.Decision | None:
    """Why `fresh` reads as work ended or requirements moved under the capture `state` carries, or None."""
    if _issues.issue_is_closed(fresh) or label in _TERMINAL_LABELS:
        return _ENDED
    return _requirements_refusal(gh, fresh, state, _state.read(state))


def _road_refusal(
    fresh: Issue, label: WorkflowLabel | None, state: PinnedState, capture: _records.CompletionCapture,
) -> _models.Decision | None:
    """Why the road `capture` reported on is not the one the issue is on, or None."""
    if _issues.issue_is_closed(fresh) or label in _TERMINAL_LABELS:
        return _ENDED
    if label is None or label in _WAITING_LABELS:
        return _models.Decision(_Standing.WAITING, _Reason.WAITING)
    if label != capture.handoff.origin:
        return _models.Decision(_Standing.INVALID, _Reason.RELABELLED)
    return None


def _requirements_refusal(
    gh: GitHubClient, fresh: Issue, state: PinnedState, capture: _records.CompletionCapture,
) -> _models.Decision | None:
    """Why the requirements read afresh refuse `capture`, or None where they are the ones its run was handed."""
    try:
        revision = _prompt_context._delivered_thread(gh, fresh, state).requirements_revision or ""
    except Exception:  # noqa: BLE001 - a thread nobody could read holds the capture, never invalidates it
        log.warning("issue=#%d could not read its requirements to admit its captured completion", fresh.number)
        return _models.Decision(_Standing.UNCERTAIN, _Reason.REQUIREMENTS_UNREAD)
    if revision != capture.handoff.requirements_revision:
        return _models.Decision(_Standing.INVALID, _Reason.REQUIREMENTS_MOVED)
    return None
