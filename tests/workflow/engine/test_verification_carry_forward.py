# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Evidence reaches another head only on a proved equal tree under the same context.

The decision is read against a rewrite the tests can tell apart by nothing but
their trees: a squash onto the tested tree, and a rebase that replays the very
same patches over a base that moved. Only the first earns a decision, and what
it earns is a binding that still names the commit the commands ran on -- so the
artifact the reconciliation publishes for the new head says which earlier
commit was tested rather than relabelling the run.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import (
    verification_carry_forward as _carry_forward,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import verification_evidence_test_support as support
from tests.workflow.fixtures import _TEST_SPEC, SHA_LENGTH

_LEVEL = "INFO"

# A whole commit id nothing in this repository reads, and an abbreviated one.
_UNKNOWN_SHA = "ab" * (SHA_LENGTH // 2)

_ABBREVIATED_SHA = support.SQUASHED_SHA[:SHA_LENGTH // 4]

# Every target that earns no decision, and the refusal it is logged under.
_REFUSED = (
    ("a rebase over a moved base", support.REBASED_SHA, "not proved to be the tested tree"),
    ("a head nobody can read", _UNKNOWN_SHA, "not proved to be the tested tree"),
    ("an abbreviated head", _ABBREVIATED_SHA, "not a whole commit id"),
)


class CarryForwardTest(unittest.TestCase, support.VerificationEvidenceCase):
    """Only full tree identity and an unchanged context carry evidence forward."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.source = self.record()
        self.reconcile()

    def decide(self, target_head: str) -> _carry_forward.CarryForward | None:
        """The decision the current evidence earns onto `target_head`."""
        with self.seams():
            return _carry_forward.carry_forward_decision(
                _TEST_SPEC, self.issue, self.state, target_head,
            )

    def test_a_squash_onto_the_tested_tree_carries_it(self) -> None:
        decision = self.decide(support.SQUASHED_SHA)
        self.moves_the_head(support.SQUASHED_SHA)
        carried = _record_state.mint_pending_evidence(
            self.state, support.ISSUE_NUMBER, decision.binding, self.source.commands,
        )
        self.assertTrue(_record_state.record_pending_evidence(self.state, carried))
        self.gh.write_pinned_state(self.issue, self.state)

        self.assertFalse(self.reconcile())

        current = _settlement.read_current_evidence(self.state)
        self.assertEqual(decision.target_tree, support.TESTED_TREE)
        self.assertEqual(
            [(found.tested_sha, found.target_head) for found in self.artifacts()],
            [
                (support.TESTED_SHA, support.TESTED_SHA),
                (support.TESTED_SHA, support.SQUASHED_SHA),
            ],
        )
        self.assertEqual(
            (current.binding.tested_sha, current.binding.target.target_head),
            (support.TESTED_SHA, support.SQUASHED_SHA),
        )
        self.assertEqual(
            [(entry.receipt, entry.retired) for entry in _settlement.read_evidence_history(self.state)],
            [(self.source.receipt, _records.Retirement.SUPERSEDED)],
        )

    def test_short_of_both_proofs_nothing_carries(self) -> None:
        # The rebase replays the same patches: its patch ids, its topic diff,
        # and its name all say "the same change", and its tree says otherwise.
        for case, target_head, refusal in _REFUSED:
            with self.subTest(case=case), self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                self.assertIsNone(self.decide(target_head))
                self.assertIn(refusal, support.logged_refusal(logged))

        with patch.object(
            config, "VERIFY_COMMANDS", (support.SUITE, "uv run ruff check"),
        ), self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
            self.assertIsNone(self.decide(support.SQUASHED_SHA))
            self.assertIn("verification context moved", support.logged_refusal(logged))

    def test_no_current_evidence_carries_nothing(self) -> None:
        # Retired evidence is history; nothing current is left to carry.
        _settlement.retire_current_evidence(self.state)

        with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
            self.assertIsNone(self.decide(support.SQUASHED_SHA))
            self.assertIn("no current evidence", support.logged_refusal(logged))


if __name__ == "__main__":
    unittest.main()
