# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A refused reviewer verdict parks only over the subject standing behind an identified notice, in a write that fits.

An approval that relies on no valid evidence parks under `reviewer_unverified`,
and a verdict the pinned comment could not persist under `reviewer_unrecorded`.
Each is measured at its own write before its notice is posted: taken over the
comment as it stands where it has no room beside what the returned run staged
-- only while that reading carries what the verdict stands on -- and posted on
and written to not at all where there is room for no park. Behind the notice
the subject is resolved again and the comment read last: a push, a repoint, a
later report, evidence, or a verdict another road put there lands no park and
drops only the verdict held, whether or not the notice was identified, while --
where nothing moved -- a subject nobody could read, or a notice nothing
identified, keeps it waiting in a write measured there. The park's write keeps
what another road wrote behind the notice, and is measured again with it. Only
a park that lands reports the wait, and only once its write is down.
"""
from __future__ import annotations

import unittest
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.validating import review_parks as _parks, review_verdicts as _verdicts
from tests.workflow.stages.validating import (
    review_park_test_support as _parked,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

UNVERIFIED = _parked.UNVERIFIED

UNRECORDED = _parked.UNRECORDED

APPROVED = "approved"

REQUESTED = "changes_requested"

REVIEW_ROUND = "review_round"

LAST_ACTION = _parked.LAST_ACTION

LEDGER = _comments._ORCH_COMMENT_IDS

# Where the pinned comment records the reviewer session a round ran, and the
# usage it folded.
LAST_REVIEW_SESSION = "last_review_session_id"

TOKENS = "issue_total_tokens"

# A park no agent's run owes, which the funnel files as well.
_AGENTLESS = "verify_failed"

# What a comment a few characters short of its ceiling has left: fewer than a
# park's flags take, or its notice's ledger entry.
_SPARE = 8

# What a comment with room for a park and not for the returned run's records
# beside it has left: those records take several times that, and the park --
# its flags, and the notice's ledger entry and watermark at their widest --
# well under it.
_ROOM_FOR_THE_PARK_ALONE = 400

# Each park a verdict takes.
_PARKS = (UNVERIFIED, UNRECORDED)

# Each park, a refusal it answers, and whether its notice asks for room on the
# pinned comment: only where room is what refused the verdict, since a verdict
# in words no record can carry is written again by the fresh reviewer alone.
_CAUSES = (
    (UNVERIFIED, _parked.REFUSAL, False),
    (UNRECORDED, _parks.NO_ROOM, True),
    (UNRECORDED, _parks.UNREADABLE, False),
)

# What a notice asking for room on the pinned comment says.
_FREE_ROOM = "free room on the pinned comment"

# What a park that lands reports beside its reason.
_REPORTED = MappingProxyType({
    "stage": "validating",
    "agent_role": "reviewer",
    "session_id": _world.REVIEWER_SESSION,
    "review_round": 0,
    "pr_number": _world.PR,
})

# The verdict each park holds, which it leaves waiting where nothing proves its
# subject moved: an approval, and -- for a verdict nothing could record -- none
# on the comment at all.
_HELD = MappingProxyType({UNVERIFIED: APPROVED, UNRECORDED: None})

# A move behind which whichever verdict the park held stays waiting.
_KEPT = object()

# A verdict record no reader takes -- a hand edit's, or another road's in a
# shape this reader refuses -- long enough that dropping it would free more
# room than a park takes. What it says is what `parked` reads back of it.
_UNREADABLE_RECORD = MappingProxyType({"verdict": "unsure", "feedback": "?" * _ROOM_FOR_THE_PARK_ALONE})

_UNSURE = "unsure"

# What another road does behind a park's notice, the verdict it leaves
# waiting, and the report revision and round the pinned comment records then:
# a later report -- spending its round -- evidence settling, a push, or a
# repoint proves what the verdict was decided over moved, and drops the verdict
# held; a verdict put in its place is that road's and stays, as written -- one
# no reader takes as surely as one it does, which a park holding no verdict
# never reads as the none it holds; and a report nobody could read proves
# nothing either way, and keeps the one held.
_MOVES = (
    ("a later report", _read.settles_a_later_report, None, (2, 1)),
    ("an evidence settlement", _read.settles_evidence, None, (1, 0)),
    ("a push", _world.pushes, None, (1, 0)),
    ("a repoint", _parked.repoints, None, (1, 0)),
    ("a replaced verdict", _parked.replaces_the_verdict, REQUESTED, (1, 0)),
    ("an unreadable verdict", partial(_parked.replaces_the_verdict, record=dict(_UNREADABLE_RECORD)), _UNSURE, (1, 0)),
    ("an unread report", _world.stops_answering, _KEPT, (1, 0)),
)

# Each park with each move behind its notice, and what it leaves: the park as
# `parked` reads it -- none landed, and none reported -- and the report
# revision and round.
_BEHIND_THE_NOTICE = tuple(
    (
        f"{reason} behind {move}",
        reason,
        road,
        (((None, False), held if waiting is _KEPT else waiting, []), recorded),
    )
    for reason, held in _HELD.items()
    for move, road, waiting, recorded in _MOVES
)

# The round another road spends behind a notice, and the tokens its own run
# folds: fields no verdict stands on.
_SPENT_ROUND = 7

_THEIR_TOKENS = 100

# What every park's notice says buys a fresh reviewer.
_RETRY = "/orchestrator continue"


def _unreadable(case) -> None:
    """`case`'s pinned comment stops answering its readers, until `_answers_again`."""
    case.github.read_pinned_state = _refuses


def _answers_again(case) -> None:
    """`case`'s pinned comment answers its readers, whether or not it stopped."""
    case.github.__dict__.pop("read_pinned_state", None)


def _refuses(_issue):
    raise RuntimeError("GitHub did not answer")


class ParkLandsTest(_parked.ParkedVerdictWorld, unittest.TestCase):
    """A refused verdict of the subject still standing parks, and reports the wait it asks for."""

    def test_each_park_lands_and_reports_its_wait(self) -> None:
        # The notice mentions a human, says why, asks for room on the pinned
        # comment only where room refused the verdict, and says what buys a
        # fresh reviewer; the park drops the verdict it refuses, keeps what the
        # run staged -- the reviewer's session and usage -- records its notice
        # as the orchestrator's and the thread read through it, and reports
        # the wait with the round, session, and pull request it ran for.
        for reason, why, asks_for_room in _CAUSES:
            with self.subTest(reason=reason, why=why):
                self.setUp()
                self.awaits(reason)

                self.parks(reason, why=why)

                pinned = self.pinned()
                notice = self.issue.comments[-1]
                self.assertEqual(
                    (
                        self.parked(),
                        [said for said in (config.HITL_MENTIONS, why, _RETRY) if said not in notice.body],
                        _FREE_ROOM in notice.body,
                        (pinned[LAST_REVIEW_SESSION], pinned[TOKENS]),
                        (pinned[LAST_ACTION], notice.id in pinned[LEDGER]),
                        _parked.reported(self),
                    ),
                    (
                        ((reason, True), None, [reason]),
                        [],
                        asks_for_room,
                        (_world.REVIEWER_SESSION, _world.REVIEWER_TOKENS),
                        (notice.id, True),
                        [dict(_REPORTED, reason=reason)],
                    ),
                )

    def test_a_park_of_no_agent_reports_its_reason(self) -> None:
        # The funnel files a park no agent's run owes as well, reported by its
        # reason alone.
        self.awaits(UNVERIFIED)

        self._run(self._files_an_agentless_park, run_agent=[])

        self.assertEqual(
            (self.parked(), _parked.reported(self)),
            (((_AGENTLESS, True), None, [_AGENTLESS]), [{"stage": "validating", "reason": _AGENTLESS}]),
        )

    def test_an_approval_park_holds_only_its_own(self) -> None:
        # The verdict waiting is a later round's approval, not the one the run
        # returned: it is not this park's to refuse or drop, so nothing is
        # posted, written, or reported, and that verdict waits as it was.
        self.awaits(UNVERIFIED)
        state = self.github.read_pinned_state(self.issue)
        later = dict(state.get(_verdicts.RETURNED_VERDICT), round=1)
        _parked.replaces_the_verdict(self, later)
        before = (self.pinned(), len(self.github.posted_comments))

        self.parks(UNVERIFIED)

        self.assertEqual(
            ((self.pinned(), len(self.github.posted_comments)), self.parked()),
            (before, ((None, False), APPROVED, [])),
        )

    def _files_an_agentless_park(self) -> None:
        state = self.github.read_pinned_state(self.issue)
        run = _world.returned_run(self, state, "LGTM\n\nVERDICT: APPROVED")
        held = _verdicts.read_returned_verdict(state)
        _parks.parks_over_the_subject(
            self.github, self.issue, state, run, (_AGENTLESS, "local verification failed.", None, held),
        )


class ParkRoomTest(_parked.ParkedVerdictWorld, unittest.TestCase):
    """A park is measured before its notice, and posted on and written to not at all where it cannot land."""

    def test_a_full_comment_parks_what_it_carries(self) -> None:
        # No room beside what the returned run staged, and room for the park
        # alone: the park is taken over the comment as it stands, the run's
        # session and usage unrecorded, and reports the reviewer it parked.
        _parked.fills_to(self, _ROOM_FOR_THE_PARK_ALONE)

        self.parks(UNRECORDED)

        unrecorded = tuple(map(self.pinned().get, (LAST_REVIEW_SESSION, TOKENS)))
        self.assertEqual(
            (self.parked(), unrecorded, _parked.reported(self)),
            (
                ((UNRECORDED, True), None, [UNRECORDED]),
                (None, None),
                [dict(_REPORTED, reason=UNRECORDED)],
            ),
        )

    def test_no_room_even_for_the_park_writes_nothing(self) -> None:
        # A comment a few characters short of its ceiling, with no waiting
        # verdict whose drop frees room, has none for the park: a notice
        # posted over a write GitHub then refuses would leave no park durable,
        # and the next tick's reviewer would answer the round again. A record
        # no reader takes is no verdict the park holds, so it is measured as
        # staying where it is rather than as room to spend.
        for leftover in (None, _UNREADABLE_RECORD):
            with self.subTest(leftover=leftover is not None):
                self.setUp()
                if leftover is not None:
                    _parked.replaces_the_verdict(self, dict(leftover))
                _parked.fills_to(self, _SPARE)
                before = (self.pinned(), len(self.issue.comments))

                self.parks(UNRECORDED)

                self.assertEqual(
                    ((self.pinned(), len(self.issue.comments)), _parked.reported(self)),
                    (before, []),
                )

    def test_an_unrecorded_park_drops_no_verdict(self) -> None:
        # A verdict the comment has waiting is no verdict an unrecorded park
        # holds: with room, the park lands and leaves that approval waiting;
        # a few characters short of the ceiling, the approval is no room to
        # spend either, so nothing is posted or written.
        for spare, expected in (
            (_ROOM_FOR_THE_PARK_ALONE * 3, (((UNRECORDED, True), APPROVED, [UNRECORDED]), 1)),
            (_SPARE, (((None, False), APPROVED, []), 0)),
        ):
            with self.subTest(spare=spare):
                self.setUp()
                self.awaits(UNVERIFIED)
                _parked.fills_to(self, spare)
                posted = len(self.github.posted_comments)

                self.parks(UNRECORDED)

                notices = len(self.github.posted_comments) - posted
                self.assertEqual((self.parked(), notices), expected)

    def test_a_park_is_measured_by_its_own_write(self) -> None:
        # A waiting approval on a comment a few characters short of its
        # ceiling. The write keeping that verdict beside the notice's ledger
        # entry has no room, and is asked only where nothing behind the notice
        # proves a move -- a report nobody could read: nothing is written, and
        # the approval waits. The park's own write drops the verdict it
        # refuses, so it fits, and the later tick that reads the report parks
        # the approval over the same comment rather than waiting on it forever.
        self.awaits(UNVERIFIED)
        _parked.fills_to(self, _SPARE)
        before = self.pinned()

        self.behind_the_notice(UNVERIFIED, _world.stops_answering)
        kept = (self.parked(), self.pinned() == before)
        self.github.report_failures.unreadable.discard(_world.PR)
        self.parks(UNVERIFIED)

        self.assertEqual(
            (kept, self.parked()),
            (
                (((None, False), APPROVED, []), True),
                ((UNVERIFIED, True), None, [UNVERIFIED]),
            ),
        )

    def test_a_moved_comment_takes_no_park_over_it(self) -> None:
        # The comment read for a park over it as it stands is one more
        # request: a later report settled by then is a subject nobody
        # reviewed, and a comment that will not read carries nothing, so
        # neither is posted on or written to.
        for road, revision in ((_read.settles_a_later_report, 2), (_unreadable, 1)):
            with self.subTest(road.__name__):
                self.setUp()
                _parked.fills_to(self, _ROOM_FOR_THE_PARK_ALONE)
                posted = len(self.issue.comments)

                self.parks(UNRECORDED, meanwhile=road)

                _answers_again(self)
                self.assertEqual(
                    (len(self.issue.comments), _read.current_report_revision(self), self.parked()),
                    (posted, revision, ((None, False), None, [])),
                )


class ParkNoticeTest(_parked.ParkedVerdictWorld, unittest.TestCase):
    """A park lands only behind an identified notice, over the subject and records it was about."""

    def test_an_unidentified_notice_parks_nothing(self) -> None:
        # A notice whose id nothing could read may have reached nobody, so no
        # park lands behind it, the thread is not read past it, and none is
        # reported: the run's records go down, and -- nothing having moved --
        # the verdict waits as it was, for the later tick that parks it behind
        # a notice identified.
        for reason, held in _HELD.items():
            with self.subTest(reason):
                self.setUp()
                self.awaits(reason)
                anchored = self.pinned()[LAST_ACTION]

                self.unidentified(reason)

                pinned = self.pinned()
                self.assertEqual(
                    (self.parked(), pinned[LAST_ACTION], pinned[LAST_REVIEW_SESSION]),
                    (((None, False), held, []), anchored, _world.REVIEWER_SESSION),
                )
                if held is not None:
                    self.parks(reason)
                    self.assertEqual(self.parked(), ((reason, True), None, [reason]))

    def test_a_move_outranks_an_unidentified_notice(self) -> None:
        # A notice nothing identified keeps the verdict waiting only where
        # nothing moved: a push behind it proves the approval is of work the
        # pull request no longer carries, so the verdict held is dropped for a
        # fresh reviewer whether or not anybody was told, and no park lands.
        self.awaits(UNVERIFIED)

        self.unidentified(UNVERIFIED, _world.pushes)

        self.assertEqual(self.parked(), ((None, False), None, []))

    def test_a_notice_parks_only_a_standing_subject(self) -> None:
        # The notice is the park's last request: whatever moved behind it is
        # work nobody reviewed, so no park lands and only the verdict held is
        # dropped, a later report kept rather than written back over. A report
        # nobody could read proves nothing, and the verdict held waits.
        for name, reason, road, expected in _BEHIND_THE_NOTICE:
            with self.subTest(name):
                self.setUp()
                self.awaits(reason)

                self.behind_the_notice(reason, road)

                self.assertEqual(
                    (self.parked(), (_read.current_report_revision(self), self.pinned()[REVIEW_ROUND])),
                    expected,
                )


class ParkWriteTest(_parked.ParkedVerdictWorld, unittest.TestCase):
    """A park's write is composed over the comment as it stands behind its notice, and made only where it fits."""

    def test_a_park_keeps_what_another_road_wrote(self) -> None:
        # Another road spends a round behind the notice, folds a run of its
        # own, reads the thread past every post there, and records two
        # notices of its own. The park lands over the comment as it stands:
        # the round is not written back over, the runs each road folded add
        # up, the thread stays read as far as that road read it, and the
        # ledger keeps both roads' posts.
        for reason in _PARKS:
            with self.subTest(reason):
                self.setUp()
                self.awaits(reason)

                self.behind_the_notice(reason, self._works_behind)

                pinned = self.pinned()
                self.assertEqual(
                    (
                        self.parked(),
                        tuple(map(pinned.get, (REVIEW_ROUND, "issue_agent_runs", TOKENS, LAST_ACTION))),
                        {*self.theirs, *self._notices(reason)}.difference(pinned[LEDGER]),
                    ),
                    (
                        ((reason, True), None, [reason]),
                        (_SPENT_ROUND, 2, _world.REVIEWER_TOKENS + _THEIR_TOKENS, self.read_through),
                        set(),
                    ),
                )

    def test_a_refused_write_reports_no_wait(self) -> None:
        # GitHub refuses the park's write behind its notice: the refusal is
        # raised out of the tick with nothing recorded, and no wait is
        # reported for a park that never landed -- the event follows the
        # write, and never stands in for it.
        for reason in _PARKS:
            with self.subTest(reason):
                self.setUp()
                self.awaits(reason)
                before = self.pinned()
                refused = patch.object(
                    self.github, "write_pinned_state", side_effect=RuntimeError("GitHub refused the edit"),
                )

                with refused, self.assertRaises(RuntimeError):
                    self.parks(reason)

                noticed = _parked.NOTICES[reason] in self.issue.comments[-1].body
                self.assertEqual(
                    (self.pinned(), noticed, _parked.reported(self)),
                    (before, True, []),
                )

    def test_a_park_writes_nothing_it_cannot_fit(self) -> None:
        # Another road retires the verdict behind the notice and leaves the
        # comment a valid body at its ceiling, so the write carrying all of it
        # beside the notice's ledger entry and watermark would not fit; or the
        # comment stops answering. Either way the park writes nothing, and
        # reports nothing, over what that road left.
        for road in (self._retires_and_fills, self._stops_answering):
            with self.subTest(road.__name__):
                self.setUp()
                self.awaits(UNVERIFIED)

                self.behind_the_notice(UNVERIFIED, road)

                _answers_again(self)
                reported = _parked.reported(self)
                self.assertEqual((self.pinned(), reported), (self.left, []))

    def _notices(self, reason: str) -> list[int]:
        """Every notice of `reason`'s park on the issue thread."""
        notice = _parked.NOTICES[reason]
        return [said.id for said in self.issue.comments if notice in said.body]

    def _works_behind(self, _case) -> None:
        """Another road's round, a run it folded, the thread read one past every comment, and two notices it posted."""
        state = self.github.read_pinned_state(self.issue)
        self.theirs = [
            _comments._post_issue_comment(self.github, self.issue, state, "Another road's notice.").id
            for _ in range(2)
        ]
        state.set(REVIEW_ROUND, _SPENT_ROUND)
        state.set("issue_agent_runs", (state.get("issue_agent_runs") or 0) + 1)
        state.set(TOKENS, (state.get(TOKENS) or 0) + _THEIR_TOKENS)
        self.read_through = max(said.id for said in self.issue.comments) + 1
        state.set(LAST_ACTION, self.read_through)
        self.github.write_pinned_state(self.issue, state)

    def _retires_and_fills(self, _case) -> None:
        """Another road's end of the waiting verdict, leaving the comment at its ceiling."""
        state = self.github.read_pinned_state(self.issue)
        state.set(_world.RETURNED_VERDICT, None)
        self.github.write_pinned_state(self.issue, state)
        _parked.fills_to(self, 0)
        self.left = self.pinned()

    def _stops_answering(self, _case) -> None:
        """The pinned comment stops answering behind the notice, left as it was."""
        self.left = self.pinned()
        _unreadable(self)

if __name__ == "__main__":
    unittest.main()
