# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A disposed verdict parks for a human only over the subject standing behind an identified notice.

Through `review_disposition`: a verdict no pinned comment can record parks
under `reviewer_unrecorded` with nothing published or acted on, and its notice
asks for room only where room is what refused it; a comment with no room even
for the park is posted on and written to not at all. An approval relying on no
evidence parks under `reviewer_unverified`, which a move behind the park's
notice turns into a verdict dropped for a fresh reviewer, and a notice nothing
identified into a verdict left waiting for the next tick to park again.

The funnel's measurements, notices, and races are covered beside
`review_parks`; this is what the disposition composes of it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.stages.validating import review_parks as _parks
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    review_park_test_support as _parked,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

ISSUE_COMMENT = "comment"

UNRECORDED = _parked.UNRECORDED

UNVERIFIED = _parked.UNVERIFIED

APPROVED = "approved"

UNDECLARED_APPROVAL = "LGTM\n\nVERDICT: APPROVED"

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# What the unrecorded park's notice asks of a human where room refused it.
FREE_ROOM = "free room on the pinned comment"

# What a waiting approval with no claim is refused in, the record keeping no
# copy of why its declaration earned none, and what the returning tick says.
NOTHING_EARNED = "nothing it declared earned verification evidence"

NOTHING_DECLARED = "declared no verification"

# What a comment with no room even for a park has left.
_SPARE = 8

_NOT_PARKED = ((None, False), None, [])

_UNVERIFIED_PARK = ((UNVERIFIED, True), None, [UNVERIFIED])

_UNRECORDED_PARK = ((UNRECORDED, True), None, [UNRECORDED])


def _nobody(_case) -> None:
    """No other road's work at all."""


# What another road does behind an unverified approval's park notice, and the
# park as `parked` reads it then: a push or a later report is work nobody
# reviewed, so the verdict is dropped for a fresh reviewer and nobody is asked.
_BEHIND_THE_NOTICE = (
    ("nothing", _nobody, _UNVERIFIED_PARK),
    ("a push", _world.pushes, _NOT_PARKED),
    ("a later report", _read.settles_a_later_report, _NOT_PARKED),
)


class UnrecordedParkTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A verdict nothing can record parks, publishing and acting on nothing, or nothing happens at all."""

    def test_an_unrecorded_verdict_parks(self) -> None:
        for name, message, filled, why in _disposed.UNRECORDED:
            with self.subTest(name):
                self.setUp()
                _disposed.fills(self, filled)

                ran = self.returns(message, **_disposed.fixing())

                self.assertEqual(
                    (
                        self.parked(),
                        FREE_ROOM in _disposed.last_notice(self),
                        _read.artifacts(self),
                        self.feedback_posts(),
                        ran[_world.RUN_AGENT].call_count,
                    ),
                    (_UNRECORDED_PARK, why == _parks.NO_ROOM, [], [], 0),
                )

    def test_no_room_for_the_park_writes_nothing(self) -> None:
        # No room for the verdict, nor for the park beside the comment as it
        # stands: nothing is posted, rather than a notice announcing a park
        # whose write then does not land.
        _parked.fills_to(self, _SPARE)
        before = self.pinned()

        self.returns(UNDECLARED_REQUEST)

        self.assertEqual(
            (self.pinned(), self.github.posted_comments, self.feedback_posts()),
            (before, [], []),
        )


class UnverifiedParkTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """An approval relying on no evidence parks only behind an identified notice, over a standing subject."""

    def test_a_move_behind_the_notice_parks_nobody(self) -> None:
        for name, road, parked in _BEHIND_THE_NOTICE:
            with self.subTest(name):
                self.setUp()
                notice = _parked.saying(_parked.NOTICES[UNVERIFIED])
                behind = _world.AnotherRoadBehind(self, ISSUE_COMMENT, notice, road)

                behind.returning(UNDECLARED_APPROVAL)

                self.assertEqual(
                    (self.parked(), NOTHING_DECLARED in _disposed.last_notice(self), self.github.label_history),
                    (parked, True, []),
                )

    def test_an_unidentified_notice_is_parked_again(self) -> None:
        # The notice may have reached nobody, so no park lands behind it and
        # the approval waits. The next tick finishes it through the run it
        # was returned in, and its proof refuses the approval that relies on
        # nothing, so it parks -- in words true of any declaration that
        # earned none, which is all the record can say.
        leaves_no_id = _parked.LeavesNoId(self.github.comment, _parked.NOTICES[UNVERIFIED])
        with patch.object(self.github, ISSUE_COMMENT, leaves_no_id):
            self.returns(UNDECLARED_APPROVAL)
        waited = self.parked()

        self.finishes()

        self.assertEqual(
            (
                waited,
                self.parked(),
                NOTHING_EARNED in _disposed.last_notice(self),
                len(self.github.posted_comments),
            ),
            (((None, False), APPROVED, []), _UNVERIFIED_PARK, True, 2),
        )


if __name__ == "__main__":
    unittest.main()
