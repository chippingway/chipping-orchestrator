# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fixtures and protocol values the shared retry-budget tests read against.

The state a live issue carries is what the budget owner is written against, so
these build it directly rather than driving a stage: what the tests pin is the
protocol every stage's gate is written on, not the gate of any one of them.
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    retry_budget as _retry_budget,
    retry_ledger as _retry_ledger,
    retry_park_state as _retry_park_state,
    retry_values as _retry_values,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import LABEL_IMPLEMENTING

ISSUE_NUMBER = 1531

CAP = 3

STAGE = "implementing"

OTHER_STAGE = "decomposing"

RETRY_CAP_EVENT = "retry_cap"

WATERMARK = 900

ELAPSED_HOURS = 25

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

RETRY_COUNT = "retry_count"

RETRY_WINDOW_START = "retry_window_start"

LAST_ACTION_COMMENT_ID = "last_action_comment_id"

AGENT_QUESTION = "agent_question"

# The sentence a park in these fixtures has still to say.
NOTICE = "hit retry cap (3/day) for x"

# The login the fake client posts under, and so the only author a receipt this
# orchestrator reads back off a thread may carry.
BOT_LOGIN = "orchestrator"

OUTSIDER = "stranger"

CONTINUED = _retry_values.RETRY_CAP_CONTINUED

_RETRY_CAP_STAGE = _retry_values.RETRY_CAP_STAGE


def state_with(**fields) -> PinnedState:
    return PinnedState(comment_id=1, data=dict(fields))


def parked_state(**fields) -> PinnedState:
    """An issue standing on an announced retry-cap park.

    Every field is overridable, including the ones that make the park what it
    is: what a hand-edited or older pinned comment leaves behind is exactly
    what the safe defaults are read against.
    """
    standing = {
        AWAITING_HUMAN: True,
        PARK_REASON: _retry_values.PARK_RETRY_CAP,
        _RETRY_CAP_STAGE: STAGE,
        RETRY_COUNT: CAP,
    }
    return state_with(**{**standing, **fields})


def decide(state: PinnedState, *, stage: str = STAGE, cap: int = CAP):
    """One gate call under a pinned cap, so no env override reaches it."""
    with patch.object(config, "MAX_RETRIES_PER_DAY", cap):
        return _retry_ledger._consume_retry_slot(state, stage=stage)


def staged_park(
    state: PinnedState, *, stage: str = STAGE, cap: int = CAP,
) -> bool:
    """A refused tick's whole durable half: the decision, then the park.

    Answers what the park staging does -- whether the thread is now owed a
    sentence.
    """
    return _retry_budget._stage_retry_cap_park(
        state, decide(state, stage=stage, cap=cap),
    )


def issue_and_client(*comments):
    gh = FakeGitHubClient()
    issue = make_issue(ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
    issue.comments.extend(comments)
    gh.add_issue(issue)
    return gh, issue


def owed(state: PinnedState) -> str | None:
    return _retry_park_state._owed_notice(state)


def phases(gh) -> list:
    return [
        record["phase"]
        for record in gh.recorded_events
        if record["event"] == RETRY_CAP_EVENT
    ]
