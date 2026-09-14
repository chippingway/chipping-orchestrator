# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Per-`target_root` serialization of the worktree creators.

`tick()` fans non-family-aware stages out across worker threads, so the
creators can run concurrently against one `spec.target_root`. The git they
run -- `git fetch`, `git worktree add`, `git worktree remove` -- writes the
parent clone's `.git/config` under `.git/config.lock`, and without
per-target_root serialization git reports `error: could not lock config
file .git/config: File exists` and the worker fails before its agent ever
spawns. Both a deterministic blocking-fake unit test and a real-git smoke
test pin the contract down.
"""

from __future__ import annotations

import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport, commands, locks
from orchestrator.git.worktrees import creation
from tests.git.concurrency_test_support import (
    BARRIER_TIMEOUT_SECONDS,
    PROBE_DELAY_SECONDS,
    THREAD_TIMEOUT_SECONDS,
    _ConcurrencyProbe,
    _start_and_join,
)
from tests.git.worktrees.real_git_test_support import (
    _EnsureRecorder,
    _RealGitWorktreeRepo,
)

BASE_BRANCH = "main"
SHARED_ISSUES = (1, 2, 3, 4)
ISSUE_NUMBERS = tuple(range(1, 7))


def _spec(repo_slug: str, target_root: str) -> _config_models.RepoSpec:
    return _config_models.RepoSpec(
        slug=repo_slug,
        target_root=Path(target_root),
        base_branch=BASE_BRANCH,
    )


def _ensure_threads(specs) -> list[threading.Thread]:
    """One `_ensure_worktree` worker per (spec, issue number) pair."""
    return [
        threading.Thread(
            target=creation._ensure_worktree,
            args=(spec, issue_number),
        )
        for spec, issue_number in specs
    ]


class EnsureWorktreeSerializationTest(unittest.TestCase):
    """Every git call the creators make rides the per-target_root lock."""

    def setUp(self) -> None:
        # Drop locks retained for temporary paths from earlier cases.
        locks._TARGET_ROOT_LOCKS.clear()

    def test_shared_root_serializes_callers(self) -> None:
        spec = _spec("acme/widget", "/tmp/orchestrator-test-shared-target-root")
        probe = _ConcurrencyProbe(delay=PROBE_DELAY_SECONDS)

        self._run_probed(probe, [(spec, number) for number in SHARED_ISSUES])

        observed = repr(probe.order)
        self.assertEqual(
            probe.maximum_in_flight,
            1,
            f"git plumbing was not serialized; order={observed}",
        )
        # And we actually drove the workers (sanity check).
        self.assertGreaterEqual(len(probe.order), len(SHARED_ISSUES))

    def test_distinct_roots_run_in_parallel(self) -> None:
        # Locks are keyed on `target_root`; two specs pointing at different
        # roots must not serialize or the multi-repo loop loses all
        # parallelism. Both threads block inside the probe simultaneously,
        # so a shared lock would stall one of them until the barrier times
        # out.
        barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)
        probe = _ConcurrencyProbe(barrier=barrier)
        specs = [
            (_spec("acme/one", "/tmp/orchestrator-test-target-root-A"), 1),
            (_spec("acme/two", "/tmp/orchestrator-test-target-root-B"), 1),
        ]

        self._run_probed(probe, specs)

        self.assertEqual(probe.maximum_in_flight, 2)

    def _run_probed(self, probe, specs) -> None:
        with (
            patch.object(commands, "_git", side_effect=probe.git),
            patch.object(
                branch_transport,
                "_authed_target_fetch",
                side_effect=probe.fetch,
            ),
            patch.object(Path, "exists", lambda _path: False),
            patch.object(Path, "mkdir", lambda _path, **_kwargs: None),
        ):
            threads = _ensure_threads(specs)
            _start_and_join(threads, timeout=THREAD_TIMEOUT_SECONDS)
            for thread in threads:
                self.assertFalse(thread.is_alive(), "worker timed out")


class EnsureWorktreeRealGitConcurrencyTest(unittest.TestCase):
    """Six concurrent workers, each requesting their own per-issue worktree
    against a real bare remote. Without the lock, even at two workers
    `git worktree add` intermittently reports `error: could not lock config
    file .git/config: File exists`; with it every worker succeeds and gets
    its own checkout deterministically.
    """

    def setUp(self) -> None:
        self._repo = _RealGitWorktreeRepo()
        self._repo.prepare(self)

    def test_same_root_ensure_worktree_serialized(self) -> None:
        recorder = _EnsureRecorder(self._repo.spec)
        recorder.run_workers(self, ISSUE_NUMBERS)
        recorder.assert_all_succeeded(self, ISSUE_NUMBERS)
        recorder.assert_worktrees_exist(self)


if __name__ == "__main__":
    unittest.main()
