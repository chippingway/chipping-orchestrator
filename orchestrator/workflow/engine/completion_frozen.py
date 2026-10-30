# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A road's handoff frozen over the reading its launch was made from, and which of its records moved since.

A frozen handoff is the digest of each pinned record a road was decided on,
taken over the reading its launch was made from (`frozen_over`), and asked
again of a later reading (`moved_since`): a record spelled otherwise since --
`null` where it was missing included, as the guarded commit tells them apart
-- is one another road moved, and the handoff it froze is no longer the one
that reading carries. Only digests are kept, so a capture holds no copy of the
records its road was decided on.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit_models as _commit_models


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
