# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One initial decomposition's pinned record, a rejected decomposer answer on it, and the correction it may earn.

Driven through the in-memory client, whose strict edit is the real client's
policy over its own records, so a write over an attempt here makes the
requests production makes and is answered as production would be: a read
GitHub leaves unanswered, an edit refused before it lands, and one that landed
with its response lost.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import patch

from orchestrator.agents.models import AgentInvocation
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.stages.decomposition import (
    correction_checkpoint as _checkpoint,
    correction_commits as _commits,
    correction_records as _records,
    correction_standing as _standing,
)
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue

ISSUE = 2462
REPO = "chippingway/chipping-orchestrator"
FIELD = "decomposer_correction"
STATUS = _commits.CorrectionStatus
REFUSAL = _commits.CorrectionRefusal
STANDING = _standing.Standing
STAGE = _records.CorrectionStage

BASELINE = "user_content_hash"
COMMAND_PIN = "decomposer_agent"
SESSION_PIN = "decomposer_session_id"
USED = "agent_runs_used"
METERED = "issue_agent_runs"
OWED_STARTED = "agent_run_owed_started"
RESERVATION = "agent_run_reservation"
RECEIPTS = "issue_usage_receipts"

# The issue sits on the initial decomposition's label, and the requirements the
# rejected decomposer was handed are its own, as the drift check fingerprints
# them, so the issue read afresh still stands as that revision; a human's edit
# names another.
LABEL = "workflow:decomposing"
REQUIREMENTS = _content_hash._compute_user_content_hash(make_issue(ISSUE), set(), comments=[])
EDITED = _content_hash._compute_user_content_hash(make_issue(ISSUE, body="edited"), set(), comments=[])
COMMAND = "codex --model gpt-5.5 -c model_reasoning_effort=high"
SESSION = "decomposer-session-1"
DIAGNOSTIC = "child 1 missing depends_on"

# The lifetime charge the rejected decomposer run was started under.
SOURCE = 4

_NONCE_SPELLING = "016x"

# What the issue carries besides the requirements, the conversation, and the
# ledger: a usage total and its receipt, a park, a watermark, the manifest
# markers, and a field this build does not know -- none of them an attempt's
# to move.
CARRIED = (
    ("issue_total_cost_usd", 1.25),
    (RECEIPTS, {"floor": 0, "recent": [[SOURCE, format(SOURCE, _NONCE_SPELLING)]]}),
    ("awaiting_human", False),
    ("park_reason", None),
    ("last_action_comment_id", 900),
    ("children", []),
    ("retry_count", 1),
    ("operator_note", "kept as written"),
)


def seeded(**record) -> CorrectionWorld:
    """An issue whose rejected decomposer run was its last charge, beside `record`, and the state its caller read."""
    issue = make_issue(ISSUE, label=LABEL)
    github = FakeGitHubClient([issue])
    pinned = {
        BASELINE: REQUIREMENTS,
        COMMAND_PIN: COMMAND,
        SESSION_PIN: SESSION,
        USED: SOURCE,
        METERED: SOURCE,
        RESERVATION: "started",
        **copy.deepcopy(dict(CARRIED)),
    }
    github.seed_state(issue, **{**pinned, **copy.deepcopy(record)})
    return CorrectionWorld(github, issue, github.read_pinned_state(issue))


@dataclasses.dataclass
class CorrectionWorld:
    """One issue, its client, and the state its caller holds and is handed what landed back on."""

    github: FakeGitHubClient
    issue: FakeIssue
    state: PinnedState

    def arms(self, armed: _records.CorrectionSource | None = None) -> _commits.CorrectionOutcome:
        """Ask for `armed` -- the seeded rejected run by default -- to be armed over the caller's state."""
        return self.asks(_checkpoint.arm, armed or source(self))

    def asks(self, operation: Callable, *arguments) -> _commits.CorrectionOutcome:
        """Ask `operation` -- an arming, read-back, exhaustion, or retirement -- over the caller's state."""
        return operation(self.github, self.issue, self.state, *arguments)

    def reads(self) -> _standing.CorrectionReading:
        """What the issue's comment says of its attempt now."""
        return _standing.read(self.github.read_pinned_state(self.issue), ISSUE)

    def record(self) -> dict:
        """What the issue's pinned comment carries now."""
        return self.github.pinned_data(ISSUE)

    def moves(self, **fields) -> None:
        """Another road writes `fields` over the comment as it stands, whole."""
        reading = self.github.read_pinned_state(self.issue)
        reading.state_data.update(copy.deepcopy(fields))
        self.github.write_pinned_state(self.issue, reading)

    def snapshot(self) -> tuple[str, int, str]:
        """The record, the pinned writes sent, and the caller's state, spelled to compare exactly."""
        return (
            json.dumps(self.record(), sort_keys=True),
            self.github.write_state_calls,
            json.dumps(self.state.state_data, sort_keys=True),
        )

    def restarted(self) -> CorrectionWorld:
        """The same issue as a fresh process reads it, holding nothing of this one's state."""
        return CorrectionWorld(self.github, self.issue, self.github.read_pinned_state(self.issue))


def invocation(world: CorrectionWorld, ordinal: int = SOURCE, **overrides) -> AgentInvocation:
    """An invocation of `world`'s issue under charge `ordinal`, charged on the comment its caller holds."""
    named = {
        "repo": REPO,
        "issue": ISSUE,
        "comment": world.state.comment_id,
        "cycle": 0,
        "ordinal": ordinal,
        "nonce": format(ordinal, _NONCE_SPELLING),
    }
    return AgentInvocation(**{**named, **overrides})


def source(world: CorrectionWorld, ordinal: int = SOURCE, **context) -> _records.CorrectionSource:
    """The rejected run under charge `ordinal`, handed the requirements, saved under the pins seeded, and its error."""
    saved = {"requirements": REQUIREMENTS, "command": COMMAND, "session": SESSION, "diagnostic": DIAGNOSTIC}
    return _records.CorrectionSource(invocation(world, ordinal), **{**saved, **context})


def attempt(world: CorrectionWorld, ordinal: int = SOURCE) -> _records.CorrectionAttempt:
    """The pending attempt `source(world, ordinal)` arms."""
    return _records.CorrectionAttempt(source(world, ordinal))


def interfering(world: CorrectionWorld, **fields) -> AbstractContextManager:
    """Let another road write `fields` once, right behind the next reading and before the commit reads again."""
    reader = _ReadThenMove(world, world.github.read_pinned_state, dict(fields))
    return patch.object(world.github, "read_pinned_state", side_effect=reader.read)


@dataclasses.dataclass
class _ReadThenMove:
    """A reading another road writes right behind, once: a whole-record write over the record as it stands."""

    world: CorrectionWorld
    reader: Callable[[FakeIssue], PinnedState]
    fields: dict

    def read(self, issue: FakeIssue) -> PinnedState:
        """The reading, with the move landed behind it."""
        fresh = self.reader(issue)
        if self.fields:
            landed = self.reader(issue)
            landed.state_data.update(self.fields)
            self.fields = {}
            self.world.github.write_pinned_state(issue, landed)
        return fresh
