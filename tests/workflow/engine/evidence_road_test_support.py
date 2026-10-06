# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Another road writing the pinned comment while an evidence write is under way.

Every road is what a second poller, a reviewer's verdict, or a hand edit does:
a whole-record write over that road's own reading of the comment, landed right
behind one of the readings the write under test takes (`Behind`). A road either
writes fields no evidence write owns (`writes_bookkeeping`), moves one record
(`Move`), replaces or spoils the comment itself (`repins`, `unparses`), or
fills it to its limit (`fills`).
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import comments as _comments, pinned_commit_models as _commit_models

# What another road writes that no evidence write owns.
INDEPENDENT = MappingProxyType({
    "issue_total_tokens": 4321,
    "issue_cost_sources": ["unknown-price"],
    "last_action_comment_id": 987654,
    "review_returned_verdict": {"round": 1, "verdict": "approved"},
    "a_field_no_binary_writes_yet": {"n": [1, None, True]},
})

# A comment another road posted and recorded as the orchestrator's.
ANOTHER_ROADS_COMMENT = 555555

# A record another road removes, rather than writes.
GONE = _commit_models.ABSENT

# A field of another road's that fills the pinned comment.
FILLER = "filler"


def writes_bookkeeping(case) -> None:
    """Another road's write of fields no evidence write owns, and of a comment of its own onto the ledger."""
    elsewhere = case.gh.read_pinned_state(case.issue)
    elsewhere.data.update(INDEPENDENT)
    _comments._track_orchestrator_comment(elsewhere, ANOTHER_ROADS_COMMENT)
    case.gh.write_pinned_state(case.issue, elsewhere)


def repins(case) -> None:
    """The pinned comment replaced by another carrying the same record."""
    record = case.gh.pinned_data(case.issue.number)
    case.gh.seed_state(case.issue, **record)


def unparses(case) -> None:
    """The pinned comment edited in place into something that does not parse."""
    case.gh._pinned[case.issue.number] = PinnedState(
        comment_id=case.gh.read_pinned_state(case.issue).comment_id, parsed=False,
    )


def fills(case) -> None:
    """The pinned comment filled to its limit with a field of another road's."""
    filling = case.gh.read_pinned_state(case.issue)
    filling.set(FILLER, "")
    room = MAX_PINNED_BODY - len(pinned_state_body(filling.data))
    filling.set(FILLER, "y" * room)
    case.gh.write_pinned_state(case.issue, filling)


@dataclass(frozen=True)
class Move:
    """Another road moving one record, to what `to` makes of the case; `GONE` removes it."""

    name: str
    record: str
    to: Callable[[Any], Any]

    def lands(self, case) -> None:
        """The move, as a whole-record write over another road's own reading of the comment."""
        elsewhere = case.gh.read_pinned_state(case.issue)
        moved_to = self.to(case)
        if moved_to is GONE:
            elsewhere.data.pop(self.record)
        else:
            elsewhere.set(self.record, moved_to)
        case.gh.write_pinned_state(case.issue, elsewhere)

    def spelled_on(self, case) -> tuple[str | None, str | None]:
        """How the comment spells the record now, and how the move spelled it; None for absent."""
        persisted = case.gh.pinned_data(case.issue.number).get(self.record, GONE)
        return _spelling(persisted), _spelling(self.to(case))


def _spelling(found: Any) -> str | None:
    """How the comment's JSON spells one value, or None for `GONE`."""
    return None if found is GONE else json.dumps(found, sort_keys=True)


@dataclass
class Behind:
    """`road` landing right behind the `number`-th pinned reading a route of `case` takes."""

    case: Any
    number: int
    road: Callable[[Any], None]
    reads: Callable[[Any], PinnedState] = field(init=False)

    def __call__(self, issue) -> PinnedState:
        fresh = self.reads(issue)
        self.number -= 1
        if not self.number:
            self.road(self.case)
        return fresh

    def __post_init__(self) -> None:
        self.reads = self.case.gh.read_pinned_state

    def runs(self, route: Callable[..., Any], *asked) -> Any:
        """What `route` answers with the road behind its readings."""
        with patch.object(self.case.gh, "read_pinned_state", self):
            return route(*asked)

    def reconciles(self) -> bool:
        """What one reconciliation of `case` answers over the reading its tick took first."""
        tick = self.case.gh.read_pinned_state(self.case.issue)
        return self.runs(self.case.reconcile, tick)
