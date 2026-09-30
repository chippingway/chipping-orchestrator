# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A disposed approval reaches the approval arc only over proved evidence, and parks only over a standing subject.

Through `review_disposition`: an approval whose own run or reuse proves valid
reaches `documenting`, from the tick its reviewer returned or from a later one
finishing it with no reviewer again; one relying on nothing valid parks under
`reviewer_unverified`, saying why; and one whose proof nobody could read holds
for a later tick. The proof, the verify gate, and the squash are requests long
enough for another road to move what the approval stands on, and a refusal or
failure over a move is a fresh reviewer's to answer, not a human's. A squash
whose notice did not go out is finished by the recovery ahead of the next
reviewer, the approval's verdict already retired.

The proof, the arc, and the parks are each covered directly beside their
owners; this is what the disposition composes of them.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.publication import models as _publication
from orchestrator.workflow.late_split import collapses as _collapses
from tests.workflow.fixtures import LABEL_DOCUMENTING
from tests.workflow.stages.validating import (
    approval_proof_test_support as _proof,
    disposed_verdict_test_support as _disposed,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

VERIFY = "_run_verify_commands"

PR_COMMENT = "pr_comment"

ARTIFACT_REREAD = "reread_verification_artifact"

UNVERIFIED = "reviewer_unverified"

APPROVED = "approved"

DOCUMENTING = (_world.ISSUE, LABEL_DOCUMENTING)

# A reviewer approving over the evidence revision `digest` names, running
# nothing of its own, and one declaring nothing at all.
REUSING = "Covered.\n\nVERIFICATION: REUSED sha256:{digest}\n\nVERDICT: APPROVED"

UNDECLARED_APPROVAL = "LGTM\n\nVERDICT: APPROVED"

# What the squash notice of two commits says about itself, and the collapse a
# squash that published leaves recorded until that notice is out.
SQUASH_NOTICE = "squashed 2 commits"

_COLLAPSED = 2

_BASE = "cc33dd44" * 5

_NOT_PARKED = ((None, False), None, [])

_UNVERIFIED_PARK = ((UNVERIFIED, True), None, [UNVERIFIED])


def _reusing(case) -> str:
    """A reuse of the evidence an earlier round settles for `case`."""
    return REUSING.format(digest=_read.settles_evidence(case).content_revision)


def _declaring(**declared):
    """A reply declaring one run as `declared` spells it, for a table of replies."""
    return lambda _case: _world.declared_run(**declared)


def _lands_a_collapse(gate, _branch, _pr_number) -> _publication._SquashOutcome:
    """A squash that published onto the head the pull request stands on, its collapse recorded."""
    _collapses.record_pending_collapse(gate.state, head=_world.HEAD, base_sha=_BASE, count=_COLLAPSED)
    return _publication._SquashOutcome(success=True, sha=_world.HEAD, count=_COLLAPSED)


class _RefusesTheSquashNotice:
    """A pull request that takes every comment but the squash notice."""

    def __init__(self, posts) -> None:
        self._posts = posts

    def __call__(self, pr_number, body):
        if SQUASH_NOTICE in body:
            raise RuntimeError("pull request comment rejected")
        return self._posts(pr_number, body)


# Each approval returned, and where it ends up: every relabel, the park as
# `parked` reads it, the verify gate's runs, and a phrase the park's notice
# says -- the returning tick's own words for a declaration that earned none.
_APPROVALS = (
    ("its own passing run", _declaring(), ([DOCUMENTING], _NOT_PARKED, 1, "")),
    ("a reuse of the handed evidence", _reusing, ([DOCUMENTING], _NOT_PARKED, 1, "")),
    ("nothing declared", lambda _case: UNDECLARED_APPROVAL, ([], _UNVERIFIED_PARK, 0, "declared no verification")),
    ("a failed run", _declaring(exit_status=1), ([], _UNVERIFIED_PARK, 0, "did not exit 0")),
    ("another command", _declaring(command="uv run ruff check"), ([], _UNVERIFIED_PARK, 0, "`VERIFY_COMMANDS`")),
)

# Another road's work behind the approval's last read of its artifact, which
# the proof refuses the approval over, and the report and evidence revisions
# the pinned comment records then: that move is kept, and nobody is asked.
_BEHIND_THE_PROOF = (
    ("a later report", _read.settles_a_later_report, (2, 1)),
    ("later evidence", _read.settles_evidence, (1, 2)),
)

# What another road does while a failed verify gate runs, and the park as
# `parked` reads it then: only a subject still standing parks, a push drops
# the verdict for a fresh reviewer, and a thread nobody could read holds it.
_UNDER_A_FAILED_GATE = (
    ("nothing", None, (("verify_failed", True), None, ["verify_failed"])),
    ("a push", _world.pushes, _NOT_PARKED),
    ("an unread report", _world.stops_answering, ((None, False), APPROVED, [])),
)


class DisposedApprovalTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """An approval reaches the approval arc over proved evidence, parks over anything else, and holds unproved."""

    def test_only_valid_evidence_reaches_the_arc(self) -> None:
        # Whichever way the approval ends, the write that ends it retires its
        # verdict, and only a park that lands is reported.
        for name, reply, expected in _APPROVALS:
            with self.subTest(name):
                self.setUp()

                ran = self.returns(reply(self), **_disposed.ON_THE_HEAD)

                self.assertEqual(
                    (
                        self.github.label_history,
                        self.parked(),
                        ran[VERIFY].call_count,
                        expected[-1] in _disposed.last_notice(self),
                    ),
                    (*expected[:-1], True),
                )

    def test_a_held_approval_needs_no_reviewer(self) -> None:
        # The artifact's post lands and its response is lost, so the tick
        # holds with the verdict and its transaction owed. The next tick's
        # reconciliation finds the artifact by its receipt, and the approval
        # goes on from the verdict the first tick wrote, through the run it
        # was returned in, with nothing spent again.
        self.github.report_failures.lost.add(_world.PR)
        self.returns(_world.declared_run(), **_disposed.ON_THE_HEAD)
        self.github.report_failures.lost.discard(_world.PR)
        spent = _read.spent(self)
        held = (self.waiting(), tuple(self.github.label_history))

        ran = self.finishes(**_disposed.ON_THE_HEAD)

        self.assertEqual(
            (
                held,
                ran[_world.RUN_AGENT].call_count,
                _read.spent(self),
                self.github.label_history,
                self.waiting(),
            ),
            ((APPROVED, ()), 0, spent, [DOCUMENTING], None),
        )

    def test_an_unread_proof_holds_the_approval(self) -> None:
        # The artifact the approval rests on cannot be read again: that is no
        # refusal, so nothing is verified, parked, or written, and the verdict
        # waits for a later tick, which proves it and hands the issue on.
        self.run = _read.seeds_a_verdict(self, _read.settles_evidence(self))
        before = self.pinned()

        with patch.object(self.github, "_verification_thread", side_effect=RuntimeError("unanswered")):
            held = self.finishes(**_disposed.ON_THE_HEAD)

        self.assertEqual(
            (self.pinned(), held[VERIFY].call_count, self.github.posted_comments, self.github.label_history),
            (before, 0, [], []),
        )
        self.finishes(**_disposed.ON_THE_HEAD)
        self.assertEqual(
            (self.github.label_history, self.waiting()),
            ([DOCUMENTING], None),
        )


class ApprovalRaceTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """An approval refused or failed over a move parks nobody, and keeps what moved."""

    def test_a_refusal_over_a_move_parks_nobody(self) -> None:
        # The proof reads the comment last and refuses the approval over
        # records another road moved behind it; the disposition holds the
        # refused approval to its subject and claim again, measured from the
        # comment its readiness was proved over, so the verdict is dropped for
        # a fresh reviewer instead of a human being asked about work nobody
        # reviewed -- and the later records are kept.
        for name, road, revisions in _BEHIND_THE_PROOF:
            with self.subTest(name):
                self.setUp()
                self.run = _read.seeds_a_verdict(self, _read.settles_evidence(self))

                behind = _world.AnotherRoadBehind(self, ARTIFACT_REREAD, bool, road)
                with patch.object(self.github, ARTIFACT_REREAD, behind):
                    ran = self.finishes(**_disposed.ON_THE_HEAD)

                self.assertEqual(
                    (
                        self.parked(),
                        self.github.posted_comments,
                        ran[VERIFY].call_count,
                        (_read.current_report_revision(self), _read.current_evidence_revision(self)),
                    ),
                    (_NOT_PARKED, [], 0, revisions),
                )

    def test_a_failed_gate_parks_a_standing_subject(self) -> None:
        for move, road, parked in _UNDER_A_FAILED_GATE:
            with self.subTest(move):
                self.setUp()
                gate = _proof.DuringTheGate(self, road, _proof.FAILED_GATE)

                self.returns(_reusing(self), verify_result=gate, **_disposed.ON_THE_HEAD)

                self.assertEqual((self.parked(), self.github.label_history), (parked, []))


class SquashRecoveryTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A squash an approval published and could not announce is finished by the recovery, not a second reviewer."""

    def test_an_unannounced_squash_is_recovered(self) -> None:
        # The squash lands and its collapse is recorded, and its notice is
        # refused: the write behind it retires the approval's verdict and
        # keeps the record the notice is worded from, and the label stays.
        # The next validating tick finishes that squash ahead of any reviewer
        # -- announcing it and handing the issue on.
        with patch.object(self.github, PR_COMMENT, _RefusesTheSquashNotice(self.github.pr_comment)):
            self.returns(_reusing(self), squash_result=_lands_a_collapse, **_disposed.ON_THE_HEAD)
        stopped = (
            self.waiting(),
            _collapses.LATE_COLLAPSE_HEAD in self.pinned(),
            tuple(self.github.label_history),
        )

        ran = self._run_validating(
            self.github, self.issue, run_agent=[], squash_result=_lands_a_collapse, **_disposed.ON_THE_HEAD,
        )

        notices = [body for _, body in self.github.posted_pr_comments if SQUASH_NOTICE in body]
        self.assertEqual(
            (stopped, ran[_world.RUN_AGENT].call_count, len(notices), self.github.label_history),
            ((None, True, ()), 0, 1, [DOCUMENTING]),
        )


if __name__ == "__main__":
    unittest.main()
