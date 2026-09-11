# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The decomposer and conversation roads that reach a process, and how each runs.

The sibling table beside this one carries the developer and the reviewer; this
one carries the three roles that TALK -- the decomposer deciding whether an
issue is one piece of work, the question stage answering somebody, and the
discussion stage arguing a design out. Each is here twice, because a
conversation's first round and the round a human's reply reopens are different
roads through the same handler, and only one of them carries a session to
resume, a park to clear, and a batch of replies to mark as read.

What is worth driving a real handler for is the same as it is there: the
charge is taken at one boundary, so what a road has to be held to is that it
GOES through that boundary carrying the issue it is spending. And these three
add a second thing to hold. Each stages something ahead of its spawn that its
own disposition owns -- a locked agent spec, a reply batch marked read, the
anchor a round opened on -- and none of it may be published by the charge that
lands in between.

The late adjudicator is the one decomposing road not in this table. It is not
a dispatched handler and runs inside a harness of its own, so its case lives
beside it in `tests/workflow/stages/decomposition/test_late_charged_run.py`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import MappingProxyType

from orchestrator import config
from orchestrator.workflow.stages.decomposition import run as _decomposing
from orchestrator.workflow.stages.discussion import handler as _discussion
from orchestrator.workflow.stages.question import handler as _question
from tests.workflow import fixtures as _support
from tests.workflow.engine.charged_run_test_support import (
    SHA_BEFORE,
    ChargedRoad,
    Driven,
    human_reply,
    seed_issue,
)

DECOMPOSING_FRESH_ISSUE = 1580
DECOMPOSING_RESUME_ISSUE = 1581
QUESTION_FRESH_ISSUE = 1582
QUESTION_RESUME_ISSUE = 1583
DISCUSSION_FRESH_ISSUE = 1584
DISCUSSION_RESUME_ISSUE = 1585

# Where on the thread each parked road was left. Seeded rather than produced
# by running a first round, so the reply below is new by a margin no park's own
# stamp can close -- and so a watermark that did NOT move reads as this number
# rather than as whatever the last tick happened to leave.
PARKED_WATERMARK = 51000

REPLY_ID = PARKED_WATERMARK + 1000

# The pinned-state fields the seeds below share. Wire strings on live issues,
# so they are spelled once here rather than retyped per road.
_KEY_AWAITING_HUMAN = "awaiting_human"
_KEY_DECOMPOSER_AGENT = "decomposer_agent"
_KEY_DECOMPOSER_SESSION_ID = "decomposer_session_id"
_KEY_DISCUSSION_AGENT = "discussion_agent"
_KEY_DISCUSSION_BASE_SHA = "discussion_base_sha"
_KEY_DISCUSSION_ROUND_BRANCH = "discussion_round_branch"
_KEY_DISCUSSION_ROUND_SHA = "discussion_round_sha"
_KEY_DISCUSSION_SESSION_ID = "discussion_session_id"
_KEY_LAST_ACTION_COMMENT_ID = "last_action_comment_id"
_KEY_PARK_REASON = "park_reason"
_KEY_QUESTION_AGENT = "question_agent"
_KEY_QUESTION_SESSION_ID = "question_session_id"

_PARK_DISCUSSION_RESPONSE = "discussion_response"
_PARK_QUESTION_ANSWER = "question_answer"

_DECOMPOSER_SESSION = "dec-sess"
_DISCUSSION_SESSION = "d-sess"
_QUESTION_SESSION = "q-sess"

# A manifest that ends the decomposition in one decision, so both decomposer
# roads reach a disposition and the write carrying it rather than a park.
_SINGLE_MANIFEST = _support._manifest('{"decision": "single", "rationale": "fits"}')

# A round that neither commits nor moves the checkout off the SHA it opened
# on. What these cases are about is the charge, and a head that moved would
# drag the publication gate into every one of them.
_UNMOVED_HEAD = MappingProxyType({"head_shas": (SHA_BEFORE,)})


@dataclass(frozen=True)
class _Conversation:
    """One road's world, and the single tick of its handler that runs in it.

    The seed and the drive are one object because neither says anything
    without the other: what a resumed road stages -- the park, the pinned
    session, the thread position its replies are read after -- is exactly what
    decides which branch of the handler the tick takes.
    """

    number: int
    label: str
    run_stage: Callable
    stage: dict = field(default_factory=dict)
    comments: tuple = ()
    run_options: MappingProxyType = MappingProxyType({})

    def drive(self, case, agent_result, **state) -> Driven:
        """Seed this road's issue, run one tick over it, and report both."""
        github, issue = seed_issue(
            self.number,
            label=self.label,
            comments=self.comments,
            stage=self.stage,
            **state,
        )
        mocks = case._run(
            lambda: self.run_stage(github, _support._TEST_SPEC, issue),
            run_agent=agent_result,
            **self.run_options,
        )
        return Driven(github, mocks, self.number)


DECOMPOSING_FRESH = ChargedRoad(
    role="decomposing-fresh",
    number=DECOMPOSING_FRESH_ISSUE,
    label=_support.LABEL_DECOMPOSING,
    drive=_Conversation(
        number=DECOMPOSING_FRESH_ISSUE,
        label=_support.LABEL_DECOMPOSING,
        run_stage=_decomposing._handle_decomposing,
    ).drive,
    agent_result=_support._agent(
        session_id=_DECOMPOSER_SESSION, last_message=_SINGLE_MANIFEST,
    ),
)

DECOMPOSING_RESUME = ChargedRoad(
    role="decomposing-resume",
    number=DECOMPOSING_RESUME_ISSUE,
    label=_support.LABEL_DECOMPOSING,
    drive=_Conversation(
        number=DECOMPOSING_RESUME_ISSUE,
        label=_support.LABEL_DECOMPOSING,
        run_stage=_decomposing._handle_decomposing,
        comments=(human_reply("please split it", comment_id=REPLY_ID),),
        stage={
            _KEY_AWAITING_HUMAN: True,
            _KEY_LAST_ACTION_COMMENT_ID: PARKED_WATERMARK,
            _KEY_DECOMPOSER_AGENT: _support.BACKEND_CLAUDE,
            _KEY_DECOMPOSER_SESSION_ID: _DECOMPOSER_SESSION,
        },
    ).drive,
    agent_result=_support._agent(
        session_id=_DECOMPOSER_SESSION, last_message=_SINGLE_MANIFEST,
    ),
)

QUESTION_FRESH = ChargedRoad(
    role="question-fresh",
    number=QUESTION_FRESH_ISSUE,
    label=_support.LABEL_QUESTION,
    drive=_Conversation(
        number=QUESTION_FRESH_ISSUE,
        label=_support.LABEL_QUESTION,
        run_stage=_question._handle_question,
    ).drive,
    agent_result=_support._agent(
        session_id=_QUESTION_SESSION, last_message="it lives in the engine",
    ),
)

QUESTION_RESUME = ChargedRoad(
    role="question-resume",
    number=QUESTION_RESUME_ISSUE,
    label=_support.LABEL_QUESTION,
    drive=_Conversation(
        number=QUESTION_RESUME_ISSUE,
        label=_support.LABEL_QUESTION,
        run_stage=_question._handle_question,
        comments=(human_reply("one more thing", comment_id=REPLY_ID),),
        stage={
            _KEY_AWAITING_HUMAN: True,
            _KEY_PARK_REASON: _PARK_QUESTION_ANSWER,
            _KEY_LAST_ACTION_COMMENT_ID: PARKED_WATERMARK,
            _KEY_QUESTION_AGENT: _support.BACKEND_CLAUDE,
            _KEY_QUESTION_SESSION_ID: _QUESTION_SESSION,
        },
    ).drive,
    agent_result=_support._agent(
        session_id=_QUESTION_SESSION, last_message="and so does its park",
    ),
)

DISCUSSION_FRESH = ChargedRoad(
    role="discussion-fresh",
    number=DISCUSSION_FRESH_ISSUE,
    label=_support.LABEL_DISCUSSION,
    drive=_Conversation(
        number=DISCUSSION_FRESH_ISSUE,
        label=_support.LABEL_DISCUSSION,
        run_stage=_discussion._handle_discussion,
        run_options=_UNMOVED_HEAD,
    ).drive,
    agent_result=_support._agent(
        session_id=_DISCUSSION_SESSION, last_message="two branches, then",
    ),
)

DISCUSSION_RESUME = ChargedRoad(
    role="discussion-resume",
    number=DISCUSSION_RESUME_ISSUE,
    label=_support.LABEL_DISCUSSION,
    drive=_Conversation(
        number=DISCUSSION_RESUME_ISSUE,
        label=_support.LABEL_DISCUSSION,
        run_stage=_discussion._handle_discussion,
        comments=(human_reply("take the second one", comment_id=REPLY_ID),),
        stage={
            _KEY_AWAITING_HUMAN: True,
            _KEY_PARK_REASON: _PARK_DISCUSSION_RESPONSE,
            _KEY_LAST_ACTION_COMMENT_ID: PARKED_WATERMARK,
            _KEY_DISCUSSION_AGENT: config.DECOMPOSE_AGENT_SPEC,
            _KEY_DISCUSSION_SESSION_ID: _DISCUSSION_SESSION,
            _KEY_DISCUSSION_ROUND_BRANCH: _support._issue_branch(
                DISCUSSION_RESUME_ISSUE,
            ),
            _KEY_DISCUSSION_ROUND_SHA: SHA_BEFORE,
            _KEY_DISCUSSION_BASE_SHA: _support.BASE_TIP_SHA,
        },
        run_options=_UNMOVED_HEAD,
    ).drive,
    agent_result=_support._agent(
        session_id=_DISCUSSION_SESSION, last_message="the second one, then",
    ),
)

# Every road a decomposer or a conversation reaches an agent through: each
# stage's opening round, and the round a human's reply reopens.
ROADS = (
    DECOMPOSING_FRESH,
    DECOMPOSING_RESUME,
    QUESTION_FRESH,
    QUESTION_RESUME,
    DISCUSSION_FRESH,
    DISCUSSION_RESUME,
)

# The three of those a human's reply reopens. Each marks the batch it quotes
# as read before it spawns, and none of it is durable until the round reports
# what it made of those replies.
RESUMED_ROADS = (DECOMPOSING_RESUME, QUESTION_RESUME, DISCUSSION_RESUME)
