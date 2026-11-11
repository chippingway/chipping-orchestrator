# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one trajectory record keeps whole, and the sizes it is kept within.

One owner for everything a record is measured against: the always-retained
headline charged before any variable array, the running total those arrays are
drawn from and the prefix of one that fits it, and the three caps the whole
thing is bounded by -- the per-field head and tail a single value is truncated
to, and the serialized byte budget one record may not exceed.

The caps are defaults rather than environment knobs, so they are declared here
rather than parsed, and this is where a caller shrinks one to bound a run it
is about to record. ``current_limits`` reads all three at the moment a record
is built, so a value patched between two records bounds the second one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

TRAJECTORY_FIELD_HEAD = 2000
TRAJECTORY_FIELD_TAIL = 2000
TRAJECTORY_RECORD_BUDGET = 200_000


@dataclass(frozen=True)
class TrajectoryLimits:
    """The three caps one record is measured against."""

    field_head: int
    field_tail: int
    record_budget: int


@dataclass(frozen=True)
class TrajectoryHeadline:
    """Always-retained trajectory fields charged before variable arrays.

    The three summaries are bounded by construction -- a run's usage totals,
    one count per disposition the item accounting settled on, and the request
    usage coverage beside its few aggregate checkpoints -- which is what lets
    them be charged and still kept whole. The item counts and the request
    coverage are the reason a truncated array cannot read as a complete one:
    they state how many items the stream identified, and how many requests
    the collection observed, however few of them the budget left room to name.
    """

    user_input: str | None
    system_prompt: str | None
    output: str | None
    run_usage: dict[str, Any]
    source_item_counts: dict[str, int]
    request_summary: dict[str, Any]

    @property
    def serialized_size(self) -> int:
        """What the always-retained fields cost the record budget.

        Only a summary the record actually writes is charged. A run that
        identified no source items leaves the counts off entirely, so charging
        their `{}` would take two bytes off the budget every variable array is
        drawn from -- enough, at the boundary, to drop a step such a run would
        otherwise keep and to flag it truncated.
        """
        text_fields = (self.user_input, self.system_prompt, self.output)
        text_size = sum(len(text_field or "") for text_field in text_fields)
        summaries = (self.run_usage, self.source_item_counts, self.request_summary)
        return text_size + sum(
            len(json.dumps(summary, default=str))
            for summary in summaries
            if summary
        )


@dataclass(frozen=True)
class TrajectoryArrays:
    """The variable arrays one record kept, in the order they were charged.

    `source_items_truncated` is carried beside them because the record-level
    `truncated` flag names no array: a run whose steps overflowed and a run
    whose accounting did both set it, and only the accounting's own flag says
    that the ids under it are a prefix rather than the whole set. The request
    usage field carries its own count of what it kept for the same reason.
    """

    turns: list[dict[str, Any]]
    source_items: list[dict[str, Any]]
    request_usage: dict[str, Any] | None
    steps: list[dict[str, Any]]
    source_items_truncated: bool


@dataclass
class TrajectoryBudget:
    """Track serialized variable-field bytes retained in one record."""

    used: int
    limit: int
    truncated: bool = False

    def include(self, field_value: Any) -> bool:
        self.used += len(json.dumps(field_value, default=str))
        if self.used <= self.limit:
            return True
        self.truncated = True
        return False

    def bounded(self, entries: Iterable[Any]) -> list[dict[str, Any]]:
        """Keep the prefix of `entries` the remaining budget has room for.

        The fixed-shape arrays -- the per-turn usage breakdown and the source
        item accounting -- are drawn the same way, each entry charged its
        whole serialized size before it is kept, so an array of thousands of
        small entries is bounded exactly as an array of a few large ones is.
        """
        kept: list[dict[str, Any]] = []
        for entry in entries:
            entry_dict = entry.to_dict()
            if not self.include(entry_dict):
                break
            kept.append(entry_dict)
        return kept


def current_limits() -> TrajectoryLimits:
    """Read the caps in force at the moment one record is built."""
    return TrajectoryLimits(
        TRAJECTORY_FIELD_HEAD,
        TRAJECTORY_FIELD_TAIL,
        TRAJECTORY_RECORD_BUDGET,
    )
