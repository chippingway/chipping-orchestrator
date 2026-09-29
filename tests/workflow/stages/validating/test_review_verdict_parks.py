# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A verdict's park lands only over the subject standing behind an identified notice, in a write that fits.

Every park a verdict of a reviewed subject can take, each entry called
directly the way its caller is to call it: an approval without valid evidence
and a verdict with no room to be recorded, right behind the verdict's
preparation, and an approval's failed verify gate or failed squash. Each is
measured before its notice is posted, so a comment with no room for it is
posted on and written to not at all, and one with no room beside what the
returned run staged takes the park over the comment as it stands. Behind the
notice the subject is resolved again and the comment read last: a push, a
repoint, a later report, or evidence another road settled there drops the
verdict for a fresh reviewer rather than asking a human about work nobody
reviewed, and a subject nobody could read, or a notice nothing identified,
keeps the verdict waiting for a later tick to park again. The park's write is
composed over the comment as it stands, so what another road wrote behind the
notice is kept -- its usage beside the run's, the thread read as far as either
read it, its ledger entries beside the notice's -- and is measured again with
it; the wait is reported only once that write is down.
"""
from __future__ import annotations

import operator
import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.validating import (
    handoff as _handoff,
    review_disposition as _disposition,
    review_parks as _parks,
)
from tests.workflow.stages.validating import (
    review_park_test_support as _parked,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

REVIEW_ROUND = "review_round"

TOKENS = "issue_total_tokens"

LEDGER = "orchestrator_comment_ids"

# Where the pinned comment records the reviewer session a round ran.
LAST_REVIEW_SESSION = "last_review_session_id"

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# A change request's feedback longer than most of what the pinned comment
# holds, and the notes that leave room for the round's own records beside it
# and not for the verdict.
_LONG = "12 passed, 1 failed " * 1000

_UNRECORDED = (
    (f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED", MAX_PINNED_BODY - len(_LONG), _disposition.NO_ROOM),
    (_parked.PARKS[1][1], 0, _disposition.UNREADABLE),
)

# What a comment a park cannot fit on has left: fewer characters than the
# park's own flags take.
_SPARE = 8

# What no park landing leaves on the comment.
_NO_PARK = (None, False)

# The round another road spends behind a notice, a field no verdict stands
# on, and the tokens its run folds into the usage totals.
_SPENT_ROUND = 7

_THEIR_TOKENS = 100

# What the comment holds once another road has worked behind a notice: the
# round it spent, the runs and tokens folded, and how far the thread was read.
_WORKED_BEHIND = operator.itemgetter(REVIEW_ROUND, "issue_agent_runs", TOKENS, "last_action_comment_id")

# How many ids the ledger holds, and a ledger at that bound of ids older than
# any comment the world posts.
_LEDGER_CAP = _comments._ORCH_COMMENT_ID_CAP

_FULL_LEDGER = range(1, _LEDGER_CAP + 1)

# Every park, the reply that earns it, and a phrase of its notice.
_FILED = tuple(park[:3] for park in _parked.PARKS)

# The parks an approval takes, which a later tick files over a verdict waiting.
_APPROVAL_PARKS = (_parked.UNVERIFIED, _parked.VERIFY_FAILED, _parked.SQUASH_FAILED)

# An approval refused where its pull request's thread stops answering behind
# the notice of its park.
_UNREAD_BEHIND = (
    _parked.UNVERIFIED,
    _parked.PARKS[0][1],
    (_parked.UNVERIFIED_NOTICE, _world.stops_answering),
)

# What another road does behind a park's notice, whether the verdict is held
# for a later tick, and the report revision and round the pinned comment
# records then: a later report -- spending its round -- evidence settling, a
# push, or a repoint proves what the verdict was decided over moved, and a
# report nobody could read proves nothing either way.
_MOVES = (
    ("a later report", _read.settles_a_later_report, False, (2, 1)),
    ("an evidence settlement", _read.settles_evidence, False, (1, 0)),
    ("a push", _world.pushes, False, (1, 0)),
    ("a repoint", _parked.repoints, False, (1, 0)),
    ("an unread report", _world.stops_answering, True, (1, 0)),
)

# Each park the funnel files with each move behind its notice, how the tick
# runs, and what it leaves: no park, the verdict an approval keeps waiting
# where nothing proved a move, the report revision and round, and no notice
# the ledger lost.
_BEHIND_THE_NOTICE = tuple(
    (
        f"{park} behind {move}",
        (park, reply, (notice, road)),
        ((_NO_PARK, waiting if holds else None, []), recorded, set()),
    )
    for park, reply, notice, waiting in _parked.PARKS[:-1]
    for move, road, holds, recorded in _MOVES
)

# The same moves behind the notice of the park an approval's failed squash
# takes, how the tick runs, and the verdict each leaves waiting: a move
# retires the approval's verdict -- over the comment as read, where the
# records moved -- a report nobody could read keeps it, and a verdict another
# road put in its place stays.
_BEHIND_THE_SQUASH_NOTICE = (
    *(
        (move, (road, _parked.APPROVED if holds else None))
        for move, road, holds, _recorded in _MOVES
    ),
    ("a replaced verdict", (_parked.replaces_the_verdict, _parked.REQUESTED)),
)


def _written_length(case) -> int:
    """How long `case`'s pinned comment is, as written."""
    return len(pinned_state_body(case.pinned()))


def _noticed(case, *phrases: str) -> set:
    """The ids of every comment on `case`'s issue saying any of `phrases`."""
    return {
        said.id
        for said in case.issue.comments
        if any(phrase in said.body for phrase in phrases)
    }


class _Unidentified:
    """An issue comment that lands, once, where it says `phrase`, with an answer naming no comment."""

    def __init__(self, posts, phrase: str) -> None:
        self._posts = posts
        self._phrase = phrase
        self._left = True

    def __call__(self, thread, body):
        posted = self._posts(thread, body)
        if self._left and self._phrase in body:
            self._left = False
            return None
        return posted


class _RefusesThePark:
    """A pinned-comment write GitHub refuses wherever it carries a park, and takes otherwise."""

    def __init__(self, writes) -> None:
        self._writes = writes

    def __call__(self, issue, state):
        if state.get("awaiting_human"):
            raise RuntimeError("GitHub refused the edit")
        return self._writes(issue, state)


class ParkedVerdictTest(_parked.ParkWorld, unittest.TestCase):
    """A verdict that may not be acted on parks in a write that fits, and only over the subject it is about."""

    def test_an_unrecorded_verdict_parks_unacted(self) -> None:
        # Nothing durable backs it, so nothing it returned is published: its
        # park says why, and a fresh reviewer is what a reply buys. The park
        # has room beside what the returned run staged -- over a comment with
        # none for the verdict, too -- so the round it records is the one
        # that ran: the reviewer's session.
        unrecorded = _parked.UNRECORDED
        for message, filled, why in _UNRECORDED:
            with self.subTest(why):
                self.setUp()
                self.fills(filled)

                self.parks(unrecorded, message)

                self.assertEqual(
                    (
                        self.parked(),
                        _read.artifacts(self),
                        self.github.label_history,
                        why in self.last_notice(),
                        self.pinned().get(LAST_REVIEW_SESSION),
                    ),
                    (((unrecorded, True), None, [unrecorded]), [], [], True, _world.REVIEWER_SESSION),
                )

    def test_no_room_beside_the_run_takes_the_comment(self) -> None:
        # A comment with exactly the room the returned run's own records take
        # has none for the park beside them: the park is taken over the
        # comment as it stands instead, the run's session and usage
        # unrecorded -- a smaller loss than a park that never lands.
        unrecorded, reply = _parked.PARKS[1][:2]
        self.parks(unrecorded, reply)
        staged = self.staged
        self.setUp()
        self.fills_to(staged)

        self.parks(unrecorded, reply)

        pinned = self.pinned()
        self.assertEqual(
            (self.parked(), pinned.get(LAST_REVIEW_SESSION), pinned.get(TOKENS)),
            (((unrecorded, True), None, [unrecorded]), None, None),
        )

    def test_no_room_even_for_the_park_writes_nothing(self) -> None:
        # A comment a few characters short of its ceiling has room for no
        # park: a notice posted over a write GitHub then refuses would leave
        # neither a verdict nor a park durable. A verdict a returned run could
        # not persist is posted about and written nowhere, and neither is an
        # approval a tick left waiting.
        self.fills_to(_SPARE)
        self.assert_untouched(self.parks, _parked.UNRECORDED, UNDECLARED_REQUEST)
        for park in _APPROVAL_PARKS:
            with self.subTest(park):
                self.setUp()
                _read.seeds_a_verdict(self, _read.settles_evidence(self))
                self.fills_to(_SPARE)

                self.assert_untouched(self.parks_waiting, _parked.FILES[park])

    def test_a_notice_parks_only_a_standing_subject(self) -> None:
        # The notice is the park's last request: a later report, evidence
        # settling, a push, or a repoint while it is posted is a subject
        # nobody reviewed, so no park lands and the verdict is dropped for a
        # fresh reviewer, a later report kept rather than written back over.
        # A report nobody could read then proves nothing: no park lands, and
        # an approval waits for a later tick. The notice is the
        # orchestrator's own either way.
        for name, arguments, left in _BEHIND_THE_NOTICE:
            with self.subTest(name):
                self.setUp()

                self.parks(*arguments)

                self.assertEqual(self._left(), left)

    def test_a_park_measures_the_verdict_it_may_keep(self) -> None:
        # A report nobody could read behind the notice keeps the verdict
        # waiting beside the notice's ledger entry, the wider of the two
        # writes a park may end in. A comment one character short of that is
        # not posted on, and never written past its ceiling.
        self.parks(*_UNREAD_BEHIND)
        kept = _written_length(self)
        self.setUp()
        self.fills(MAX_PINNED_BODY - kept + 1)

        self.parks(*_UNREAD_BEHIND)

        self.assertEqual(
            (
                self.parked()[1],
                _parked.UNVERIFIED_NOTICE in self.last_notice(),
                _written_length(self) <= MAX_PINNED_BODY,
            ),
            (_parked.APPROVED, False, True),
        )

    def assert_untouched(self, files, *arguments) -> None:
        """Assert that `files` over `arguments` posts, writes, and reports nothing."""
        before = (self.pinned(), len(self.github.posted_comments))

        files(*arguments)

        after = (self.pinned(), len(self.github.posted_comments))
        self.assertEqual((after, self.parked()[2]), (before, []))

    def _left(self) -> tuple:
        """The park left, the report revision and round recorded, and every park notice the ledger lost."""
        recorded = (_read.current_report_revision(self), self.pinned().get(REVIEW_ROUND))
        ledger = self.pinned().get(LEDGER) or ()
        lost = _noticed(self, *_parked.NOTICES).difference(ledger)
        return (self.parked(), recorded, lost)


class ParkNoticeTest(_parked.ParkWorld, unittest.TestCase):
    """A park lands only behind an identified notice, in a write re-measured over what moved behind it."""

    def test_an_unidentified_notice_parks_nothing(self) -> None:
        # A notice whose id nothing could read may have reached nobody, so no
        # park lands behind it and none is reported: the verdict waits as it
        # was, and the later tick that files it again parks behind a notice
        # that is identified. A verdict with no room to persist leaves none.
        for park, reply, notice, waiting in _parked.PARKS:
            with self.subTest(park):
                self.setUp()
                with patch.object(self.github, "comment", _Unidentified(self.github.comment, notice)):
                    self.parks(park, reply)
                self.assertEqual(self.parked(), (_NO_PARK, waiting, []))
                if waiting is not None:
                    self.parks_waiting(_parked.FILES[park])
                    self.assertEqual(self.parked(), ((park, True), None, [park]))

    def test_a_park_remeasures_what_moved_behind_it(self) -> None:
        # Another road settles a later report behind the notice, retires the
        # verdict, and leaves the comment a valid body at its ceiling: the
        # write carrying all of that beside the notice's ledger entry and
        # watermark would not fit, so the park writes nothing.
        for park, reply, notice in _FILED:
            with self.subTest(park):
                self.setUp()

                self.parks(park, reply, (notice, self._fills_it))

                self.assertEqual(
                    (self.pinned(), _written_length(self), self.parked()[2]),
                    (self.written, MAX_PINNED_BODY, []),
                )

    def test_a_squash_park_holds_to_its_subject(self) -> None:
        # A push, a repoint, a later report, or later evidence behind the
        # notice of the park an approval's failed squash takes is work nobody
        # reviewed: no park lands, and the approval's verdict is retired for a
        # fresh reviewer -- over the comment as read where the records moved,
        # so a verdict another road put in its place stays. A report nobody
        # could read then proves nothing: no park lands, and the verdict waits.
        for move, (road, waiting) in _BEHIND_THE_SQUASH_NOTICE:
            with self.subTest(move):
                self.setUp()

                self._squashes_behind(road)

                self.assertEqual(self.parked(), (_NO_PARK, waiting, []))

    def test_a_recovered_squash_keeps_a_later_verdict(self) -> None:
        # The recovery of a squash an earlier tick did not finish holds no
        # verdict and no subject: its park lands over the records in hand and
        # leaves a later round's verdict waiting for the road that finishes it.
        _read.seeds_a_verdict(self, _read.settles_evidence(self), _parked.REQUESTED)

        self.parks_waiting(self._recovers)

        squash = _parked.SQUASH_FAILED
        left = ((squash, True), _parked.REQUESTED, [squash])
        self.assertEqual(self.parked(), left)

    def _squashes_behind(self, road) -> None:
        """One tick filing the park an approval's failed squash takes, `road` another road's work behind its notice."""
        squash, reply, notice = _FILED[-1]
        self.parks(squash, reply, (notice, road))

    def _recovers(self, case, state, _run) -> None:
        """The recovery of a squash an earlier tick did not finish, filing the park its failure takes."""
        words = f"{_parked.SQUASH_NOTICE} (lease refused); the collapse stands in the reflog"
        held = _handoff._Held(None, dict(state.data))
        _parks.parks_the_failed_squash(case.github, case.issue, state, words, held)

    def _fills_it(self, _case) -> None:
        """Another road's settlement of a later report retiring the verdict, leaving the comment at its ceiling."""
        _read.settles_a_later_report(self)
        state = self.github.read_pinned_state(self.issue)
        state.set(_world.RETURNED_VERDICT, None)
        self.github.write_pinned_state(self.issue, state)
        self.fills_to(0)
        self.written = self.pinned()


class ParkWriteTest(_parked.ParkWorld, unittest.TestCase):
    """A park's write keeps what another road wrote behind its notice, and reports the wait only once down."""

    def test_a_park_keeps_what_another_road_wrote(self) -> None:
        # Another road spends a round behind a park's notice, folds a run of
        # its own into the usage totals, and reads the thread past the notice:
        # the park lands composed over the comment as it stands, so the round
        # is not written back over, the run this tick folded is added to that
        # road's -- one a verdict with no room staged and never wrote among
        # them -- and the thread stays read as far as that road read it, past
        # the park's own mark.
        for park, reply, notice in _FILED:
            with self.subTest(park):
                self.setUp()

                self.parks(park, reply, (notice, self._works_behind))

                worked = (_SPENT_ROUND, 2, _world.REVIEWER_TOKENS + _THEIR_TOKENS, self.read_through)
                self.assertEqual(
                    (self.parked(), _WORKED_BEHIND(self.pinned())),
                    (((park, True), None, [park]), worked),
                )

    def test_another_roads_ledger_entries_are_kept(self) -> None:
        # Another road records two orchestrator comments of its own behind a
        # park's notice: the park's write merges the ledger rather than keeping
        # one side's, so that road's comments and the notice alike stay the
        # orchestrator's to every later prompt.
        for park, reply, notice in _FILED:
            with self.subTest(park):
                self.setUp()

                self.parks(park, reply, (notice, self._posts_two_notices))

                posted = {*self.theirs, *_noticed(self, notice)}
                self.assertEqual(posted.difference(self.pinned()[LEDGER]), set())
                self.assertEqual(self.parked()[0], (park, True))

    def test_a_full_ledger_keeps_its_newest_ids(self) -> None:
        # Over a ledger already at its cap, each post evicts the oldest id,
        # and the park's write merges the comment's own reading back in --
        # which still carries that id. The ledger it writes holds the newest
        # ids there are: the evicted one stays evicted, no newer one goes
        # instead, and the notice is recorded.
        for park, reply, notice in _FILED:
            with self.subTest(park):
                self.setUp()
                self._seeds_a_full_ledger()

                self.parks(park, reply)

                kept = self.pinned()[LEDGER]
                newest = sorted({*_FULL_LEDGER, *kept})[-_LEDGER_CAP:]
                self.assertEqual(
                    (len(kept), _noticed(self, notice).difference(kept), sorted(kept)),
                    (_LEDGER_CAP, set(), newest),
                )

    def test_a_refused_write_reports_no_wait(self) -> None:
        # The wait is reported only once the park's write is down: a write
        # GitHub refuses lands no park, and nobody is told the issue waits.
        for park, reply, _notice, waiting in _parked.PARKS:
            with self.subTest(park):
                self.setUp()
                refusing = _RefusesThePark(self.github.write_pinned_state)

                with patch.object(self.github, "write_pinned_state", refusing), self.assertRaises(RuntimeError):
                    self.parks(park, reply)

                self.assertEqual(self.parked(), (_NO_PARK, waiting, []))

    def _works_behind(self, _case) -> None:
        """Another road's write of the round, which no verdict stands on, a run it folded, and a thread it read further.

        Read one past every comment the issue and its pull request carry, as
        answering a reply that landed behind the notice does.
        """
        state = self.github.read_pinned_state(self.issue)
        state.set(REVIEW_ROUND, _SPENT_ROUND)
        state.set("issue_agent_runs", (state.get("issue_agent_runs") or 0) + 1)
        state.set(TOKENS, (state.get(TOKENS) or 0) + _THEIR_TOKENS)
        said = (*self.issue.comments, *self.pull_request.issue_comments)
        self.read_through = max(comment.id for comment in said) + 1
        state.set("last_action_comment_id", self.read_through)
        self.github.write_pinned_state(self.issue, state)

    def _posts_two_notices(self, _case) -> None:
        """Another road's two identified orchestrator comments on the issue, recorded in the ledger it writes."""
        state = self.github.read_pinned_state(self.issue)
        self.theirs = [
            _comments._post_issue_comment(self.github, self.issue, state, "Another road's notice.").id
            for _ in range(2)
        ]
        self.github.write_pinned_state(self.issue, state)

    def _seeds_a_full_ledger(self) -> None:
        """A ledger at its bound, of ids older than any comment the world posts."""
        state = self.github.read_pinned_state(self.issue)
        state.set(LEDGER, list(_FULL_LEDGER))
        self.github.write_pinned_state(self.issue, state)


if __name__ == "__main__":
    unittest.main()
