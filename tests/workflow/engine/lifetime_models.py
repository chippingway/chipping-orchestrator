# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Scenario legs, journeys, and observed passes for lifetime-budget tests."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from orchestrator.workflow.engine import (
    run_ledger_values as _run_ledger_values,
    run_limit as _run_limit,
)
from tests.support.fakes import FakeGitHubClient
from tests.workflow.engine import lifetime_ticks as _lifetime_ticks
from tests.workflow.fixtures import (
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    _agent,
)

# Small enough that a whole lifetime fits in a handful of ticks, and large
# enough that the walk before the ceiling is a walk rather than one spawn.
ALLOWANCE = 4

# How many ticks a walk takes past the last run it can pay for. Two rather
# than one: the first meets the refusal that takes the park, and the second is
# the tick that has to add nothing to the thread.
REFUSED_TICKS = 2


@dataclass(frozen=True)
class Leg:
    """One tick of a journey: what it runs, and the world it runs in.

    `staged` is what the workflow would have left on the issue by the time
    this stage is entered, and it is re-applied on every pass so a road that
    consumed its own work -- a batch of feedback marked read, a session
    retired -- has work in front of it again. `world` is the hermetic patch
    context that stage runs inside, and `around` is whatever else has to be
    held open for it (the git seams a rebase reads through).

    `tick` is what the pass actually runs. Ordinarily that is the dispatcher,
    which is the whole of a tick for one issue; a leg that names the base
    refresh instead is the other half of one, and it runs ahead of every
    dispatch rather than through it.
    """

    role: str
    label: str
    staged: Mapping[str, Any]
    world: Mapping[str, Any] = field(default_factory=dict)
    agent_result: Any = field(default_factory=_agent)
    around: Callable[[], Any] | None = None
    tick: Callable[..., Callable[[], Any]] = _lifetime_ticks.dispatched_tick
    # What a human says to the issue on the way into this stage, written
    # afresh on every pass. A round that reads a thread consumes it, so a leg
    # whose road is woken by a reply is handed a new one rather than having
    # the mark it just moved put back.
    replies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Journey:
    """One issue walked repeatedly over the same legs until it runs out.

    The legs cycle, so a journey is the shape of a loop an issue really can
    sit in -- a fix answered by a review answered by a fix -- rather than a
    list of stages picked to add up to the allowance.
    """

    name: str
    legs: tuple[Leg, ...]
    seed: Mapping[str, Any] = field(default_factory=dict)
    pull_request: bool = False
    pr_fields: Mapping[str, Any] = field(default_factory=dict)
    # How many ticks the walk takes: enough to spend the whole allowance, and
    # the two that meet the refusal afterwards. A journey carrying a leg that
    # starts no process -- a base refresh -- spends nothing on those passes
    # and says how many more it needs.
    ticks: int = ALLOWANCE + REFUSED_TICKS


@dataclass(frozen=True)
class Pass:
    """What one tick of a walk started, and the round it left behind.

    The round travels with the spawn count because a reset is the one thing a
    journey about resets can only show by watching: a round staged back to
    nothing proves nothing, and a round the tick itself put back proves the
    loop really has no end.
    """

    spawned: int
    review_round: Any


@dataclass(frozen=True)
class Walk:
    """What one walk left behind: the issue, and every pass over it."""

    github: FakeGitHubClient
    issue: Any
    passes: tuple[Pass, ...]

    @property
    def spawns(self) -> tuple[int, ...]:
        """How many processes each tick of this walk started."""
        return tuple(walked.spawned for walked in self.passes)

    @property
    def rounds(self) -> tuple[Any, ...]:
        """The review round each tick left the issue on."""
        return tuple(walked.review_round for walked in self.passes)

    @property
    def total(self) -> int:
        """How many agent processes this walk started, over every tick."""
        return sum(self.spawns)

    @property
    def spent(self) -> int:
        """What the issue's own pinned comment says it has spent."""
        return self.pinned.get(_run_ledger_values.AGENT_RUNS_USED)

    @property
    def pinned(self) -> dict:
        """The issue's durable state, as any later process would read it."""
        return self.github.pinned_data(self.issue.number)

    @property
    def parked(self) -> bool:
        """Whether the issue is durably stopped on its spent ledger."""
        return bool(self.pinned.get(KEY_AWAITING_HUMAN)) and (
            self.pinned.get(KEY_PARK_REASON) == _run_limit.PARK_AGENT_RUN_LIMIT
        )

    @property
    def notices(self) -> list[str]:
        """Every exhaustion notice this issue's thread was ever told."""
        return [
            body
            for number, body in self.github.posted_comments
            if number == self.issue.number and _EXHAUSTION_PHRASE in body
        ]


# What the park's own sentence says, and nothing else on the thread does.
_EXHAUSTION_PHRASE = "lifetime agent-run allowance"
