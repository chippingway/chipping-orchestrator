# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The cycle-retirement window a concurrent close observation must recognize.

The held cycle id and the close noticed during retirement share the process
observation lock. Leaving the window always drops its cycle marker and hands
the retiring caller the close that its own remote write could not reread."""
from __future__ import annotations

import contextlib
from dataclasses import dataclass

from orchestrator.workflow.engine import observation_state as _observation_state


@dataclass
class RetiringCycle:
    """One worker's retirement window, and what landed inside it.

    Mutable where `ReceiptClaim` is frozen, because the answer is not known
    when the window opens: `observed` is written as the window CLOSES, under
    the lock that closes it, so what a caller reads afterwards is every close
    latched while the cycle was still advertised and nothing latched after.

    Built before the write it covers rather than by the `with` that holds it,
    so the answer outlives the block that decided it.
    """

    key: tuple[str, int]
    cycle_id: int
    observed: bool = False

    @contextlib.contextmanager
    def held(self):
        """Advertise this cycle for as long as the retirement write runs.

        A retirement is the one write that takes a cycle identity OFF a
        record, and everything that decides what a close is worth reads that
        identity: a poll asks the record whether there is a cycle a close
        would end, and the ending itself is entered from the mark a cycle
        carries. So between that write and the barrier behind it the record
        answers "nothing to end" about an issue whose worker is still holding
        the reading -- and a poll that believed it would drop the observation
        the worker is about to ask for.

        Held across the write, so both orderings answer the same: a poll that
        reads the record first sees the cycle, and one that reads it after
        sees this. What is advertised is the cycle id, which is what makes the
        observation DURABLE across the retirement -- the receipt a poll leaves
        on the thread is scoped to a cycle, and a retired record has none to
        scope it to.

        What the window OBSERVED is taken as it closes, under the same lock
        that closes it. That is the whole of the handoff: a barrier the worker
        takes before the exit leaves an interval -- however short -- in which
        a poll can still latch a close and post a receipt against the cycle
        this is advertising, and the worker would pass on having seen neither.
        Deciding it at the exit leaves no such interval: every observation
        made while the cycle was advertised is reported, and one made after it
        finds a record with no cycle and no window to correlate against, so it
        is dropped rather than written down.

        A cycle id of zero is no cycle at all -- an umbrella the initial
        decomposer made retires nothing -- and advertising one would have a
        poll keep a reading against an identity nothing could ever correlate
        it to. Nothing is advertised and nothing is observed.

        A worker holds one for one issue at a time, because the scheduler
        admits no second worker for an issue one is already running.
        """
        if not self.cycle_id:
            yield
            return
        with _observation_state._lock:
            _observation_state._retiring[self.key] = self.cycle_id
        try:
            yield
        finally:
            with _observation_state._lock:
                _observation_state._retiring.pop(self.key, None)
                self.observed = self.key in _observation_state._observed


def retiring(
    repo_slug: str, issue_number: int, cycle_id: int,
) -> RetiringCycle:
    """The window one retirement is made inside, before it is held."""
    return RetiringCycle(
        key=_observation_state._owner_key(repo_slug, issue_number), cycle_id=int(cycle_id),
    )


def cycle_being_retired(
    repo_slug: str, issue_number: int,
) -> int | None:
    """The cycle a worker is retiring off this record right now, if any."""
    with _observation_state._lock:
        return _observation_state._retiring.get(_observation_state._owner_key(repo_slug, issue_number))
