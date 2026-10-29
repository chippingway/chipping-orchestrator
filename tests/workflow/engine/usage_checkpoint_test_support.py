# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue's pinned record, an invoked run's result, and the accounting checkpoint asked over them.

Driven through the in-memory client, whose strict edit is the real client's
policy over its own records, so a checkpoint here makes the requests production
makes and is answered as production would be: a read GitHub leaves unanswered,
an edit refused before it lands, and one that landed with its response lost.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import patch

from orchestrator.agents.models import AgentInvocation, AgentResult
from orchestrator.github.pinned_state import SCHEMA_VERSION_KEY, AdmissionStatus, PinnedState
from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    issue_usage as _issue_usage,
    usage_checkpoint as _usage_checkpoint,
    usage_receipts as _usage_receipts,
)
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue

ISSUE = 1650
REPO = "chippingway/chipping-orchestrator"

RUNS = _issue_usage.AGENT_RUNS
TOKENS = _issue_usage.TOTAL_TOKENS
COST = _issue_usage.TOTAL_COST
SOURCES = _issue_usage.COST_SOURCES
RECEIPTS = _usage_receipts.RECEIPTS
FLOOR = "floor"
RECENT = "recent"
CYCLE = "late_cycle_id"
REPORTED = "reported"

STATUS = _usage_checkpoint.AccountingStatus
REFUSAL = _usage_checkpoint.AccountingRefusal

# The tokens one run below reports, what the meter counts of them, and its cost.
INPUT_TOKENS = 100
OUTPUT_TOKENS = 50
RUN_TOKENS = INPUT_TOKENS + OUTPUT_TOKENS
RUN_COST = 0.5

# What one run lands on an issue that had counted nothing.
ONE_RUN = (1, RUN_TOKENS, RUN_COST, [REPORTED])

# A run whose usage parsed with no price, which adds nothing to the cost total.
UNPRICED = UsageMetrics(backend="claude", cost_source="no-usage")

# The fields an identity carries, as `AccountingWorld.ran` tells them from a result's.
_IDENTITY = frozenset(identity_field.name for identity_field in dataclasses.fields(AgentInvocation))

_NONCE_SPELLING = "016x"
_UNSUPPORTED_VERSION = 2


def invocation(ordinal: int, **overrides) -> AgentInvocation:
    """An invocation of this issue's repository, cycle 0, under charge `ordinal`, its nonce derived from it.

    It names no comment unless `overrides` does: a world's runs are of the
    comment it was seeded with (`AccountingWorld.ran`).
    """
    named = {
        "repo": REPO,
        "issue": ISSUE,
        "comment": None,
        "cycle": 0,
        "ordinal": ordinal,
        "nonce": format(ordinal, _NONCE_SPELLING),
    }
    return AgentInvocation(**{**named, **overrides})


def invoked(ran_as: AgentInvocation | None, **overrides) -> AgentResult:
    """What one process returned, identified as `ran_as`, its usage parsed as a claude run that reported its cost."""
    finished = {
        "session_id": None,
        "last_message": "done",
        "exit_code": 0,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
        "usage": UsageMetrics(
            backend="claude",
            input_tokens=INPUT_TOKENS,
            output_tokens=OUTPUT_TOKENS,
            cost_usd=RUN_COST,
            cost_source=REPORTED,
        ),
        "invocation": ran_as,
    }
    return AgentResult(**{**finished, **overrides})


def seeded(**record) -> AccountingWorld:
    """An issue pinned with `record`, and the state its caller read off it."""
    issue = make_issue(ISSUE)
    github = FakeGitHubClient([issue])
    github.seed_state(issue, **copy.deepcopy(record))
    return AccountingWorld(github, issue, github.read_pinned_state(issue))


def counted(record: dict) -> tuple:
    """The meter a record carries: runs, tokens, cost, and cost tags."""
    return tuple(record.get(counter) for counter in (RUNS, TOKENS, COST, SOURCES))


def unpinned(world: AccountingWorld, *, malformed: bool = False, unsupported: bool = False) -> None:
    """A hand edit leaves the comment unparseable or under version 2, or deletes it."""
    if not (malformed or unsupported):
        world.github._pinned.pop(ISSUE)
        return
    world.github._pinned[ISSUE] = PinnedState(
        comment_id=world.state.comment_id,
        state_data={} if malformed else {**world.record(), SCHEMA_VERSION_KEY: _UNSUPPORTED_VERSION},
        parsed=not malformed,
        supported=False,
        admission_status=AdmissionStatus.MALFORMED if malformed else AdmissionStatus.UNSUPPORTED,
    )


@dataclasses.dataclass
class AccountingWorld:
    """One issue, its client, and the state its caller holds and is handed the accounting back on."""

    github: FakeGitHubClient
    issue: FakeIssue
    state: PinnedState

    def account(self, agent_result: AgentResult) -> _usage_checkpoint.AccountingOutcome:
        """Ask the checkpoint to account `agent_result` over the caller's state."""
        return _usage_checkpoint.checkpoint(self.github, self.issue, self.state, agent_result)

    def ran(self, ordinal: int = 1, **overrides) -> _usage_checkpoint.AccountingOutcome:
        """Account one run under charge `ordinal`, charged on the comment the caller holds.

        `overrides` naming an identity field shape the invocation -- another
        comment among them -- and the rest the result it returned.
        """
        named = {"comment": self.state.comment_id, **overrides}
        identity = {key: named.pop(key) for key in _IDENTITY.intersection(named)}
        return self.account(invoked(invocation(ordinal, **identity), **named))

    def refused_quietly(self, ordinal: int = 1, **overrides) -> tuple:
        """Account one run: its status, refusal, and fields named, and whether issue and caller stood as they were."""
        before = self.snapshot()
        outcome = self.ran(ordinal, **overrides)
        return outcome.status, outcome.refusal, outcome.fields, self.snapshot() == before

    def restarted(self) -> AccountingWorld:
        """The same issue as a fresh process reads it, holding nothing of this one's state."""
        return AccountingWorld(self.github, self.issue, self.github.read_pinned_state(self.issue))

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

    def interfering(self, **fields) -> AbstractContextManager:
        """Let another road write `fields` once, right behind the checkpoint's read-back and before its commit reads."""
        reader = _ReadThenMove(self.github, self.github.read_pinned_state, dict(fields))
        return patch.object(self.github, "read_pinned_state", side_effect=reader.read)


@dataclasses.dataclass
class _ReadThenMove:
    """A reading another road writes right behind, once: a whole-record write over the record as it stands."""

    github: FakeGitHubClient
    reader: Callable[[FakeIssue], PinnedState]
    fields: dict = dataclasses.field(default_factory=dict)

    def read(self, issue: FakeIssue) -> PinnedState:
        """The reading, with the move landed behind it."""
        fresh = self.reader(issue)
        if self.fields:
            landed = self.reader(issue)
            landed.state_data.update(self.fields)
            self.fields = {}
            self.github.write_pinned_state(issue, landed)
        return fresh
