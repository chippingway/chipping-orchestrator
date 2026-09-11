# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A late agent attempt and the retry accounting its pre-spawn write must omit.

The attempt identity is durable before the process starts, while its retry
charge stays in memory until a completion is recorded. Close-latch checks
restore the unspent counters before cancellation can write them.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split.models import (
    LatePhase,
)
from orchestrator.workflow.stages.decomposition import (
    late_owner as _late_owner,
    late_park_state as _late_park_state,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateContext,
    _LateDisposition,
    _LateRun,
)

# The per-issue accounting the pre-spawn write leaves exactly as it found it:
# every field the shared gate charges a fresh spawn against, which is what
# this has to mirror rather than a subset of. They move together -- an expired
# window is reopened at zero before the count is incremented, and the attempt
# a continuation bought is decremented beside that same count -- so a set
# missing one of them refunds half a spend: the run this tick then declines
# would cost the issue a human's continuation while handing its counters back.
_ACCOUNTING_FIELDS = (
    "retry_count", "retry_window_start", "retry_cap_continued",
)


def _latched_stop(
    context: _LateContext, unspent: dict,
) -> _LateDisposition | None:
    """Ask the close latch with the retry accounting handed back.

    The latch is asked twice on the way to a spawn, and both times the slot
    this tick charged is sitting in memory: the gate takes it before the
    first, and `_begin` puts it back on after the write it holds it out of.
    A latch that fires ends the cycle with a write of its own -- and what
    that write would carry is a spend for an agent that never started, which
    is the one thing a declined run may not leave behind. The attempt a
    continuation bought is spent by the same gate, so it is handed back by
    the same move.

    Put on again only where the tick goes on to spawn. Where it stops, the
    accounting stays as the issue had it and the cancellation records exactly
    that.
    """
    spent = _accounting(context.state)
    _apply_accounting(context.state, unspent)
    stopped = _late_owner._latch_stops(context)
    if stopped is None:
        _apply_accounting(context.state, spent)
    return stopped


def _begin(
    context: _LateContext, run: _LateRun, unspent: dict,
) -> None:
    """Record what this run IS, and the phase it reached, before it starts.

    Deliberately NOT the accounting. The identity of the attempt has to be
    durable before the agent starts -- it is what a crashed tick reads back
    instead of paying for a second run -- but the retry slot this run holds
    must not be, because a run the tick then declines is one every other stage
    drops by returning without writing. Flushing the slot here would spend the
    issue's daily budget on a run whose outcome nothing kept, so a shutdown
    sweep landing on late adjudication over and over could exhaust the cap
    without ever producing an answer. So the write goes out with the counters
    as they stood, and the increment becomes durable only on a path that
    records what the run decided.
    """
    # Past this point the tick has an agent's answer to report, so a park it
    # takes is news even when it carries the reason the last one did: a second
    # question is a different question. What the retired-park memory quiets is
    # the reconciliation retry that spawned nothing and found the same wall.
    context.retired_park = None
    context.generation = context.generation.at_phase(LatePhase.ADJUDICATING)
    _late_session._record_late_spawn(context.state, run)
    spent = _accounting(context.state)
    _apply_accounting(context.state, unspent)
    _late_park_state._persist(context)
    _apply_accounting(context.state, spent)


def _accounting(state: PinnedState) -> dict:
    """The per-issue retry accounting as it stands, for a write to leave out."""
    return {name: state.get(name) for name in _ACCOUNTING_FIELDS}


def _apply_accounting(state: PinnedState, accounting: dict) -> None:
    """Put the retry accounting back to exactly the values captured.

    A field that was absent is dropped rather than written as null, so a
    round trip through here leaves the pinned comment as it found it.
    """
    for name, counted in accounting.items():
        if counted is None:
            state.data.pop(name, None)
        else:
            state.set(name, counted)
