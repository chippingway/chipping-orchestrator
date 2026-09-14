# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an artifact-maintenance test stands in for, and what it does not.

The hold is stood in for wherever the question is what the pass DOES with the
answer -- granted, refused, taken at all -- because how that answer is reached
is held to its own contract in `tests/scheduler/`. The teardown under it is
stood in for the same way, so a runtime test never needs a clone, a remote, or
a checkout to say which repository's candidates went to which client.

The one place both come back is the claim check: the guard the pass is handed
is the live scheduler's own reading, so a test about that runs the real
scheduler and the real pass over a candidate holding no artifacts, which the
claim gate answers before anything on disk or on GitHub is asked about.
"""
from __future__ import annotations

import contextlib
import unittest
from collections.abc import Iterator
from typing import NamedTuple

from orchestrator.config.models import RepoSpec
from orchestrator.git.worktrees.candidates import CandidateLayout, IssueArtifacts, MaintenanceCandidate, MaintenanceScan
from orchestrator.git.worktrees.maintenance_results import MaintenanceOutcome, MaintenanceReason, MaintenanceResult
from orchestrator.runtime.exclusion import ExclusiveHost
from orchestrator.runtime.state import RuntimeState
from orchestrator.scheduler.service import IssueScheduler
from tests.runtime import polling_test_support as _support

CANDIDATES_ATTR = "_maintenance_candidates"
MAINTAINED_ATTR = "_maintained_candidates"
LIFECYCLE_LOGGER = "orchestrator.worktree_lifecycle"
ALPHA_ISSUE_NUMBER = 41
BETA_ISSUE_NUMBER = 42

# One issue at a time, since nothing here submits: what a live scheduler is
# built for in these tests is the claim it holds and the guard that reads it.
_LIVE_CAP = 1


def candidate(spec: RepoSpec, issue_number: int) -> MaintenanceCandidate:
    """One candidate of one repository, holding nothing on this host.

    Empty on purpose: what a runtime test decides is which client is asked
    about which issue, and a candidate with artifacts would invite a teardown
    to be attempted against a host no test built.
    """
    return MaintenanceCandidate(
        artifacts=IssueArtifacts(
            spec=spec, issue_number=issue_number, worktrees=(), branches=(),
        ),
        layout=CandidateLayout.REMOTE_ONLY,
    )


def scan(
    candidates: list[MaintenanceCandidate], refused: tuple[str, ...] = (),
) -> MaintenanceScan:
    """The discovery's whole answer over a host."""
    return MaintenanceScan(candidates=tuple(candidates), refused=refused)


class Turn(NamedTuple):
    """One repository's turn in a pass, as the recorder kept it."""

    github_client: object
    candidates: tuple[MaintenanceCandidate, ...]
    claimed: object
    going: object


class StubScheduler:
    """A scheduler that grants or refuses the hold as a test asks it to.

    `is_active` answers what a quiesced host answers -- nothing is running --
    so a test using this stub is about the pass's composition rather than
    about the claim gate underneath it. `closed` is the other half of that:
    the reading the pass comes back for as it spends a granted hold, which a
    test flips to stand in for a signal landing mid-pass.
    """

    def __init__(self, *, quiet: bool = True) -> None:
        self.quiet = quiet
        self.closed = False
        self.holds = 0
        self.bounds: list[float] = []

    @contextlib.contextmanager
    def maintenance_barrier(self, *, timeout: float) -> Iterator[bool]:
        self.holds += 1
        self.bounds.append(timeout)
        yield self.quiet

    def is_active(self, repo_slug: str, issue_number: int) -> bool:
        return False

    def is_closed(self) -> bool:
        return self.closed


class RecordedPass:
    """`_maintained_candidates` stand-in recording each repository's turn.

    Keeps the client, the candidates, and the guard each turn was handed,
    because the split between repositories is what a caller of that owner is
    responsible for: the client is authenticated against one repository, and a
    candidate that reached the wrong one is the failure worth catching.
    """

    def __init__(self) -> None:
        self.turns: list[Turn] = []

    def __call__(self, github_client, candidates, *, claimed, going):
        taken = tuple(candidates)
        self.turns.append(Turn(github_client, taken, claimed, going))
        return tuple(self.kept(one) for one in taken)

    def kept(self, taken: MaintenanceCandidate) -> MaintenanceResult:
        """The answer a pass that decided to keep a candidate gives."""
        return MaintenanceResult(
            candidate=taken,
            outcome=MaintenanceOutcome.RETAINED,
            reason=MaintenanceReason.UNPROVEN,
        )

    @property
    def asked(self) -> list:
        """Which issues each client was asked about, in the order it was asked."""
        return [
            (
                turn.github_client.slug,
                tuple(one.artifacts.issue_number for one in turn.candidates),
            )
            for turn in self.turns
        ]


class StoppingPass(RecordedPass):
    """A pass the run is stopped inside, on its first repository's turn."""

    def __init__(self, state) -> None:
        super().__init__()
        self._state = state

    def __call__(self, github_client, candidates, *, claimed, going):
        self._state.running = False
        return super().__call__(
            github_client, candidates, claimed=claimed, going=going,
        )


class _MaintenanceTestCase(unittest.TestCase):
    """Two configured repositories, a granted hold, and one recorder.

    Two rather than one, because the pass over several repositories is what
    this owner is for: the discovery spans the host and every candidate has to
    reach the client of the repository it belongs to.

    The run these tests build holds the host, which is what a composed run of
    either launch mode does by the time a pass is reached. A run that holds
    nothing is its own case, and the pass declines it -- so it is asked for
    explicitly rather than arrived at by leaving a field out.
    """

    def setUp(self) -> None:
        self.clients = _support.build_clients(
            [_support.ALPHA_REPO, _support.BETA_REPO],
        )
        self.scheduler = StubScheduler()
        self.recorded = RecordedPass()

    def state(self, **fields) -> RuntimeState:
        """A run that holds this host, as a composed one of either mode does."""
        return RuntimeState(host_claim=ExclusiveHost(), **fields)

    @property
    def specs(self) -> list[RepoSpec]:
        return [spec for spec, _client in self.clients]

    def live_scheduler(self) -> IssueScheduler:
        """A real scheduler, shut down however the test ends."""
        scheduler = IssueScheduler(
            global_cap=_LIVE_CAP, per_repo_cap=_LIVE_CAP,
        )
        self.addCleanup(scheduler.shutdown)
        return scheduler
