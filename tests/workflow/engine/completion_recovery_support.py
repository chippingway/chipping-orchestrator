# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue whose developer run captured its completion, the checkout it ran in, and the capture landed on it.

The capture is landed through its own checkpoint over the pinned comment the
in-memory client holds, as a producer will land one, so every reading the
recovery takes -- the read-back, the issue, the thread its requirements are
fingerprinted from, the pull request -- is a request the client answers as
production would. The checkout is the one seam stood in for: its identity
and its head are answered on the git owners that read them.
"""
from __future__ import annotations

import contextlib
import copy
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.agents.models import AgentInvocation, AgentResult
from orchestrator.git.verification import probes as _probes
from orchestrator.git.worktrees import evidence as _evidence, models as _models, naming as _naming, paths as _paths
from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_records as _records,
    completion_routes as _routes,
    completion_spelling as _spelling,
    invocations as _invocations,
    prompt_context as _prompt_context,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.fixtures import _TEST_SPEC

NUMBER = 2427
PR_NUMBER = 77
FIELD = _records.DEVELOPER_COMPLETION
BEFORE = "1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b"
SOURCE = "5c5c5c5c5c5c5c5c5c5c5c5c5c5c5c5c5c5c5c5c"
ELSEWHERE = "e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1e1"
BRANCH = _naming._branch_name(_TEST_SPEC, NUMBER)
WORKTREE = _paths._worktree_path(_TEST_SPEC, NUMBER)

# What a hand edit spells to take a field off the comment.
DROPPED = object()

# The lifetime count the issue's own work left before the captured run.
RUNS_USED = 3

# What the captured run ran under, and the digest of the prompt it was handed.
COMMAND = "claude --model claude-opus-5-5"
PROMPT = "abababababababababababababababababababababababababababababababab"

# The charge the captured run was started under, as its invocation names it.
ORDINAL = 3
NONCE = "00000000000000a3"

# A live late adjudication of the issue's own candidate, measured past its ceiling.
ADJUDICATING = MappingProxyType({
    "late_cycle_id": 1,
    "late_generation": 1,
    "late_root_issue": NUMBER,
    "late_current_issue": NUMBER,
    "late_lineage_depth": 0,
    "late_candidate_sha": SOURCE,
    "late_base_sha": BEFORE,
    "late_threshold": 100,
    "late_additions": 500,
    "late_phase": "adjudicating",
})

# What the run returned: a completed READY report.
_READY = "Done.\n\nREPORT: READY\nImplemented it; the focused checks pass.\nREPORT: END"

# Where the captured run ran, and the commits it started on and reported on.
_RUN = MappingProxyType({
    "command": COMMAND,
    "prompt_revision": PROMPT,
    "worktree": str(WORKTREE),
    "branch": BRANCH,
    "before_sha": BEFORE,
    "source_sha": SOURCE,
})


def road(
    route: _routes.CompletionRoute = _routes.CompletionRoute.IMPLEMENTATION,
    origin: WorkflowLabel = WorkflowLabel.IMPLEMENTING,
    frozen: tuple = (),
) -> tuple:
    """The road a capture is taken on: its route, the label it reports under, and the handoff frozen over."""
    return (route, origin, frozen)


def read_capture(record: dict) -> _records.CompletionCapture | _records.ResolvedCapture | None:
    """The capture a pinned record carries, read as its own reader reads it."""
    return _spelling.read_record(record.get(FIELD))


def landed_capture(
    github: FakeGitHubClient, issue, ran: _records.CompletionRun, taken_on: tuple,
) -> _records.CompletionCapture:
    """Land, on `issue`'s pinned comment, the capture of one READY return that ran as `ran` on `taken_on`.

    Its requirements are the ones the issue reads as now, fingerprinted as a
    developer prompt is handed them, and its invocation a charge on that
    comment.
    """
    state = github.read_pinned_state(issue)
    handoff = _handoff(github, issue, taken_on)
    completion = _checkpoint.captured(_returned(state, issue.number), handoff, ran)
    if not _checkpoint.capture(github, issue, state, completion).settled:
        raise AssertionError("the capture did not land")
    return completion


def _handoff(github: FakeGitHubClient, issue, taken_on: tuple) -> _records.CompletionHandoff:
    """What `taken_on` froze before the launch, over the requirements the issue reads as now."""
    route, origin, frozen = taken_on
    state = github.read_pinned_state(issue)
    thread = _prompt_context._delivered_thread(github, issue, state)
    return _records.CompletionHandoff(route, origin, thread.requirements_revision, frozen=frozen)


def _returned(state, issue_number: int) -> AgentResult:
    """A completed READY return, from a process charged on the comment `state` was read from, in its cycle."""
    invocation = AgentInvocation(
        repo=state.repo_slug, issue=issue_number, comment=state.comment_id, cycle=_invocations.cycle_of(state),
        ordinal=ORDINAL, nonce=NONCE,
    )
    return AgentResult(
        session_id="dev-sess", last_message=_READY, exit_code=0, timed_out=False, stdout="", stderr="",
        invocation=invocation,
    )


class CapturedWorld:
    """One issue on `label`, its run's completion captured, the checkout standing on `head`."""

    def __init__(self, label: WorkflowLabel = WorkflowLabel.IMPLEMENTING, *, pull_request: bool = False) -> None:
        self.issue = make_issue(NUMBER, label=str(label))
        self.github = FakeGitHubClient([self.issue])
        recorded = {"branch": BRANCH, "agent_runs_used": RUNS_USED, "issue_agent_runs": RUNS_USED}
        if pull_request:
            recorded["pr_number"] = PR_NUMBER
            standing_on = FakePRRef(sha=BEFORE)
            self.github.add_pr(FakePR(number=PR_NUMBER, head_branch=BRANCH, head=standing_on))
        self.github.seed_state(self.issue, **recorded)
        self.head = SOURCE
        self.identity = _models.ProbeAnswer.CONFIRMED

    def captured(self, taken_on: tuple | None = None, **run) -> _records.CompletionCapture:
        """Land the capture of one READY return on `taken_on` (`road()`), its run overridden by `run`."""
        ran = _records.CompletionRun(**{**_RUN, **run})
        return landed_capture(self.github, self.issue, ran, taken_on or road())

    def record(self) -> dict:
        """What the pinned comment carries now, copied."""
        return copy.deepcopy(self.github.pinned_data(NUMBER))

    def hand_edit(self, **fields) -> None:
        """Somebody edits the pinned comment in place: each of `fields` set, or taken off where given `DROPPED`."""
        pinned = self.github._pinned[NUMBER].state_data
        for name, edited in fields.items():
            if edited is DROPPED:
                pinned.pop(name, None)
            else:
                pinned[name] = copy.deepcopy(edited)

    def checkout(self) -> contextlib.AbstractContextManager:
        """The checkout's identity and head as they stand at each read, answered on the git owners read through.

        The head is a commit the store holds whatever it names: a head no
        store holds is driven on a real repository (`captured_checkout_support`).
        """
        seams = contextlib.ExitStack()
        seams.enter_context(patch.object(_evidence, "_checkout_identity", MagicMock(side_effect=self._identity)))
        seams.enter_context(patch.object(_probes, "_head_sha", MagicMock(side_effect=self._head)))
        seams.enter_context(patch.object(_probes, "_commit_present", MagicMock(return_value=True)))
        return seams

    def _identity(self, *_read) -> _models.ProbeAnswer:
        """What the checkout's identity reads as now."""
        return self.identity

    def _head(self, *_read) -> str:
        """The commit the checkout stands on now."""
        return self.head


class RepairedBehind:
    """A pinned read that lands somebody's hand edit of `fields` just before its `reading`th answer, once.

    Every answer before it is the comment as it stood, so whatever the
    dispatch decided on them is decided on a record the edit then moves.
    """

    def __init__(self, world: CapturedWorld, reading: int, **fields) -> None:
        self._world = world
        self._reader = world.github.read_pinned_state
        self._reading = reading
        self._fields = fields
        self._answered = 0

    def __call__(self, issue):
        """The reading, the edit landed first where this is the one it lands behind."""
        self._answered += 1
        if self._answered == self._reading:
            self._world.hand_edit(**self._fields)
        return self._reader(issue)
