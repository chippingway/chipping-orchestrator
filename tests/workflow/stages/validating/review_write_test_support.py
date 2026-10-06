# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Another road writing the pinned comment while a reviewer round's guarded write is under way.

Every road is what a second poller, another round, or a hand edit does to the
comment of a case carrying `github` and `issue`: a whole-record write of some
fields over that road's own reading (`Writes`), or the comment itself
unparsed or replaced. `AnotherRoadAhead` lands one right
ahead of a guarded commit -- behind the last reading the write was decided on,
where no request of the tick's own leaves room for one -- so what the commit
refuses, or keeps, is visibly about that one road.
"""
from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit as _pinned_commit

# Another road's work on a case.
_Road = Callable[[Any], None]


@dataclass(frozen=True)
class Writes:
    """Another road's whole-record write of `fields` over its own reading of the comment."""

    fields: Mapping[str, Any]

    def __call__(self, case) -> None:
        elsewhere = case.github.read_pinned_state(case.issue)
        elsewhere.data.update(copy.deepcopy(dict(self.fields)))
        case.github.write_pinned_state(case.issue, elsewhere)


def unparses(case) -> None:
    """The pinned comment edited in place into something that does not parse."""
    pinned = case.github.read_pinned_state(case.issue).comment_id
    case.github._pinned[case.issue.number] = PinnedState(comment_id=pinned, parsed=False)


def repins(case) -> None:
    """The pinned comment replaced by another carrying the same record."""
    record = case.github.pinned_data(case.issue.number)
    case.github.seed_state(case.issue, **record)


class AnotherRoadAhead:
    """`road` doing another road's work right ahead of a guarded commit, the first time `when` says so.

    `when` is asked of the commit's staged record, as the comment would carry
    it; the road lands before the commit reads the comment afresh.
    """

    def __init__(self, case, when: Callable[[Mapping], bool], road: _Road) -> None:
        self._case = case
        self._when = when
        self._road = road
        self._commits = _pinned_commit.commit
        self._pending = True

    def __call__(self, gh, issue, guard, staged, *derived):
        if self._pending and self._when(staged):
            self._pending = False
            self._road(self._case)
        return self._commits(gh, issue, guard, staged, *derived)

    def patched(self):
        """A patch of the guarded commit with this road ahead of it."""
        return patch.object(_pinned_commit, "commit", self)
