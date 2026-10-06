# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A carry refused, abandoned with the approval it was recorded for.

A carry is a transaction carrying a run onto a head it did not run on
(`verification_carry_forward`): its tested commit is another than the head it
answers for. Only an approval's squash records one, and it answers for that
head only on that approval's word. So nothing a later route does makes it
answer again once anything short of a reading nobody could take has refused
it -- its proof ahead of the post, the source it copied its transcript from,
the reading of its own artifact under its receipt, or the proof and both
artifacts re-read ahead of its settlement -- and a context, a head, or an
artifact put back afterwards would otherwise let it settle and move the label
with no review of what moved in between.

Such a carry is abandoned into history (`verification_settlement_state`), and
the approval it was recorded for retired in the same guarded commit: its
subject written null, which no reader of an approval acts on
(`review_subjects.approval_covers_current`), until a fresh reviewer's approval
is recorded in its place. Only that approval, spelled exactly as the carry
recorded it: one another road recorded in its place -- of another subject, or
the same one spelled otherwise -- stands. And it is retired whether or not the
comment has room for the carry's own entry, since that write only shrinks the
comment -- the carry then stays owed for a later tick to abandon, under an
approval nothing acts on. Which approval a run was recorded for is this
owner's rule for a settled carry invalidated too (`retires_its_approval`,
`stages/validating/squash_evidence.py`), and for a carry still owed, which
holds the move it was recorded for until it settles or is abandoned
(`awaits_settlement`).

The abandonment is staged on the pinned comment read afresh and committed
guarded by that reading (`verification_durable`), owning only the record, the
history it goes into, and the approval (`ABANDONS`): a transaction, an
approval, or any other bound record another road moved after the tick read the
comment refuses it with nothing written, and every field it does not own -- a
returned verdict, a usage total, a watermark, comment ids -- is kept as the
comment carries it when it lands. The reconciliation's own retirements abandon
through here every transaction that will never settle (`verification_transaction`),
a carry or not, taking a carry's approval with it. A route behind the
reconciliation abandons a carry only, and only on a refusal of the carry
itself: the publication, at the reading of its own artifact
(`verification_publishing`), and the settlement, in the commit that records the
artifact's ledger entry, where the comment read behind its proof still carries
every bound record as the tick read it (`verification_settling`). Any other
transaction those routes refuse stays owed for the route that answers it.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    review_subjects as _review_subjects,
    verification_durable as _durable,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)

log = logging.getLogger("orchestrator.workflow")

# What abandoning a transaction may write: the record, the history it goes
# into, and the approval a carry takes with it.
ABANDONS = (
    _records.PENDING_EVIDENCE,
    _records.EVIDENCE_HISTORY,
    _review_subjects.APPROVED_SUBJECT,
)


def is_carry(pending: _records.PendingEvidence | None) -> bool:
    """Whether `pending` carries a run onto a head it did not run on."""
    return pending is not None and pending.binding.tested_sha != pending.binding.target.target_head


def abandons(state: PinnedState, pending: _records.PendingEvidence | None) -> bool:
    """Abandon the transaction `state` records, retiring the approval a carry was recorded for; whether it went.

    Only the transaction the comment still records, and its entry only where
    the comment can carry it (`verification_settlement_state.retire_pending_evidence`).
    A carry's approval goes only while the approval record is the one it was
    recorded for -- the very subject the carry answers for -- so an approval
    another road put in its place stands. And it goes whether or not the
    entry fits: writing the subject null only shrinks the comment, so the
    refusal persists while a carry with no room to be abandoned stays owed,
    for the next tick to abandon once there is. The caller commits, False
    included, since the approval may have gone all the same; every field this
    stages is one of `ABANDONS`.
    """
    if _record_state.read_pending_evidence(state) != pending:
        return False
    if is_carry(pending):
        retires_its_approval(state, pending.binding)
    return _settlement.retire_pending_evidence(state, pending)


def awaits_settlement(state: PinnedState, pending: _records.PendingEvidence | None, head: str) -> bool:
    """Whether `pending` is a carry onto `head` still owed for the approval it was recorded for.

    A carry the reconciliation refused is abandoned rather than left owed, so
    one still owed behind it stood down on what a later tick answers -- a
    comment with no room to settle into, before the post or behind it, or a
    record another road wrote meanwhile -- and the move it was recorded for
    waits on it. Only while that approval stands: one retired, or replaced by
    another road's, moves nothing over the carry.
    """
    if not is_carry(pending) or pending.binding.target.target_head != head:
        return False
    return _is_its_approval(state, pending.binding)


def retires_its_approval(state: PinnedState, binding: _records.EvidenceBinding) -> None:
    """Write the approval null where it is the one `binding` answers for, and leave any other.

    The approval a run was recorded for is the very subject it answers for,
    so an approval another road recorded in its place, of another subject, is
    not this evidence's to retire -- whether the evidence goes owed or
    settled.
    """
    if _is_its_approval(state, binding):
        state.set(_review_subjects.APPROVED_SUBJECT, None)


def _is_its_approval(state: PinnedState, binding: _records.EvidenceBinding) -> bool:
    """Whether the approval record is exactly the subject `binding` answers for, as the comment's JSON spells both.

    Spelled rather than compared as Python values, which call a pull request
    number `12.0` the `12` it was recorded as: a record another road wrote
    otherwise is that road's, and no reader takes a respelled one for this
    approval either.
    """
    recorded = _commit_models.spelled(state.data, _review_subjects.APPROVED_SUBJECT)
    return recorded == _commit_models.spelling(binding.target.subject)


def abandons_afresh(
    gh: GitHubClient, issue: Issue, state: PinnedState, pending: _records.PendingEvidence | None,
) -> bool:
    """Abandon `pending` over the comment read afresh, in one guarded commit; True where the tick holds.

    `pending` is the transaction `state` records, or None for a record nobody
    can read, which is dropped with no entry. Staged on the comment read
    afresh and held to every record the evidence is bound through
    (`verification_durable`), and committed guarded by that reading, so a
    transaction another road recorded meanwhile is never written away: a
    comment that will not read holds the tick, and one whose records moved --
    before that reading or under the commit -- is left as it stands with the
    transaction owed, for the next tick to answer what it carries then. One
    with no room for the entry keeps it owed too, but takes a carry's
    approval (`abandons`), which is committed all the same. A commit nobody
    confirmed holds, and the next tick finds the record gone or abandons it
    again, with no second entry.
    """
    durable, refused = _durable.durable_comment(gh, issue, state)
    if refused is None:
        guard = _durable.guarded(durable, ABANDONS)
        if not abandons(durable, pending):
            log.error(
                "issue=#%d has no room on its pinned comment to abandon the "
                "verification evidence it owes; leaving it owed", issue.number,
            )
        refused = _durable.lands(gh, issue, state, guard, durable)
    if refused is None:
        return False
    log.info(
        "issue=#%d is not abandoning the verification evidence it owes: %s",
        issue.number, refused.refusal,
    )
    return refused.holds
