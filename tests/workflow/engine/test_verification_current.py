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

A carry that copied the current evidence's transcript is held to that source
until it settles: the source still the current record, its artifact still the
one that settled and carrying exactly the commands copied. A source edited,
deleted, or retired, or a copy carrying other commands, refuses the carry; a
thread nobody could read holds it; a transaction that copied nothing is
never asked.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    verification_current as _current,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    verification_evidence_test_support as support,
    verification_record_test_support as _record_support,
)

_DEFER = _evidence_models.ReportEvidenceVerdict.DEFER

_HOLD = _evidence_models.ReportEvidenceVerdict.HOLD

# Every move after settlement, the verdict it earns, and the refusal it names.
_REFUSALS = (
    (
        "the artifact was deleted",
        lambda case: case.pull_request.issue_comments.remove(support.artifact_comment(case)),
        _DEFER, "artifact is gone or no longer the one that settled",
    ),
    (
        "the artifact was edited",
        lambda case: setattr(support.artifact_comment(case), "body", "Tests passed, trust me."),
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
        "a newer revision was posted and never settled",
        support.posts_unsettled,
        _DEFER, "newer than the current record",
    ),
    (
        "the thread would not read",
        lambda case: case.gh.report_failures.unreadable.add(support.PR_NUMBER),
        _HOLD, "artifact could not be re-read",
    ),
    (
        "the issue records another pull request",
        lambda case: case.state.set("pr_number", support.PR_NUMBER + 1),
        _DEFER, "another pull request than the one this issue records",
    ),
    (
        "the head moved",
        lambda case: case.moves_the_head(support.REBASED_SHA),
        _DEFER, "moved off the recorded commit",
    ),
)


def _unchanged(copied: _records.PendingEvidence) -> _records.PendingEvidence:
    """The copy as minted."""
    return copied


# Every move of a copy's source, how the copy is spelled, and the verdict --
# None for none -- the copy earns.
_SOURCE_MOVES = (
    ("nothing moved", lambda case: None, _unchanged, None),
    (
        "the source was edited",
        lambda case: setattr(support.artifact_comment(case), "body", "Tests passed, trust me."),
        _unchanged, _DEFER,
    ),
    (
        "the source was deleted",
        lambda case: case.pull_request.issue_comments.remove(support.artifact_comment(case)),
        _unchanged, _DEFER,
    ),
    ("the source was retired", lambda case: _settlement.retire_current_evidence(case.state), _unchanged, _DEFER),
    (
        "the thread would not read",
        lambda case: case.gh.report_failures.unreadable.add(support.PR_NUMBER),
        _unchanged, _HOLD,
    ),
    (
        "the copy carries other commands",
        lambda case: None,
        lambda copied: replace(copied, commands=(_record_support.ran(exit_status=1),)),
        _DEFER,
    ),
    (
        "nothing was copied",
        lambda case: case.pull_request.issue_comments.remove(support.artifact_comment(case)),
        lambda copied: replace(copied, copied_from=None),
        None,
    ),
)


class CurrentEvidenceVerdictTest(unittest.TestCase, support.VerificationEvidenceCase):
    """PROVED only while the evidence is still true and still published."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_only_settled_evidence_is_proved(self) -> None:
        absent = support.current_verdict(self)
        self.record()
        self.reconcile()

        standing = support.current_verdict(self)

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

                refused = support.current_verdict(self)

                self.assertIs(refused.verdict, verdict)
                self.assertIn(refusal, refused.refusal)

    def test_a_pass_flag_its_artifact_contradicts(self) -> None:
        # A reviewer's account of a failed command settles as failing evidence
        # and is proved as such; the pinned flag rewritten to claim it passed
        # no longer describes the artifact, whose commands say one exited 1.
        self.record(self.binding(source=EvidenceSource.REVIEWER_REPORTED), exit_status=1)
        self.reconcile()
        failing = support.current_verdict(self)
        claimed = dict(self.state.get(_records.CURRENT_EVIDENCE), passed=True)
        self.state.set(_records.CURRENT_EVIDENCE, claimed)

        refused = support.current_verdict(self)

        self.assertIs(failing.verdict, _evidence_models.ReportEvidenceVerdict.PROVED)
        self.assertIs(refused.verdict, _DEFER)
        self.assertIn("no longer the one that settled", refused.refusal)


class CopiedSourceVerdictTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A carry answers only while the source it copied still says what was copied."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_only_the_source_as_copied_answers(self) -> None:
        for moved, moves, spelled, verdict in _SOURCE_MOVES:
            with self.subTest(moved=moved):
                self.setUp()
                copied = spelled(self._copies_the_current())
                moves(self)

                self.assertIs(self._verdict(copied), verdict)

    def _copies_the_current(self) -> _records.PendingEvidence:
        """Settle evidence, and mint a carry onto the squashed head copying its transcript."""
        self.record()
        self.reconcile()
        source = _settlement.read_current_evidence(self.state)
        return _record_state.mint_pending_evidence(
            self.state, support.ISSUE_NUMBER, self.binding().retargeted(support.SQUASHED_SHA),
            (_record_support.ran(),), source.receipt,
        )

    def _verdict(self, copied: _records.PendingEvidence) -> _evidence_models.ReportEvidenceVerdict | None:
        """What the source `copied` names earns it now, None for no refusal."""
        refused = _current.copied_source_verdict(self.gh, self.state, copied, self.pull_request)
        return None if refused is None else refused.verdict


if __name__ == "__main__":
    unittest.main()
