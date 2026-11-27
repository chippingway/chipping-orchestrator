# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the park over a run that committed and reported nothing quotes of that run.

A developer that committed part of the work and needs a human's decision on the
rest ends on its question with no report, so the run's last message is what the
reply to that park has to answer. It is quoted whole wherever one comment
carries it, and held to the rule every comment of this orchestrator's keeps: no
receipt marker in its raw text, since a comment of ours carrying one reads as
the step it names.
"""

from __future__ import annotations

import unittest

from orchestrator.github.comments import ORCHESTRATOR_COMMENT_MARKER, RECEIPT_MARKER_PREFIX
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from tests.workflow.engine import report_commit_test_support as commit_support
from tests.workflow.fixtures import _agent

# How the notice opens its quote of the run's last message, and what it says
# where only the end of that message fits.
_QUOTE_HEADING = "The developer's last message"

_CUT = "cut to the end of it that fits in this comment"

# A decision whose question and first choice open the message and whose second
# choice closes it, with an account between them far longer than the budget a
# report body is asked to keep under, and still far inside one comment.
_ASKED = "Who should land the retry fix?"

_FIRST_CHOICE = "1. I can open a separate pull request."

_SECOND_CHOICE = "2. You can land it directly and I can rebase."

_ACCOUNT_SENTENCES = 80

_ACCOUNT = "The retry change is independent of the validation fix. " * _ACCOUNT_SENTENCES

# A choice naming the receipt prefix, which the raw comment may not carry and
# the human still has to read.
_MARKER_CHOICE = f"1. Keep matching `{RECEIPT_MARKER_PREFIX}` as it is."

# What the notice quotes of each last message, and what it may not.
_QUOTED_MESSAGES = (
    ("nothing at all", " \n ", (), (_QUOTE_HEADING,)),
    (
        "a decision around a long account",
        f"{_ASKED}\n\n{_FIRST_CHOICE}\n\n{_ACCOUNT}\n\n{_SECOND_CHOICE}",
        (f"> {_ASKED}", f"> {_FIRST_CHOICE}", f"> {_SECOND_CHOICE}"),
        (_CUT,),
    ),
    (
        "a choice naming the receipt prefix",
        f"{_ASKED}\n\n{_MARKER_CHOICE}\n{_SECOND_CHOICE}",
        (
            f"> {_ASKED}",
            "> 1. Keep matching `&lt;!--orchestrator-` as it is.",
            f"> {_SECOND_CHOICE}",
        ),
        (),
    ),
)

# The decision an oversized message ends on, as the prompt asks.
_DECISION = f"{_ASKED}\n\n{_FIRST_CHOICE}\n{_SECOND_CHOICE}"

# Heads one comment cannot carry before that decision, and how short of the
# ceiling the cut notice may fall. With no line breaks every character cut
# shortens the comment by exactly one, so the cut is exact; across many short
# lines the character just past the cut may be a break, which spends its
# blockquote prefix too -- and counted as one character apiece, those breaks
# would cut the decision away with the head.
_OVERSIZED_HEADS = (
    ("no line breaks", "x" * MAX_PINNED_BODY, 1),
    ("many short lines", "x\n" * (MAX_PINNED_BODY // 2), len("\n> ")),
)


class UnreportedRunNoticeTest(unittest.TestCase):
    """The quote of the run's last message, at its edges."""

    def test_the_last_message_is_quoted_whole(self) -> None:
        # A run that said nothing gets no empty quote. A decision is quoted
        # whole wherever the comment carries it, however long the account
        # between its choices. A receipt prefix is escaped rather than
        # dropped, so the choice naming it still reads while the raw comment
        # carries no receipt of ours.
        for described, message, said, unsaid in _QUOTED_MESSAGES:
            with self.subTest(message=described):
                notice = _notice(self, message)

                self.assertEqual(
                    (
                        [fragment for fragment in said if fragment not in notice],
                        [fragment for fragment in unsaid if fragment in notice],
                        RECEIPT_MARKER_PREFIX in notice.replace(ORCHESTRATOR_COMMENT_MARKER, ""),
                    ),
                    ([], [], False),
                )

    def test_a_message_past_the_comment_keeps_its_end(self) -> None:
        # Past what GitHub accepts in one comment, the head goes and the end
        # the prompt puts the decision in stays -- cut to the ceiling, the
        # notice's own words, the blockquote prefixes, and the comment marker
        # counted, so nothing is dropped that the comment had room for.
        for described, head, slack in _OVERSIZED_HEADS:
            with self.subTest(head=described):
                notice = _notice(self, f"{head}\n{_DECISION}")

                self.assertEqual(
                    (
                        [line for line in _DECISION.splitlines() if line and f"> {line}" not in notice],
                        _CUT in notice,
                        MAX_PINNED_BODY - len(notice) in range(slack),
                    ),
                    ([], True, True),
                )


def _notice(case: unittest.TestCase, message: str) -> str:
    """The comment the park over a finished run ending on `message` posts, as posted."""
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
