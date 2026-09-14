# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The contract each discussion prompt makes with its agent.

Each clause here is one the stage would be pointless without: an agent that
asks a human for facts `git log` answers burns a round, one that returns a
single answer instead of a tree hides the decision, one that asks about naming
crowds out the architecture, one that asks everything at once asks for
decisions its own earlier answers may moot, and one that starts implementing
has taken the confirmation this stage exists to wait for.

The resume prompt is held to the same contract plus the one clause only it can
break. A round that read the humans' answers as agreement and stopped there
would end the conversation without advancing it, so what it is asked for is
the tree redrawn around what those answers settled and the frontier they
opened up -- and the no-write rule is restated, since an answered design
question is the moment an agent is likeliest to decide it may now build.

Both carry the plan clause, and both are checked for it. The confirmation can
land on either -- an opening prompt is also what a round with no session to
resume is given, however many rounds in that happens -- and the clause has to
name the same single path, the same "nothing else", and the same "do not push"
that the publication check enforces, or a plan written to the letter of the
prompt is refused by the orchestrator that asked for it.
"""

from __future__ import annotations

import unittest

from orchestrator.workflow.engine import conversation_prompts as _conversation_prompts
from tests.support.fakes import FakeComment, FakeUser, make_issue
from tests.workflow.fixtures import _TEST_SPEC

_PROMPT_ISSUE_NUMBER = 950
_ISSUE_TITLE = "give the sink its own schema"
_ISSUE_BODY = "the writer and the sink disagree about who owns the columns"
_THREAD_TEXT = "@alice: this decides the migration story too"
_REPLY_AUTHOR = "alice"
_REPLY_BODY = "1: own it. 2: overruled, keep the shim."
_REPLY_ID = 4200
_PLAN_PATH = f"plans/issue-{_PROMPT_ISSUE_NUMBER}.md"

# The one write a confirmed discussion earns, stated in both prompts. Each
# clause is a bound the orchestrator enforces after the fact: a plan committed
# with anything beside it is refused whole, so an agent told less than this
# would lose the round it spent writing it.
_REQUIRED_PLAN_CLAUSES = (
    # Only an explicit shared understanding unlocks the write.
    "understand the design the same way",
    "Once they have confirmed exactly that -- and only then",
    # The path, and everything the plan has to carry.
    f"`{_PLAN_PATH}` and COMMIT that file",
    "decisions the thread resolved and what each one rules out",
    "evidence and research behind them",
    "alternatives you considered and why they lost",
    "risks and how each would show up",
    "implementation plan that follows",
    # Exactly one file, and the orchestrator publishes it.
    "Commit that ONE file and nothing else",
    "no code, no configuration, no second plan",
    "do NOT push it or open a pull request",
    "publishes it for review itself",
    "A commit that touches anything else publishes nothing",
)

# One clause per thing a resumed round has to do that an opening one does not.
_REQUIRED_FOLLOWUP_CLAUSES = (
    # The humans' answers are decisions, not suggestions to re-argue.
    "Their answers settle the questions those answers cover",
    "even where you recommended otherwise",
    # The tree is redrawn around them rather than re-derived from scratch.
    "Fold the answers back into the design tree you already have",
    "expand the branches those answers have opened up",
    # A new frontier, with the settled questions gone from it.
    "NUMBERED list of the questions answerable right now",
    "already answered earns none at all",
    "your own recommended answer",
    "If nothing is left open",
    # Answering a question is not the confirmation to start building.
    "MUST NOT modify, create, delete, commit, or push any file",
    "MUST NOT start implementing",
    "an answered question is not the confirmation to begin",
    "Unless the reply above states explicitly",
)

# One clause per thing the round has to do, quoted from the prompt so a
# rewrite that drops the behavior fails here rather than in production.
_REQUIRED_CLAUSES = (
    # Research the repository rather than interviewing the human about it.
    "Research the repository yourself first",
    "Do NOT ask a human for a fact you can read",
    # Explore openly, including the option the code does not suggest, and
    # name the research that would change the answer.
    "as a tree rather than as a single answer",
    "at least one unconventional option",
    "Name any research worth doing",
    # Architecture decisions, not implementation trivia.
    "Keep it at the architecture level",
    "implementation trivia",
    # A numbered, currently-answerable frontier with recommendations.
    "NUMBERED list of the questions that can be answered right",
    "does not depend on another question you are also asking",
    "your own recommended answer",
    # Nothing happens until a human says so.
    "MUST NOT modify, create, delete, commit, or push any file",
    "MUST NOT start implementing",
    "Until a human states explicitly on this thread",
    "nothing is settled and no work begins",
)


class DiscussionPromptTest(unittest.TestCase):

    def setUp(self) -> None:
        self.prompt = _conversation_prompts._build_discussion_prompt(
            _TEST_SPEC,
            make_issue(
                _PROMPT_ISSUE_NUMBER, title=_ISSUE_TITLE, body=_ISSUE_BODY,
            ),
            _THREAD_TEXT,
            [_TEST_SPEC],
            _PLAN_PATH,
        )

    def test_every_clause_reaches_the_agent(self) -> None:
        for clause in (*_REQUIRED_CLAUSES, *_REQUIRED_PLAN_CLAUSES):
            with self.subTest(clause=clause):
                self.assertIn(clause, self.prompt)

    def test_round_is_framed_as_a_discussion(self) -> None:
        self.assertIn(
            f"architecture discussion on GitHub issue #{_PROMPT_ISSUE_NUMBER}",
            self.prompt,
        )
        self.assertIn(_ISSUE_TITLE, self.prompt)
        self.assertIn("Nobody has asked you to implement anything", self.prompt)

    def test_a_settled_question_is_not_asked_again(self) -> None:
        # This prompt is also what a round with no session to resume is given,
        # and that round's thread already holds the answers to some of what it
        # is about to number.
        self.assertIn(
            "treat anything the conversation above has already settled as "
            "decided",
            self.prompt,
        )


class DiscussionFollowupPromptTest(unittest.TestCase):

    def setUp(self) -> None:
        self.prompt = _conversation_prompts._build_discussion_followup_prompt(
            [
                FakeComment(
                    id=_REPLY_ID,
                    body=_REPLY_BODY,
                    user=FakeUser(_REPLY_AUTHOR),
                ),
            ],
            _PLAN_PATH,
        )

    def test_every_clause_reaches_the_agent(self) -> None:
        for clause in (*_REQUIRED_FOLLOWUP_CLAUSES, *_REQUIRED_PLAN_CLAUSES):
            with self.subTest(clause=clause):
                self.assertIn(clause, self.prompt)

    def test_the_reply_is_quoted_with_its_author(self) -> None:
        # The agent answers a specific human by number, so who said what has
        # to survive into the prompt rather than arriving as anonymous text.
        self.assertIn(f"> @{_REPLY_AUTHOR}: {_REPLY_BODY}", self.prompt)


if __name__ == "__main__":
    unittest.main()
