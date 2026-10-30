# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A road's handoff frozen over its launch's reading, which of its records moved since, and the stretch it delivered.

A frozen handoff is the digest of each pinned record a road was decided on,
taken over the reading its launch was made from (`frozen_over`), and asked
again of a later reading (`moved_since`): a record spelled otherwise since --
`null` where it was missing included, as the guarded commit tells them apart
-- is one another road moved, and the handoff it froze is no longer the one
that reading carries. Only digests are kept, so a capture holds no copy of the
records its road was decided on.

The issue-thread stretch a road's prompt quoted is frozen beside them, for a
road that records it once its report is handed on, and read back only whole
(`delivered_stretch`).
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit_models as _commit_models, report_record_values as _record_values
from orchestrator.workflow.late_split import payloads as _payloads

# A delivered stretch: its two ends.
_ENDS = 2


def frozen_over(state: PinnedState, fields: Iterable[str]) -> tuple:
    """The handoff `fields` freeze over `state`: each one's name and the digest of its spelling, sorted.

    A field the state lacks is the digest of the empty spelling, which no
    field the comment carries is spelled as.
    """
    frozen = {
        field: hashlib.sha256(
            (_commit_models.spelled(state.state_data, field) or "").encode(),
        ).hexdigest()
        for field in fields
    }
    return tuple(sorted(frozen.items()))


def moved_since(state: PinnedState, frozen: tuple) -> tuple[str, ...]:
    """The records of `frozen` that `state` spells otherwise than they were frozen; empty where none moved."""
    now = dict(frozen_over(state, (field for field, _digest in frozen)))
    return tuple(
        field for field, digest in frozen
        if now[field] != digest
    )


def delivered_stretch(raw: Any) -> tuple | None:
    """A delivered stretch as a capture writes it -- none, or the two ends of one in order -- or None.

    Each end is a comment id as the delivered stretch records one
    (`thread_delivery`), the lower one 0 where the prompt left nothing out,
    neither past the recorded bound nor the upper below the lower.
    """
    if not isinstance(raw, list) or len(raw) not in {0, _ENDS}:
        return None
    ends = [_payloads.as_count(end) for end in raw]
    if None in ends or any(end > _record_values.MAX_RECORDED_NUMBER for end in ends):
        return None
    return tuple(ends) if ends == sorted(ends) else None
