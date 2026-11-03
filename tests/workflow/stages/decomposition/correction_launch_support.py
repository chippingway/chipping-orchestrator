# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A rejected decomposer run on the correction world, and the correction road asked over it.

The road is asked directly, as the manifest dispatch and a later tick's
reconciliation ask it, with only the decomposer process scripted (`Runner`)
and the read-only checkout named, so the
strict writes, the arming, the daily retry, the run circuit's charge, and every
fresh read of the issue are the production ones. What befalls the issue
meanwhile (`Meanwhile`) can land right before one of its fresh fetches
(`OnFetch`), which a launch makes in pairs, before and behind each check's
thread read: ahead of its daily retry, on the reading its charge is written
over, immediately before the charge's edit leaves, behind that charge, on the
reading its start is written over, and immediately before the start's edit
leaves -- or right behind another of the client's reads, a thread read among
them, or during the strict editor's own walk to the comment ahead of an edit
(`OnWalk`).
"""
from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents import models as _agent_models, runner as _agent_runner
from orchestrator.workflow.stages.decomposition import correction_road as _road
from orchestrator.workflow.stages.decomposition.models import _DecomposerRunPlan
from tests.support.fakes import FakeLabel
from tests.workflow.git_owners import seam_patch
from tests.workflow.repo_values import _TEST_SPEC, EXISTING_CHECKOUT
from tests.workflow.stages.decomposition import correction_test_support as support

# A split whose second child leaves its list out, which the parser refuses as
# `support.DIAGNOSTIC`.
REJECTED = (
    "```orchestrator-manifest\n"
    '{"decision": "split", "children": [{"title": "A", "body": "a", "depends_on": []}, {"title": "B", "body": "b"}]}\n'
    "```"
)

# The read-only checkout the saved session was opened in, one this host holds.
CHECKOUT = EXISTING_CHECKOUT

# The daily retry budget, and the count it keeps.
DAILY = 3
RETRIES = "retry_count"

# The issue fetch on the reading a launch's charge is written over, the one
# immediately before the charge's edit leaves, the one right behind that
# charge, the one on the reading its start is written over, and the one
# immediately before the start's edit leaves.
ON_THE_CHARGE = 3
AT_THE_CHARGE = 5
BEHIND_THE_CHARGE = 7
BEFORE_THE_START = 9
AT_THE_START = 11

# The thread read a spent budget's landed park reconciles its notice on.
THE_NOTICE_READ = 3

# The hold a human applies.
PAUSED = "paused"


def rejected(world: support.CorrectionWorld, **fields) -> _DecomposerRunPlan:
    """The plan of the run charged at `support.SOURCE`, completed and accounted, its answer `REJECTED` unless named."""
    returned = {
        "session_id": support.SESSION,
        "last_message": REJECTED,
        "exit_code": 0,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
        "invocation": support.invocation(world),
        **fields,
    }
    return _DecomposerRunPlan(agent_result=_agent_models.AgentResult(**returned))


def opened(days_ago: int) -> str:
    """A retry window opened `days_ago` days back."""
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def replaced(meanwhile: Meanwhile) -> None:
    """A human posts the record, as it reads, as a new pinned comment in place of the one it was on."""
    world = meanwhile.world
    world.github.seed_state(world.issue, **world.record())


@dataclasses.dataclass
class Runner:
    """The runner seam: each process invoked, with what the comment carried as it was, answered with no message.

    `limit` is the lifetime run ceiling the launch is charged against, none
    unless named.
    """

    world: support.CorrectionWorld
    limit: int = 0
    launches: list = dataclasses.field(default_factory=list)

    def __call__(self, backend: str, prompt: str, cwd, *, options) -> _agent_models.AgentResult:
        self.launches.append((backend, prompt, cwd, options, self.world.record()))
        return _agent_models.AgentResult(
            session_id=support.SESSION, last_message="", exit_code=0, timed_out=False, stdout="", stderr="",
        )

    def asks(self, operation, *arguments):
        """Ask the road's `operation` over the world's caller state, the process scripted, under `limit`."""
        world = self.world
        with (
            patch.object(config, "MAX_AGENT_RUNS_PER_ISSUE", self.limit),
            patch.object(config, "MAX_RETRIES_PER_DAY", DAILY),
            patch.object(_agent_runner, "run_agent", self),
            seam_patch("_decompose_worktree_path", lambda spec, number: CHECKOUT),
        ):
            return operation(world.github, _TEST_SPEC, world.issue, world.state, *arguments)

    def requests(self, run_plan: _DecomposerRunPlan) -> _road.CorrectionAsk:
        """Ask for the correction `run_plan`'s answer earns."""
        return self.asks(_road.requests, run_plan)

    def launch(self, attempt=None) -> _agent_models.AgentResult | None:
        """Ask for the launch of `attempt`, the one the seeded rejected run armed unless named."""
        return self.asks(_road.launch, attempt or support.attempt(self.world))


@dataclasses.dataclass(frozen=True)
class Meanwhile:
    """What befalls `world`'s issue while a correction is armed or charged."""

    world: support.CorrectionWorld

    def hold(self) -> None:
        self.world.issue.labels.append(FakeLabel(PAUSED))

    def lift(self) -> None:
        issue = self.world.issue
        issue.labels = [label for label in issue.labels if label.name != PAUSED]

    def close(self) -> None:
        self.world.issue.closed = True

    def relabel(self) -> None:
        self.world.github.set_workflow_label(self.world.issue, "workflow:ready")

    def edit(self) -> None:
        self.world.issue.body = "Ship one command-line entry point instead."

    def unreadable(self) -> None:
        raise RuntimeError("502")

    def rewrites(self, **fields) -> None:
        """Another road or a human writes `fields` over the comment, whole."""
        self.world.moves(**fields)


@dataclasses.dataclass
class OnFetch:
    """The issue fetch -- or another read on the client -- letting `move` befall the world right before its `nth` call.

    Before the `nth` issue fetch, and right behind the `nth` call of any
    other read named (`patch`'s `seam`), since what that read returned is
    what a move behind it outdates.
    """

    meanwhile: Meanwhile
    nth: int
    move: object
    fetch: object
    behind: bool = False
    seen: int = 0

    def __call__(self, *args, **kwargs):
        self.seen += 1
        due = self.seen == self.nth
        if due and not self.behind:
            self.move(self.meanwhile)
        answered = self.fetch(*args, **kwargs)
        if due and self.behind:
            self.move(self.meanwhile)
        return answered

    @classmethod
    def patch(cls, world: support.CorrectionWorld, nth: int, move, seam: str = "get_issue"):
        """The world's issue fetch, or its read `seam`, so patched for the block; `move` is a `Meanwhile` method."""
        github = world.github
        read = getattr(github, seam)
        reads = cls(Meanwhile(world), nth, move, read, behind=seam != "get_issue")
        return patch.object(github, seam, side_effect=reads)


@dataclasses.dataclass
class OnWalk:
    """The strict editor's walk to the comment, letting `move` befall the world while its `nth` walk is out."""

    meanwhile: Meanwhile
    nth: int
    move: object
    walk: object
    seen: int = 0

    def __call__(self, issue, comment_id, *, authoritative: bool = False):
        located = self.walk(issue, comment_id, authoritative=authoritative)
        self.seen += int(authoritative)
        if authoritative and self.seen == self.nth:
            self.move(self.meanwhile)
        return located

    @classmethod
    def patch(cls, world: support.CorrectionWorld, nth: int, move):
        """The world's strict walk, so patched for the block; `move` is a `Meanwhile` method."""
        walks = cls(Meanwhile(world), nth, move, world.github._pinned_comment)
        return patch.object(world.github, "_pinned_comment", side_effect=walks)
