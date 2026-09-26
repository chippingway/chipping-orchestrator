# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A reader relying on current evidence proves it, and its publication, first.

The current record says what a settlement put on the pull request once. A
reader about to rely on it -- a reviewer handed it, a readiness decision -- is
told PROVED only while the world still matches the binding AND the pull request
still carries the very artifact that settled, under the handoff that settled
it, with the pass flag its commands earn. A deleted or edited artifact, a
handoff describing other evidence, a pass flag the artifact contradicts, and a
moved head each refuse it; a thread nobody could read holds.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    verification_proof as _proof,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import verification_evidence_test_support as support
from tests.workflow.fixtures import _TEST_SPEC

_DEFER = _evidence_models.ReportEvidenceVerdict.DEFER

_HOLD = _evidence_models.ReportEvidenceVerdict.HOLD

# Every move after settlement, the verdict it earns, and the refusal it names.
_REFUSALS = (
    (
        "the artifact was deleted",
        lambda case: case.pull_request.issue_comments.remove(case.artifact_comment()),
        _DEFER, "artifact is gone or no longer the one that settled",
    ),
    (
        "the artifact was edited",
        lambda case: setattr(case.artifact_comment(), "body", "Tests passed, trust me."),
        _DEFER, "artifact is gone or no longer the one that settled",
    ),
    (
        "the handoff names other evidence",
        lambda case: case.state.set(_records.EVIDENCE_HANDOFF, dict(
            case.state.get(_records.EVIDENCE_HANDOFF), receipt="issue-7-verification-9",
        )),
        _DEFER, "handoff does not describe the current evidence",
    ),
    (
        "the thread would not read",
        lambda case: case.gh.report_failures.unreadable.add(support.PR_NUMBER),
        _HOLD, "artifact could not be re-read",
    ),
    (
        "the head moved",
        lambda case: case.moves_the_head(support.REBASED_SHA),
        _DEFER, "moved off the recorded commit",
    ),
)


class CurrentEvidenceVerdictTest(unittest.TestCase, support.VerificationEvidenceCase):
    """PROVED only while the evidence is still true and still published."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def verdict(self) -> _evidence_models.ReportEvidence:
        """What a reader asking now is told about the current evidence."""
        with self.seams():
            return _proof.current_evidence_verdict(
                _proof.ProofReading(self.gh, _TEST_SPEC, self.issue, self.state),
            )

    def artifact_comment(self):
        """The comment the current evidence was published as."""
        comment_id = _settlement.read_current_evidence(self.state).comment_id
        return next(
            posted for posted in self.pull_request.issue_comments
            if posted.id == comment_id
        )

    def test_only_settled_evidence_is_proved(self) -> None:
        absent = self.verdict()
        self.record()
        self.reconcile()

        standing = self.verdict()

        self.assertEqual(
            (absent.verdict, standing.verdict),
            (_DEFER, _evidence_models.ReportEvidenceVerdict.PROVED),
        )
        self.assertIs(standing.pull_request, self.pull_request)

    def test_every_move_refuses_the_current_evidence(self) -> None:
        for moved, moves, verdict, refusal in _REFUSALS:
            with self.subTest(moved=moved):
                self.setUp()
                self.record()
                self.reconcile()
                moves(self)

                refused = self.verdict()

                self.assertIs(refused.verdict, verdict)
                self.assertIn(refusal, refused.refusal)


    def test_a_pass_flag_its_artifact_contradicts(self) -> None:
        # A failed run settles as failing evidence and is proved as such; the
        # pinned flag rewritten to claim it passed no longer describes the
        # artifact, whose commands say one exited 1.
        self.record(exit_status=1)
        self.reconcile()
        failing = self.verdict()
        claimed = dict(self.state.get(_records.CURRENT_EVIDENCE), passed=True)
        self.state.set(_records.CURRENT_EVIDENCE, claimed)

        refused = self.verdict()

        self.assertIs(failing.verdict, _evidence_models.ReportEvidenceVerdict.PROVED)
        self.assertIs(refused.verdict, _DEFER)
        self.assertIn("no longer the one that settled", refused.refusal)


if __name__ == "__main__":
    unittest.main()
