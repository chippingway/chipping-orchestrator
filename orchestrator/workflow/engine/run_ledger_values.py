# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Validated pinned fields for the lifetime agent-run ledger.

The used count is floored by the legacy usage meter. Missing allowances defer
to configuration, and malformed counts or reservation phases grant no evidence."""
from __future__ import annotations

from typing import Any

from orchestrator.config import settings as config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import run_ledger_models as _run_ledger_models

# The ceiling in force on THIS issue, where the issue carries one of its own.
# Absent -- which is every issue nobody has decided anything special about --
# means `MAX_AGENT_RUNS_PER_ISSUE` governs and is read live. Present and
# readable, it governs instead and the setting is not consulted at all: a
# per-issue allowance is a decision somebody took about this issue, and
# re-reading the global where the allowance is spent would make that decision
# worth whatever the global had become since. Recorded as the ceiling itself
# and in the setting's own unit, so a `0` here says unlimited exactly as a `0`
# there does.
AGENT_RUN_ALLOWANCE = "agent_run_allowance"

# How many agent runs this issue has spent in its whole life, across every
# role, every stage, and every cycle it has walked.
AGENT_RUNS_USED = "agent_runs_used"

# The launch currently holding one of those charges, and how far it got.
# Absent means no launch this owner knows about is outstanding.
AGENT_RUN_RESERVATION = "agent_run_reservation"

# Which launch that is: the fingerprint its reader derives from the request,
# recorded in the same write as the phase so the two are never read apart. A
# phase alone says a charge is standing and not what it is standing for, and a
# charge nothing can identify is one any launch could claim.
AGENT_RUN_FINGERPRINT = "agent_run_fingerprint"

# The per-issue meter the usage accounting folds every parsed agent exit onto.
# Read here as the seed and the floor of the count above, never written.
_LEGACY_RUNS_USED = "issue_agent_runs"


def _allowance_in_force(state: PinnedState) -> int:
    """The ceiling this issue is actually held to.

    The issue's own where it carries a readable one, and the configured
    setting everywhere else. A field that is not a real, non-negative whole
    number is not an allowance somebody decided -- a hand edit, an older
    binary, a truncated write -- and reading it as one would hold the issue to
    a number nothing wrote. Falling back to the setting is the ordinary answer
    every issue without a per-issue allowance already gets.
    """
    allowance = _counted(state.get(AGENT_RUN_ALLOWANCE))
    if allowance is None:
        return config.MAX_AGENT_RUNS_PER_ISSUE
    return allowance


def _runs_used(state: PinnedState) -> int:
    """How many agent runs this issue has spent, over both meters.

    The larger of the two rather than this ledger's own. An issue that
    predates the ledger has spent runs only the legacy meter recorded, and one
    running under both is counted by both -- so the larger is the count that
    loses neither, and it can only ever go up.

    A field that is not a real, non-negative whole number counts as nothing
    rather than raising: a damaged meter must not strand an issue behind a
    crash on every poll, and the other meter is still there to answer.
    """
    meters = (
        _counted(state.get(AGENT_RUNS_USED)),
        _counted(state.get(_LEGACY_RUNS_USED)),
    )
    return max(
        (count for count in meters if count is not None), default=0,
    )


def _reservation(state: PinnedState) -> _run_ledger_models.RunPhase | None:
    """The launch this issue has outstanding, if it names a known phase.

    Anything else -- absent, hand-edited, or a phase written by a binary this
    one is older than -- reads as no reservation at all. What that costs is a
    launch nobody can account for; what reading an unknown phase as a live one
    would cost is a reader acting on a claim it cannot interpret.
    """
    try:
        return _run_ledger_models.RunPhase(state.get(AGENT_RUN_RESERVATION))
    except ValueError:
        return None


def _fingerprint(state: PinnedState) -> str | None:
    """The launch a standing charge was taken for, if one is recorded.

    Anything but a non-empty string reads as no launch named. What that costs
    is one charge nothing can be matched against -- the next launch pays for
    itself, which is the answer this owner already gives a charge whose phase
    it cannot read.
    """
    recorded = state.get(AGENT_RUN_FINGERPRINT)
    if not isinstance(recorded, str) or not recorded:
        return None
    return recorded


def _counted(raw: Any) -> int | None:
    """One counted field, or None unless it is a real whole count.

    Zero is a real answer for both fields this reads -- an unlimited
    allowance, and an issue that has spent nothing -- so absence is reported
    as None rather than as zero, leaving each caller to say what its own
    missing field means. `bool` is refused explicitly, since it is an `int` in
    this language and a `true` would otherwise count as one run.
    """
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return None
    return raw
