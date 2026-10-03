# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue's pinned record, the reading a commit is captured over, and the roads that move it meanwhile.

Driven through the in-memory client, whose strict edit is the real client's
policy over its own records, so a commit here makes the requests production
makes and is answered as production would be. Another road is a whole-record
write through the legacy writer, which is what every unmigrated caller is.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit as _commit, pinned_commit_models as _models
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue

ISSUE = 41
PR = "pr_number"
SETTLED = "settled_record"
WATERMARK = "last_read_comment_id"
TOTAL = "usage_total"
LEDGER = "orchestrator_comment_ids"
RETIRED = "retired_marker"
UNKNOWN = "a_field_no_binary_writes_yet"

# The record the caller reads: a prerequisite, a field it owns and replaces, one
# it owns and leaves alone, and three that are somebody else's.
RECORD = MappingProxyType({
    PR: 17,
    SETTLED: {"revision": 3, "at": {"comment": 901}},
    WATERMARK: 55,
    TOTAL: 1200,
    LEDGER: [11, 12],
    RETIRED: "old",
})

# What the caller replaces its settled record with: longer than the one it read,
# so a candidate carrying it outweighs the record it lands over.
SETTLED_ANEW = MappingProxyType({"revision": 4, "at": {"comment": 902}, "note": "settled again"})

_OWNED = (SETTLED, WATERMARK)

_NO_TRANSFORMS: Mapping[str, _models.Transform] = MappingProxyType({})


def recorded(*, settled: bool = False, **fields: Any) -> dict:
    """`RECORD` with `fields` over it, a field given ABSENT dropped, and the settled record anew where `settled`."""
    record = copy.deepcopy(dict(RECORD))
    if settled:
        record[SETTLED] = copy.deepcopy(dict(SETTLED_ANEW))
    record.update(fields)
    return {name: kept for name, kept in record.items() if kept is not _models.ABSENT}


def seeded(
    record: Mapping[str, Any] | None = None,
    *,
    owned: Iterable[str] = _OWNED,
) -> CommitWorld:
    """An issue pinned with `record` -- `RECORD` by default, nothing for an empty one -- as its caller read it."""
    issue = make_issue(ISSUE)
    github = FakeGitHubClient([issue])
    pinned = recorded() if record is None else record
    if pinned:
        github.seed_state(issue, **copy.deepcopy(dict(pinned)))
    return CommitWorld.of(github, issue, owned=owned)


def unparse(world: CommitWorld) -> None:
    """A hand edit leaves the pinned comment in place, carrying nothing that parses."""
    world.github._pinned[ISSUE] = PinnedState(comment_id=world.state.comment_id, parsed=False)


def repin(world: CommitWorld) -> None:
    """The pinned comment is replaced by another one carrying the same record."""
    world.github.seed_state(world.issue, **recorded())


def unpin(world: CommitWorld) -> None:
    """The pinned comment is deleted."""
    world.github._pinned.pop(ISSUE)


@dataclass
class CommitWorld:
    """One issue, its client, the state its caller read and stages on, and the commit guarded by that reading."""

    github: FakeGitHubClient
    issue: FakeIssue
    state: PinnedState
    guard: _models.PinnedCommit

    @classmethod
    def of(cls, github: FakeGitHubClient, issue: FakeIssue, *, owned: Iterable[str] = _OWNED) -> CommitWorld:
        """The issue as its caller reads it now, captured on `pr_number` and owning `owned`."""
        state = github.read_pinned_state(issue)
        guard = _models.PinnedCommit.capture(state, prerequisites=(PR,), owned=owned)
        return cls(github, issue, state, guard)

    def settle(self) -> None:
        """Stage the settled record anew on the caller's state."""
        self.state.set(SETTLED, copy.deepcopy(dict(SETTLED_ANEW)))

    def commit(self, derived: Mapping[str, _models.Transform] = _NO_TRANSFORMS) -> _models.CommitOutcome:
        """Commit the caller's staged state under its guard."""
        return _commit.commit(self.github, self.issue, self.guard, self.state.data, derived)

    def another_road(self, **fields: Any) -> None:
        """Another road's whole-record write over the record as it stands, a field given ABSENT dropped."""
        landed = self.github.read_pinned_state(self.issue)
        landed.data.update(fields)
        landed.data = {
            name: kept for name, kept in landed.data.items()
            if kept is not _models.ABSENT
        }
        self.github.write_pinned_state(self.issue, landed)

    def record(self) -> dict:
        """What the issue's pinned comment carries now."""
        return self.github.pinned_data(ISSUE)

    def snapshot(self) -> tuple[str, int, str]:
        """The record, the pinned writes sent, and the caller's state, spelled to compare exactly."""
        return (
            json.dumps(self.record(), sort_keys=True),
            self.github.write_state_calls,
            json.dumps(self.state.data, sort_keys=True),
        )

    def interfering(self, move: Callable[[CommitWorld], None]) -> AbstractContextManager:
        """Let `move` land once, right behind the next fresh reading and before anything is sent over it."""
        reader = _ReadThenMove(self, self.github.read_pinned_state, [move])
        return patch.object(self.github, "read_pinned_state", side_effect=reader.read)


@dataclass
class _ReadThenMove:
    """A reading another road writes right behind.

    The move is taken off before it runs, since the road it stands for reads
    the record itself.
    """

    world: CommitWorld
    reader: Callable[[FakeIssue], PinnedState]
    pending: list[Callable[[CommitWorld], None]] = field(default_factory=list)

    def read(self, issue: FakeIssue) -> PinnedState:
        """The reading, with the move landed behind it."""
        fresh = self.reader(issue)
        while self.pending:
            self.pending.pop()(self.world)
        return fresh
