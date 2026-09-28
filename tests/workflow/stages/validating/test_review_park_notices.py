# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A verdict's park lands only behind a notice somebody can read, in a write the comment has room for.

Every park a verdict of a reviewed subject can take -- the reviewer's own two,
its approval's failed verify gate, and its approval's failed squash. A notice
nothing identified may have reached nobody, so no park lands behind it: the
verdict waits as it was, for the tick that finishes it to park behind a notice
that is identified. And the park's write carries whatever moved on the comment
behind its notice, where another road can have left no room for what the park
adds beside it: that write is measured again, and not made.

The parks themselves, and the subject each is held to behind its notice, are
in `test_review_disposition.py` beside this.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from tests.workflow.stages.validating import review_verdict_test_support as _world
from tests.workflow.stages.validating.test_review_disposition import (
    _PARKS,
    APPROVED,
    ISSUE_COMMENT,
    PARK_EVENT,
    SQUASH_FAILED_NOTICE,
    VERDICT,
    _RefusesOnce,
    _settles_a_later_report,
)

# Each park `_PARKS` spells, and the one an approval's failed squash takes,
# spelled the same way: an approval over the evidence its passing run
# published, whose squash the remote refuses.
_EVERY_PARK = (
    *_PARKS,
    (
        "squash_failed",
        (_world.declared_run(), 0, SQUASH_FAILED_NOTICE),
        APPROVED,
        {"squash_result": (False, None, 0, "force-push rejected")},
    ),
)


class ParkNoticeTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A park lands only behind an identified notice, and is never written past the comment's ceiling."""

    def test_an_unidentified_notice_parks_nothing(self) -> None:
        # A notice whose id nothing could read may have reached nobody, so no
        # park lands behind it and none is reported: the verdict waits as it
        # was, and the later tick that finishes it parks behind a notice that
        # is identified. A verdict with no room to persist leaves none waiting.
        for park, reply, waiting, options in _EVERY_PARK:
            with self.subTest(park):
                left = self._unidentified(*reply, **options)
                self.assertEqual(left, ((None, False), waiting, []))
                if waiting is not None:
                    self.finishes(**options)
                    self.assertEqual(self._parked(), ((park, True), None, [park]))

    def test_a_park_remeasures_what_moved_behind_it(self) -> None:
        # Another road settles a later report behind the notice, retires the
        # verdict, and leaves the comment a valid body at its ceiling: the
        # write carrying all of that beside the notice's ledger entry and
        # watermark would not fit, so the park writes nothing and the comment
        # stays as that road wrote it.
        for park, reply, _waiting, options in _EVERY_PARK:
            with self.subTest(park):
                left = self._filled_behind(*reply, **options)
                self.assertEqual(left, (self.written, MAX_PINNED_BODY, []))

    def _unidentified(self, message: str, filled: int, notice: str, **options) -> tuple:
        """What the park `message` earns over `filled` notes leaves where its `notice` is posted with no id.

        As `_parked` reads it.
        """
        self.setUp()
        self._fills(filled)
        unidentified = _RefusesOnce(self.github.comment, notice, lands=True)
        with patch.object(self.github, ISSUE_COMMENT, unidentified):
            self.returns(message, **options)
        return self._parked()

    def _filled_behind(self, message: str, filled: int, notice: str, **options) -> tuple:
        """What the park `message` earns over `filled` notes leaves where another road fills the comment behind it.

        The pinned comment, its length, and every park reported.
        """
        self.setUp()
        self._fills(filled)
        behind = _world.AnotherRoadBehind(self, ISSUE_COMMENT, lambda body: notice in body, self._fills_it)
        behind.returning(message, **options)
        standing = self.pinned()
        return (standing, len(pinned_state_body(standing)), self._parked()[2])

    def _parked(self) -> tuple:
        """The park the pinned comment records, the verdict it leaves waiting, and every park reported."""
        pinned = self.pinned()
        return (
            (pinned.get(_world.PARK_REASON), bool(pinned.get("awaiting_human"))),
            (pinned.get(_world.RETURNED_VERDICT) or {}).get(VERDICT),
            [event.get("reason") for event in self.github.recorded_events if event["event"] == PARK_EVENT],
        )

    def _fills_it(self, _case) -> None:
        """Another road's settlement of a later report retiring the verdict, leaving the comment at its ceiling."""
        _settles_a_later_report(self)
        state = self.github.read_pinned_state(self.issue)
        state.set(_world.RETURNED_VERDICT, None)
        self.github.write_pinned_state(self.issue, state)
        self._fills(0)
        self._fills(MAX_PINNED_BODY - len(pinned_state_body(self.pinned())))
        self.written = self.pinned()

    def _fills(self, filled: int) -> None:
        """Put `filled` characters of operator notes on the pinned comment."""
        state = self.github.read_pinned_state(self.issue)
        state.set("operator_notes", "x" * filled)
        self.github.write_pinned_state(self.issue, state)


if __name__ == "__main__":
    unittest.main()
