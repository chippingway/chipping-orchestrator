# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Evidence reaches another head only on a proved equal tree, a published source, and a review of that head.

The decision is read against a rewrite the tests can tell apart by nothing but
their trees: a squash onto the tested tree, and a rebase that replays the very
same patches over a base that moved. Only the first earns a decision, and only
once a report about the new head has settled and a reviewer was handed it, and
while the evidence being carried is still the artifact the pull request shows.
What it earns is a binding that still names the commit the commands ran on --
so the artifact the reconciliation publishes for the new head says which
earlier commit was tested rather than relabelling the run -- and answers for
the review of the new head, which is the subject the validating reader builds.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    verification_carry_forward as _carry_forward,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import verification_evidence_test_support as support, verification_report_fixture as _report
from tests.workflow.fixtures import SHA_LENGTH

_LEVEL = "INFO"

# A whole commit id nothing in this repository reads, and an abbreviated one.
_UNKNOWN_SHA = "ab" * (SHA_LENGTH // 2)

_ABBREVIATED_SHA = support.SQUASHED_SHA[:SHA_LENGTH // 4]

# Every target that earns no decision even with a review of the head pushed,
# that head, and the refusal it is logged under.
_REFUSED = (
    ("a rebase over a moved base", support.REBASED_SHA, support.REBASED_SHA, "not proved to be the tested tree"),
    ("a head nobody can read", _UNKNOWN_SHA, _UNKNOWN_SHA, "not proved to be the tested tree"),
    ("an abbreviated head", _ABBREVIATED_SHA, support.SQUASHED_SHA, "not a whole commit id"),
    ("the head it already answers for", support.TESTED_SHA, support.TESTED_SHA, "already answers for the target head"),
    ("an annotated tag of the tested tree", support.TAG_SHA, support.TAG_SHA, "not proved to be the tested tree"),
)

# What can happen to the source's artifact after it settled, and the refusal
# each is logged under.
_UNPUBLISHED = (
    (
        "deleted",
        lambda case: case.pull_request.issue_comments.remove(support.artifact_comment(case)),
        "artifact is gone or no longer the one that settled",
    ),
    (
        "edited",
        lambda case: setattr(support.artifact_comment(case), "body", "Tests passed, trust me."),
        "artifact is gone or no longer the one that settled",
    ),
    (
        "superseded by a newer artifact never settled",
        support.posts_unsettled,
        "newer than the current record",
    ),
)

_OLD_REVIEW_REFUSAL = "not about the head the evidence answers for"


class _CarryingCase(support.VerificationEvidenceCase):
    """Settled evidence on the tested commit, and a rewrite of it to carry it to."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.source = self.record()
        self.reconcile()

    def decide(self, target_head: str) -> _carry_forward.CarryForward | None:
        """The decision the current evidence earns onto `target_head`."""
        with self.seams():
            return _carry_forward.carry_forward_decision(support.reading(self), target_head)

    def rewrites(self, head: str) -> None:
        """Push `head`, and settle a report about it that a reviewer is handed."""
        self.moves_the_head(head)
        _report.settles_report(self, 2, _report.LATER_REPORT_TEXT, head=head)
        self.gh.write_pinned_state(self.issue, self.state)

    def carries(self, binding: _records.EvidenceBinding) -> _records.PendingEvidence:
        """Record a transaction carrying the source's run under `binding`, as a producer does."""
        carried = _record_state.mint_pending_evidence(
            self.state, support.ISSUE_NUMBER, binding, self.source.commands,
        )
        self.assertTrue(_record_state.record_pending_evidence(self.state, carried))
        self.gh.write_pinned_state(self.issue, self.state)
        return carried


class CarryForwardTest(unittest.TestCase, _CarryingCase):
    """Only full tree identity and an unchanged context carry evidence forward."""

    def setUp(self) -> None:
        _CarryingCase.setUp(self)

    def test_a_squash_onto_the_tested_tree_carries_it(self) -> None:
        self.rewrites(support.SQUASHED_SHA)
        decision = self.decide(support.SQUASHED_SHA)
        self.carries(decision.binding)

        self.assertFalse(self.reconcile())

        current = _settlement.read_current_evidence(self.state)
        self.assertEqual(decision.target_tree, support.TESTED_TREE)
        self.assertEqual(
            [
                (found.tested_sha, found.target_head, found.review_subject)
                for found in self.artifacts()
            ],
            [
                (support.TESTED_SHA, support.TESTED_SHA, support.TESTED_SHA),
                (support.TESTED_SHA, support.SQUASHED_SHA, support.SQUASHED_SHA),
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
        self.assertTrue(support.current_verdict(self).proved)

    def test_short_of_both_proofs_nothing_carries(self) -> None:
        # The rebase replays the same patches: its patch ids, its topic diff,
        # and its name all say "the same change", and its tree says otherwise.
        for case, target_head, pushed, refusal in _REFUSED:
            with self.subTest(case=case):
                self.setUp()
                self.rewrites(pushed)
                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertIsNone(self.decide(target_head))
                    self.assertIn(refusal, support.logged_refusal(logged))

        self.setUp()
        self.rewrites(support.SQUASHED_SHA)
        with patch.object(
            config, "VERIFY_COMMANDS", (support.SUITE, "uv run ruff check"),
        ), self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
            self.assertIsNone(self.decide(support.SQUASHED_SHA))
            self.assertIn("verification context moved", support.logged_refusal(logged))

    def test_no_current_evidence_carries_nothing(self) -> None:
        # Retired evidence is history; nothing current is left to carry.
        self.rewrites(support.SQUASHED_SHA)
        _settlement.retire_current_evidence(self.state)

        with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
            self.assertIsNone(self.decide(support.SQUASHED_SHA))
            self.assertIn("no current evidence", support.logged_refusal(logged))


class UncarriedEvidenceTest(unittest.TestCase, _CarryingCase):
    """An equal tree carries nothing unpublished, and nothing for a review of the old head."""

    def setUp(self) -> None:
        _CarryingCase.setUp(self)

    def test_an_unpublished_source_carries_nothing(self) -> None:
        # The artifact the source settled as, deleted or edited away, or
        # superseded by a newer one posted and never settled: its saved
        # transcript is evidence nobody can be shown as the latest, and
        # carrying it would publish it again under a new receipt.
        for moved, moves, refusal in _UNPUBLISHED:
            with self.subTest(moved=moved):
                self.setUp()
                self.rewrites(support.SQUASHED_SHA)
                moves(self)

                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertIsNone(self.decide(support.SQUASHED_SHA))
                    self.assertIn(refusal, support.logged_refusal(logged))

    def test_a_review_of_the_old_head_is_not_carried(self) -> None:
        # Pushed and never reported or reviewed again: the validating reader
        # would refuse the settled report as stale against the new head, so
        # nothing is decided, and a transaction carrying the old review is
        # never published.
        self.moves_the_head(support.SQUASHED_SHA)
        with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
            self.assertIsNone(self.decide(support.SQUASHED_SHA))
            self.assertIn("no review_subject about the target head", support.logged_refusal(logged))
        self.carries(self.source.binding.retargeted(support.SQUASHED_SHA))

        with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
            self.assertFalse(self.reconcile())
            self.assertIn(_OLD_REVIEW_REFUSAL, support.logged_refusal(logged))

        self.assertEqual(len(self.artifacts()), 1)

    def test_a_review_of_the_old_head_is_not_current(self) -> None:
        # Settled with no proof, as an earlier build could have: a reader
        # relying on it is refused rather than told it answers for the head.
        self.moves_the_head(support.SQUASHED_SHA)
        carried = self.carries(self.source.binding.retargeted(support.SQUASHED_SHA))
        landed = self.gh.publish_verification_artifact(self.pull_request, carried.artifact).landed_id
        self.state.data = _settlement.settled_state(self.state, carried, landed, None).data

        refused = support.current_verdict(self)

        self.assertIs(refused.verdict, _evidence_models.ReportEvidenceVerdict.DEFER)
        self.assertIn(_OLD_REVIEW_REFUSAL, refused.refusal)


if __name__ == "__main__":
    unittest.main()
