# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned approval acts only over settled, passing evidence that covers the configuration and stands.

An approval reaches the approval arc -- the verify gate, the approval record,
the squash -- only once the evidence it relies on is settled, passed, covers
every configured verification command, and is proved current; it parks for a
human otherwise, and a proof nobody could read holds it for a later tick. Each
request on the way is long enough for another road to push, settle a later
revision, or put a verdict of its own in place of this one: the approval then
moves nothing, parks nobody, and puts back nothing that road wrote.

The preparation the approval is acted on behind is in
`test_review_disposition.py`, the change request's handoff in
`test_review_verdict_handoffs.py`, and the parks' notices in
`test_review_verdict_parks.py`.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.verification.models import VerifyResult
from tests.workflow.fixtures import LABEL_DOCUMENTING
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

VERIFY = "_run_verify_commands"

SQUASH = "_squash_and_force_push"

REREAD = "reread_report_location"

ARTIFACT_REREAD = "reread_verification_artifact"

PR_COMMENT = "pr_comment"

ISSUE_COMMENT = "comment"

REVIEW_ROUND = "review_round"

UNVERIFIED = "reviewer_unverified"

DOCUMENTING = (_world.ISSUE, LABEL_DOCUMENTING)

APPROVED = "approved"

REQUESTED = "changes_requested"

# A reviewer approving over the evidence revision `digest` names, running
# nothing of its own, and one declaring nothing at all.
REUSING = "Covered.\n\nVERIFICATION: REUSED sha256:{digest}\n\nVERDICT: APPROVED"

UNDECLARED_APPROVAL = "LGTM\n\nVERDICT: APPROVED"

# An evidence digest nothing in the world names.
OTHER_DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

# What a park that did not land, and one an unverified approval landed, leave.
_NOT_PARKED = ((None, False), None, [])

_UNVERIFIED_PARK = ((UNVERIFIED, True), None, [UNVERIFIED])


def _reusing(case, named=None) -> str:
    """A reuse of the evidence an earlier round settles for `case`, or of the digest `named` beside it."""
    settled = _read.settles_evidence(case).content_revision
    return REUSING.format(digest=named or settled)


def _declaring(**declared):
    """A reply declaring one run as `declared` spells it, for a table of replies."""
    return lambda _case: _world.declared_run(**declared)


# Each approval returned, and where it ends up: every relabel, the park as
# `parked` reads it, the artifacts the pull request shows, the verify gate's
# runs, and a phrase the park's notice says. Only settled, passing, covering
# evidence reaches `documenting`, and a park names what refused it.
_APPROVALS = (
    ("its own passing run", _declaring(), ([DOCUMENTING], _NOT_PARKED, 1, 1, "")),
    ("a reuse of the handed evidence", _reusing, ([DOCUMENTING], _NOT_PARKED, 1, 1, "")),
    (
        "a reuse of other evidence",
        partial(_reusing, named=OTHER_DIGEST),
        ([], _UNVERIFIED_PARK, 1, 0, "evidence"),
    ),
    (
        "nothing declared",
        lambda _case: UNDECLARED_APPROVAL,
        ([], _UNVERIFIED_PARK, 0, 0, "declared no verification"),
    ),
    ("a failed run", _declaring(exit_status=1), ([], _UNVERIFIED_PARK, 1, 0, "did not exit 0")),
    (
        "another command",
        _declaring(command="uv run ruff check"),
        ([], _UNVERIFIED_PARK, 1, 0, "every command `VERIFY_COMMANDS`"),
    ),
    (
        "another head",
        lambda _case: _world.declared_run().replace(_world.HEAD, _world.OTHER_HEAD),
        ([], _UNVERIFIED_PARK, 0, 0, "names another commit"),
    ),
)

# Settled evidence a waiting approval's claim says passed and covers the
# configuration, and the words the park names what it really shows for.
_MISDESCRIBED = (
    ("a failed run", {"exit_status": 1}, "did not exit 0"),
    ("another command", {"command": "uv run ruff check"}, "every command `VERIFY_COMMANDS`"),
)

# An approval whose verify gate fails with another road's work landing during
# it, and what it leaves: the park as `parked` reads it, and the report
# revision and round. Only a subject still standing parks: a later report --
# spending its round -- evidence settling, or a push drops the verdict for a
# fresh reviewer, and a report nobody could read proves nothing and holds it.
_UNDER_A_FAILED_GATE = (
    ("nothing", None, ((("verify_failed", True), None, ["verify_failed"]), (1, 0))),
    ("a later report", _read.settles_a_later_report, (_NOT_PARKED, (2, 1))),
    ("an evidence settlement", _read.settles_evidence, (_NOT_PARKED, (1, 0))),
    ("a push", _world.pushes, (_NOT_PARKED, (1, 0))),
    ("an unread report", _world.stops_answering, (((None, False), APPROVED, []), (1, 0))),
)

# Where another road puts a later round's change request in place of the
# verdict this tick is acting on, spending a round beside it: the reply that
# earned this tick's verdict, the request behind which the other lands -- with
# which of those requests it is -- and how the tick runs. Behind the squash
# notice the approval is finishing a rewrite already made, and behind a failed
# squash's park notice, parking one that never went.
_REPLACED = (
    (
        "behind the approval comment",
        _reusing,
        (PR_COMMENT, _disposed.saying(_disposed.APPROVAL_NOTICE), 1),
        {},
    ),
    (
        "behind the feedback post",
        lambda _case: f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED",
        (PR_COMMENT, _disposed.saying(_disposed.FEEDBACK_NOTICE), 1),
        {},
    ),
    (
        "behind the park notice",
        lambda _case: UNDECLARED_APPROVAL,
        (ISSUE_COMMENT, _disposed.saying(_disposed.UNVERIFIED_NOTICE), 1),
        {},
    ),
    # The fourth artifact reread, behind the two the round's handover took and
    # the proof's own, is the approval's last before the comment is read again.
    ("behind the approval's proof", _reusing, (ARTIFACT_REREAD, bool, 4), {}),
    (
        "behind the squash notice",
        _reusing,
        (PR_COMMENT, _disposed.saying(_disposed.SQUASH_NOTICE), 1),
        {"squash_result": (True, _world.HEAD, 2, None)},
    ),
    (
        "behind the squash failure's notice",
        _reusing,
        (ISSUE_COMMENT, _disposed.saying(_disposed.SQUASH_FAILED_NOTICE), 1),
        {"squash_result": (False, None, 0, "force-push rejected")},
    ),
)


class DisposedApprovalTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """An approval reaches the approval arc over settled, passing, covering evidence, and parks otherwise."""

    def test_only_valid_evidence_reaches_the_arc(self) -> None:
        # Whichever way the approval ends, its verdict is retired by the
        # write that ends it, and only a park that lands is reported.
        for name, reply, expected in _APPROVALS:
            with self.subTest(name):
                self.setUp()

                ran = self.returns(reply(self))

                self.assertEqual(
                    (
                        self.github.label_history,
                        self.parked(),
                        len(_read.artifacts(self)),
                        ran[VERIFY].call_count,
                        expected[-1] in self.last_notice(),
                    ),
                    (*expected[:-1], True),
                )

    def test_a_claim_is_held_to_the_evidence_it_names(self) -> None:
        # The claim's flags are the verdict's copy of what the evidence said;
        # the approval rests on the evidence, which shows otherwise.
        for name, settled, refusal in _MISDESCRIBED:
            with self.subTest(name):
                self.setUp()
                _read.seeds_a_verdict(self, _read.settles_evidence(self, **settled))

                ran = self.finishes()

                self.assertEqual(
                    (
                        self.parked(),
                        ran[VERIFY].call_count,
                        ran[_world.RUN_AGENT].call_count,
                        self.github.label_history,
                        refusal in self.last_notice(),
                    ),
                    (_UNVERIFIED_PARK, 0, 0, [], True),
                )

    def test_a_held_publication_needs_no_reviewer(self) -> None:
        # The post lands and its response is lost: the tick holds with the
        # verdict and its transaction owed. The next tick's reconciliation
        # finds the artifact by its receipt, and the approval goes on from
        # the verdict the first tick wrote.
        self.github.report_failures.lost.add(_world.PR)
        self.returns(_world.declared_run())
        self.github.report_failures.lost.discard(_world.PR)
        spent = _read.spent(self)
        self.assertEqual((self.waiting(), self.github.label_history), (APPROVED, []))

        finished = self.finishes()

        self.assertEqual(
            (
                finished[_world.RUN_AGENT].call_count,
                _read.spent(self),
                len(_read.artifacts(self)),
                self.github.label_history,
                self.waiting(),
            ),
            (0, spent, 1, [DOCUMENTING], None),
        )

    def test_an_unread_proof_holds_the_approval(self) -> None:
        # The artifact the approval rests on cannot be read again: that is no
        # refusal, so nothing is verified, parked, or written, and the verdict
        # waits for a later tick, which proves it and hands the issue on.
        _read.seeds_a_verdict(self, _read.settles_evidence(self))
        before = self.pinned()

        with patch.object(self.github, "_verification_thread", side_effect=RuntimeError("unanswered")):
            held = self.finishes()

        self.assertEqual(
            (self.pinned(), held[VERIFY].call_count, self.github.posted_comments, self.github.label_history),
            (before, 0, [], []),
        )
        self.finishes()
        self.assertEqual(self.github.label_history, [DOCUMENTING])


class ApprovalRaceTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """An approval never writes back records another road wrote, nor acts or parks over a subject that moved."""

    def test_a_settlement_behind_the_verify_gate(self) -> None:
        # A later revision settles while the gate runs, or behind the subject
        # it resolves once the gate passes: the approval rests on evidence no
        # longer current, so the issue does not move on and nobody is asked,
        # and the newer records are kept rather than written back.
        for name, during in (("during the gate", True), ("behind its subject", False)):
            with self.subTest(name):
                self.setUp()
                self._verified = False
                behind = _world.AnotherRoadBehind(self, REREAD, self._after_the_gate, _read.settles_evidence)
                gate = partial(self._gate, road=_read.settles_evidence if during else None)

                with patch.object(self.github, REREAD, behind):
                    self.returns(_reusing(self), verify_result=gate)

                self.assertEqual(
                    (
                        self.github.label_history,
                        _read.current_evidence_revision(self),
                        self.pinned()["verification_evidence_revision"],
                        self.parked(),
                    ),
                    ([], 2, 2, _NOT_PARKED),
                )

    def test_a_failed_gate_parks_a_standing_subject(self) -> None:
        # A failure over a subject nobody reviewed is no failure of the
        # approval: it is dropped for a fresh reviewer rather than parked, and
        # a later report's round is kept. A report nobody could read behind
        # the gate proves nothing, so nothing parks and the verdict waits.
        for move, road, expected in _UNDER_A_FAILED_GATE:
            with self.subTest(move):
                self.setUp()
                gate = partial(self._gate, road=road, status="failed")

                self.returns(_reusing(self), verify_result=gate)

                self.assertEqual(
                    (
                        self.parked(),
                        (_read.current_report_revision(self), self.pinned().get(REVIEW_ROUND)),
                        self.github.label_history,
                    ),
                    (*expected, []),
                )

    def test_a_later_settlement_behind_the_proof(self) -> None:
        # A later revision settles behind the approval's last read of its
        # artifact: the approval is neither acted on nor parked -- a fresh
        # reviewer handed the newer evidence answers it -- and the newer
        # records are kept.
        message = _reusing(self)
        behind = _world.AnotherRoadBehind(self, ARTIFACT_REREAD, bool, _read.settles_evidence, 4)

        behind.returning(message)

        self.assertEqual(
            (self.github.label_history, _read.current_evidence_revision(self), self.parked()),
            ([], 2, _NOT_PARKED),
        )

    def test_a_settlement_behind_the_approval_comment(self) -> None:
        # Evidence settles while the approval comment is posted: no rewrite
        # goes out over it and nothing the approval holds is written but the
        # comment's own ledger entry. The next tick drops the verdict, whose
        # evidence the later revision superseded, rather than moving on.
        message = _reusing(self)
        behind = _world.AnotherRoadBehind(
            self, PR_COMMENT, _disposed.saying(_disposed.APPROVAL_NOTICE), _read.settles_evidence,
        )

        ran = behind.returning(message)

        approval = next(
            said.id for said in self.pull_request.issue_comments if _disposed.APPROVAL_NOTICE in said.body
        )
        self.assertEqual(
            (
                ran[SQUASH].call_count,
                _read.current_evidence_revision(self),
                self.waiting(),
                self.pinned().get("review_approved_subject"),
                approval in self.pinned()[_disposed.LEDGER],
            ),
            (0, 2, APPROVED, None, True),
        )

        self.finishes()

        self.assertEqual((self.parked(), self.github.label_history), (_NOT_PARKED, []))

    def _gate(self, *_args, road=None, status: str = "ok", **_kw) -> VerifyResult:
        """A verify gate answering `status`, during which `road` does another road's work, or behind which one may."""
        if road is None:
            self._verified = True
        else:
            road(self)
        return VerifyResult(status=status)

    def _after_the_gate(self, _location) -> bool:
        """Whether a reread is one behind a verify gate `_gate` answered with nobody else's work."""
        return self._verified


class ReplacedVerdictTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A verdict another road put in place of the one a tick is acting on is left standing."""

    def test_a_replaced_verdict_is_left_standing(self) -> None:
        # Whichever request that road lands behind, this tick squashes no
        # further, relabels, parks, or hands over nothing, and drops nothing
        # but its own verdict, so the other verdict and its round stand. What
        # it posted on the way is still recorded as the orchestrator's.
        for name, reply, behind, options in _REPLACED:
            with self.subTest(name):
                self.setUp()

                ran = _world.AnotherRoadBehind(
                    self, *behind[:2], self._replaces, behind[2],
                ).returning(reply(self), **options)

                self.assertEqual(
                    self._left(ran),
                    (
                        int("squash_result" in options),
                        (True, 1),
                        ((None, False), REQUESTED, []),
                        [],
                        True,
                    ),
                )

    def _replaces(self, _case) -> None:
        """Another road's write putting a later round's change request in place of the verdict, spending a round."""
        state = self.github.read_pinned_state(self.issue)
        self.replacement = {
            "round": 1,
            "verdict": REQUESTED,
            "subject": state.get("review_subject"),
            "feedback": "A later round's feedback.",
            "evidence": None,
            "handed": None,
        }
        state.set(_world.RETURNED_VERDICT, self.replacement)
        state.set(REVIEW_ROUND, 1)
        self.github.write_pinned_state(self.issue, state)

    def _left(self, ran) -> tuple:
        """The squashes taken, that road's verdict and round, the park, every relabel, and whether each post is ours."""
        standing = self.pinned()
        posted = {
            said.id
            for said in (*self.issue.comments, *self.pull_request.issue_comments)
            if any(notice in said.body for notice in _disposed.NOTICES)
        }
        return (
            ran[SQUASH].call_count,
            (standing[_world.RETURNED_VERDICT] == self.replacement, standing[REVIEW_ROUND]),
            self.parked(),
            self.github.label_history,
            posted <= set(standing[_disposed.LEDGER]),
        )


if __name__ == "__main__":
    unittest.main()
