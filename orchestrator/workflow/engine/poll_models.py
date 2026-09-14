# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retain polling closure evidence and partition family, fanout, and cleanup work.

Deferred closes survive a missing poll result. Cleanup work leaves the
family bucket, while blocked and umbrella family walks retain their
capacity exemption.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from orchestrator.github.issues import (
    CLEANUP_ROUTE_LABELS,
)
from orchestrator.workflow.state import WorkflowLabel

_FAMILY_AWARE_LABELS = frozenset((
    WorkflowLabel.DECOMPOSING, WorkflowLabel.BLOCKED, WorkflowLabel.UMBRELLA,
))

_CAP_EXEMPT_FAMILY_LABELS = frozenset((
    WorkflowLabel.BLOCKED, WorkflowLabel.UMBRELLA,
))

# Every label whose CLOSED issues the sweep yields for cleanup only. Kept as a
# set of the members the sweep publishes so the two cannot drift: a label
# queried there and missing here is a closed issue dispatched to the stage
# handler its label names, which is the one thing the cleanup route exists to
# prevent.
_CLEANUP_ROUTE_LABELS = frozenset(CLEANUP_ROUTE_LABELS)


@dataclass(frozen=True)
class _PollReading:
    """What the poll established about one issue, carried to its worker.

    Both halves are readings the ENUMERATION took, and neither is one the
    worker can take again: it mints its own client and refetches the issue, so
    a human who reopens one in that window would have the fresh object answer
    differently. `cleanup_only` is the route a closed late owner was
    classified into and may not be re-derived out of; `closed` is the same
    reading for an issue whose label names an ordinary terminal instead, where
    the guard that ends a live cycle is what reads it.
    """

    cleanup_only: bool = False
    closed: bool = False


# What an ordinary open issue carries, which is nothing at all.
_POLLED_OPEN = _PollReading()


@dataclass(frozen=True)
class _PollablePartition:
    """Family / fanout split of one repo's pollable issues for a single tick.

    ``family_numbers`` and ``family_labels`` are index-aligned so the
    cap-exempt decision (`_family_bucket_cap_exempt`) can read each
    family-aware issue's workflow label. ``fanout_closed`` is the subset of
    ``fanout_numbers`` whose issue is already closed -- a cheap terminal
    finalize, or a cleanup pass over a closed owner's ledger, and neither
    spawns, so both are submitted cap-exempt.
    """
    family_numbers: list[int]
    family_labels: list[str | None]
    fanout_numbers: list[int]
    fanout_closed: set[int]
    cleanup_numbers: set[int] = field(default_factory=set)


@dataclass
class _PollablePartitionBuilder:
    """Sorts one tick's issues, with the held observations overriding it.

    ``deferred`` is the set an earlier tick observed closed and could hand to
    no worker, and it decides this issue's route on its own -- ahead of the
    label, ahead of the close, and ahead of every filter that runs before this
    builder, because the reading those all come from is exactly what a reopen,
    a park, or a relabel in the meantime has taken away. An issue in it goes
    where a closed owner goes: fan-out, cap-exempt, and cleanup-only. What
    the sweep does with one that reads open again is mark the cancellation
    the observed close already earned and stop there, which is safe on any
    label and a no-op for an issue carrying no late cycle at all.
    """

    family_numbers: list[int] = field(default_factory=list)
    family_labels: list[str | None] = field(default_factory=list)
    fanout_numbers: list[int] = field(default_factory=list)
    fanout_closed: set[int] = field(default_factory=set)
    cleanup_numbers: set[int] = field(default_factory=set)
    deferred: frozenset[int] = frozenset()

    yielded: set[int] = field(default_factory=set)

    def owed(self, issue_number: int) -> bool:
        """Whether an earlier poll's held observation decides this route."""
        return issue_number in self.deferred

    def add(self, issue_number: int, label: str | None, closed: bool) -> None:
        owed = self.owed(issue_number)
        self.yielded.add(issue_number)
        if not owed and _drains_in_family_bucket(label, closed):
            self.family_numbers.append(issue_number)
            self.family_labels.append(label)
            return
        self.fanout_numbers.append(issue_number)
        if closed or owed:
            self.fanout_closed.add(issue_number)
        if owed or (closed and label in _CLEANUP_ROUTE_LABELS):
            self.cleanup_numbers.add(issue_number)

    def add_unyielded(self) -> None:
        """Add every held observation this enumeration never reached.

        What the enumeration yields is decided by the labels the closed sweep
        queries, so a human who moves the label off one of them -- or closes
        the issue on a label the sweep does not query at all -- makes the
        owner unreachable. The observation is older than any of that and is
        not lost with it: the issue is added by NUMBER, on the strength of the
        reading alone, and routed exactly where a closed owner goes.
        """
        for owed in sorted(self.deferred - self.yielded):
            self.add(owed, None, True)

    def build(self) -> _PollablePartition:
        return _PollablePartition(
            self.family_numbers,
            self.family_labels,
            self.fanout_numbers,
            self.fanout_closed,
            self.cleanup_numbers,
        )


def _drains_in_family_bucket(label: str | None, closed: bool) -> bool:
    """Whether this issue belongs in the serialized, all-or-nothing bucket.

    Every family-aware label does, with one exception: a CLOSED issue on a
    cleanup-swept label runs the sweep rather than the stage its label names,
    and the sweep neither spawns nor activates. Leaving it in the bucket would
    tie its exemption to whatever else landed there -- one open `decomposing`
    issue and the whole bucket is cap-counted, so a repository at its cap
    stops reclaiming refs until the decomposer is idle.
    """
    if closed and label in _CLEANUP_ROUTE_LABELS:
        return False
    return label is None or label in _FAMILY_AWARE_LABELS


def _family_bucket_cap_exempt(family_labels: list[str | None]) -> bool:
    """True when a family bucket may skip the per-repo / global caps.

    A bucket is cap-exempt only when EVERY issue in it this tick runs a
    no-agent / no-worktree handler -- all labels in ``_CAP_EXEMPT_FAMILY_LABELS``
    (``blocked`` / ``umbrella``, pure dep-graph walks). Such a bucket must
    always get its turn even when the parallel caps are saturated by real
    implementation work: a ``blocked`` parent polling its children, or an
    ``umbrella`` aggregating them, would otherwise be starved of the only
    per-repo slot under the default ``parallel_limit=1`` -- and a ``blocked``
    parent waiting on its own children would deadlock them. A bucket
    containing ``decomposing`` (spawns the decomposer agent) or an
    unlabeled-pickup ``None`` (routes through ``_handle_pickup``, may spawn an
    agent) stays cap-counted.

    A closed issue on a cleanup-swept label is not here to be exempted: it is
    partitioned as fan-out instead (see ``_drains_in_family_bucket``), so it
    is submitted cap-exempt on its own rather than tying its turn to whatever
    else this bucket happens to hold.
    """
    return all(lbl in _CAP_EXEMPT_FAMILY_LABELS for lbl in family_labels)
