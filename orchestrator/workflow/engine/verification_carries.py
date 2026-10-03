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
the approval it was recorded for retired in the same write: its subject
written null, which no reader of an approval acts on
(`review_subjects.approval_covers_current`), until a fresh reviewer's approval
is recorded in its place. Only that approval: one another road recorded in its
place, of another subject, stands. And it is retired whether or not the
comment has room for the carry's own entry, since that write only shrinks the
comment -- the carry then stays owed for a later tick to abandon, under an
approval nothing acts on. Any other transaction a route behind the
reconciliation answers stays owed; this owner abandons a carry only. Which
approval a run was recorded for is this owner's rule for a settled carry
invalidated too (`retires_its_approval`, `stages/validating/squash_evidence.py`),
and for a carry still owed, which holds the move it was recorded for until it
settles or is abandoned (`awaits_settlement`).
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    review_subjects as _review_subjects,
    verification_durable as _durable,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)

log = logging.getLogger("orchestrator.workflow")


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
    for the next tick to abandon once there is. The caller writes, False
    included, since the approval may have gone all the same.
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
    return state.get(_review_subjects.APPROVED_SUBJECT) == pending.binding.target.subject


def retires_its_approval(state: PinnedState, binding: _records.EvidenceBinding) -> None:
    """Write the approval null where it is the one `binding` answers for, and leave any other.

    The approval a run was recorded for is the very subject it answers for,
    so an approval another road recorded in its place, of another subject, is
    not this evidence's to retire -- whether the evidence goes owed or
    settled.
    """
    if state.get(_review_subjects.APPROVED_SUBJECT) == binding.target.subject:
        state.set(_review_subjects.APPROVED_SUBJECT, None)


def abandons_afresh(
    gh: GitHubClient, issue: Issue, state: PinnedState, pending: _records.PendingEvidence,
) -> bool:
    """Abandon the refused carry `pending` over the comment read afresh, and write it; True where the tick holds.

    Composed over the comment read afresh and held to every record the
    evidence is bound through (`verification_durable`), so a transaction
    another road recorded meanwhile is never written away: a comment that will
    not read holds the tick, and one whose records moved is left as it stands
    with the carry owed, for the next tick's proof to answer. One with no room
    for the entry keeps the carry owed too, but takes the approval's
    retirement (`abandons`), which is written all the same.
    """
    durable, moved = _durable.durable_comment(gh, issue, state)
    if moved is not None:
        log.info("issue=#%d is not abandoning the refused carry it owes: %s", issue.number, moved.refusal)
        return moved.holds
    read = dict(durable.data)
    abandoned = abandons(durable, pending)
    log.log(
        logging.INFO if abandoned else logging.ERROR,
        "issue=#%d %s the refused carry of verification evidence revision %d; "
        "the approval it was recorded for, where it still stands, is retired", issue.number,
        "abandoned" if abandoned else "has no room to abandon", pending.revision,
    )
    if durable.data != read:
        state.data = durable.data
        gh.write_pinned_state(issue, state)
    return False
