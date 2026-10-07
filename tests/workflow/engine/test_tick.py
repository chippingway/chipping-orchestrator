# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The tick owner's per-tick pass order, and the collaborators it hands to."""
from __future__ import annotations

import functools
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.skills import catalog
from orchestrator.workflow.engine import community, dispatch, parallel, tick
from tests.support.fakes import FakeGitHubClient
from tests.workflow.engine import tick_parallel_test_support as support
from tests.workflow.engine.dispatch_scheduler_workers import patch_base_refresh
from tests.workflow.repo_values import _TEST_SPEC

_EXPECTED_PASSES = ("refresh", "sweep", "catalog", "dispatch")


# The two in-tick widths and the owner each one has to reach, read as
# (`parallel_limit`, the sequential loop ran, the bounded pool ran).
_IN_TICK_ROUTES = (
    (1, True, False),
    (2, False, True),
)


class _PassRecorder:
    """Stands in for one tick pass and notes when it fired."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def pass_named(self, name: str):
        return functools.partial(self._record, name)

    def _record(self, name: str, *_args, **_kwargs) -> None:
        self.calls.append(name)


class TickPassOrderTest(unittest.TestCase):
    """The passes run once each, in the order the later ones depend on."""

    def test_pass_order_holds_on_both_routes(self) -> None:
        # The base fetch has to land before the two passes that read what it
        # left behind -- a handler would otherwise rebase onto the SHA its
        # worktree was created at, and the catalog would ls-tree a stale base
        # ref -- and the sweep and the catalog have to sit before the
        # scheduler / in-tick split rather than inside one branch, or a
        # scheduler-driven deployment silently stops labeling outsider PRs and
        # reporting its skill catalog.
        for scheduler in (None, object()):
            with self.subTest(scheduler=scheduler is not None):
                self.assertEqual(
                    self._passes_driven_by(scheduler), list(_EXPECTED_PASSES),
                )

    def _passes_driven_by(self, scheduler) -> list[str]:
        recorder = _PassRecorder()
        with (
            patch_base_refresh(recorder.pass_named("refresh")),
            patch.object(
                community, "_sweep_community_contribution_prs",
                recorder.pass_named("sweep"),
            ),
            patch.object(
                catalog, "_emit_repo_skill_catalog",
                recorder.pass_named("catalog"),
            ),
            patch.object(
                dispatch, "_dispatch_via_scheduler",
                recorder.pass_named("dispatch"),
            ),
            patch.object(
                tick, "_run_sequential_tick", recorder.pass_named("dispatch"),
            ),
        ):
            tick.tick(FakeGitHubClient(), _TEST_SPEC, scheduler=scheduler)
        return recorder.calls


class TickInTickRouteTest(unittest.TestCase):
    """Each in-tick width is driven by the owner that defines it.

    The two modes are separate owners rather than one loop at two widths, so
    the tick names each of them: a route resolved anywhere but on the owner
    would leave the real pass running under a mock aimed at it.
    """

    def test_each_limit_reaches_only_its_own_owner(self) -> None:
        for limit, sequential, bounded in _IN_TICK_ROUTES:
            with self.subTest(parallel_limit=limit):
                self.assertEqual(
                    self._routes_driven_by(limit), (sequential, bounded),
                )

    def _routes_driven_by(self, limit: int) -> tuple[bool, bool]:
        sequential = MagicMock()
        bounded = MagicMock()
        with (
            patch_base_refresh(),
            patch.object(tick, "_run_sequential_tick", sequential),
            patch.object(parallel, "_run_parallel_tick", bounded),
        ):
            tick.tick(FakeGitHubClient(), support._spec(parallel_limit=limit))
        return sequential.called, bounded.called


class TickInvokesSweepTest(unittest.TestCase):
    """`tick` must drive the community-contribution sweep on every tick so a
    newly-opened outsider PR is labeled without the operator having to take
    action.
    """

    def test_tick_calls_sweep_after_refresh(self) -> None:
        gh = FakeGitHubClient()
        refresh = MagicMock()
        sweep = MagicMock()
        with patch_base_refresh(refresh), \
             patch.object(community, "_sweep_community_contribution_prs", sweep):
            tick.tick(gh, _TEST_SPEC)
        sweep.assert_called_once_with(gh, _TEST_SPEC)


if __name__ == "__main__":
    unittest.main()
