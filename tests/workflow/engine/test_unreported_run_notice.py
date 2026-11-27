# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the park over a run that committed and reported nothing quotes of that run.

A developer that committed part of the work and needs a human's decision on the
rest ends on its question with no report, so the run's last message is what the
reply to that park has to answer. The quote is bounded and held to the rule
every notice of this orchestrator's keeps: a receipt marker is described, never
quoted, since a comment of ours carrying one reads as the step it names.
"""

from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from tests.workflow import report_refusals as _refusals
from tests.workflow.engine import report_commit_test_support as commit_support
from tests.workflow.fixtures import _agent

# How the notice opens its quote of the run's last message, and the question a
# quoted message ends on.
_QUOTE_HEADING = "The developer's last message"

_ASKED = "Which of the two fixes should land on the base branch first?"

# A message's head long enough that the question after it is past the budget.
_PADDING = "x" * _refusals.WRITING_BUDGET

_CUT = f"cut to its last {_refusals.WRITING_BUDGET:,} characters"

# What the notice quotes of each last message, and what it may not: nothing for
# a run that said nothing, prose rather than a receipt, and the tail of a
# message past the budget a report body is asked to keep under.
_QUOTED_MESSAGES = (
    ("nothing at all", " \n ", (), (_QUOTE_HEADING,)),
    (
        "a receipt",
        f"Keep `{_refusals.QUOTED_RECEIPT}` as it is? {_ASKED}",
        ("is not quoted here", "described in prose"),
        (_refusals.QUOTED_RECEIPT, _ASKED),
    ),
    (
        "a message past the budget",
        f"{_PADDING}\n{_ASKED}",
        (f"> {_ASKED}", _CUT),
        (_PADDING,),
    ),
)


class UnreportedRunNoticeTest(unittest.TestCase):
    """The quote of the run's last message, at its edges."""

    def test_the_last_message_is_quoted_within_bounds(self) -> None:
        # A run that said nothing gets no empty quote; a message carrying a
        # receipt is described rather than quoted; and a message past the
        # budget keeps its tail, where the prompt puts the question.
        for described, message, said, unsaid in _QUOTED_MESSAGES:
            with self.subTest(message=described):
                notice = _notice(self, message)

                self.assertEqual(
                    (
                        [fragment for fragment in said if fragment not in notice],
                        [fragment for fragment in unsaid if fragment in notice],
                    ),
                    ([], []),
                )


def _notice(case: unittest.TestCase, message: str) -> str:
    """The notice the park over a finished run ending on `message` posts."""
    stopped, _github, issue = commit_support.records(
        PinnedState(), _agent(last_message=message),
    )
    case.assertTrue(stopped)
    return next(
        posted.body for posted in issue.comments
        if "developer run finished" in (posted.body or "")
    )


if __name__ == "__main__":
    unittest.main()
