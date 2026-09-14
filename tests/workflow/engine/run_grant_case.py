# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Parked-issue setup and racing GitHub doubles for agent-run grant tests."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import (
    run_grant as _run_grant,
)
from tests.workflow.engine import (
    run_grant_test_support as grant,
    run_limit_seeds as _limit_seeds,
    run_limit_test_support as support,
)

# What somebody writes while the tick is answering the command above it. Not a
# command itself: what it stands for is any word a stage below is still owed.
_RACING_WORDS = "hold off on this until Friday please"

# What the read that builds a budget record answers with when it cannot.
_LABEL_FAILURE = "label read refused"


def _asking(body: str = grant.VALID):
    """One comment carrying a request, buyable unless the caller says else."""
    return grant.command(body)


class _RacingPost:
    """The orchestrator's own post, with somebody else's comment landing first.

    Stands in for the one window where this owner can be overtaken: the batch
    has been read, the receipt is not written yet, and the comment that
    arrives in between is one no read here has seen.
    """

    def __init__(self, gh) -> None:
        self._posting = gh.comment

    def __call__(self, issue, body):
        issue.comments.append(grant.command(
            _RACING_WORDS, comment_id=grant.RACING_COMMENT_ID,
        ))
        return self._posting(issue, body)


class _FlakyLabel:
    """The label read that answers once and fails after.

    A grant reads the label twice: the park's own audit phase asks ahead of
    the write that persists the grant, and the budget record asks on the far
    side of it. Only the second read is past the point of no return, so only
    a failure there can strand a tick that has already changed the issue.
    """

    def __init__(self, gh) -> None:
        self._reading = gh.workflow_label
        self._reads = 0

    def __call__(self, issue):
        self._reads += 1
        if self._reads > 1:
            raise RuntimeError(_LABEL_FAILURE)
        return self._reading(issue)


class _ParkCase(unittest.TestCase):
    """One issue standing on a spent ledger, and what a thread says to it."""

    def _lift(self, *comments, state=None):
        self._thread(*comments)
        self.state = grant.spent_state() if state is None else state
        return _run_grant._lifts_the_park(self.gh, self.issue, self.state)

    def _thread(self, *comments) -> None:
        client, issue = support.issue_and_client(*comments)
        self.gh = client
        self.issue = issue

    def _lost_the_write(self, *comments) -> None:
        """One tick that wrote its receipt to the thread and nothing else.

        The window every receipt here is idempotent across: the post landed,
        the write that would have consumed the command did not, and the next
        tick reads the same request off the same thread.
        """
        self._thread(*comments)
        with (
            patch.object(
                self.gh, "write_pinned_state", side_effect=RuntimeError("502"),
            ),
            self.assertRaises(RuntimeError),
        ):
            _run_grant._lifts_the_park(
                self.gh, self.issue, grant.spent_state(),
            )

    def _replayed(self):
        """The next tick, reading pinned state the lost write never moved."""
        self.state = grant.spent_state()
        return _run_grant._lifts_the_park(self.gh, self.issue, self.state)

    def _lift_racing(self, *comments):
        """One tick answering a command while the thread grows under it.

        The only window in which it can: the batch is read once, and the
        receipt is written after that read.
        """
        self._thread(*comments)
        self.state = grant.spent_state()
        with patch.object(
            self.gh, "comment", side_effect=_RacingPost(self.gh),
        ):
            return _run_grant._lifts_the_park(
                self.gh, self.issue, self.state,
            )

    def _recorded(self) -> dict:
        return self.gh.pinned_data(support.ISSUE_NUMBER)

    def _assert_ledger_untouched(self) -> None:
        self.assertNotIn(support.ALLOWANCE_FIELD, self.state.data)
        self.assertEqual(self.state.get(support.USED_FIELD), _limit_seeds.ALLOWANCE)
