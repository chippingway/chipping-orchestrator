# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The comment a dormant recovery reads last before a reset, laid over the tick's state where another road moved it.

The reset's record (`rewrite_recovery_parks.records_the_reset`) lets the reset go on over the comment it reads
afresh behind its own writes, and the tick's state is written behind that reset -- whole, by a recovery context that
hands in no park of its own. A usage total another road added to by then, a revision floor it raised, or a
transaction it recorded would be put back by that write. So `lays_what_moved` lays that reading over the state for
every field another road moved since the tick's own reading, each taken in as read
(`rewrite_finish_rechecks.lays`), so a guarded write behind counts none of it as the tick's own move either; a field
the tick staged itself stays staged, for the write behind to merge or refuse as the guarded commit does. A move of a
field the caller holds the reading to, or a transaction another road recorded pending under a receipt the attempt
does not name, holds the reset.

Dormant, as that record is: no recovery context the workflow builds reaches it.
"""
from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from typing import Any

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_landing_records as _landing_records,
    verification_record_state as _record_state,
    verification_records as _evidence_records,
)
from orchestrator.workflow.engine.rewrite_finish_rechecks import lays


def lays_what_moved(state: PinnedState, reading: PinnedState, held: Collection[str] = ()) -> bool:
    """Lay over `state` each field `reading` spells otherwise than the reading `state` was synced with; whether to hold.

    `reading` is the comment read afresh. A field `state` itself spells otherwise than that reading is the tick's own
    staging and is left as it is. True where any field laid is one of `held`, or where another road recorded a
    transaction pending there under a receipt the attempt `reading` carries does not name -- a successor the reset
    would otherwise go on under. A state nothing was read into has no reading to measure moves from, and lays nothing.
    """
    if state.synced is None:
        return False
    synced = json.loads(state.synced)
    moved = _moved(reading.data, synced) - _moved(state.data, synced)
    lays(state, reading, moved)
    if not moved.isdisjoint(held):
        return True
    return _evidence_records.PENDING_EVIDENCE in moved and _unnamed(reading)


def _unnamed(reading: PinnedState) -> bool:
    """Whether `reading` carries a transaction pending under a receipt the attempt it carries does not name."""
    if _record_state.read_pending_evidence(reading) is None:
        return False
    return _landing_records.captured(reading) is None


def _moved(
    after: Mapping[str, Any], before: Mapping[str, Any],
) -> set[str]:
    """Every field `after` spells otherwise than `before`, one that either lacks included."""
    spelled = _commit_models.spelled
    return {
        field for field in after.keys() | before.keys()
        if spelled(after, field) != spelled(before, field)
    }
