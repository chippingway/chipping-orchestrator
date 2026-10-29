# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The accounting checkpoint over the real client's walk of an issue thread.

Driven over the PyGithub-shaped issue and comment doubles, so every read and
the strict edit the checkpoint lands through walk the thread as production
does: the record is the first comment of the bot's that reads as one, and an
operator can turn an earlier comment into that record at any moment, the
issue's writer claim notwithstanding.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from dataclasses import dataclass
from unittest.mock import patch

from orchestrator.workflow.engine import usage_checkpoint as _usage_checkpoint
from tests.github.pinned_state_test_support import BOT, bot_comment, marker, state_client
from tests.support.fakes import FakeComment, FakeUser, make_issue
from tests.workflow.engine import usage_checkpoint_test_support as support

_EARLIER_ID = 1
_CHARGED_ID = 2
_RECORD_BODY = marker({"agent_runs_used": 1})
_ORDINARY = "an ordinary comment of the bot's"
_WALK = "_pinned_comment"


@dataclass
class _DisplacedOnWalk:
    """The strict edit's walk of the thread, behind an operator turning the earlier comment into a record."""

    walk: Callable
    earlier: FakeComment

    def __call__(self, *walked, **asked):
        self.earlier.edit(_RECORD_BODY)
        return self.walk(*walked, **asked)


class DisplacedRecordTest(unittest.TestCase):
    """A run is accounted only on the comment that is still the issue's record when the edit lands."""

    def setUp(self) -> None:
        self.client = state_client()
        self.client._repo_slug = support.REPO
        self.earlier = FakeComment(_EARLIER_ID, _ORDINARY, FakeUser(BOT))
        self.charged = bot_comment(_CHARGED_ID, _RECORD_BODY)
        self.issue = make_issue(support.ISSUE, comments=[self.earlier, self.charged])
        self.ran = support.invoked(support.invocation(1, comment=_CHARGED_ID))

    def test_the_charged_record_is_accounted(self) -> None:
        state = self.client.read_pinned_state(self.issue)

        outcome = _usage_checkpoint.checkpoint(self.client, self.issue, state, self.ran)

        landed = self.client.read_pinned_state(self.issue)
        self.assertIs(outcome.status, support.STATUS.ACCOUNTED)
        self.assertEqual(landed.comment_id, _CHARGED_ID)
        self.assertEqual(support.counted(landed.state_data), support.ONE_RUN)

    def test_a_displaced_record_settles_nothing(self) -> None:
        # The bot's earlier comment is turned into a record behind the
        # commit's own reading, right before the edit walks the thread: the
        # charged comment is no longer the record any reader takes, so
        # nothing is laid on it or on the record ahead of it.
        state = self.client.read_pinned_state(self.issue)
        displaced = _DisplacedOnWalk(self.client._pinned_comment, self.earlier)

        with patch.object(self.client, _WALK, side_effect=displaced):
            outcome = _usage_checkpoint.checkpoint(self.client, self.issue, state, self.ran)

        self.assertEqual((outcome.status, outcome.settled), (support.STATUS.REFUSED, False))
        self.assertEqual((self.earlier.body, self.charged.body), (_RECORD_BODY, _RECORD_BODY))
        self.assertNotIn(support.RUNS, state.state_data)


if __name__ == "__main__":
    unittest.main()
