# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A quota retirement the pinned comment would not take, across the ticks that owe it.

The tick that owes it is held as a live pause holds one, writing nothing over
the comment, and every developer launch after it -- in this process or one
restarted on the same host -- waits until a later reading lands it. A tick
whose own attempt could not land it launches nothing, even where a second
attempt in that tick does. The host record it is owed from is
`test_quota_retirement_host`'s.
"""
from __future__ import annotations

import importlib
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.stages.implementing import quota_record as _quota_record
from tests.workflow.stages.implementing import (
    quota_retirement_test_support as quota,
    retry_test_support as support,
)

_QUOTA = quota.QUOTA
_PINNED_SESSION = quota.PINNED_SESSION
_FRESH_SESSION = quota.FRESH_SESSION
_FRESH_LAUNCH = quota.FRESH_LAUNCH
_PARK = quota.PARK
_PARKED = quota.PARKED
_MOVED = quota.MOVED
_PIN = quota.PIN
_RECORD = quota.RECORD
_RUNS = quota.RUNS
_WATERMARK = quota.WATERMARK
_EDIT = "edit_pinned_state"
_CAPTURED = "developer_completion"
_launch = quota.launch
_retired = quota.retired


class QuotaRetirementRefusalTest(quota.QuotaTicks, unittest.TestCase):
    """A retirement the comment would not take holds the tick that owes it and
    every developer launch after it, writing nothing over the comment, until a
    later tick lands it ahead of its plan.
    """

    def test_unanswered_retirement_outlives_a_restart(self) -> None:
        # The edit landing the retirement goes unanswered while an operator
        # pauses the issue mid-run, and the poller is restarted after that
        # tick, which wrote nothing. Nothing in the restarted process remembers
        # the stop, yet its next tick, the edit still unanswered, launches
        # nothing at all: no run is charged and the reply waits under the park.
        # The stopped attempt was accounted and never captured, so no recovery
        # hands anything of it on past the withheld tick. Once the edit is
        # answered the retirement lands ahead of the plan, and the reply goes
        # to a fresh conversation.
        github, issue = self._issue(**_PARKED)
        quota.reply(github, issue, support.GUIDANCE_REPLY)
        github.pinned_failures.refused.add(quota.ISSUE)
        with self._paused(github):
            self._tick(github, issue, _QUOTA, has_new_commits=False)
        importlib.reload(_quota_record)

        held = self._replied(github, issue)

        self.assertEqual((held.call_count, github.posted_comments), (0, []), "no launch and nothing posted")
        self.assertEqual(
            self._pinned(github, _PIN, _RECORD, _RUNS, _CAPTURED, *_PARK),
            {_PIN: _PINNED_SESSION, _RECORD: None, _RUNS: 1, _CAPTURED: None, **_PARK},
        )

        github.pinned_failures.refused.clear()
        resumed = self._replied(github, issue)

        self.assertEqual(_launch(resumed), _FRESH_LAUNCH)
        self.assertEqual(
            self._pinned(github, _PIN, _RECORD, _RUNS),
            {_PIN: _FRESH_SESSION, _RECORD: _retired(pending=False), _RUNS: 2},
        )

    def test_moved_comment_keeps_its_move(self) -> None:
        # Another writer lands on the comment between the reading the
        # retirement is committed over and its edit, so the commit is refused
        # as moved, with no pause to stop the tick. The tick honors the
        # refusal: nothing it staged -- the park, its notice, the consumed
        # reply -- goes out over the other writer's field. The next tick lands
        # the retirement before it plans, and the reply goes to a fresh
        # conversation with that field still standing.
        github, issue = self._issue(**_PARKED)
        quota.reply(github, issue, support.GUIDANCE_REPLY)
        with patch.object(github, _EDIT, partial(quota.edit_after_a_move, github)):
            self._tick(github, issue, _QUOTA, has_new_commits=False)

        self.assertEqual(github.posted_comments, [])
        self.assertEqual(
            self._pinned(github, _MOVED, _PIN, _RECORD, *_PARK),
            {_MOVED: True, _PIN: _PINNED_SESSION, _RECORD: None, **_PARK},
        )

        resumed = self._replied(github, issue)

        self.assertEqual(_launch(resumed), _FRESH_LAUNCH)
        self.assertEqual(
            self._pinned(github, _MOVED, _PIN, _RECORD),
            {_MOVED: True, _PIN: _FRESH_SESSION, _RECORD: _retired(pending=False)},
        )

    def test_withheld_tick_launches_nothing(self) -> None:
        # The retirement an unanswered edit left owed fails again ahead of the
        # next resume's plan, another writer having moved the comment, and
        # lands at the launch right after it. That tick's state is withheld --
        # it could record nothing a launch leads to, neither a question nor
        # the reply it consumed -- so it makes none. The tick after it resumes
        # the reply in a fresh conversation and consumes it.
        github, issue = self._issue(**_PARKED)
        answered = quota.reply(github, issue, support.GUIDANCE_REPLY)
        github.pinned_failures.refused.add(quota.ISSUE)
        self._tick(github, issue, _QUOTA, has_new_commits=False)
        github.pinned_failures.refused.clear()

        with patch.object(github, _EDIT, partial(quota.edit_after_a_move, github)):
            held = self._replied(github, issue)

        held.assert_not_called()
        self.assertEqual(github.posted_comments, [])
        self.assertEqual(
            self._pinned(github, _MOVED, _PIN, _RECORD, *_PARK),
            {_MOVED: True, _PIN: None, _RECORD: _retired(), **_PARK},
            "the retirement landed at the launch, and nothing else the tick staged went out",
        )

        resumed = self._replied(github, issue)

        self.assertEqual(
            (_launch(resumed), self._pinned(github, _WATERMARK, _PIN)),
            (_FRESH_LAUNCH, {_WATERMARK: answered, _PIN: _FRESH_SESSION}),
            "a fresh conversation answers the reply, and the reply is consumed",
        )


if __name__ == "__main__":
    unittest.main()
