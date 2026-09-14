# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Wire payloads, constants, and fixtures for agent analytics tests."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from orchestrator.agents import runner as _agent_runner
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage import trajectory as _trajectory
from orchestrator.workflow.engine import run_circuit as _run_circuit
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow import (
    patch_runner as _runner,
    repo_values as _repo,
    stage_labels as _labels,
    stage_names as _stages,
    state_values as _roles,
    value_helpers as _value_helpers,
    verdict_values as _verdicts,
)
from tests.workflow.engine import event_values as _events

# The owner a tracked run's trajectory is parsed on, so a fail-open test
# patches the module the analytics writer calls.
usage_trajectory = _trajectory

# The owner the tracked spawn dispatches on, for the same reason: a mock left
# anywhere else would let the real CLI run.
agent_runner = _agent_runner

EVENT_AGENT_EXIT = _events.EVENT_AGENT_EXIT
EVENT_AGENT_SPAWN = _events.EVENT_AGENT_SPAWN
EVENT_AGENT_TRAJECTORY = _events.EVENT_AGENT_TRAJECTORY
EVENT_SKILL_TRIGGERED = _events.EVENT_SKILL_TRIGGERED
BACKEND_CLAUDE = _repo.BACKEND_CLAUDE
BACKEND_CODEX = _repo.BACKEND_CODEX
TEST_BASE_BRANCH = _repo.TEST_BASE_BRANCH
TEST_REPO_SLUG = _repo.TEST_REPO_SLUG
_FAKE_WT = _repo._FAKE_WT
_TEST_SPEC = _repo._TEST_SPEC
LABEL_IMPLEMENTING = _labels.LABEL_IMPLEMENTING
LABEL_VALIDATING = _labels.LABEL_VALIDATING
ROLE_DEVELOPER = _roles.ROLE_DEVELOPER
ROLE_REVIEWER = _roles.ROLE_REVIEWER
STAGE_IMPLEMENTING = _stages.STAGE_IMPLEMENTING
STAGE_VALIDATING = _stages.STAGE_VALIDATING
_analytics_records = _value_helpers._analytics_records
REVIEW_APPROVED_MESSAGE = _verdicts.REVIEW_APPROVED_MESSAGE
_PatchedWorkflowMixin = _runner._PatchedWorkflowMixin
_EVENT_KEY = "event"
_STAGE_KEY = "stage"
_AGENT_ROLE_KEY = "agent_role"
_COST_USD_KEY = "cost_usd"
_ANALYTICS_FILENAME = "analytics.jsonl"
_ANALYTICS_PATH_ATTR = "ANALYTICS_LOG_PATH"
_TRAJECTORY_PATH_ATTR = "TRAJECTORY_LOG_PATH"
_TRACK_SKILLS_ATTR = "TRACK_SKILL_TRIGGERS"
_RUN_AGENT_ATTR = "run_agent"
_CODEX_MODEL = "gpt-5-codex"
_IGNORED_PROMPT = "ignored"
_DEVELOP_SKILL = "develop"
_REVIEW_SKILL = "review"
_TRAJECTORY_PROMPT = "implement the widget"
_REPORTED_COST_USD = 0.0123
_CODEX_INPUT_TOKENS = 2000
_CODEX_CACHED_TOKENS = 500
_CODEX_OUTPUT_TOKENS = 800
_IMPLEMENTING_ANALYTICS_ISSUE_NUMBER = 101
_REDACTION_ISSUE_NUMBER = 102
_REVIEW_ISSUE_NUMBER = 103
_REVIEW_PR_NUMBER = 44
_TIMEOUT_ISSUE_NUMBER = 104
_AUDIT_ISSUE_NUMBER = 105
_DISABLED_SINK_ISSUE_NUMBER = 106
_CODEX_FALLBACK_ISSUE_NUMBER = 107
_CLAUDE_FALLBACK_ISSUE_NUMBER = 108
_USAGE_HELPER_ISSUE_NUMBER = 401
_TRAJECTORY_ISSUE_NUMBER = 301
_PROMPT_FORWARDING_ISSUE_NUMBER = 302
_TRAJECTORY_FAILURE_ISSUE_NUMBER = 303
_TRAJECTORY_SINK_ISSUE_NUMBER = 562
_SKILL_AGENT_ISSUE_NUMBER = 201
_SKILL_REUSE_ISSUE_NUMBER = 202


def _tracked_budget(
    gh: FakeGitHubClient, issue_number: int,
) -> _run_circuit.AgentRunBudget:
    """The budget a directly driven tracked run is charged against.

    The issue is registered on the client because the charge the boundary
    takes is written to it -- these cases are about what the run behind that
    charge records, so the issue has to be one the client can answer for.
    """
    issue = make_issue(issue_number, label=LABEL_IMPLEMENTING)
    gh.add_issue(issue)
    return _run_circuit.AgentRunBudget(issue=issue, state=PinnedState())


def _skill_events(gh: FakeGitHubClient) -> list[dict]:
    return [
        event for event in gh.recorded_events
        if event[_EVENT_KEY] == EVENT_SKILL_TRIGGERED
    ]


class _RaisingOnSkillGitHubClient(FakeGitHubClient):
    def emit_event(self, event, **kwargs):
        if event == EVENT_SKILL_TRIGGERED:
            raise RuntimeError("emit boom")
        return super().emit_event(event, **kwargs)


def _analytics_path(
    case,
    prefix: str,
    filename: str = _ANALYTICS_FILENAME,
) -> Path:
    temp_dir = tempfile.TemporaryDirectory(prefix=prefix)
    case.addCleanup(temp_dir.cleanup)
    return Path(temp_dir.name) / filename


def _assert_redacted_record(
    case,
    record: dict,
    raw_stdout: str,
    secret_marker: str,
) -> None:
    serialized_record = json.dumps(record)
    case.assertNotIn(secret_marker, serialized_record)
    case.assertNotIn("please use token", serialized_record)
    case.assertNotIn("missing scope", serialized_record)
    case.assertNotIn(raw_stdout, serialized_record)
    for forbidden in (
        "prompt",
        "stdout",
        "stderr",
        "last_message",
        "cwd",
    ):
        case.assertNotIn(forbidden, record)
