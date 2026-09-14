# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One tracked run driven into the trajectory sink, and what it is read by.

Every writer test enters the same way -- a finished `record_agent_exit` with
the two sinks pointed at a temporary directory -- so the case that describes
one run and the emit that drives it live here rather than in each module. The
record keys and identity values below are shared for the same reason: what the
serializer wrote is asserted by name in several of them.
"""

from __future__ import annotations

import contextlib
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from orchestrator.agents.models import AgentResult
from orchestrator.observability.analytics import settings as analytics_settings
from orchestrator.observability.analytics.recording import agent_exit as _agent_exit_records
from tests.observability.analytics.analytics_reload_helpers import reload_analytics as _reload

ANALYTICS_LOG_PATH = "ANALYTICS_LOG_PATH"

TRACK_SKILL_TRIGGERS = "TRACK_SKILL_TRIGGERS"

TRAJECTORY_LOG_PATH = "TRAJECTORY_LOG_PATH"

TRAJECTORY_RETENTION_DAYS = "TRAJECTORY_RETENTION_DAYS"

ANALYTICS_FILENAME = "analytics.jsonl"

ANALYTICS_FILENAME_ALTERNATE = "a.jsonl"

TRAJECTORY_FILENAME = "trajectory.jsonl"

AGENT_EXIT = "agent_exit"

AGENT_TRAJECTORY = "agent_trajectory"

BASH_TOOL_NAME = "Bash"

CLAUDE = "claude"

CLAUDE_MODEL = "claude-sonnet-4-6"

CODEX = "codex"

DEVELOPER = "developer"

PROMPT_TEXT = "p"

REDACTION_MARKER = "***"

REPO = "owner/repo"

SESSION_ID = "sess-traj"

STAGE_IMPLEMENTING = "implementing"

BACKEND_KEY = "backend"

CONTENT_KEY = "content"

DISPOSITION_KEY = "disposition"

EVENT_KEY = "event"

IDENTIFIED_ITEMS_KEY = "identified"

INPUT_TOKENS_KEY = "input_tokens"

ITEM_ID_KEY = "item_id"

ITEM_TYPE_KEY = "item_type"

KIND_KEY = "kind"

NAME_KEY = "name"

OUTPUT_KEY = "output"

OUTPUT_TOKENS_KEY = "output_tokens"

RUN_USAGE_KEY = "run_usage"

SOURCE_ITEMS_KEY = "source_items"

SOURCE_ITEM_COUNTS_KEY = "source_item_counts"

SOURCE_ITEMS_TRUNCATED_KEY = "source_items_truncated"

STEPS_KEY = "steps"

STORED_DISPOSITION = "stored"

UNSUPPORTED_DISPOSITION = "unsupported"

EXCLUDED_DISPOSITION = "excluded"

EMPTY_DISPOSITION = "empty"

TOOL_CALL_KIND = "tool_call"

TOOL_ID_KEY = "tool_id"

TOOL_RESULT_KIND = "tool_result"

TRUNCATED_KEY = "truncated"

TURN_KEY = "turn"

TURNS_KEY = "turns"

USER_INPUT_KEY = "user_input"

AGENT_EXIT_ISSUE_NUMBER = 7

TRAJECTORY_REVIEW_ROUND = 2

TRAJECTORY_RETRY_COUNT = 1


@dataclass(frozen=True)
class TrajectoryExitCase:
    """One finished agent run as the two sinks are pointed at it."""

    stdout: str
    prompt: str | None = None
    traj_path: Path | None = None
    analytics_path: Path | None = None
    backend: str = CLAUDE
    track: bool = False


@contextlib.contextmanager
def trajectory_sink(retention: str | None = None):
    """Point the trajectory knobs at a temporary `trajectory.jsonl` sink."""
    with tempfile.TemporaryDirectory() as sink_dir:
        path = Path(sink_dir) / TRAJECTORY_FILENAME
        environment = {TRAJECTORY_LOG_PATH: str(path)}
        if retention is not None:
            environment[TRAJECTORY_RETENTION_DAYS] = retention
        _reload(environment)
        yield path


class RecordAgentExitTrajectorySupport(unittest.TestCase):
    """`record_agent_exit` writes the opt-in trajectory record only when
    `TRAJECTORY_LOG_PATH` is enabled, redacts every free-text field, applies
    head/tail + total-size truncation caps, and never lets a trajectory
    failure drop the baseline `agent_exit` usage record."""

    def _emit(self, **options):
        case = TrajectoryExitCase(**options)
        with (
            patch.object(analytics_settings, ANALYTICS_LOG_PATH, case.analytics_path),
            patch.object(analytics_settings, TRAJECTORY_LOG_PATH, case.traj_path),
            patch.object(analytics_settings, TRACK_SKILL_TRIGGERS, case.track),
        ):
            return _agent_exit_records.record_agent_exit(
                repo=REPO,
                issue=AGENT_EXIT_ISSUE_NUMBER,
                stage=STAGE_IMPLEMENTING,
                agent_role=DEVELOPER,
                backend=case.backend,
                agent_spec=case.backend,
                resume_session_id=None,
                result=AgentResult(
                    session_id=SESSION_ID,
                    last_message="",
                    exit_code=0,
                    timed_out=False,
                    stdout=case.stdout,
                    stderr="",
                ),
                duration_s=float(0),
                review_round=TRAJECTORY_REVIEW_ROUND,
                retry_count=TRAJECTORY_RETRY_COUNT,
                prompt=case.prompt,
            )
