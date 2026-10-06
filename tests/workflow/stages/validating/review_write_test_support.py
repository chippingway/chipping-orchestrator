# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Another road writing the pinned comment while a reviewer round's guarded write is under way.

Every road is what a second poller, another round, or a hand edit does to the
comment of a case carrying `github` and `issue`: a whole-record write of some
fields over that road's own reading (`Writes`), or the comment itself
unparsed or replaced. `AnotherRoadAhead` lands one right
ahead of a guarded commit, or of its preparation -- behind the last reading
the write was decided on, where no request of the tick's own leaves room for
one -- so what the commit refuses, or keeps, is visibly about that one road,
and what that road left is kept on the case (`leaves`). Beside them: GitHub
taking every pinned-comment edit and losing its response
(`loses_the_responses`), and a tick made as every dispatch makes it, under
the issue's writer claim (`under_the_claim`).
"""
from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.scheduler import writer_claims as _writer_claims
from orchestrator.workflow.engine import pinned_commit as _pinned_commit

# Another road's work on a case.
_Road = Callable[[Any], None]


@dataclass(frozen=True)
class Writes:
    """Another road's whole-record write of `fields` over its own reading of the comment.

    A field given as `...` is taken off the record rather than written.
    """

    fields: Mapping[str, Any]

    def __call__(self, case) -> None:
        elsewhere = case.github.read_pinned_state(case.issue)
        merged = {**elsewhere.data, **copy.deepcopy(dict(self.fields))}
        taken_off = {field for field, spelled in merged.items() if spelled is ...}
        elsewhere.data = {field: merged[field] for field in merged.keys() - taken_off}
        case.github.write_pinned_state(case.issue, elsewhere)


def unparses(case) -> None:
    """The pinned comment edited in place into something that does not parse."""
    pinned = case.github.read_pinned_state(case.issue).comment_id
    case.github._pinned[case.issue.number] = PinnedState(comment_id=pinned, parsed=False)


def repins(case) -> None:
    """The pinned comment replaced by another carrying the same record."""
    record = case.github.pinned_data(case.issue.number)
    case.github.seed_state(case.issue, **record)


def leaves(road: _Road, case) -> None:
    """`road`'s work on `case`, and the pinned comment as it left it, kept on `case` as `left_behind`."""
    road(case)
    case.left_behind = case.github.pinned_data(case.issue.number)


def loses_the_responses(case) -> None:
    """GitHub taking every pinned-comment edit on `case`'s issue from here on, and losing its response."""
    case.github.pinned_failures.lost.add(case.issue.number)


def under_the_claim(case, tick: Callable[[], Any]) -> Any:
    """`tick` made as every dispatch makes it, under the issue's writer claim; its answer, or None where refused."""
    repo_id, issue_number = case.github.repo_id, case.issue.number
    with _writer_claims.issue_writer(repo_id, issue_number) as held:
        return tick() if held else None


class AnotherRoadAhead:
    """`road` doing another road's work right ahead of a guarded commit, the first time `when` says so.

    `when` is asked of the commit's staged record, as the comment would carry
    it; the road lands before the commit reads the comment afresh. `request`
    is `commit`, or `prepare` for the preparation a commit with an effect to
    make first measures ahead of that effect.
    """

    def __init__(
        self, case, when: Callable[[Mapping], bool], road: _Road, request: str = "commit",
    ) -> None:
        self._case = case
        self._when = when
        self._road = road
        self._request = request
        self._commits = getattr(_pinned_commit, request)
        self._pending = True

    def __call__(self, gh, issue, guard, staged, *derived):
        if self._pending and self._when(staged):
            self._pending = False
            self._road(self._case)
        return self._commits(gh, issue, guard, staged, *derived)

    def patched(self):
        """A patch of the guarded commit, or its preparation, with this road ahead of it."""
        return patch.object(_pinned_commit, self._request, self)
