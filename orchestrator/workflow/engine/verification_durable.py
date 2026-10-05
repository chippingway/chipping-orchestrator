# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned comment read afresh before any evidence write is composed, and what a guarded write of it answers.

An artifact post, a pull-request read, or the dispatch ahead of the evidence
guard is long enough for another road to write the pinned comment: a developer
report settling a later revision, a reviewer recording the subject it was
handed, another evidence transaction replacing this one. Nothing in the state
the tick holds sees any of it, and a write composed over that state would put
the replaced records back over the newer ones -- a settlement declaring
evidence current for a subject the comment no longer carries, or a retirement
erasing a transaction recorded meanwhile and lowering the revision floor under
it. So the settlement and every retirement ask here first.

So the comment is read again, through the guarded commit's own reading
(`pinned_commit.reread`), and it has to be the comment this tick read and
still carry every record the evidence is bound through exactly as the state in
hand spells them: the developer report's transaction and settled pair, the
review subjects -- the approved one among them, since evidence carried across
an approval's squash answers for the approved review -- and this domain's own
records and revision floor. Which records those are is this domain's choice,
and they are the prerequisites of every guarded write it makes (`guarded`);
the comparison is the commit's, as the comment's JSON spells each record, so a
field written `null` where there was none, or `true` where there was `1`, is a
move. The records that move are the caller's to refuse over; the
fresh reading comes back with them, since it is the one comment any write may
still be laid over.

A comment that will not read or parse, or is no longer the one the state was
read from, holds: nobody could say what it carries, and a write over it would
pin a second comment or replace one nobody read. A guarded write is answered in
the same two words (`refusal_of`): one that could not read the comment as it
was captured, or went out and was never confirmed, holds, since the record may
read either way and the transaction's receipt settles it on a later tick;
every other refusal -- a record that moved, a comment that moved under the
edit, a write the comment has no room for -- defers, with whatever the write
was for still owed.
"""
from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    pinned_commit_models as _commit_models,
    report_records as _report_records,
    review_subjects as _review_subjects,
    verification_records as _records,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict

# Every record the evidence is bound through: the pull request, the developer
# report's transaction and settled pair, the review subjects -- the approved
# one included, which evidence carried across an approval's squash answers
# through -- and this domain's own four records and the revision floor beside
# them.
_BOUND_RECORDS = (
    "pr_number",
    _report_records.PENDING_REPORT,
    _report_records.DELIVERED_REPORT,
    _report_records.CURRENT_REPORT,
    _report_records.REPORT_HANDOFF,
    _review_subjects.REVIEW_SUBJECT,
    _review_subjects.RETURNED_SUBJECT,
    _review_subjects.APPROVED_SUBJECT,
    _records.PENDING_EVIDENCE,
    _records.CURRENT_EVIDENCE,
    _records.EVIDENCE_HISTORY,
    _records.EVIDENCE_HANDOFF,
    _records.REVISION_FLOOR,
)

_UNREAD = ReportEvidence(
    ReportEvidenceVerdict.HOLD,
    "the pinned comment could not be read again as the one this tick read",
)

# What every refusal of a guarded write means here, save a moved prerequisite,
# which names the record (`_moved`). A write staging a field it never declared
# is this build's own fault; it defers rather than hold every later tick, and
# what it was for stays owed, which every consumer fails closed on.
_REFUSALS = MappingProxyType({
    _commit_models.CommitRefusal.UNREADABLE: _UNREAD,
    _commit_models.CommitRefusal.MALFORMED: _UNREAD,
    _commit_models.CommitRefusal.REPLACED: _UNREAD,
    _commit_models.CommitRefusal.MOVED: ReportEvidence(
        ReportEvidenceVerdict.DEFER, "the pinned comment moved while it was being written",
    ),
    _commit_models.CommitRefusal.OWNED_CONFLICT: ReportEvidence(
        ReportEvidenceVerdict.DEFER, "another road wrote a record this write replaces",
    ),
    _commit_models.CommitRefusal.UNDECLARED_WRITE: ReportEvidence(
        ReportEvidenceVerdict.DEFER, "the write staged a record it does not own",
    ),
    _commit_models.CommitRefusal.OVERFLOW: ReportEvidence(
        ReportEvidenceVerdict.DEFER, "the pinned comment has no room for the write",
    ),
    _commit_models.CommitRefusal.INADMISSIBLE: ReportEvidence(
        ReportEvidenceVerdict.DEFER, "the write's own check refused the record it would leave",
    ),
})

_UNCONFIRMED = ReportEvidence(
    ReportEvidenceVerdict.HOLD,
    "the pinned comment was written and the write was never confirmed",
)


def guarded(state: PinnedState, owned: Iterable[str]) -> _commit_models.PinnedCommit:
    """The commit `state` guards as it was read: every bound record a prerequisite, and `owned` the caller's to write.

    Captured before anything is staged on `state`, since what the write
    changes is told by its difference from this.
    """
    return _commit_models.PinnedCommit.capture(state, prerequisites=_BOUND_RECORDS, owned=owned)


def durable_comment(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> tuple[PinnedState | None, ReportEvidence | None]:
    """The comment read afresh, and the refusal its records earn, if any.

    `(comment, None)` where it carries every bound record as `state` does,
    `(comment, DEFER)` where one moved, and `(None, HOLD)` where it will not
    read or parse or is not the comment `state` was read from.
    """
    guard = guarded(state, ())
    durable = _commit.reread(gh, issue, guard)
    if not isinstance(durable, PinnedState):
        return None, _UNREAD
    moved = guard.moved(durable.data)
    return durable, (_moved(moved) if moved else None)


def refusal_of(outcome: _commit_models.CommitOutcome) -> ReportEvidence | None:
    """What one guarded write's outcome refuses here: None where it was prepared or landed."""
    if outcome.status is _commit_models.CommitStatus.UNCONFIRMED:
        return _UNCONFIRMED
    if outcome.refusal is None:
        return None
    if outcome.refusal is _commit_models.CommitRefusal.PREREQUISITE_CHANGED:
        return _moved(outcome.fields)
    return _REFUSALS[outcome.refusal]


def _moved(fields: tuple[str, ...]) -> ReportEvidence:
    """The refusal the bound records `fields` earn by moving."""
    named = ", ".join(fields)
    return ReportEvidence(
        ReportEvidenceVerdict.DEFER, f"the pinned comment's {named} moved since this tick read it",
    )
