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

Each write the arc makes lands as a guarded commit over the comment read
afresh: a record it was decided on that another road moves right ahead of the
handoff's write -- or a comment that will not parse, was replaced, or has no
room for the write -- refuses it, and the label is not moved over it, while
another road's independent bookkeeping is kept beside the handoff. A handoff
write whose response is lost moves nothing that tick, and the next tick moves
the label alone, with no second reviewer, gate, squash, or approval comment.

The proof that hands the approval on is in `test_unverified_approvals.py`.
"""
from __future__ import annotations

import itertools
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.publication import models as _publication
from orchestrator.workflow.late_split import collapses as _collapses, handoffs as _late_handoffs
from tests.workflow.fixtures import LABEL_DOCUMENTING
from tests.workflow.stages.validating import (
    approval_commit_test_support as _one,
    approval_proof_test_support as _proof,
    review_park_test_support as _parked,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    review_write_test_support as _roads,
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

# Each of those behind a gate that passed and one that failed, and what the
# approval leaves: the park as `parked` reads it, and every relabel -- none
# but the one a standing subject behind a passing gate earns.
_BEHIND_EACH_GATE = (
    (_proof.PASSED_GATE, _DURING_THE_GATE[1:]),
    (_proof.FAILED_GATE, _DURING_THE_GATE),
)

_GATES = (
    ("nothing", None, _proof.PASSED_GATE, (_NOT_PARKED, [DOCUMENTING])),
    *(
        (move, road, verified, (left, []))
        for verified, rows in _BEHIND_EACH_GATE
        for move, road, left in rows
    ),
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

# The record the handoff's write leaves of the commit its relabel is owed over,
# which that write alone stages.
HANDOFF = _late_handoffs.LATE_COLLAPSE_HANDOFF

TOKENS = "issue_total_tokens"

THEIR_NOTE = "another_road_note"

# Another road's own records, which no write of the arc owns: a usage total it
# folded, and a note nothing here reads.
_THEIR_BOOKS = MappingProxyType({TOKENS: 5_000, THEIR_NOTE: "kept"})

_KEEPS_BOOKS = _roads.Writes(_THEIR_BOOKS)

# Which guarded commit is which, by what it stages: the handoff's write, which
# alone records the commit its relabel is owed over; the write retiring the
# approval's verdict; and the park a failed squash takes.
_THE_HANDOFF = _one.staging(HANDOFF)

_THE_RETIREMENT = _one.staging(_world.RETURNED_VERDICT, None)

_THE_SQUASH_PARK = _one.staging("park_reason", SQUASH_FAILED)


# Another road's park, its record of a squash, and a developer report it
# records as owed: records the tail reads and ends, or that a review subject
# stands only without, which no reading of the tail's carried.
_PARKS = _roads.Writes({"awaiting_human": True, "park_reason": VERIFY_FAILED})

_COLLAPSES = _roads.Writes({
    _collapses.LATE_COLLAPSE_HEAD: "aa11bb22" * 5,
    _collapses.LATE_COLLAPSE_BASE_SHA: "cc33dd44" * 5,
    _collapses.LATE_COLLAPSE_COUNT: 3,
})

_OWES_A_REPORT = _roads.Writes({"developer_report_owed": True})

# Another road's write right ahead of the handoff's commit that refuses it: a
# record that commit was decided on moved -- a later report, a later evidence
# revision, a replaced verdict, the issue repointed, a report owed, a park or
# a collapse recorded -- or the comment unparsed, replaced, or filled to its
# limit. Nothing records the approval or its handoff, and the label is not
# moved. Where a record the comment still parses with moved, what the arc
# posted is recorded over what that road left -- the approval comment on the
# ledger -- and where it is one the approval was proved over, the report debt
# among them, the approval's verdict is retired for a fresh reviewer, as behind
# any request of the arc; a verdict that road put in its place stays. A park or
# a collapse keeps the approval waiting, and so does anything else.
_AHEAD_OF_THE_HANDOFF = (
    ("a later report settled", _read.settles_a_later_report, (None, True)),
    ("a later evidence revision", _read.settles_evidence, (None, True)),
    ("a replaced verdict", _replaces, (REQUESTED, True)),
    ("a repointed pull request", _parked.repoints, (None, True)),
    ("a report owed", _OWES_A_REPORT, (None, True)),
    ("a park recorded", _PARKS, (APPROVED, True)),
    ("a collapse recorded", _COLLAPSES, (APPROVED, True)),
    ("an unparsed comment", _roads.unparses, (None, False)),
    ("a replaced comment", _roads.repins, (APPROVED, False)),
    ("a full comment", lambda case: _parked.fills_to(case, 0), (APPROVED, False)),
)

# The same park, collapse, and report debt written while a request of the tail
# is out instead -- the verify gate, or the squash -- with the verdict each
# leaves waiting: a park or a collapse keeps it, and a report owed retires it.
_DURING_A_REQUEST = (
    ("a park", _PARKS, APPROVED),
    ("a collapse record", _COLLAPSES, APPROVED),
    ("a report owed", _OWES_A_REPORT, None),
)

# Each request, the seam it is made through, and what that seam answers.
_REQUESTS = MappingProxyType({
    "the verify gate": ("verify_result", _proof.PASSED_GATE),
    "the squash": ("squash_result", _publication._SquashOutcome(success=True)),
})

# The seams a tick runs an agent, a verify gate, and a squash through.
_RUNS = (_world.RUN_AGENT, "_run_verify_commands", SQUASH)

# Two roads another road takes right ahead of the failed squash's park commit.
_LATER = "a later report ahead of the park"

_BOOKS = "its own books"

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

    def test_a_verdict_put_ahead_of_retiring_stays(self) -> None:
        # A push during the gate moves the subject, and another road puts a
        # later round's verdict in the approval's place right ahead of the
        # commit retiring it: that commit is refused rather than written over
        # the other road's verdict, which stays waiting, and nothing parks or
        # moves.
        self.waits_on_settled_evidence()
        gate = _proof.DuringTheGate(self, _world.pushes, _proof.PASSED_GATE)

        with _roads.AnotherRoadAhead(self, _THE_RETIREMENT, _replaces).patched():
            self.approves(verify_result=gate)

        self.assertEqual(
            (self.parked(), self.github.label_history), ((_NO_PARK, REQUESTED, []), []),
        )

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

    def test_a_write_right_ahead_of_the_park_commit(self) -> None:
        # Another road writes after the park's last reading and before its
        # commit. A later report refuses the park -- nothing parks or is
        # reported, the notice is recorded as the orchestrator's, and the
        # verdict resting on the report that moved is retired -- while a run
        # it folded and a note of its own are kept beside the park.
        for name, road, expected, kept in (
            (_LATER, _read.settles_a_later_report, _NOT_PARKED, (2, None)),
            (_BOOKS, _KEEPS_BOOKS, ((SQUASH_FAILED, True), None, [SQUASH_FAILED]), (1, "kept")),
        ):
            with self.subTest(name):
                self.setUp()
                self.waits_on_settled_evidence()

                with _roads.AnotherRoadAhead(self, _THE_SQUASH_PARK, road).patched():
                    self.approves(squash_result=_REFUSED_SQUASH)

                pinned = self.pinned()
                self.assertEqual(
                    (
                        self.parked(),
                        (_read.current_report_revision(self), pinned.get(THEIR_NOTE)),
                        self.issue.comments[-1].id in pinned[_proof.LEDGER],
                    ),
                    (expected, kept, True),
                )

    def test_a_lost_park_write_is_not_mentioned_again(self) -> None:
        # The park's commit lands and its response is lost: the park is on the
        # comment, but nothing reports a human wait behind a write nobody
        # confirmed. The next tick reads the park standing and asks nobody
        # again: no notice, no reviewer, no report.
        self.waits_on_settled_evidence()

        with _one.LosesOneResponse(self, _THE_SQUASH_PARK).patched():
            self.approves(squash_result=_REFUSED_SQUASH)
        parked = self.parked()
        mentioned = len(self.issue.comments)
        ran = self._run_validating(
            self.github, self.issue, run_agent=[], head_shas=(_world.HEAD,),
        )

        self.assertEqual(parked, ((SQUASH_FAILED, True), None, []))
        self.assertEqual(
            (self.parked(), len(self.issue.comments), ran[_world.RUN_AGENT].call_count),
            (parked, mentioned, 0),
        )


class HandoffWriteRaceTest(_proof.ApprovedVerdictWorld, unittest.TestCase):
    """The handoff's guarded write, and another road's write right ahead of it."""

    def test_a_move_ahead_of_the_handoff_refuses_it(self) -> None:
        for move, road, waiting in _AHEAD_OF_THE_HANDOFF:
            with self.subTest(move):
                self.setUp()
                self.waits_on_settled_evidence()

                with _roads.AnotherRoadAhead(self, _THE_HANDOFF, road).patched():
                    self.approves()

                pinned = self.pinned()
                self.assertEqual(
                    (
                        self.github.label_history,
                        (self.waiting(), self._approval_recorded_as_ours()),
                        pinned.get(APPROVED_SUBJECT),
                        HANDOFF in pinned,
                    ),
                    ([], waiting, None, False),
                )

    def test_independent_bookkeeping_is_kept(self) -> None:
        # Another road folds a run and leaves a note of its own right ahead of
        # the handoff's commit: the handoff lands beside both, and the label
        # moves over it.
        self.waits_on_settled_evidence()

        with _roads.AnotherRoadAhead(self, _THE_HANDOFF, _KEEPS_BOOKS).patched():
            self.approves()

        pinned = self.pinned()
        self.assertEqual(
            (
                self.github.label_history,
                self.waiting(),
                pinned.get(APPROVED_SUBJECT) is not None,
                {field: pinned.get(field) for field in _THEIR_BOOKS},
                HANDOFF in pinned,
            ),
            ([DOCUMENTING], None, True, dict(_THEIR_BOOKS), False),
        )

    def test_a_lost_handoff_moves_the_label_alone(self) -> None:
        # The handoff's write lands and its response is lost: nothing behind it
        # is acted on, so the label stays. The record it left says the move is
        # owed, and the next tick moves the label alone -- no reviewer, no
        # gate, no squash, no second approval comment, nothing more spent --
        # and ends that record behind it.
        self.waits_on_settled_evidence()
        self.github.pinned_failures.lost.add(_world.ISSUE)
        self.approves()
        self.github.pinned_failures.lost.discard(_world.ISSUE)
        recorded = self.pinned()
        relabeled = list(self.github.label_history)
        before = (len(self.pull_request.issue_comments), _read.spent(self))

        ran = self._run_validating(
            self.github, self.issue, run_agent=[], head_shas=(_world.HEAD,),
        )

        self.assertEqual(
            (recorded.get(HANDOFF), recorded.get(_world.RETURNED_VERDICT), relabeled),
            (_world.HEAD, None, []),
        )
        self.assertEqual(
            (
                [ran[seam].call_count for seam in _RUNS],
                (len(self.pull_request.issue_comments), _read.spent(self)),
                self.github.label_history,
                HANDOFF in self.pinned(),
            ),
            ([0, 0, 0], before, [DOCUMENTING], False),
        )

    def test_a_move_during_a_request_holds_the_tail(self) -> None:
        # Another road parks the issue, records a squash on it, or records a
        # developer report as owed while the verify gate runs or the squash
        # does. None is laid over the state in hand and cleared or ended by a
        # write behind it: the label stays, nothing records the approval or
        # its handoff, that road's record stands as it wrote it, and the
        # approval waits for a later tick -- save behind a report owed, a debt
        # its review subject stands only without, which retires it.
        for (move, road, waiting), request in itertools.product(_DURING_A_REQUEST, _REQUESTS):
            with self.subTest(move, request=request):
                self.setUp()
                self.waits_on_settled_evidence()

                self._moves_during(request, road)

                pinned = self.pinned()
                self.assertEqual(
                    (
                        self.github.label_history,
                        self.waiting(),
                        (pinned.get(APPROVED_SUBJECT), HANDOFF in pinned),
                        {field: pinned.get(field) for field in road.fields},
                    ),
                    ([], waiting, (None, False), dict(road.fields)),
                )

    def _moves_during(self, request: str, road) -> None:
        """One approval tick, `road` doing another road's work while `request` is out."""
        seam, answered = _REQUESTS[request]
        self.approves(**{seam: _proof.DuringTheGate(self, road, answered)})

    def _approval_recorded_as_ours(self) -> bool:
        """Whether the pinned ledger of the orchestrator's own comments names the approval comment."""
        posted = [said.id for said in self.pull_request.issue_comments if _proof.APPROVAL_NOTICE in said.body]
        return posted[0] in self.pinned().get(_proof.LEDGER, [])


if __name__ == "__main__":
    unittest.main()
