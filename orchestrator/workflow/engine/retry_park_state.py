# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The durable daily-retry park and the sentence its thread is still owed.

Reading and settling an obligation changes no launch count. The park keeps
its own stage so a later tick can reconcile the notice without running a stage."""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import retry_values as _retry_values


def _park_stands(state: PinnedState) -> bool:
    """Whether this issue is stopped, right now, on an exhausted budget.

    Both halves are asked. The flag alone is every stage's park, and the
    reason alone outlives the park a resume already cleared.
    """
    if not state.get(_retry_values._AWAITING_HUMAN):
        return False
    return state.get(_retry_values._PARK_REASON) == _retry_values.PARK_RETRY_CAP


def _park_stage(state: PinnedState) -> str | None:
    """Which stage's fresh spawn the standing park ran out of, if it says.

    An issue parked before this field existed, or hand-edited out of it,
    answers None -- the audit record drops the stage rather than reporting a
    guessed one, and the next refusal writes its own.
    """
    stage = state.get(_retry_values.RETRY_CAP_STAGE)
    return stage if isinstance(stage, str) and stage else None


def _owed_notice(state: PinnedState) -> str | None:
    """The sentence this park has still to say, if it has one.

    Anything but a non-empty string reads as nothing owed: an issue recorded
    before this field existed, and a hand-edited one, both leave a park that
    says nothing rather than a tick that raises over the shape of a note.
    """
    owed = state.get(_retry_values.RETRY_CAP_NOTICE)
    return owed if isinstance(owed, str) and owed else None


def _settle_notice(state: PinnedState) -> None:
    """Drop the obligation, however it ended.

    One name for both endings, because the field records an obligation rather
    than an event: a sentence posted to the thread and a park a continuation
    retired before anybody read it leave exactly nothing owed.
    """
    state.data.pop(_retry_values.RETRY_CAP_NOTICE, None)


def _cap_message(decision: _retry_values.RetryDecision) -> str:
    """What the park explains to the humans it stops the issue for.

    The window it opened at is quoted because that is the fact the refusal was
    made on, and the one an operator needs to tell a budget that is genuinely
    spent from a counter something left behind.
    """
    return (
        f"hit retry cap ({decision.cap}/day) for {decision.stage}; "
        f"manual intervention needed. "
        f"Window opened at {decision.window_start}."
    )
