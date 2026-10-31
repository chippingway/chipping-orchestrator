# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A road's handoff frozen over its launch's reading, which of its records moved since, and the stretch it delivered.

A frozen handoff is the digest of each pinned record a road was decided on,
taken over the reading its launch was made from (`frozen_over`) -- for a road
freezing from a tick's state, the comment as that state last read or wrote it
(`frozen_over_the_comment`), so a move the tick staged and has yet to write is
never read afterwards as another road's -- and asked again of a later reading
(`moved_since`): a record spelled otherwise since --
`null` where it was missing included, as the guarded commit tells them apart
-- is one another road moved, and the handoff it froze is no longer the one
that reading carries. Only digests are kept, so a capture holds no copy of the
records its road was decided on.

The issue-thread stretch a road's prompt quoted is frozen beside them, for a
road that records it once its report is handed on -- or, on a drift resume
over an open pull request, beside the stretch of that pull request's
conversation, for its recovery's cursor carry -- and read back only whole
(`delivered_stretch`).

A road that froze the code-publication receipt -- one launched over a checkout
an earlier run committed onto and never pushed, whose own head the pull
request does not carry -- names through it the head that pull request stands
on (`published_over`): the commit this orchestrator last published there,
which the frozen digest holds to the one the launch read.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import operator
from collections.abc import Iterable
from typing import Any

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    report_record_values as _record_values,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.late_split import payloads as _payloads

# A delivered stretch: its two ends.
_ENDS = 2

# How many ends the delivered stretches may come to: none, one stretch, or two.
_SHAPES = frozenset((0, _ENDS, 2 * _ENDS))

# The code-publication receipt a road may freeze, as the implementing stage
# spells it -- the commit last pushed onto a pull request, the head that push
# replaced, and that pull request -- a road freezing all three, since the
# push writes them as one record.
PUBLISHED_COMMIT = "implementing_published_sha"
PUBLISHED_LEASE = "implementing_published_lease"
PUBLISHED_PULL_REQUEST = "implementing_published_pr"


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


def frozen_over_the_comment(state: PinnedState, fields: Iterable[str]) -> tuple:
    """The handoff `fields` freeze over the comment `state` was last read or written as, nothing it staged since."""
    synced = state.state_data if state.synced is None else json.loads(state.synced)
    return frozen_over(PinnedState(state_data=synced), fields)


def moved_since(state: PinnedState, frozen: tuple) -> tuple[str, ...]:
    """The records of `frozen` that `state` spells otherwise than they were frozen; empty where none moved."""
    now = dict(frozen_over(state, (field for field, _digest in frozen)))
    return tuple(
        field for field, digest in frozen
        if now[field] != digest
    )


def published_over(state: PinnedState, frozen: tuple) -> tuple[str, ...]:
    """The commit the receipt names on the pull request `state` records, where `frozen` froze it; else empty.

    Read through the receipt's own owner (`stages/implementing/
    late_publication_state`, resolved when called), so a receipt naming
    another pull request, or nothing it can read, names no head at all.
    """
    if PUBLISHED_COMMIT not in dict(frozen):
        return ()
    receipts = importlib.import_module(_stage_targets._LATE_PUBLICATION_STATE_OWNER)
    commit = receipts._published_commit(state)
    number = receipts._recorded_pull_request(state)
    on_it = bool(number) and receipts._published_pull_request(state) == number
    return (commit,) if commit and on_it else ()


def delivered_stretch(raw: Any) -> tuple | None:
    """The delivered stretches as a capture writes them -- none, one, or two, each its two ends in order -- or None.

    Each end is a comment id as the delivered stretch records one
    (`thread_delivery`), the lower one 0 where the prompt left nothing out,
    neither past the recorded bound nor the upper below the lower. One is the
    issue thread's; a second, which only a road whose contract takes it may
    carry (`completion_routes.RouteContract.stretches`), is the stretch of a
    pull request's conversation a two-surface prompt quoted beside it
    (`stages/implementing/drift_road.DriftReading`).
    """
    if not isinstance(raw, list) or len(raw) not in _SHAPES:
        return None
    ends = [_payloads.as_count(end) for end in raw]
    if None in ends or any(end > _record_values.MAX_RECORDED_NUMBER for end in ends):
        return None
    lower, upper = ends[::_ENDS], ends[1::_ENDS]
    return tuple(ends) if all(map(operator.le, lower, upper)) else None
