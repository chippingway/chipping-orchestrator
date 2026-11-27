# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settle a Codex token_count against the branch history as it stood when the report arrived."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cached_property
from itertools import chain, islice
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from orchestrator.observability.usage.request_codex_counters import LAST_USAGE, Counters
from orchestrator.observability.usage.request_codex_scope import Line

if TYPE_CHECKING:
    from orchestrator.observability.usage.request_codex_fold import Branch, Requests


class RecordMatch(NamedTuple):
    """The record to consume on this branch. Unkept records have only a count and are consumed in order."""

    queue: Literal["pending", "unkept", "earlier"]
    index: int = 0


_PENDING_HEAD = RecordMatch("pending")


class Settlement(NamedTuple):
    """A repeat keeps the branch's position. Other reports can prove a request, answer a record, or do both."""

    repeated: bool = False
    gained: Counters | None = None
    record: RecordMatch | None = None


@dataclass(frozen=True)
class Report:
    """A token_count with a readable running sum and the request usage and metadata it reported beside it."""

    line: Line
    token_info: dict[str, Any]
    running: Counters
    capacity: int | None = None
    flags: Mapping[str, bool] | None = None

    @cached_property
    def own(self) -> Counters | None:
        """Only last_token_usage supplies a request's counters."""
        return Counters.of(self.token_info.get(LAST_USAGE))

    @property
    def moving(self) -> frozenset[str]:
        """The counters a new request with this usage would move."""
        raw = {} if self.own is None else self.own.raw
        return frozenset(counter for counter, count in raw.items() if count > 0)

    def settle(self, branch: Branch, requests: Requests) -> Settlement:
        """Decide which record this report answers and what usage it proves from the history preceding it.

        A repeat of a known sum answers nothing. A rise can answer a record even when its size or its origin is
        uncertain. Proving a request also takes an exact advance from a known sum and, for this invocation, enough
        evidence to distinguish it from a late report.
        """
        current = branch.proven_at(requests.scan.unread_lines)
        if current and self.running.repeats(branch.running, self.moving):
            return Settlement(repeated=True)
        record = self._match_record(branch, requests.scan.limits.branches)
        own = self.own
        proven = current and own is not None and self.running.advanced_by(
            branch.running, own, branch.floor,
        )
        if proven and self.line.own:
            proven = not self._ambiguous(branch, requests, record)
        return Settlement(gained=own if proven else None, record=record)

    def _match_record(self, branch: Branch, limit: int) -> RecordMatch | None:
        """Prefer the first matching pending record, then an unkept one, then the first match from an earlier run."""
        if not self._rises(branch):
            return None
        index = self._first_match(islice(branch.pending, limit))
        if index is not None:
            return RecordMatch("pending", index)
        if branch.unkept:
            return RecordMatch("unkept")
        index = self._first_match(branch.earlier)
        return None if index is None else RecordMatch("earlier", index)

    def _rises(self, branch: Branch) -> bool:
        """A record needs a sum above the branch's historical floor, including after a shrink or a sparse report."""
        for counter, reading in self.running.readings.items():
            before = 0 if branch.running is None else branch.floor.get(counter)
            if before is not None and reading.known and (reading.count or 0) > before:
                return True
        return False

    def _ambiguous(self, branch: Branch, requests: Requests, record: RecordMatch | None) -> bool:
        """Once another branch has reported, this branch needs a matching head record to establish a new request.
        Even then, a compatible outstanding record on another branch or from an earlier invocation could be the
        source of a late report.
        """
        others = [other for other in requests.branches.values() if other is not branch]
        recorded = record == _PENDING_HEAD and branch.pending[0] is not None
        if not recorded and any(other.reported for other in others):
            return True
        # Beyond the search bound even one more record could match any counters.
        if any(other.unkept for other in others):
            return True
        retained = sum(len(other.pending) for other in others)
        if retained > requests.scan.limits.branches:
            return True
        pending = chain.from_iterable(other.pending for other in others)
        earlier = chain.from_iterable(other.earlier for other in requests.branches.values())
        return self._first_match(chain(pending, requests.unplaced, earlier)) is not None

    def _first_match(self, records: Iterable[Counters | None]) -> int | None:
        """The first record whose known counters are consistent with the request usage."""
        for index, record in enumerate(records):
            if _agrees(self.own, record):
                return index
        return None


def _agrees(given: Counters | None, other: Counters | None) -> bool:
    """A record can repeat this request's usage if every counter known in both agrees."""
    if given is None or other is None:
        return True
    readings = given.readings
    return all(
        reading == readings[counter]
        for counter, reading in other.readings.items()
        if reading.known and counter in readings and readings[counter].known
    )
