# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close a poll observed, put where the tests of two packages can set it.

A poll that finds a late-split owner closed while a worker holds it latches
that reading process-wide and leaves a marked receipt on the issue thread. The
latch is what the run in flight asks before every step the remote keeps; the
receipt is what the process after a restart has instead of it.

All of it is process state -- the latch, the memo saying the receipt landed,
the generation that memo is counted against, the claim a poll posts one under,
the claim on the one thread walk a process owes each owner, the cycle a
worker is retiring off a record right now, the issues a worker is acting on,
and the settlements one of those windows has postponed -- so every case that
touches any of them replaces all eight first. That is also how a RESTART
is written: fresh registries beside a thread that still carries the receipt are
exactly what a new process wakes up to.

Here rather than beside either caller because the dispatcher's own tests set
these and the decomposition stage's tests read them, and a second copy of the
fixture would drift from whichever of the two it was not written for.
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator.workflow.engine import observation_state as _observation_state, observations as _observations
from orchestrator.workflow.stages.decomposition import (
    late_close_reading as _late_close_reading,
)

# Every registry the shared observation-state owner keeps, with the empty container a new
# process starts each one on: two of them count rather than merely hold, so a
# case that replaced them all with sets would be testing a record production
# cannot produce.
_REGISTRIES = (
    ("_observed", set),
    ("_receipted", dict),
    ("_posting", set),
    ("_settlements", dict),
    ("_scanned", set),
    ("_retiring", dict),
    ("_publishing", dict),
    ("_deferred", set),
)


def receipt_for(issue_number: int, cycle_id: int) -> str:
    """The receipt one cycle's observed close is stamped with.

    Built through the production spelling, so a test that plants one plants
    exactly what a later process scans for.
    """
    return _late_close_reading._observed_close_marker(issue_number, cycle_id)


class ObservedCloseCase:
    """A case whose process-wide close observations are its own."""

    def _fresh_process(self) -> None:
        """Replace every registry with the one a new process starts on."""
        for held, empty in _REGISTRIES:
            replaced = patch.object(_observation_state, held, empty())
            replaced.start()
            self.addCleanup(replaced.stop)

    def _latch_close(self, repo_slug: str, issue_number: int) -> None:
        """What the polling thread does with a close it can hand nowhere."""
        _observations.observe_close(repo_slug, issue_number)

    def _observed(self, repo_slug: str) -> frozenset:
        """Which of this repo's closes no pass has settled."""
        return _observations.observed_closes(repo_slug)

    def _settle_latches(self, repo_slug: str) -> None:
        """What the pass that took an observation leaves behind: nothing."""
        for held in _observations.observed_closes(repo_slug):
            _observations.settle_close(repo_slug, held)
