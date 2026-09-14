# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Process stops before and during candidate classification and cleanup."""
from __future__ import annotations

from orchestrator.git.worktrees import (
    eligibility,
)


class Stopping:
    """A continuation a test flips, standing in for the signal that flips it."""

    def __init__(self) -> None:
        self.going = True

    def __call__(self) -> bool:
        return self.going


class StopsWhileClassifying:
    """A classification the run is stopped during, on the real classifier.

    Where a signal really lands. The readings are where a candidate's seconds
    go -- the issue, its pull requests, what the remote carries -- and the
    verdict they end at is what every deletion behind them would be pinned to,
    so a stop that arrives in the middle of them is the one that must not be
    answered by going ahead and deleting.
    """

    def __init__(self, stopping: Stopping) -> None:
        self._stopping = stopping
        self._real = eligibility._classify_artifacts

    def __call__(self, gh, artifacts):
        verdict = self._real(gh, artifacts)
        self._stopping.going = False
        return verdict


class StoppedAfter:
    """A continuation that goes on for a fixed number of candidates.

    What a signal landing mid-repository looks like from inside the pass, and
    the reason the answer is asked per candidate: the caller says yes to the
    candidates before the stop and no to every one behind it, and `asked` is
    the record of how often it was put.
    """

    def __init__(self, allowed: int) -> None:
        self.asked: list[bool] = []
        self._allowed = allowed

    def __call__(self) -> bool:
        going = len(self.asked) < self._allowed
        self.asked.append(going)
        return going
