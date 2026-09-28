# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A verdict's park lands only over the subject standing behind an identified notice, in a write that fits.

Every park a verdict of a reviewed subject can take -- an approval without
valid evidence, a verdict with no room to be recorded, its approval's failed
verify gate, and its approval's failed squash. Each is measured before its
notice is posted, so a comment with no room for it is posted on and written to
not at all. Behind the notice the subject is resolved again and the comment
read last: a push, a later report, or evidence another road settled there
drops the verdict for a fresh reviewer rather than asking a human about work
nobody reviewed, and a subject nobody could read, or a notice nothing
identified, keeps the verdict waiting for a later tick to park again. The
park's write is composed over the comment as it stands, so what another road
wrote behind the notice is kept, and is measured again with it.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.verification.models import VerifyResult
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.validating import review_claims as _claims, review_disposition as _disposition
from tests.workflow.fixtures import LABEL_DOCUMENTING
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)
from tests.workflow.value_helpers import _open_pr_for

UNVERIFIED = "reviewer_unverified"

UNRECORDED = "reviewer_unrecorded"

APPROVED = "approved"

REQUESTED = "changes_requested"

REVIEW_ROUND = "review_round"

ISSUE_COMMENT = "comment"

UNDECLARED_APPROVAL = "LGTM\n\nVERDICT: APPROVED"

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

DOCUMENTING = (_world.ISSUE, LABEL_DOCUMENTING)

# A squash the remote refuses, as the approval's squash seam answers it.
REFUSED_SQUASH = MappingProxyType({"squash_result": (False, None, 0, "force-push rejected")})

# A change request's feedback longer than most of what the pinned comment
# holds, and the notes that leave room for the round's own records beside it
# and not for the verdict.
_LONG = "12 passed, 1 failed " * 1000

_TOO_LONG_REQUEST = f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED"

_NO_ROOM_FOR_IT = MAX_PINNED_BODY - len(_LONG)

# What a comment a park cannot fit on has left: fewer characters than the
# park's own flags take.
_SPARE = 8

# The round another road spends behind a request: a field no verdict stands on.
_SPENT_ROUND = 7

# What a refused approval parked on a waiting record with no claim says of the
# declaration behind it, which that record keeps no copy of.
_NOTHING_EARNED = "nothing it declared earned verification evidence"

_NOT_PARKED = ((None, False), None, [])

_UNRECORDED_PARK = ((UNRECORDED, True), None, [UNRECORDED])

# Each verdict that cannot be persisted, the operator notes filling the comment
# ahead of it, and the words its park says why: no room for the verdict, no
# room for its transaction beside it -- a failed run's output the transaction
# quotes again -- or feedback in words UTF-8 cannot carry.
_UNRECORDED = (
    ("no room for the verdict", _TOO_LONG_REQUEST, _NO_ROOM_FOR_IT, _disposition.NO_ROOM),
    (
        "no room for its evidence",
        _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED", output=_LONG),
        MAX_PINNED_BODY - len(_LONG) * 3 // 2,
        _disposition.NO_ROOM,
    ),
    ("feedback UTF-8 cannot carry", "1. Handle \ud800 too.\n\nVERDICT: CHANGES_REQUESTED", 0, _disposition.UNREADABLE),
)

# Every park the funnel files behind its notice: the reply that earns it over
# the operator notes filling the comment, a phrase of its notice, the verdict
# it leaves waiting where no park lands over it, and how the tick runs.
_PARKS = (
    (UNVERIFIED, (UNDECLARED_APPROVAL, 0, _disposed.UNVERIFIED_NOTICE), APPROVED, {}),
    (UNRECORDED, (_TOO_LONG_REQUEST, _NO_ROOM_FOR_IT, "could not be recorded"), None, {}),
    (
        "verify_failed",
        (_world.declared_run(), 0, "local verification failed"),
        APPROVED,
        {"verify_result": VerifyResult(status="failed")},
    ),
)

# Those, and the park an approval's failed squash takes, spelled the same way.
_EVERY_PARK = (
    *_PARKS,
    ("squash_failed", (_world.declared_run(), 0, _disposed.SQUASH_FAILED_NOTICE), APPROVED, REFUSED_SQUASH),
)

# What another road does behind a park's notice, whether the verdict is held
# for a later tick, and the report revision and round the pinned comment
# records then: a later report -- spending its round -- evidence settling, or
# a push proves what the verdict was decided over moved, and a report nobody
# could read proves nothing either way.
_MOVES = (
    ("a later report", _read.settles_a_later_report, False, (2, 1)),
    ("an evidence settlement", _read.settles_evidence, False, (1, 0)),
    ("a push", _world.pushes, False, (1, 0)),
    ("an unread report", _world.stops_answering, True, (1, 0)),
)

# Each park with each move behind its notice, and what it leaves: the park as
# `parked` reads it, whether the notice was posted, the report revision and
# round, and every relabel. No park lands, and none is reported.
_BEHIND_THE_NOTICE = tuple(
    (
        f"{park} behind {move}",
        (*reply, road),
        options,
        (((None, False), waiting if holds else None, []), True, recorded, []),
    )
    for park, reply, waiting, options in _PARKS
    for move, road, holds, recorded in _MOVES
)

def _repoints(case) -> None:
    """Another road pointing `case`'s issue at another pull request than the one its reviewer reviewed."""
    _open_pr_for(case.github, issue_number=_world.ISSUE, pr_number=_world.PR + 1)
    state = case.github.read_pinned_state(case.issue)
    state.set("pr_number", _world.PR + 1)
    case.github.write_pinned_state(case.issue, state)


def _replaces_the_verdict(case) -> None:
    """Another road putting a later round's change request in place of `case`'s waiting verdict."""
    state = case.github.read_pinned_state(case.issue)
    replacement = dict(state.get(_world.RETURNED_VERDICT), verdict=REQUESTED, feedback="A later round's feedback.")
    state.set(_world.RETURNED_VERDICT, dict(replacement, round=1, evidence=None))
    case.github.write_pinned_state(case.issue, state)


# What moves an approval's subject or its records behind the notice of the
# park its failed squash takes, and the verdict each leaves waiting: a push, a
# repoint, a later report, or later evidence retires the approval's verdict --
# over the comment as read, where the records moved -- a report nobody could
# read keeps it, and a verdict another road put in its place stays.
_BEHIND_THE_SQUASH_NOTICE = (
    ("a push", _world.pushes, None),
    ("a repoint", _repoints, None),
    ("a later report", _read.settles_a_later_report, None),
    ("an evidence settlement", _read.settles_evidence, None),
    ("an unread report", _world.stops_answering, APPROVED),
    ("a replaced verdict", _replaces_the_verdict, REQUESTED),
)

# Each request behind which another road spends a round, the reply and notes
# that reach it, the request and a phrase of the post, how the tick runs, and
# what it leaves: the park as `parked` reads it beside every relabel. Every
# park the funnel files, and the approval's own comment, squash notice, and
# failed squash's notice.
_SPENT_BEHIND = (
    *(
        (
            park,
            reply[:2],
            (ISSUE_COMMENT, reply[2]),
            options,
            (((park, True), None, [park]), []),
        )
        for park, reply, _waiting, options in _PARKS
    ),
    (
        "the approval comment",
        (_world.declared_run(), 0),
        ("pr_comment", _disposed.APPROVAL_NOTICE),
        {},
        (_NOT_PARKED, [DOCUMENTING]),
    ),
    (
        "the squash notice",
        (_world.declared_run(), 0),
        ("pr_comment", _disposed.SQUASH_NOTICE),
        {"squash_result": (True, _world.HEAD, 2, None)},
        (_NOT_PARKED, [DOCUMENTING]),
    ),
    (
        "the failed squash's notice",
        (_world.declared_run(), 0),
        (ISSUE_COMMENT, _disposed.SQUASH_FAILED_NOTICE),
        REFUSED_SQUASH,
        ((("squash_failed", True), None, ["squash_failed"]), []),
    ),
)


# Where another road records orchestrator comments of its own: behind a park's
# notice, and behind the approval comment on the way to the squash -- the reply
# that reaches each, and the request and a phrase of the post it lands behind.
_LEDGER_WINDOWS = (
    ("the park's notice", UNDECLARED_APPROVAL, (ISSUE_COMMENT, _disposed.UNVERIFIED_NOTICE)),
    ("the approval comment", _world.declared_run(), ("pr_comment", _disposed.APPROVAL_NOTICE)),
)


def _fills_to(case, spare: int) -> None:
    """Fill `case`'s pinned comment with operator notes to `spare` characters short of its ceiling."""
    _disposed.fills(case, 0)
    body = pinned_state_body(case.pinned())
    _disposed.fills(case, MAX_PINNED_BODY - len(body) - spare)


def _written_length(case) -> int:
    """How long `case`'s pinned comment is, as written."""
    return len(pinned_state_body(case.pinned()))


class ParkedVerdictTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A verdict that may not be acted on parks, and only over the subject it is about."""

    def test_an_unrecorded_verdict_parks_unacted(self) -> None:
        # Nothing durable backs it, so nothing it returned is published or
        # acted on: its park says why, and a fresh reviewer is what a reply
        # buys.
        for name, message, filled, why in _UNRECORDED:
            with self.subTest(name):
                self.setUp()
                _disposed.fills(self, filled)

                ran = self.returns(message)

                self.assertEqual(
                    (
                        self.parked(),
                        self.pinned().get(_world.PENDING_EVIDENCE),
                        _read.artifacts(self),
                        ran[_world.RUN_AGENT].call_count,
                        _disposed.feedback_posts(self),
                        self.github.label_history,
                        why in self.last_notice(),
                    ),
                    (_UNRECORDED_PARK, None, [], 0, [], [], True),
                )

    def test_no_room_even_for_the_park_writes_nothing(self) -> None:
        # A comment a few characters short of its ceiling has room for no
        # park either: a notice posted over a write GitHub then refuses would
        # leave neither a verdict nor a park durable.
        _fills_to(self, _SPARE)
        before = (self.pinned(), len(self.github.posted_comments))

        ran = self.returns(UNDECLARED_REQUEST)

        self.assertEqual(
            (
                (self.pinned(), len(self.github.posted_comments)),
                ran[_world.RUN_AGENT].call_count,
                _disposed.feedback_posts(self),
                self.github.label_history,
            ),
            (before, 0, [], []),
        )

    def test_a_notice_parks_only_a_standing_subject(self) -> None:
        # The notice is the park's last request: a later report, a push, or
        # evidence settling while it is posted is a subject nobody reviewed,
        # so no park lands and the verdict is dropped for a fresh reviewer, a
        # later report kept rather than written back over. A report nobody
        # could read then proves nothing: no park lands, and the verdict an
        # approval persisted waits for a later tick.
        for name, case, options, expected in _BEHIND_THE_NOTICE:
            with self.subTest(name):
                self.assertEqual(self._moved_behind_the_notice(*case, **options), expected)

    def test_a_park_measures_the_verdict_it_may_keep(self) -> None:
        # A report nobody could read behind the notice keeps the verdict
        # waiting beside the notice's ledger entry, the wider of the two
        # writes a park may end in. A comment one character short of that is
        # not posted on, and never written past its ceiling.
        unread = _MOVES[-1][1]
        self._moved_behind_the_notice(UNDECLARED_APPROVAL, 0, _disposed.UNVERIFIED_NOTICE, unread)
        kept = len(pinned_state_body(self.pinned()))

        left = self._moved_behind_the_notice(
            UNDECLARED_APPROVAL, MAX_PINNED_BODY - kept + 1, _disposed.UNVERIFIED_NOTICE, unread,
        )

        self.assertEqual(
            (left[0][1], left[1], _written_length(self) <= MAX_PINNED_BODY),
            (APPROVED, False, True),
        )

    def _moved_behind_the_notice(self, message: str, filled: int, notice: str, road, **options) -> tuple:
        """What the park `message` earns over `filled` notes leaves where `road` moves its subject behind `notice`.

        The park as `parked` reads it, whether the notice was posted, the
        current report revision and round, and every relabel.
        """
        self.setUp()
        _disposed.fills(self, filled)
        behind = _world.AnotherRoadBehind(self, ISSUE_COMMENT, _disposed.saying(notice), road)
        behind.returning(message, **options)
        return (
            self.parked(),
            notice in self.last_notice(),
            (_read.current_report_revision(self), self.pinned().get(REVIEW_ROUND)),
            self.github.label_history,
        )


class ParkNoticeTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A park lands only behind an identified notice, and in a write re-measured over what moved behind it."""

    def test_an_unidentified_notice_parks_nothing(self) -> None:
        # A notice whose id nothing could read may have reached nobody, so no
        # park lands behind it and none is reported: the verdict waits as it
        # was, and the later tick that finishes it parks behind a notice that
        # is identified. A verdict with no room to persist leaves none.
        for park, reply, waiting, options in _EVERY_PARK:
            with self.subTest(park):
                left = self._unidentified(*reply, **options)
                self.assertEqual(left, ((None, False), waiting, []))
                if waiting is not None:
                    self.finishes(**options)
                    self.assertEqual(self.parked(), ((park, True), None, [park]))

    def test_a_retried_park_says_only_what_is_true(self) -> None:
        # An approval declaring a run on another commit earns no evidence, and
        # its park's notice says why -- but that notice left no id, so the
        # tick that finishes the waiting verdict parks it again. The record
        # keeps no copy of why nothing was earned, so that notice says only
        # what is true of every such declaration.
        elsewhere = _world.declared_run().replace(_world.HEAD, _world.OTHER_HEAD)
        self._unidentified(elsewhere, 0, _disposed.UNVERIFIED_NOTICE)

        self.finishes()

        notices = [body for _, body in self.github.posted_comments if _disposed.UNVERIFIED_NOTICE in body]
        self.assertEqual(
            (
                len(notices),
                "names another commit" in notices[0],
                _claims.NO_DECLARATION in notices[-1],
                _NOTHING_EARNED in notices[-1],
                self.parked()[0],
            ),
            (2, True, False, True, (UNVERIFIED, True)),
        )

    def test_a_park_remeasures_what_moved_behind_it(self) -> None:
        # Another road settles a later report behind the notice, retires the
        # verdict, and leaves the comment a valid body at its ceiling: the
        # write carrying all of that beside the notice's ledger entry and
        # watermark would not fit, so the park writes nothing.
        for park, reply, _waiting, options in _EVERY_PARK:
            with self.subTest(park):
                self.setUp()
                _disposed.fills(self, reply[1])

                _world.AnotherRoadBehind(
                    self, ISSUE_COMMENT, _disposed.saying(reply[2]), self._fills_it,
                ).returning(reply[0], **options)

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
        for move, road, waiting in _BEHIND_THE_SQUASH_NOTICE:
            with self.subTest(move):
                self.setUp()

                _world.AnotherRoadBehind(
                    self, ISSUE_COMMENT, _disposed.saying(_disposed.SQUASH_FAILED_NOTICE), road,
                ).returning(_world.declared_run(), **REFUSED_SQUASH)

                self.assertEqual(self.parked(), ((None, False), waiting, []))

    def _unidentified(self, message: str, filled: int, notice: str, **options) -> tuple:
        """What the park `message` earns over `filled` notes leaves where its `notice` is posted with no id."""
        self.setUp()
        _disposed.fills(self, filled)
        unidentified = _disposed.RefusesOnce(self.github.comment, notice, lands=True)
        with patch.object(self.github, ISSUE_COMMENT, unidentified):
            self.returns(message, **options)
        return self.parked()

    def _fills_it(self, _case) -> None:
        """Another road's settlement of a later report retiring the verdict, leaving the comment at its ceiling."""
        _read.settles_a_later_report(self)
        state = self.github.read_pinned_state(self.issue)
        state.set(_world.RETURNED_VERDICT, None)
        self.github.write_pinned_state(self.issue, state)
        _fills_to(self, 0)
        self.written = self.pinned()


class ParkWriteTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A park's or an approval's write keeps what another road wrote, and a failed squash's park fits or is not made."""

    def test_a_park_keeps_what_another_road_wrote(self) -> None:
        # Another road spends a round behind a park's notice, or behind a post
        # an approval makes on its way to the handoff or to the park its
        # failed squash takes: the park or the approval goes on, composed over
        # the comment as it stands, so the round is not written back over.
        for name, reply, behind, options, expected in _SPENT_BEHIND:
            with self.subTest(name):
                self.setUp()
                _disposed.fills(self, reply[1])

                _world.AnotherRoadBehind(
                    self, behind[0], _disposed.saying(behind[1]), self._spends_a_round,
                ).returning(reply[0], **options)

                self.assertEqual(
                    ((self.parked(), self.github.label_history), self.pinned().get(REVIEW_ROUND)),
                    (expected, _SPENT_ROUND),
                )

    def test_a_full_comment_takes_no_squash_park(self) -> None:
        # An approval finished over a comment a few characters short of its
        # ceiling has no room for the park its failed squash takes: nothing is
        # posted on the issue and nothing written, which the squash already
        # answers as a tick that died before its write.
        _read.seeds_a_verdict(self, _read.settles_evidence(self))
        _fills_to(self, _SPARE)
        before = (self.pinned(), len(self.github.posted_comments))

        self.finishes(**REFUSED_SQUASH)

        self.assertEqual(
            (
                (self.pinned(), len(self.github.posted_comments)),
                self.parked()[2],
            ),
            (before, []),
        )

    def test_another_roads_ledger_entries_are_kept(self) -> None:
        # Another road records two orchestrator comments of its own behind a
        # park's notice, or behind the approval comment on the way to the
        # squash: every write behind that merges the ledger rather than keeping
        # one side's, so that road's comments and this tick's own posts alike
        # stay the orchestrator's to every later prompt.
        for name, reply, behind in _LEDGER_WINDOWS:
            with self.subTest(name):
                self.setUp()

                _world.AnotherRoadBehind(
                    self, behind[0], _disposed.saying(behind[1]), self._posts_two_notices,
                ).returning(reply)

                self.assertEqual(self._unrecorded_posts(), set())

    def _spends_a_round(self, _case) -> None:
        """Another road's write of the round, which no verdict stands on."""
        state = self.github.read_pinned_state(self.issue)
        state.set(REVIEW_ROUND, _SPENT_ROUND)
        self.github.write_pinned_state(self.issue, state)

    def _posts_two_notices(self, _case) -> None:
        """Another road's two identified orchestrator comments on the issue, recorded in the ledger it writes."""
        state = self.github.read_pinned_state(self.issue)
        self.theirs = [
            _comments._post_issue_comment(self.github, self.issue, state, "Another road's notice.").id
            for _ in range(2)
        ]
        self.github.write_pinned_state(self.issue, state)

    def _unrecorded_posts(self) -> set:
        """Every orchestrator comment -- another road's, and each notice this tick posted -- the ledger lost."""
        ours = {
            said.id
            for said in (*self.issue.comments, *self.pull_request.issue_comments)
            if any(notice in said.body for notice in _disposed.NOTICES)
        }
        recorded = set(self.pinned()[_disposed.LEDGER])
        return (ours | set(self.theirs)) - recorded


if __name__ == "__main__":
    unittest.main()
