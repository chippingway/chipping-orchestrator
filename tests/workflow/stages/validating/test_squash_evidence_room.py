# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The room a squash's carry needs on the pinned comment, the approval's claim on it included.

The carry is recorded beside the approval's claim pointed at it, and that
claim can grow as it is pointed: one on evidence the reviewer reused reads
`published` once it names the carried transaction. So the room is measured
with the claim as it will be written. At the last character the comment can
carry the whole of it, the carry is recorded and the comment fits; one past,
the carry is refused and the evidence answered as having no room -- although
the transaction alone would still have been taken there -- and nothing staged
is ever past the limit GitHub accepts.
"""
from __future__ import annotations

import unittest
import uuid

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    report_record_state as _report_record_state,
    verification_carry_forward as _carry_forward,
    verification_record_state as _record_state,
    verification_records as _records,
)
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    review_verdicts as _verdicts,
    squash_evidence as _squash_evidence,
)
from tests.workflow.engine import verification_record_test_support as _support

ISSUE = _support.ISSUE_NUMBER

SQUASHED = "5c3a91b7" * 5

NONCE = uuid.UUID(int=0).hex

# The receipt the reviewer's run settled under at revision 1.
SETTLED_RECEIPT = _records.RECEIPT.format(issue=ISSUE, revision=1, nonce=NONCE)

# That run, carried from the tested commit onto the squashed head, copying the
# artifact it settled as.
CARRY = _carry_forward.CarryForward(
    source=_support.binding(source=EvidenceSource.REVIEWER_REPORTED),
    target_head=SQUASHED,
    target_tree=_support.TESTED_TREE,
    subject=_support.SUBJECT.recorded(),
    commands=(_support.ran(),),
    copied_from=SETTLED_RECEIPT,
)

# That run as it settled, and the approval's claim on it: reused rather than run.
SETTLED = _records.PendingEvidence(
    receipt=SETTLED_RECEIPT,
    revision=1,
    binding=CARRY.source,
    commands=CARRY.commands,
)

REUSED = _verdicts.EvidenceClaim(
    use=_verdicts.EvidenceUse.REUSED,
    receipt=SETTLED.receipt,
    revision=SETTLED.revision,
    digest=SETTLED.content_revision,
    passed=True,
    covers=True,
)


def _comment(padding: int) -> PinnedState:
    """A pinned comment holding the approval's claim, revision 1 spent, and `padding` characters of anything else."""
    return PinnedState(comment_id=1, state_data={
        "pr_number": _support.PR_NUMBER,
        _records.REVISION_FLOOR: SETTLED.revision,
        _approved_evidence.APPROVED_EVIDENCE: REUSED.recorded(),
        "padding": "x" * padding,
    })


def _carried_beside(padding: int) -> PinnedState:
    """`_comment(padding)` with what the carry owes it staged."""
    state = _comment(padding)
    _squash_evidence.SquashEvidence(carry=CARRY).stages(state, ISSUE)
    return state


class CarryRoomTest(unittest.TestCase):
    """The carry is recorded only where the comment carries it and the claim rebound to it."""

    def test_the_claim_is_measured_with_the_carry(self) -> None:
        last = self._last_recorded()
        for padding, recorded in ((last, True), (last + 1, False)):
            with self.subTest(padding=padding):
                state = _carried_beside(padding)

                self.assertEqual(_record_state.read_pending_evidence(state) is not None, recorded)
                self.assertTrue(_report_record_state.fits_the_comment(state.data))
        alone = _comment(last + 1)
        self.assertTrue(_record_state.record_pending_evidence(
            alone, _record_state.mint_pending_evidence(
                alone, ISSUE, CARRY.binding, CARRY.commands, CARRY.copied_from,
            ),
        ))

    def _last_recorded(self) -> int:
        """The most padding beside which the carry is still recorded, found by bisection."""
        low, high = 0, MAX_PINNED_BODY
        while low + 1 < high:
            middle = (low + high) // 2
            if _record_state.read_pending_evidence(_carried_beside(middle)) is None:
                high = middle
            else:
                low = middle
        self.assertGreater(low, 0)
        return low


if __name__ == "__main__":
    unittest.main()
