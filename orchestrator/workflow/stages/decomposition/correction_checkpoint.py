# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Arm, read back, exhaust, and retire one decomposer manifest correction, each in one guarded commit.

A dormant facility: only the prepared correction helpers call these
(`correction_road`), and no production road calls those yet, so production
decomposition keeps its own outcomes, and a manifest that fails validation
still parks awaiting a human (`outcomes._park_unparsed_manifest`).

`arm` lands the one allowance a rejected decomposer answer earns as the issue's
pending `decomposer_correction`, through the guarded pinned-state commit
(`pinned_commit.commit`) owning that field and nothing else
(`correction_commits`), decided on the field, the workflow cycle, the
requirements baseline, the two decomposer pins, the run ledger, and the usage
receipts. The source has to be what the record says it is: charged on this
comment in its cycle, the last charge the run ledger counts with no start the
ledgers record at or past it, handed the requirements the baseline records, and saved under the command and session the
pins name -- so an allowance is never armed for a conversation nobody saved,
or for a run something has run behind. One attempt is held at a time: another
source's pending attempt refuses it, and so does a resolved attempt covering
this source's charge -- the correction's own invocation, and every charge made
before the attempt resolved -- so asking again, a restart, or a correction's own
rejected answer never re-arms a spent attempt. A damaged or displaced claim
refuses it and is never replaced, and so does a comment with no room for the
attempt's widest resolution (`correction_room.resolves`). Room for its launch
is the admission's to measure (`correction_standing`), so an attempt armed on a
comment too full for that reads CROWDED and grants nothing. The same source's
pending attempt already standing
is the read-back of an earlier attempt -- a lost response, a retry -- and
nothing is sent.

`read_back` is the fresh, admitted reading alone, bound to no source, so a
process that restarted holding nothing reconstructs what stands from the
comment, and the field is laid onto its state as the comment's.

`exhaust` spends a pending attempt -- its correction answered, a start nobody
can account for was given up on, or no launch is to be made -- naming the
correction's own invocation where one returned, and covering every charge up to
the run count it reads (`correction_records.CorrectionAttempt.floor`). It
grants nothing, so it is taken whatever the reading says of the launch's start.
`retire` ends a pending attempt only on evidence: a reading that proves its
context moved (`correction_standing.moved`), held to that very evidence, so a
baseline or pin nobody can read, or one put back meanwhile, retires nothing.
Each resolution's floor is the run count read strictly, and only where it
covers every charge the ledgers still record
(`correction_records.CorrectionAttempt.floor_on`): a charge count nobody can
read, or a usage meter beside it nobody can, bounds nothing -- the meter alone
is only a floor of what was spent -- and neither does a count below the charge
an owed start or a usage receipt records, or beside either record unread. A
floor under any of those would let a correction charged above it, its own
rejected answer, arm again once the count read as it should, so each is
refused as UNCOUNTED, the attempt left pending and granting nothing until a
count reads that covers them.
Either asked again over an attempt already where it asks is STANDING; over one
resolved the other way, refused. Every write sends only a record that reads
back as itself, so a member past what a record holds -- a correction charged
beyond the widest recorded number -- refuses the write as UNRECORDABLE rather
than leaving a damaged claim where the attempt stood; a run count past it
resolves under the widest floor a record holds, which covers every source one
could name.

None of them charges, starts, or invokes anything: the one launch an eligible
attempt buys is the run circuit's, owed once (`correction_standing.owed_launch`).
A write sent and never confirmed withholds the caller's state, and only a
read-back says what landed.
"""
from __future__ import annotations

from functools import partial

from github.Issue import Issue

from orchestrator.agents.models import AgentInvocation
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import run_ledger_values as _run_ledger_values
from orchestrator.workflow.stages.decomposition import (
    correction_commits as _commits,
    correction_records as _records,
    correction_room as _room,
    correction_standing as _standing,
)

_REFUSAL = _commits.CorrectionRefusal
_STAGE = _records.CorrectionStage

# What an arming and a retirement are decided on beside the attempt and the
# cycle: the context the source was armed under, and the run ledger it was the
# last charge of.
_EVIDENCED = (*_standing.CONTEXT, *_standing.LEDGER)


def arm(
    gh: GitHubClient, issue: Issue, state: PinnedState, source: _records.CorrectionSource,
) -> _commits.CorrectionOutcome:
    """Land the one correction allowance `source`'s rejected answer earns, over the comment `state` names.

    LANDED is this call's write and STANDING an earlier one of the same source
    read back; either way the attempt is laid onto `state` as the comment's,
    and what that comment says of it -- ELIGIBLE where its launch may be made
    now -- rides the answer.
    """
    commit = _commits.CorrectionCommit(gh, issue, state, source.invocation)
    fresh = commit.fresh()
    if isinstance(fresh, _commits.CorrectionOutcome):
        return fresh
    attempt = _records.CorrectionAttempt(source)
    if _records.read(fresh) == attempt:
        return commit.standing(fresh)
    refused = _arming_refusal(fresh, attempt, issue.number)
    if refused is not None:
        return commit.refused(refused, fresh)
    return commit.lands(fresh, attempt, _EVIDENCED, partial(_has_room, attempt))


def read_back(gh: GitHubClient, issue: Issue, state: PinnedState) -> _commits.CorrectionOutcome:
    """What `issue`'s record says of its correction attempt, read afresh and laid onto `state`; nothing is sent.

    STANDING with the reading's standing (`correction_standing.read`), ABSENT
    included. A comment that will not read, is not admitted, or is not the one
    `state` names is refused: none of them says whether a write landed.
    """
    commit = _commits.CorrectionCommit(gh, issue, state)
    fresh = commit.fresh()
    if isinstance(fresh, _commits.CorrectionOutcome):
        return fresh
    return commit.standing(fresh)


def exhaust(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    attempt: _records.CorrectionAttempt,
    correction: AgentInvocation | None = None,
) -> _commits.CorrectionOutcome:
    """Spend `attempt`, naming `correction` where its launch returned one, over the comment `state` names.

    `correction` has to have run on the source's record and cycle under a
    later charge. One already exhausted is STANDING, whatever it names.
    """
    commit = _commits.CorrectionCommit(gh, issue, state, attempt.source.invocation)
    pending = _pending_attempt(commit, attempt, _STAGE.EXHAUSTED)
    if isinstance(pending, _commits.CorrectionOutcome):
        return pending
    fresh, standing = pending
    if correction is not None and not attempt.source.charged_after(correction):
        return commit.refused(_REFUSAL.UNRELATED, fresh)
    floor = standing.floor_on(fresh)
    if floor is None:
        return commit.refused(_REFUSAL.UNCOUNTED, fresh)
    return commit.lands(fresh, standing.resolved(_STAGE.EXHAUSTED, floor, correction), _standing.LEDGER)


def retire(
    gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt,
) -> _commits.CorrectionOutcome:
    """Retire `attempt` over the comment `state` names, where that comment proves its context moved.

    Decided on the evidence as well as the attempt, so a baseline or a pin
    put back since refuses it. One already retired is STANDING.
    """
    commit = _commits.CorrectionCommit(gh, issue, state, attempt.source.invocation)
    pending = _pending_attempt(commit, attempt, _STAGE.RETIRED)
    if isinstance(pending, _commits.CorrectionOutcome):
        return pending
    fresh, standing = pending
    if _standing.moved(fresh, attempt.source) is not _standing.Standing.STALE:
        return commit.refused(_REFUSAL.NO_EVIDENCE, fresh)
    floor = standing.floor_on(fresh)
    if floor is None:
        return commit.refused(_REFUSAL.UNCOUNTED, fresh)
    return commit.lands(fresh, standing.resolved(_STAGE.RETIRED, floor), _EVIDENCED)


def _pending_attempt(
    commit: _commits.CorrectionCommit, attempt: _records.CorrectionAttempt, asked: _records.CorrectionStage,
) -> tuple[PinnedState, _records.CorrectionAttempt] | _commits.CorrectionOutcome:
    """The fresh reading and `attempt` pending on it, or the answer that ends a resolution first.

    No attempt of its source is ABSENT; one already resolved as `asked` is
    STANDING, nothing sent; one resolved the other way is RESOLVED.
    """
    fresh = commit.fresh()
    if isinstance(fresh, _commits.CorrectionOutcome):
        return fresh
    standing = _records.read(fresh)
    if standing is None or standing.source != attempt.source:
        return commit.refused(_REFUSAL.ABSENT, fresh)
    if standing.stage is asked:
        return commit.standing(fresh)
    if standing.stage is not _STAGE.PENDING:
        return commit.refused(_REFUSAL.RESOLVED, fresh)
    return fresh, standing


def _arming_refusal(fresh: PinnedState, attempt: _records.CorrectionAttempt, issue_number: int) -> _REFUSAL | None:
    """Why `attempt` may not be armed over `fresh`, or None.

    Whatever the record carries has to be bound to it and give way -- resolved, and covering no charge at or
    past this source's -- and the source has to be the last charge the ledger
    counts, with no owed start at or past it, its requirements and saved
    conversation the ones the record names.
    """
    standing = _records.read(fresh)
    owed_at = attempt.owed_at
    refusals = (
        (standing is not None and not standing.source.binds(fresh, issue_number), _REFUSAL.DISPLACED),
        (standing is not None and standing.stage is _STAGE.PENDING, _REFUSAL.UNRESOLVED),
        (standing is not None and standing.covers(owed_at), _REFUSAL.SUPERSEDED),
        (_run_ledger_values._runs_used_strictly(fresh) != owed_at, _REFUSAL.SUPERSEDED),
        (_standing.started(fresh, owed_at), _REFUSAL.SUPERSEDED),
        (_standing.moved(fresh, attempt.source) is not None, _REFUSAL.UNSAVED),
    )
    return next((refusal for refused, refusal in refusals if refused), None)


def _has_room(attempt: _records.CorrectionAttempt, candidate: PinnedState) -> _REFUSAL | None:
    """None where `candidate` has room for `attempt` at its widest resolution; NO_ROOM otherwise."""
    return None if _room.resolves(candidate.state_data, attempt) else _REFUSAL.NO_ROOM
