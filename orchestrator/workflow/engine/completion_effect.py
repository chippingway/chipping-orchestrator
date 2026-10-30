# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a pending captured completion is owed, decided, and then read again behind the last fetch before its effect.

A retirement and a handoff are effects, and the readings an admission takes
(`completion_admission`) are requests a human can land a move between: a
control applied, a relabel, a close or a reopening, an edit of the body or
the thread, a commit or a reset in the checkout, a push to the pull request.
So the issue is fetched once more behind them (`completion_admission.live_issue`)
-- a fetch that fails, a control, or a label moved holds the capture -- and
every reading the effect stands on that a pinned comment cannot carry is
taken again behind that fetch, the effect standing only where each answers
as it did.

For a handoff that is all of them: the issue open and asking for the
requirements the run was handed, the checkout on the commit reported on, and
the pull request at the head the admission read. For a retirement it is the
one reading that proved it -- an issue closed or requirements moved, a
checkout moved, a pull request ended or moved -- since a human putting that
back while the effect waited leaves a capture that may be the issue's again.
Every other proof stands: the records it was read off bind the retirement's
own commit (`completion_evidence.DecidedOn`). A reading that answers
otherwise holds the capture with nothing written or handed on, for the next
dispatch to decide afresh; one nobody can take again holds it as unread.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_admission as _admission,
    completion_recovery_models as _models,
    completion_sources as _sources,
    completion_state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

_Standing = _models.Standing
_Reason = _models.Reason

_MOVED_BEHIND = _models.Decision(_Standing.UNCERTAIN, _Reason.MOVED_BEHIND)


def decided(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: WorkflowLabel | None,
    state: PinnedState,
) -> _models.Decision:
    """What the pending capture `state` carries is owed, its effect's readings taken again behind the last fetch.

    An answer that makes no effect -- a hold, or a wait -- is the
    admission's own, with nothing read again.
    """
    decision = _admission.decided(gh, spec, issue, label, state)
    if decision.standing is not _Standing.INVALID and decision.admitted is None:
        return decision
    fresh = _admission.live_issue(gh, issue, label)
    if isinstance(fresh, _models.Decision):
        return fresh
    return _repeated(_Reading(gh, spec, fresh, label, state), decision)


@dataclass(frozen=True)
class _Reading:
    """The world an effect is read again in: the issue as its last fetch read it, beside the dispatch's record."""

    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    label: WorkflowLabel | None
    state: PinnedState

    def issue_answer(self) -> _models.Decision | None:
        """Why the issue reads as work ended or requirements moved, or None."""
        return _admission.issue_refusal(self.gh, self.issue, self.label, self.state)

    def checkout_answer(self) -> _models.Decision | None:
        """Why the branch or the checkout is no longer the one the capture reported from, or None."""
        capture = _state.read(self.state)
        return _sources.checkout_refusal(self.spec, self.issue.number, self.state, capture)

    def pull_request_answer(self) -> _models.Decision | str | None:
        """The head the recorded pull request stands on, None where none is recorded, or why it refuses."""
        return _sources.pull_request_head(self.gh, self.state, _state.read(self.state))


# The proofs of staleness read off something a pinned comment cannot carry, and the reading each is taken again with.
_REREADS: MappingProxyType[_Reason, Callable[[_Reading], object]] = MappingProxyType({
    _Reason.ENDED: _Reading.issue_answer,
    _Reason.REQUIREMENTS_MOVED: _Reading.issue_answer,
    _Reason.CHECKOUT_MOVED: _Reading.checkout_answer,
    _Reason.PULL_REQUEST_ENDED: _Reading.pull_request_answer,
    _Reason.PULL_REQUEST_MOVED: _Reading.pull_request_answer,
})


def _repeated(reading: _Reading, decision: _models.Decision) -> _models.Decision:
    """`decision`, where every reading its effect stands on answers the same taken again in `reading`; else a hold."""
    if decision.admitted is not None:
        return _admitted_again(reading, decision.admitted)
    reread = _REREADS.get(decision.reason)
    if reread is None:
        return decision
    again = reread(reading)
    return decision if again == decision else _held(again)


def _admitted_again(reading: _Reading, admitted: _models.AdmittedCompletion) -> _models.Decision:
    """`admitted` handed on with the issue `reading` fetched, where it, its checkout, and its PR still admit it."""
    refused = reading.issue_answer() or reading.checkout_answer()
    head = None if refused else reading.pull_request_answer()
    if refused is None and head == admitted.pull_request_head:
        return _models.Decision(_Standing.APPLICABLE, admitted=admitted.refetched(reading.issue))
    return _held(refused or head)


def _held(again: object) -> _models.Decision:
    """The hold a reading taken again makes where it answered otherwise: its own where nobody could take it."""
    unread = isinstance(again, _models.Decision) and again.standing is _Standing.UNCERTAIN
    return again if unread else _MOVED_BEHIND
