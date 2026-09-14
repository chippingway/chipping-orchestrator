# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Daily retry charges, bounded continuations, and expiry of the rolling window.

A standing cap refuses another charge. A granted attempt remains a separate
bounded allowance, and an unreadable window starts a fresh measured interval."""
from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.config import settings as config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    retry_park_state as _retry_park_state,
    retry_values as _retry_values,
    usage as _usage,
)


def _consume_retry_slot(state: PinnedState, *, stage: str) -> _retry_values.RetryDecision:
    """Decide whether a fresh spawn may run, and charge it when it may.

    Only fresh spawns are counted. A resume on a human reply and a recovered
    worktree's push are an unblock signal and carried-over work, not retries.

    A standing retry-cap park is the first thing asked and it refuses on its
    own, ahead of the cap and ahead of the window. What stands there was
    announced as needing a human, and every other way of getting past it is
    something no human answered: the clock passing the window, and an operator
    widening `MAX_RETRIES_PER_DAY` or turning it off entirely -- a setting
    change is not the continuation the notice asked for, and reading it as one
    would resume the workflow silently. Only `_grant_continuation` lifts it.

    Below that park, an issue a continuation has bought attempts for is
    answered from those attempts and from nothing else. The setting is not
    consulted at all there: read at spend time it would make a grant worth
    whatever the cap had become in between -- nothing, once it is turned off,
    or several attempts once it is widened -- and what a human bought is one
    attempt whenever it is taken.

    An issue with no grant on it is answered by the setting. An unbounded
    budget (`MAX_RETRIES_PER_DAY <= 0`) allows everything and keeps no
    accounting -- and drops what it finds, so that turning it off is not a
    pause on a window nobody could spend while it was off. Kept, that window
    would refuse the first spawn after the budget came back, out of a count
    charged under a setting that has been changed twice since. A bounded
    budget opens its window at the first counted attempt and reopens it once
    24h have passed.

    A refusal writes nothing. Everything durable a refusal implies is staged
    by `_stage_retry_cap_park`, which the caller runs when it has decided this
    tick is the one that parks.
    """
    if _retry_park_state._park_stands(state):
        return _retry_values.RetryDecision(
            False, stage, _bound_in_force(state),
            int(state.get(_retry_values._RETRY_COUNT) or 0),
            state.get(_retry_values._RETRY_WINDOW_START),
        )
    granted = _granted_attempts(state)
    if granted is not None:
        return _spend_granted_attempt(state, stage, granted)
    bound = config.MAX_RETRIES_PER_DAY
    if bound <= 0:
        state.data.pop(_retry_values._RETRY_WINDOW_START, None)
        state.data.pop(_retry_values._RETRY_COUNT, None)
        return _retry_values.RetryDecision(True, stage, bound, 0, None)
    if _window_is_over(state):
        state.set(_retry_values._RETRY_WINDOW_START, _usage._now_iso())
        state.set(_retry_values._RETRY_COUNT, 0)
    spent = int(state.get(_retry_values._RETRY_COUNT) or 0)
    window_start = state.get(_retry_values._RETRY_WINDOW_START)
    if spent >= bound:
        return _retry_values.RetryDecision(False, stage, bound, spent, window_start)
    state.set(_retry_values._RETRY_COUNT, spent + 1)
    return _retry_values.RetryDecision(True, stage, bound, spent + 1, window_start)


def _spend_granted_attempt(
    state: PinnedState, stage: str, granted: int,
) -> _retry_values.RetryDecision:
    """Answer an issue that runs on what a continuation bought it.

    The grant is the whole budget while it lasts: no window is renewed under
    it and no cap is read, so an attempt a human paid for is worth exactly one
    spawn whenever it is taken and whatever the setting has become since.

    A grant with nothing left in it refuses, and the caller parks on it as it
    parks on any other exhausted budget -- which is what makes the next
    attempt a human's word again rather than the clock's. The ordinary counter
    is charged beside it so the spawn a grant pays for is reported like every
    other one.
    """
    spent = int(state.get(_retry_values._RETRY_COUNT) or 0)
    window_start = state.get(_retry_values._RETRY_WINDOW_START)
    if granted <= 0:
        return _retry_values.RetryDecision(
            False, stage, _retry_values._GRANTED_ATTEMPTS, spent, window_start,
        )
    state.set(_retry_values.RETRY_CAP_CONTINUED, granted - 1)
    state.set(_retry_values._RETRY_COUNT, spent + 1)
    return _retry_values.RetryDecision(
        True, stage, _retry_values._GRANTED_ATTEMPTS, spent + 1, window_start,
    )


def _granted_attempts(state: PinnedState) -> int | None:
    """How many attempts a continuation still owes this issue, if it runs on
    one at all.

    Absent is the one answer that means "no grant": an issue nobody has
    continued carries nothing here, and the reset a publication writes spells
    the same thing as null. Both answer None and are decided by the configured
    budget, as every issue that never hit the cap is.

    Anything else PRESENT says this issue runs on grants, and from there the
    only question is how many it has left. A number is read into the range a
    continuation can produce: a bigger one a hand edit left buys the same
    single attempt, and a negative buys nothing. A value that is not a number
    at all -- `true`, `"1"`, a list -- proves no attempt, so it hands out
    none. Read instead as no grant, it would fall through to the setting and
    answer a renewal-shaped record with a whole window's worth of spawns, or
    with every spawn where the budget is off, off the strength of something
    somebody typed. `bool` is refused explicitly, since it is an `int` in this
    language and a `true` would otherwise read as an attempt still owed.

    Failing closed costs a park that asks a human, which is the same thing
    the field itself is there to ask for.
    """
    granted = state.get(_retry_values.RETRY_CAP_CONTINUED)
    if granted is None:
        return None
    if isinstance(granted, bool) or not isinstance(granted, int):
        return 0
    return min(max(granted, 0), _retry_values._GRANTED_ATTEMPTS)


def _grant_is_unspent(state: PinnedState) -> bool:
    """Whether a continuation has bought an attempt nothing has taken yet.

    A claim about the ROAD the next agent run has to take, which is why it is
    asked outside this owner at all. What a continuation buys is a fresh
    spawn -- the only run the budget counts and the only one this gate is
    consulted for -- so every seam that would instead resume a locked session
    has to stand down while one is outstanding. A resume there would run the
    agent the human paid for and leave the grant on the issue unspent, ready
    to buy a second.

    Absent and exhausted answer the same way, since neither is an attempt
    somebody is still owed: an issue with no grant is decided by the
    configured budget, and one whose grant is spent is back to being decided
    by it at the next window.
    """
    granted = _granted_attempts(state)
    return granted is not None and granted > 0


def _bound_in_force(state: PinnedState) -> int:
    """How many fresh spawns this issue is allowed at all, for the record.

    What a refusal reports, so that the notice quotes the bound the issue was
    actually held to: the attempts a continuation bought where it runs on
    those, and the configured cap everywhere else.
    """
    if _granted_attempts(state) is None:
        return config.MAX_RETRIES_PER_DAY
    return _retry_values._GRANTED_ATTEMPTS


def _window_is_over(state: PinnedState) -> bool:
    """Whether the standing window has run out, or was never readable.

    An absent, unparsable, or offset-free stamp answers True and a new window
    is opened over it: a budget nobody can account for is worse than one
    charged from now, and what stops a runaway is the park below rather than
    the clock. A naive stamp is refused rather than compared -- reading one as
    UTC would invent the very fact the comparison turns on, and no writer here
    produces one.
    """
    stamp = state.get(_retry_values._RETRY_WINDOW_START)
    if not stamp:
        return True
    try:
        opened = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return True
    if opened.tzinfo is None:
        return True
    return datetime.now(UTC) - opened > _retry_values._WINDOW
