# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue's pinned record, a developer run returned over it, and the completion captured from it.

Driven through the in-memory client, whose strict edit is the real client's
policy over its own records, so a write over a capture here makes the requests
production makes and is answered as production would be: a read GitHub leaves
unanswered, an edit refused before it lands, and one that landed with its
response lost.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json

from orchestrator.agents.models import AgentInvocation, AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_commits as _commits,
    completion_records as _records,
    completion_routes as _routes,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue

ISSUE = 2426
REPO = "chippingway/chipping-orchestrator"
FIELD = _records.DEVELOPER_COMPLETION
STATUS = _commits.CheckpointStatus
REFUSAL = _commits.CheckpointRefusal
STAGE = _records.CaptureStage

REQUIREMENTS = hashlib.sha256(b"the requirements the run was handed").hexdigest()
BEFORE = hashlib.sha1(b"the head the run started on", usedforsecurity=False).hexdigest()
SOURCE = hashlib.sha1(b"the head the report is about", usedforsecurity=False).hexdigest()
BRANCH = "orchestrator/chippingway__chipping-orchestrator/issue-2426"
REPORT = "Implemented the capture.\n\nChecks: the focused suite passed."
READY = f"Done.\n\nREPORT: READY\n{REPORT}\nREPORT: END"
VERIFIED_PR = 12
VERIFIED_COMMENT = 88
VERIFIED_REVISION = hashlib.sha256(b"the report already on the pull request").hexdigest()
VERIFIED = (
    f"REPORT: VERIFIED https://github.com/{REPO}/pull/{VERIFIED_PR}"
    f"#issuecomment-{VERIFIED_COMMENT} sha256:{VERIFIED_REVISION}"
)
SESSION = "session-1"

# What actually ran, and where.
RUN = _records.CompletionRun(
    command="claude --model claude-opus-5-5 --permission-mode bypassPermissions",
    prompt_revision=hashlib.sha256(b"the prompt the run was handed").hexdigest(),
    worktree="/worktrees/chippingway__chipping-orchestrator/issue-2426",
    branch=BRANCH,
    before_sha=BEFORE,
    source_sha=SOURCE,
)

# The first implementation's road, which answers no frozen handoff.
IMPLEMENTATION = _records.CompletionHandoff(
    route=_routes.CompletionRoute.IMPLEMENTATION,
    origin=WorkflowLabel.IMPLEMENTING,
    requirements_revision=REQUIREMENTS,
)

_NONCE_SPELLING = "016x"

# What every run below reports it used, accounted as it returned.
_USAGE = UsageMetrics(backend="claude", cost_source="reported")


def returned(ran_as: AgentInvocation | None, message: str = READY, **overrides) -> AgentResult:
    """What one tracked process returned, identified as `ran_as`: a completed run ending on `message`."""
    finished = {
        "session_id": SESSION,
        "last_message": message,
        "exit_code": 0,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
        "usage": _USAGE,
        "invocation": ran_as,
    }
    return AgentResult(**{**finished, **overrides})


def seeded(**record) -> CompletionWorld:
    """An issue pinned with `record` beside the requirements its run was handed, and the state its caller read."""
    issue = make_issue(ISSUE)
    github = FakeGitHubClient([issue])
    github.seed_state(issue, user_content_hash=REQUIREMENTS, **copy.deepcopy(record))
    return CompletionWorld(github, issue, github.read_pinned_state(issue))


@dataclasses.dataclass
class CompletionWorld:
    """One issue, its client, and the state its caller holds and is handed what landed back on."""

    github: FakeGitHubClient
    issue: FakeIssue
    state: PinnedState

    def invocation(self, ordinal: int = 1, **overrides) -> AgentInvocation:
        """An invocation of this issue under charge `ordinal`, charged on the comment the caller holds."""
        named = {
            "repo": REPO,
            "issue": ISSUE,
            "comment": self.state.comment_id,
            "cycle": 0,
            "ordinal": ordinal,
            "nonce": format(ordinal, _NONCE_SPELLING),
        }
        return AgentInvocation(**{**named, **overrides})

    def completion(
        self,
        ordinal: int = 1,
        *,
        handoff: _records.CompletionHandoff = IMPLEMENTATION,
        message: str = READY,
        **overrides,
    ) -> _records.CompletionCapture:
        """The capture of one completed run under charge `ordinal` on `handoff`'s road."""
        ran = returned(self.invocation(ordinal), message, **overrides)
        built = _checkpoint.captured(ran, handoff, RUN)
        if not isinstance(built, _records.CompletionCapture):
            raise TypeError(f"the run earns no capture: {built}")
        return built

    def captures(self, completion: _records.CompletionCapture) -> _commits.CheckpointOutcome:
        """Ask for `completion` to be captured over the caller's state."""
        return _checkpoint.capture(self.github, self.issue, self.state, completion)

    def asks(self, operation, *arguments) -> _commits.CheckpointOutcome:
        """Ask `operation` -- a capture, its read-back, transfer, or retirement -- over the caller's state."""
        return operation(self.github, self.issue, self.state, *arguments)

    def record(self) -> dict:
        """What the issue's pinned comment carries now."""
        return self.github.pinned_data(ISSUE)

    def snapshot(self) -> tuple[str, int, str]:
        """The record, the pinned writes sent, and the caller's state, spelled to compare exactly."""
        return (
            json.dumps(self.record(), sort_keys=True),
            self.github.write_state_calls,
            json.dumps(self.state.state_data, sort_keys=True),
        )

    def restarted(self) -> CompletionWorld:
        """The same issue as a fresh process reads it, holding nothing of this one's state."""
        return CompletionWorld(self.github, self.issue, self.github.read_pinned_state(self.issue))
