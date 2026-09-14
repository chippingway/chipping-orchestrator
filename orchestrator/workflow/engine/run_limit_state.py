# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Durable lifetime-limit parks and the exact allowance a notice explains.

An owed notice is valid only for the count and allowance it names. A changed
ledger replaces that obligation; settlement clears the notice, never the
lifetime charge or the separate park waiting for an operator grant."""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    run_ledger_values as _run_ledger_values,
    run_limit_values as _run_limit_values,
)
from orchestrator.workflow.engine.run_ledger_models import AgentRunLedger


def _park_stands(state: PinnedState) -> bool:
    """Whether this issue is stopped, right now, on a spent lifetime ledger.

    Both halves are asked. The flag alone is every stage's park, and the
    reason alone outlives a park something has already taken down.
    """
    if not state.get(_run_limit_values._AWAITING_HUMAN):
        return False
    return state.get(_run_limit_values._PARK_REASON) == _run_limit_values.PARK_AGENT_RUN_LIMIT


def _stage_park(state: PinnedState, ledger: AgentRunLedger) -> bool:
    """Record the park a spent ledger takes, and what it owes a thread.

    In memory only, like every other field a refused tick stages: what makes
    it durable is the caller's own write, which is what keeps the park and the
    obligation it carries in one write rather than two.

    Returns whether the thread is now owed a sentence. A park already standing
    whose notice has been said is not announced again -- that repeat is the
    whole failure this protocol exists to stop, and nothing else would stop
    it, since a park is re-asked on every tick that reaches it. Nor is such a
    park rewritten: the flag and the reason under it are already what this
    refusal would say.

    A park whose sentence was never said keeps that sentence verbatim for as
    long as it is about the reading the ledger still shows. The obligation is
    a claim about a comment that may already be on the thread, and the thread
    is searched for exactly the text the park recorded, so a sentence reworded
    by a later tick would find nothing and post a second notice. A sentence
    about some other reading is the one thing worth replacing: it quotes an
    allowance or a spend this issue has moved off, and a human shown those
    numbers is being asked about a state that is over.
    """
    if not _park_stands(state):
        state.set(_run_limit_values._AWAITING_HUMAN, True)
        state.set(_run_limit_values._PARK_REASON, _run_limit_values.PARK_AGENT_RUN_LIMIT)
        _owe_notice(state, ledger)
        return True
    owed = _owed_notice(state)
    if owed is None:
        return False
    if not owed.explains(ledger):
        _owe_notice(state, ledger)
    return True


def _owed_notice(state: PinnedState) -> _run_limit_values.OwedNotice | None:
    """The sentence this park has still to say, and what it is about.

    Anything but a whole record reads as nothing owed: an issue recorded
    before this field existed, and a hand-edited one, both leave a park that
    says nothing rather than a tick that raises over the shape of a note. The
    counts are part of that record rather than decoration -- a sentence with
    no reading behind it is one nothing can hold up against the ledger, so it
    is no obligation this owner can honor.
    """
    owed = state.get(_run_limit_values.AGENT_RUN_LIMIT_NOTICE)
    if not isinstance(owed, dict):
        return None
    message = owed.get(_run_limit_values._NOTICE_MESSAGE)
    allowance = _run_ledger_values._counted(owed.get(_run_limit_values._NOTICE_ALLOWANCE))
    spent = _run_ledger_values._counted(owed.get(_run_limit_values._NOTICE_SPENT))
    if not isinstance(message, str) or not message:
        return None
    if allowance is None or spent is None:
        return None
    return _run_limit_values.OwedNotice(message=message, allowance=allowance, spent=spent)


def _owe_notice(state: PinnedState, ledger: AgentRunLedger) -> None:
    """Record this park's sentence, and the reading it was written for."""
    state.set(_run_limit_values.AGENT_RUN_LIMIT_NOTICE, {
        _run_limit_values._NOTICE_MESSAGE: _limit_message(ledger),
        _run_limit_values._NOTICE_ALLOWANCE: ledger.allowance,
        _run_limit_values._NOTICE_SPENT: ledger.used,
    })


def _settle_notice(state: PinnedState) -> None:
    """Drop the obligation, however it ended.

    One name for both endings, because the field records an obligation rather
    than an event: a sentence posted to the thread and one a park retired
    before anybody read it leave exactly nothing owed.
    """
    state.data.pop(_run_limit_values.AGENT_RUN_LIMIT_NOTICE, None)


def _limit_message(ledger: AgentRunLedger) -> str:
    """What the park explains to the humans it stops the issue for.

    Both numbers are quoted because they are the facts the refusal was made
    on, and because the allowance is not always the setting: an issue may
    carry one of its own, and a human reading a ceiling they did not
    configure needs to see the one this issue was actually held to.
    """
    return (
        f"spent this issue's lifetime agent-run allowance "
        f"({ledger.used}/{ledger.allowance} runs); manual intervention "
        f"needed. A lifetime total is spent once, so no window reopens it."
    )
