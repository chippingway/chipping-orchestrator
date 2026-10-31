# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Capture one developer completion on its issue, read it back, and retire it, each in one guarded commit.

`captured` builds the capture of one returned run: eligible only through the
road contract and the outcome owner's completed-run reader (`completion_routes`),
with what the road froze before the launch and what actually ran beside it. It
writes nothing.

`capture` lands it as the issue's PENDING `developer_completion`, through the
guarded pinned-state commit (`pinned_commit.commit`) owning that field and
nothing else, decided on the field itself, the workflow cycle, and the
delivered report, over the comment the caller holds read afresh and admitted
(`completion_commits`). So
taking a capture moves no session pin, requirements baseline, watermark, park,
round, approval, publication or evidence record, whatever the caller staged;
those are its road's to settle once the report is handed on. One capture is
held at a time and never replaced while unresolved: another invocation's
pending capture refuses it, and so does a resolved capture of this invocation
or of a later one, since a charge's ordinal orders an issue's invocations and
is never reused -- a replay of an older return is never fresh work. A damaged
capture refuses it too, and so does a handed-off capture whose report has not
settled -- the transaction its delivery became still stands, or a claim of
either record nobody can read: until then that capture is the one record of
the commit the report is about, and of the report having come from a capture
at all (`completion_state.source_owed`). A handoff owed only to its delivery,
standing unbound beside no transaction, gives way to a later capture that
carries it as `supersedes` (`completion_handoff.carried`): that capture's own
transfer supersedes the delivery, and meanwhile the delivery is held to the
commit the carried handoff names. A capture of this invocation
already standing is the read-back of an earlier attempt -- a lost response, a
retry -- and nothing is sent; past PENDING, the report's owner is laid back
onto the caller beside it (`completion_handoff.confirmed`), so a caller that
read the capture before its transfer never writes the delivery away.

The report is measured, never cut. Over the comment read afresh, so a refusal
holds back a caller whose reading is stale, the capture's own reading is asked
first: a report quoting a receipt marker or past its ceiling is refused with
that reading's reason; then the comment it would leave, with every terminator
escaped and never as the writer falls back to rendering it unescaped, against
what one comment holds; then, measured the same way, the room the transfer
into the delivery will need over that very comment, with its binding and
settlement (`completion_handoff.admits_the_capture`). Either room refusal is
the comment's (`report_record_room.CommentOverflow`). A refused capture wrote
nothing, so the run's usage accounting -- its own checkpoint, already asked as
the run returned (`usage_checkpoint`) -- stands or falls on its own, and a
comment with room for neither is refused twice rather than either being
claimed.

`read_back` is the fresh, admitted reading alone: the stage the record carries
for one invocation, or None where it carries no capture of it -- for a
handed-off one, with the delivery that owns its report laid onto the caller
beside it (`completion_handoff.TRANSFERRED`). `retire` ends a capture by a
guarded decision: a pending one only as INVALIDATED, since its report is held
nowhere else -- still carrying a handoff it carries where that handoff's
delivery still stands, so the invocation a replay names is refused while the
delivery stays held to its source -- and a handed-off one either way once its
delivery is bound or gone, its report the delivery's already. A SETTLED
retirement of a capture never handed off -- a transfer that was sent and
never confirmed, read back as not landed -- is
refused, so the only copy of a report is never dropped on the strength of a
handoff nobody confirmed. Retirement keeps the invocation, which is what
refuses a later capture of it.

The implementing stage's shared developer coordinator captures through
`captured` and `capture` as each attempt on a report-producing road returns
(`stages/implementing/completion_roads`) -- the implementing roads', a
reviewer's change request's, a pull request feedback round's, and every
requirements-drift resume's, whose roads its validating, fixing, in_review, and
conflict callers freeze -- and each road's disposition
withdraws a capture through `retire`
ahead of a park that hands its report to nobody. The dispatcher's recovery (`completion_recovery`) reads a pending
capture through `read_back` alone and ends one its readings proved stale
through `retire`.
"""
from __future__ import annotations

from dataclasses import replace
from functools import partial

from github.Issue import Issue

from orchestrator.agents.models import AgentInvocation, AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_commits as _commits,
    completion_handoff as _handoff,
    completion_records as _records,
    completion_routes as _routes,
    completion_spelling as _spelling,
    completion_state as _state,
    pinned_commit as _pinned_commit,
    pinned_commit_models as _commit_models,
)
from orchestrator.workflow.engine.completion_evidence import DecidedOn
from orchestrator.workflow.engine.report_outcome_models import _ReadyReport, _ReportRefusal, _VerifiedReport
from orchestrator.workflow.engine.report_record_values import RecordRefusal, report_text_refusal
from orchestrator.workflow.engine.report_records import DELIVERED_REPORT, PENDING_REPORT

# What every write over a capture owns, and what it is decided on: the capture,
# the cycle, and the delivery and transaction a handed-off capture may still be
# owed to.
_OWNED = (_records.DEVELOPER_COMPLETION,)

_DECIDED_ON = (*_commits.DECIDED_ON, DELIVERED_REPORT, PENDING_REPORT)

# The stage a capture holding its report is at, and the reason no pending one is retired for.
_PENDING = _records.CaptureStage.PENDING
_SETTLED = _records.RetirementReason.SETTLED


def captured(
    agent_result: AgentResult, handoff: _records.CompletionHandoff, run: _records.CompletionRun,
) -> _records.CompletionCapture | _routes.Ineligible | _ReportRefusal:
    """The capture `agent_result` earns on the road `handoff` froze, having run as `run`; or why it earns none.

    The session is the one the result returned, and the accounting what the
    tracked spawn's checkpoint left on it: unresolved where it marked the
    result `unaccounted`, nothing owed where no usage was parsed, and settled
    otherwise.
    """
    handed = bool(handoff.frozen)
    outcome = _routes.eligible_outcome(agent_result, handoff.route, handoff.origin, handed=handed)
    if not isinstance(outcome, (_ReadyReport, _VerifiedReport)):
        return outcome
    accounting = _records.CaptureAccounting.SETTLED
    if agent_result.unaccounted:
        accounting = _records.CaptureAccounting.UNRESOLVED
    elif agent_result.usage is None:
        accounting = _records.CaptureAccounting.NOTHING_OWED
    return _records.CompletionCapture(
        invocation=agent_result.invocation,
        handoff=handoff,
        run=run,
        outcome=outcome,
        accounting=accounting,
        session_id=agent_result.session_id,
    )


def capture(
    gh: GitHubClient, issue: Issue, state: PinnedState, completion: _records.CompletionCapture,
) -> _commits.CheckpointOutcome:
    """Land `completion` as `issue`'s pending capture over the comment `state` names, or say why not.

    LANDED is this call's write and STANDING an earlier one of the same
    invocation read back; either way the capture is laid onto `state` as the
    comment's. An edit sent and never confirmed withholds `state`, and only a
    read-back says whether it landed.
    """
    commit = _commits.CompletionCommit(gh, issue, state, completion.invocation)
    fresh = commit.fresh()
    if isinstance(fresh, _commits.CheckpointOutcome):
        return fresh
    standing = _state.read(fresh)
    if standing is not None and standing.invocation == completion.invocation:
        return _handoff.confirmed(commit, fresh, standing.stage)
    refused = _unrecordable(completion) or _refusal(fresh, standing, completion.invocation)
    if refused is not None:
        return commit.refused(refused)
    carrying = replace(completion, supersedes=_handoff.carried(fresh, standing))
    return _lands(commit, fresh, carrying, partial(
        _handoff.admits_the_capture, captured=carrying, issue_number=issue.number,
    ))


def read_back(
    gh: GitHubClient, issue: Issue, state: PinnedState, invocation: AgentInvocation,
) -> _commits.CheckpointOutcome:
    """The stage `issue`'s record carries for `invocation`'s capture, read afresh; nothing is sent.

    STANDING with the stage, or with None where the admitted record carries
    no capture of this invocation -- the supported absence, or another
    invocation's capture. What the field holds is laid onto `state` as the
    comment's. A comment that will not read, is not admitted, or names
    another record, and a capture or cycle nobody can read, are refused: none
    of them says whether a write landed.
    """
    commit = _commits.CompletionCommit(gh, issue, state, invocation)
    fresh = commit.fresh()
    if isinstance(fresh, _commits.CheckpointOutcome):
        return fresh
    standing = _state.read(fresh)
    if standing is None or standing.invocation != invocation:
        return commit.standing(fresh, None)
    return _handoff.confirmed(commit, fresh, standing.stage)


def retire(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    invocation: AgentInvocation,
    reason: _records.RetirementReason,
) -> _commits.CheckpointOutcome:
    """Retire `invocation`'s capture for `reason`, keeping which invocation it was.

    A pending capture is retired only as INVALIDATED; a handed-off one
    either way, once the report it was handed off as has settled or been
    superseded. One already retired is STANDING.

    An invalidation is a decision taken over the reading `state` is, so it
    is decided on all of that reading: refused (EVIDENCE_MOVED) where the
    comment read afresh no longer reads as it -- a human's repair of the very
    record that proved the capture stale among them -- and landed only where
    the candidate its commit sends still spells that whole reading beside the
    capture (`completion_evidence.DecidedOn`), a field it lacked and somebody
    restored or added since included, so the caller decides again on a fresh
    reading rather than discarding a capture on evidence that is gone.
    """
    commit = _commits.CompletionCommit(gh, issue, state, invocation)
    fresh = commit.fresh()
    if isinstance(fresh, _commits.CheckpointOutcome):
        return fresh
    standing = _state.read(fresh)
    if standing is None or standing.invocation != invocation:
        return commit.refused(_commits.CheckpointRefusal.ABSENT)
    if standing.stage is _records.CaptureStage.RETIRED:
        return _handoff.confirmed(commit, fresh, standing.stage)
    refused = _refusal(fresh, standing, invocation, reason, state)
    if refused is not None:
        return commit.refused(refused)
    invalidated = reason is _records.RetirementReason.INVALIDATED
    return _lands(
        commit,
        fresh,
        _records.ResolvedCapture(
            invocation=invocation,
            stage=_records.CaptureStage.RETIRED,
            reason=reason,
            supersedes=_handoff.carried(fresh, standing),
        ),
        DecidedOn.over(fresh) if invalidated else None,
        decided_on=tuple(fresh.state_data) if invalidated else (),
    )


def _lands(
    commit: _commits.CompletionCommit,
    fresh: PinnedState,
    record: _records.CompletionCapture | _records.ResolvedCapture,
    admits: _commit_models.Admits | None = None,
    decided_on: tuple[str, ...] = (),
) -> _commits.CheckpointOutcome:
    """Commit `record` as the capture over `fresh`, owning that field alone, decided on `_DECIDED_ON` and more."""
    prerequisites = (*_DECIDED_ON, *decided_on)
    guard = _commit_models.PinnedCommit.capture(fresh, prerequisites=prerequisites, owned=_OWNED, admits=admits)
    staged = {**fresh.state_data, _records.DEVELOPER_COMPLETION: _spelling.spelled(record)}
    landed = _pinned_commit.commit(commit.gh, commit.issue, guard, staged)
    return commit.landed(landed, record.stage, fresh)


def _refusal(
    fresh: PinnedState,
    standing: _records.CompletionCapture | _records.ResolvedCapture | None,
    invocation: AgentInvocation,
    reason: _records.RetirementReason | None = None,
    caller: PinnedState | None = None,
) -> _commits.CheckpointRefusal | None:
    """Why the capture `standing` is may not give way, over `fresh`; None where it may.

    A capture of `invocation` gives way to it (`reason` None) only where it
    is none, or an earlier charge's resolved one: a pending capture is
    unresolved, and a resolved one of the same or a later charge is newer
    than this return. A retirement for `reason` takes a pending capture only
    as INVALIDATED. Neither replaces nor retires a handed-off capture whose
    report has not settled (`completion_state.source_owed`): it is the one
    record of the commit that report is about. An invalidation is refused
    where `fresh` no longer reads as the `caller`'s reading it was decided on.
    """
    if standing is None:
        return None
    invalidated = reason is _records.RetirementReason.INVALIDATED and caller is not None
    owed = (
        _state.source_owed(fresh, standing.standing_handoff)
        and _handoff.carried(fresh, standing) is None
        if reason is None
        else _state.source_owed(fresh, standing)
    )
    refusals = (
        (invalidated and _commits._stale(fresh, caller), _commits.CheckpointRefusal.EVIDENCE_MOVED),
        (reason is None and standing.stage is _PENDING, _commits.CheckpointRefusal.UNRESOLVED),
        (reason is None and standing.invocation.ordinal >= invocation.ordinal, _commits.CheckpointRefusal.SUPERSEDED),
        (reason is _SETTLED and standing.stage is _PENDING, _commits.CheckpointRefusal.NOT_HANDED_OFF),
        (owed, _commits.CheckpointRefusal.UNBOUND),
    )
    return next((refusal for refused, refusal in refusals if refused), None)


def _unrecordable(completion: _records.CompletionCapture) -> RecordRefusal | None:
    """Why `completion` could not be recorded on any comment, or None.

    A READY report is held to the report records' own reading, so a report
    quoting a receipt marker or past its ceiling is refused with that reason;
    anything else that would not read back as this very capture is an
    invalid record.
    """
    if isinstance(completion.outcome, _ReadyReport):
        refused = report_text_refusal(completion.outcome.report)
        if refused is not None:
            return refused
    if _spelling.read_record(_spelling.spelled(completion)) != completion:
        return RecordRefusal.INVALID_RECORD
    return None
