# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A proved approval acts, parks, and retires its verdict only over the subject still standing behind each request.

The verify gate, the approval comment, the squash, and the park a failed gate
or squash takes are each long enough for another road to push, edit the issue,
settle a later report or evidence revision, or put another verdict in place of
the approval. Behind each, the subject is resolved again and the pinned comment
read last: a move acts on nothing and parks nobody, retires only the verdict
the approval held, and keeps what that road wrote; a subject nobody could read
keeps the verdict for a later tick. A failed gate or squash over the subject
still standing parks, behind a notice that was identified.

The proof that hands the approval on is in `test_unverified_approvals.py`.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.publication import models as _publication
from tests.workflow.fixtures import LABEL_DOCUMENTING
from tests.workflow.stages.validating import (
    approval_proof_test_support as _proof,
    review_park_test_support as _parked,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

SQUASH = "_squash_and_force_push"

PR_COMMENT = "pr_comment"

ISSUE_COMMENT = "comment"

REVIEW_ROUND = "review_round"

APPROVED = "approved"

REQUESTED = "changes_requested"

DOCUMENTING = (_world.ISSUE, LABEL_DOCUMENTING)

VERIFY_FAILED = "verify_failed"

SQUASH_FAILED = "squash_failed"

APPROVED_SUBJECT = "review_approved_subject"

# What a human edits the issue body to while a request is in flight.
_EDITED_BODY = "Also handle an empty configuration file."

# A squash that failed with the approved commits still on the branch.
_REFUSED_SQUASH = _publication._SquashOutcome(error="force-push rejected", standing=_publication.BRANCH_INTACT)

# A park that landed nowhere, with the verdict waiting as it is named -- or
# retired -- and nothing reported.
_NO_PARK = (None, False)

_NOT_PARKED = (_NO_PARK, None, [])

_PUSHED = "a push"

_UNREAD = "an unread report"

_DELETED_ARTIFACT = "a deleted artifact"

_UNREAD_ARTIFACT = "an unread artifact"


def _spends_a_round(case) -> None:
    """Another road's write of the next review round, which no verdict stands on."""
    state = case.github.read_pinned_state(case.issue)
    state.set(REVIEW_ROUND, state.get(REVIEW_ROUND) + 1)
    case.github.write_pinned_state(case.issue, state)


def _edits_the_issue(case) -> None:
    """A human editing the issue body, which moves the requirements the approval was of."""
    case.issue.body = _EDITED_BODY


def _replaces(case) -> None:
    """Another road putting a later round's change request in place of the approval."""
    later = dict(case.pinned()[_world.RETURNED_VERDICT], round=1, verdict=REQUESTED)
    later["feedback"] = _world.REQUESTED
    _parked.replaces_the_verdict(case, later)


# What another road does while the verify gate runs, and what the approval
# leaves behind a gate that failed: the park, the verdict waiting, and every
# park reported. Only a subject still standing is parked -- or, behind a gate
# that passed, acted on, reaching `documenting` with nothing parked -- and its
# verdict retired by the write that does it; a later report, evidence
# settling, or a push drops the verdict for a fresh reviewer, a verdict put in
# its place is that road's and stays, and a report nobody could read proves
# nothing and keeps the verdict. The evidence's artifact is proved again too,
# since the pull request can move it where no record shows: one deleted
# drops the verdict, and one nobody could read keeps it. Behind a passing gate
# each of those leaves what it leaves behind a failed one.
_DURING_THE_GATE = (
    ("nothing", None, ((VERIFY_FAILED, True), None, [VERIFY_FAILED])),
    ("a later report", _read.settles_a_later_report, _NOT_PARKED),
    ("an evidence settlement", _read.settles_evidence, _NOT_PARKED),
    (_PUSHED, _world.pushes, _NOT_PARKED),
    ("a replaced verdict", _replaces, (_NO_PARK, REQUESTED, [])),
    (_UNREAD, _world.stops_answering, (_NO_PARK, APPROVED, [])),
    (_DELETED_ARTIFACT, _proof.deletes_the_artifact, _NOT_PARKED),
    (_UNREAD_ARTIFACT, _proof.stops_reading_the_artifact, (_NO_PARK, APPROVED, [])),
)



def _behind(verified, rows) -> tuple:
    """Each of `rows` behind a gate answering `verified`, relabeling nothing."""
    behind = []
    for move, road, left in rows:
        behind.append((move, road, verified, (left, [])))
    return tuple(behind)


# Each of those behind a gate that passed and one that failed, and what the
# approval leaves: the park as `parked` reads it, and every relabel.
_GATES = (
    ("nothing", None, _proof.PASSED_GATE, (_NOT_PARKED, [DOCUMENTING])),
    *_behind(_proof.PASSED_GATE, _DURING_THE_GATE[1:]),
    *_behind(_proof.FAILED_GATE, _DURING_THE_GATE),
)

# What another road does while the approval comment is posted, and the verdict
# it leaves waiting: a push, an edit, evidence settling, or its artifact
# deleted there is work nobody reviewed -- or evidence that no longer proves --
# and retires the approval's verdict, a verdict put in its place stays, and a
# subject or artifact nobody could read keeps the approval's.
_BEHIND_THE_APPROVAL = (
    (_PUSHED, _world.pushes, None),
    ("an edit of the issue", _edits_the_issue, None),
    ("an evidence settlement", _read.settles_evidence, None),
    (_DELETED_ARTIFACT, _proof.deletes_the_artifact, None),
    ("a replaced verdict", _replaces, REQUESTED),
    (_UNREAD, _world.stops_answering, APPROVED),
    (_UNREAD_ARTIFACT, _proof.stops_reading_the_artifact, APPROVED),
)

# What another road does behind a failed squash's park notice, and what the
# approval leaves: the park, the verdict waiting, and every park reported.
# Only the subject still standing parks, and a later report or a push drops
# the verdict; a report nobody could read parks nobody and keeps it.
_BEHIND_THE_SQUASH_PARK = (
    ("nothing", lambda _case: None, ((SQUASH_FAILED, True), None, [SQUASH_FAILED])),
    ("a later report", _read.settles_a_later_report, _NOT_PARKED),
    (_PUSHED, _world.pushes, _NOT_PARKED),
    (_UNREAD, _world.stops_answering, (_NO_PARK, APPROVED, [])),
)

# What the later report another road settles during a gate leaves, and the
# later evidence revision: the report revision and the round it spent, and the
# evidence revision current.
_KEPT_REPORT = (2, 1)

_KEPT_EVIDENCE = 2

# What the comment keeps of another road's write during the gate, whichever way
# the gate answered, read off the case, beside what it has to be: the reading
# behind the gate carries each onto the state before anything is written.
_KEPT_DURING_THE_GATE = MappingProxyType({
    "a later report": (
        lambda case: (_read.current_report_revision(case), case.pinned()[REVIEW_ROUND]),
        _KEPT_REPORT,
    ),
    "an evidence settlement": (_read.current_evidence_revision, _KEPT_EVIDENCE),
})


class GateRaceTest(_proof.ApprovedVerdictWorld, unittest.TestCase):
    """What lands while the verify gate runs decides whether the approval is acted on or parked."""

    def test_only_a_standing_subject_acts_or_parks(self) -> None:
        # And whatever the other road wrote is kept, whichever way the gate
        # answered: a later report and the round it spent, or a later
        # evidence revision.
        for move, road, verified, expected in _GATES:
            with self.subTest(move, status=verified.status):
                self.setUp()
                self.waits_on_settled_evidence()

                self.approves(verify_result=_proof.DuringTheGate(self, road, verified))

                self.assertEqual((self.parked(), self.github.label_history), expected)
                self.assertEqual(*self._kept_during_the_gate(move))

    def test_a_gate_park_needs_an_identified_notice(self) -> None:
        # The gate's park goes through the funnel every park of a reviewed
        # subject takes: behind a push landing while its notice is posted it
        # lands nowhere and drops the verdict, and behind a notice GitHub took
        # without an id it lands nowhere and keeps the verdict.
        noticed = _proof.saying(_proof.VERIFY_NOTICE)
        behind = (
            (_PUSHED, lambda: _world.AnotherRoadBehind(self, ISSUE_COMMENT, noticed, _world.pushes), None),
            ("no id", lambda: _parked.LeavesNoId(self.github.comment, _proof.VERIFY_NOTICE), APPROVED),
        )
        for name, posts, waiting in behind:
            with self.subTest(name):
                self.setUp()
                self.waits_on_settled_evidence()

                with patch.object(self.github, ISSUE_COMMENT, posts()):
                    self.approves(verify_result=_proof.FAILED_GATE)

                self.assertEqual(self.parked(), (_NO_PARK, waiting, []))

    def _kept_during_the_gate(self, move: str) -> tuple:
        """What the comment keeps of `move`'s write during the gate, and what it has to; None twice where unchecked."""
        reads, kept = _KEPT_DURING_THE_GATE.get(move, (lambda _case: None, None))
        return reads(self), kept


class ApprovalCommentRaceTest(_proof.ApprovedVerdictWorld, unittest.TestCase):
    """What lands while the approval comment is posted decides whether the squash goes out."""

    def test_a_moved_subject_squashes_nothing(self) -> None:
        # No rewrite goes out and no approval is recorded; the approval comment
        # stays the orchestrator's on the ledger whichever way the verdict went.
        for move, road, waiting in _BEHIND_THE_APPROVAL:
            with self.subTest(move):
                self.setUp()
                self.waits_on_settled_evidence()
                behind = _world.AnotherRoadBehind(self, PR_COMMENT, _proof.saying(_proof.APPROVAL_NOTICE), road)

                with patch.object(self.github, PR_COMMENT, behind):
                    ran = self.approves()

                self.assertEqual(
                    (
                        ran[SQUASH].call_count,
                        self.github.label_history,
                        self.waiting(),
                        self.pinned().get(APPROVED_SUBJECT),
                        self._approval_is_ours(),
                    ),
                    (0, [], waiting, None, True),
                )

    def test_rounds_spent_around_the_gate_are_kept(self) -> None:
        # Another road spends a round while the verify gate runs, and another
        # while the approval comment is posted: each reading carries it onto
        # the state, so the later round is kept rather than written back over
        # by the one before it -- and the approval still reaches `documenting`.
        self.waits_on_settled_evidence()
        behind = _world.AnotherRoadBehind(self, PR_COMMENT, _proof.saying(_proof.APPROVAL_NOTICE), _spends_a_round)
        gate = _proof.DuringTheGate(self, _spends_a_round, _proof.PASSED_GATE)

        with patch.object(self.github, PR_COMMENT, behind):
            self.approves(verify_result=gate)

        round_n = self.pinned()[REVIEW_ROUND]
        self.assertEqual((self.github.label_history, round_n), ([DOCUMENTING], 2))
        self.assertIsNone(self.waiting())

    def _approval_is_ours(self) -> bool:
        """Whether the approval comment on the pull request is on the ledger of the orchestrator's own."""
        posted = [said.id for said in self.pull_request.issue_comments if _proof.APPROVAL_NOTICE in said.body]
        return posted[0] in self.pinned()[_proof.LEDGER]


class SquashParkTest(_proof.ApprovedVerdictWorld, unittest.TestCase):
    """A failed squash parks through `review_parks`, over the approved subject standing behind its notice."""

    def test_a_squash_park_needs_the_subject_standing(self) -> None:
        noticed = _proof.saying(_proof.SQUASH_FAILED_NOTICE)
        for move, road, expected in _BEHIND_THE_SQUASH_PARK:
            with self.subTest(move):
                self.setUp()
                self.waits_on_settled_evidence()
                behind = _world.AnotherRoadBehind(self, ISSUE_COMMENT, noticed, road)

                with patch.object(self.github, ISSUE_COMMENT, behind):
                    self.approves(squash_result=_REFUSED_SQUASH)

                self.assertEqual((self.parked(), self.github.label_history), (expected, []))

    def test_a_squash_park_needs_an_identified_notice(self) -> None:
        # The squash's park lands only behind a notice GitHub answered with
        # an id: behind one taken without, no park is recorded or reported,
        # nothing is relabeled, and the approval's verdict keeps waiting for
        # a later tick to answer.
        self.waits_on_settled_evidence()
        posts = _parked.LeavesNoId(self.github.comment, _proof.SQUASH_FAILED_NOTICE)

        with patch.object(self.github, ISSUE_COMMENT, posts):
            self.approves(squash_result=_REFUSED_SQUASH)

        self.assertEqual(self.parked(), (_NO_PARK, APPROVED, []))
        self.assertEqual(self.github.label_history, [])

    def test_moved_evidence_records_only_the_notice(self) -> None:
        # A later revision settles while the park's notice is posted: nothing
        # the approval holds is written over it -- no park -- but the notice
        # stays the orchestrator's on the ledger and the verdict, resting on
        # the evidence that moved, is retired.
        self.waits_on_settled_evidence()
        behind = _world.AnotherRoadBehind(
            self, ISSUE_COMMENT, _proof.saying(_proof.SQUASH_FAILED_NOTICE), _read.settles_evidence,
        )

        with patch.object(self.github, ISSUE_COMMENT, behind):
            self.approves(squash_result=_REFUSED_SQUASH)

        notice = self.issue.comments[-1]
        self.assertEqual(
            (
                self.parked(),
                _read.current_evidence_revision(self),
                notice.id in self.pinned()[_proof.LEDGER],
                _proof.SQUASH_FAILED_NOTICE in notice.body,
            ),
            (_NOT_PARKED, _KEPT_EVIDENCE, True, True),
        )


if __name__ == "__main__":
    unittest.main()
