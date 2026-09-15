# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ticks an open dependency walk is dispatched on, and the ticks it is not.

`workflow:blocked` and `workflow:umbrella` name handlers that only walk a
dependency graph, so `DEPENDENCY_POLL_EVERY_N_TICKS` leaves them out between
two due polls -- counted on the enumeration the way the closed sweep counts,
the first poll and every Nth after it. What these cases pin down is that the
skip lands before anything is partitioned, submitted, or handed a worker
client, on every dispatch path, and that it takes nothing else with it: the
family bucket still serializes what is left, and a closed owner's cleanup is
still routed.
"""
from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.skills import catalog
from orchestrator.workflow.engine import (
    dispatch_partition as _dispatch_partition,
    poll_models as _poll_models,
    tick as _tick,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine.dispatch_scheduler_test_support import (
    _patch_process_issue,
    _SchedulerWorkflowTest,
)
from tests.workflow.engine.dispatch_scheduler_workers import patch_base_refresh
from tests.workflow.fixtures import (
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    LABEL_IMPLEMENTING,
    LABEL_UMBRELLA,
)
from tests.workflow.observation_support import ObservedCloseCase

_CADENCE_ATTR = "DEPENDENCY_POLL_EVERY_N_TICKS"

_SWEEP_CADENCE_ATTR = "CLOSED_ISSUE_SWEEP_EVERY_N_TICKS"

_EVERY_TICK = 1

_CADENCE = 5

# One whole cadence and the poll that opens the next, so a case sees the first
# due poll, every skipped one, and the due poll after them.
_POLLS = tuple(range(1, _CADENCE + 2))

# Each cadence beside the polls it is due on.
_CADENCES = (
    (_EVERY_TICK, frozenset(_POLLS)),
    (_CADENCE, frozenset((1, _CADENCE + 1))),
)

_DECOMPOSING_NUMBER = 1
_BLOCKED_NUMBER = 2
_UMBRELLA_NUMBER = 4
_PICKUP_NUMBER = 5
_CLOSED_OWNER_NUMBER = 7
_FANOUT_NUMBER = 9

_DEPENDENCY_WALKS = (
    (_BLOCKED_NUMBER, LABEL_BLOCKED),
    (_UMBRELLA_NUMBER, LABEL_UMBRELLA),
)

# The walks beside every kind of open work their skip must leave alone, in the
# order the enumeration yields them.
_MIXED_OPEN = (
    (_DECOMPOSING_NUMBER, LABEL_DECOMPOSING),
    *_DEPENDENCY_WALKS,
    (_PICKUP_NUMBER, None),
    (_FANOUT_NUMBER, LABEL_IMPLEMENTING),
)

_POOL_LIMIT = 3

_SEQUENTIAL = "sequential"
_POOL = "pool"
_SCHEDULER = "scheduler"

_WORKER_PATHS = tuple(
    (boundary, cadence, due_polls)
    for boundary in (_POOL, _SCHEDULER)
    for cadence, due_polls in _CADENCES
)

_EVERY_PATH = tuple(
    (_SEQUENTIAL, cadence, due_polls) for cadence, due_polls in _CADENCES
) + _WORKER_PATHS

# Which issues one tick processed, each with whether it went as a cleanup.
_Routes = dict[int, bool]


def _repo(*, mixed: bool) -> FakeGitHubClient:
    """The two open walks, alone or beside everything else a tick carries.

    Mixed, the repo also holds a closed umbrella owner, which the closed sweep
    yields for its cleanup whatever the dependency cadence says.
    """
    github = FakeGitHubClient()
    for issue_number, label in _MIXED_OPEN if mixed else _DEPENDENCY_WALKS:
        github.add_issue(make_issue(issue_number, label=label))
    if mixed:
        github.add_issue(make_issue(
            _CLOSED_OWNER_NUMBER, label=LABEL_UMBRELLA, closed=True,
        ))
    return github


def _family_bucket(*, due: bool) -> list[tuple[int, str | None]]:
    """The mixed repo's family bucket, in enumeration order."""
    walks = list(_DEPENDENCY_WALKS) if due else []
    return [
        (_DECOMPOSING_NUMBER, LABEL_DECOMPOSING),
        *walks,
        (_PICKUP_NUMBER, None),
    ]


def _mixed_routes(*, due: bool) -> _Routes:
    """Every issue the mixed repo's tick processes, and whether as cleanup."""
    routes = dict.fromkeys(
        (_DECOMPOSING_NUMBER, _PICKUP_NUMBER, _FANOUT_NUMBER), False,
    )
    if due:
        routes.update(dict.fromkeys(dict(_DEPENDENCY_WALKS), False))
    routes[_CLOSED_OWNER_NUMBER] = True
    return routes


class _TickProbe:
    """What each tick handed to processing, and the worker clients it minted.

    Locked, because the two worker paths record from their own threads.
    """

    def __init__(self, github: FakeGitHubClient) -> None:
        self.routes_per_tick: list[_Routes] = []
        self.mints_per_tick: list[int] = []
        self._github = github
        self._lock = threading.Lock()
        self._routes: _Routes = {}
        self._minted = 0

    def process(self, _gh, _spec, issue, **route) -> None:
        """Record the issue with the route its dispatch carried."""
        reading = route.get("reading", _poll_models._POLLED_OPEN)
        with self._lock:
            self._routes[int(issue.number)] = reading.cleanup_only

    def mint(self) -> FakeGitHubClient:
        """Count a worker client, answering with the one fake repo."""
        with self._lock:
            self._minted += 1
        return self._github

    def tick_ended(self) -> None:
        """Close the finished tick's record and start the next one empty."""
        with self._lock:
            self.routes_per_tick.append(dict(self._routes))
            self.mints_per_tick.append(self._minted)
            self._routes.clear()
            self._minted = 0


class _DependencyCadenceCase(ObservedCloseCase, _SchedulerWorkflowTest):
    """Fresh close observations, and a closed sweep on every poll."""

    def setUp(self) -> None:
        self._fresh_process()
        every_sweep = patch.object(config, _SWEEP_CADENCE_ATTR, _EVERY_TICK)
        every_sweep.start()
        self.addCleanup(every_sweep.stop)

    def _polled(
        self, github: FakeGitHubClient, cadence: int, boundary: str,
    ) -> _TickProbe:
        """Tick the repo once per poll on one path, probing every tick."""
        probe = _TickProbe(github)
        with (
            patch.object(config, _CADENCE_ATTR, cadence),
            patch_base_refresh(),
            patch.object(catalog, "_emit_repo_skill_catalog"),
            _patch_process_issue(side_effect=probe.process),
            patch.object(github, "_for_worker_thread", side_effect=probe.mint),
        ):
            for _ in _POLLS:
                self._ticked(github, boundary)
                probe.tick_ended()
        return probe

    def _ticked(self, github: FakeGitHubClient, boundary: str) -> None:
        """One tick on the dispatch path this boundary names, run to the end."""
        if boundary == _SEQUENTIAL:
            _tick.tick(github, self._spec(parallel_limit=1))
        elif boundary == _POOL:
            _tick.tick(github, self._spec(parallel_limit=_POOL_LIMIT))
        else:
            scheduler = self._scheduler()
            _tick.tick(github, self._spec(), scheduler=scheduler)
            scheduler.shutdown(wait=True)


class PartitionCadenceTest(_DependencyCadenceCase):
    """The partition the bounded pool and the scheduler both submit from."""

    def test_the_walks_join_only_a_due_family_bucket(self) -> None:
        # The bucket keeps its order and its other members on every poll, so
        # a skipped tick still serializes `decomposing` beside the pickup; the
        # closed owner fans out as cleanup whichever poll it is.
        for cadence, due_polls in _CADENCES:
            partitions = self._partitions(cadence)
            for poll, partition in zip(_POLLS, partitions, strict=True):
                with self.subTest(cadence=cadence, poll=poll):
                    self.assertEqual(
                        list(zip(
                            partition.family_numbers,
                            partition.family_labels,
                            strict=True,
                        )),
                        _family_bucket(due=poll in due_polls),
                    )
                    self.assertEqual(
                        partition.fanout_numbers,
                        [_FANOUT_NUMBER, _CLOSED_OWNER_NUMBER],
                    )
                    self.assertEqual(
                        partition.cleanup_numbers, {_CLOSED_OWNER_NUMBER},
                    )

    def test_a_held_close_outranks_a_skipped_poll(self) -> None:
        # An open walk this process already saw closed is owed the cleanup
        # that reading earned, and dropping it with the skip would lose the
        # one thing a reopen could not take off the remote.
        github = _repo(mixed=True)
        with patch.object(config, _CADENCE_ATTR, _CADENCE):
            _dispatch_partition._partition_pollable_issues(github, self._spec())
            skipped = _dispatch_partition._partition_pollable_issues(
                github, self._spec(), frozenset((_BLOCKED_NUMBER,)),
            )

        self.assertNotIn(
            _UMBRELLA_NUMBER, skipped.family_numbers + skipped.fanout_numbers,
        )
        self.assertNotIn(_BLOCKED_NUMBER, skipped.family_numbers)
        self.assertIn(_BLOCKED_NUMBER, skipped.cleanup_numbers)

    def _partitions(
        self, cadence: int,
    ) -> list[_poll_models._PollablePartition]:
        """One partition of a fresh mixed repo per poll, at this cadence."""
        github = _repo(mixed=True)
        with patch.object(config, _CADENCE_ATTR, cadence):
            return [
                _dispatch_partition._partition_pollable_issues(
                    github, self._spec(),
                )
                for _ in _POLLS
            ]


class TickCadenceTest(_DependencyCadenceCase):
    """Every path a tick can take, from enumeration to the handler."""

    def test_each_path_walks_only_on_due_ticks(self) -> None:
        # The sequential loop classifies on the polling thread and mints
        # nothing; the two worker paths mint one client per issue they
        # process, so a skipped walk costs neither a dispatch nor a client.
        for boundary, cadence, due_polls in _EVERY_PATH:
            self._assert_mixed_ticks(boundary, cadence, due_polls)

    def test_a_skipped_tick_mints_no_worker_client(self) -> None:
        # With nothing else open, the walks are the whole of a worker tick's
        # spend: a client each on a due poll and none at all in between.
        for boundary, cadence, due_polls in _WORKER_PATHS:
            probe = self._polled(_repo(mixed=False), cadence, boundary)
            with self.subTest(boundary=boundary, cadence=cadence):
                self.assertEqual(
                    probe.mints_per_tick,
                    [
                        len(_DEPENDENCY_WALKS) if poll in due_polls else 0
                        for poll in _POLLS
                    ],
                )

    def _assert_mixed_ticks(
        self, boundary: str, cadence: int, due_polls: frozenset[int],
    ) -> None:
        probe = self._polled(_repo(mixed=True), cadence, boundary)
        for poll, routes, minted in zip(
            _POLLS, probe.routes_per_tick, probe.mints_per_tick, strict=True,
        ):
            with self.subTest(boundary=boundary, cadence=cadence, poll=poll):
                self.assertEqual(routes, _mixed_routes(due=poll in due_polls))
                self.assertEqual(
                    minted, 0 if boundary == _SEQUENTIAL else len(routes),
                )


if __name__ == "__main__":
    unittest.main()
