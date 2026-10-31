# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Usage parsing and surfaced tracked-agent metrics."""
from __future__ import annotations

import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.agents.models import AgentResult
from orchestrator.observability.analytics import settings as analytics_settings, sink as analytics_sink
from orchestrator.observability.usage import (
    cost_evidence as _cost,
    metrics as _usage_metrics,
    price_catalogue as _price_catalogue,
    token_evidence as _tokens,
)
from orchestrator.workflow.engine import usage as engine_usage
from tests.support import agy_stream as _agy
from tests.support.fakes import FakeGitHubClient
from tests.workflow.engine import usage_frames as _usage_frames, usage_test_support as support

BACKEND_CLAUDE = support.BACKEND_CLAUDE
BACKEND_CODEX = support.BACKEND_CODEX
EVENT_AGENT_EXIT = support.EVENT_AGENT_EXIT
EVENT_SKILL_TRIGGERED = support.EVENT_SKILL_TRIGGERED
STAGE_IMPLEMENTING = support.STAGE_IMPLEMENTING
ROLE_DEVELOPER = support.ROLE_DEVELOPER
_ANALYTICS_FILENAME = support._ANALYTICS_FILENAME
_ANALYTICS_PATH_ATTR = support._ANALYTICS_PATH_ATTR
_CLAUDE_CACHE_WRITE_TOKENS = _usage_frames._CLAUDE_CACHE_WRITE_TOKENS
_CLAUDE_INPUT_TOKENS = _usage_frames._CLAUDE_INPUT_TOKENS
_CLAUDE_MODEL = _usage_frames._CLAUDE_MODEL
_CLAUDE_OUTPUT_TOKENS = _usage_frames._CLAUDE_OUTPUT_TOKENS
_CODEX_MODEL = support._CODEX_MODEL
_DEVELOP_SKILL = support._DEVELOP_SKILL
_EVENT_KEY = support._EVENT_KEY
_FAKE_WT = support._FAKE_WT
_IGNORED_PROMPT = support._IGNORED_PROMPT
_INPUT_TOKENS_KEY = _usage_frames._INPUT_TOKENS_KEY
_OUTPUT_TOKENS_KEY = _usage_frames._OUTPUT_TOKENS_KEY
_REPORTED_COST_USD = support._REPORTED_COST_USD
_REVIEW_SKILL = support._REVIEW_SKILL
_RUN_AGENT_ATTR = support._RUN_AGENT_ATTR
_agent_runner = support.agent_runner
_SKILL_KEY = _usage_frames._SKILL_KEY
_SKILL_OUTPUT_TOKENS = _usage_frames._SKILL_OUTPUT_TOKENS
_TRACK_SKILLS_ATTR = support._TRACK_SKILLS_ATTR
_TRAJECTORY_PATH_ATTR = support._TRAJECTORY_PATH_ATTR
_USAGE_HELPER_ISSUE_NUMBER = support._USAGE_HELPER_ISSUE_NUMBER
_USAGE_KEY = _usage_frames._USAGE_KEY
_analytics_path = support._analytics_path
_tracked_budget = support._tracked_budget
_analytics_records = support._analytics_records
_claude_stdout = _usage_frames._claude_stdout
_claude_stdout_with_skills = _usage_frames._claude_stdout_with_skills
_codex_stdout_no_model = _usage_frames._codex_stdout_no_model
_CLAUDE_CACHE_READ_TOKENS = 100
_RECORDED_USAGE_FIELDS = (_cost.COST_USD, "cost_source", _cost.COST_EVIDENCE, _tokens.TOKEN_EVIDENCE)
# An exit well inside Gemini 3.8 Flash's first rates, and the resumed fixture's
# step priced at them: its input, cached input, and output at the page's rates.
_AGY_EXITED_AT = datetime.fromisoformat("2026-10-31T12:00:00+00:00")
_FLASH_CHARGES = (
    (_agy.INPUT_TOKENS, 0.75),
    (_agy.CACHE_READ_TOKENS, 0.075),
    (_agy.OUTPUT_TOKENS, 3.75),
)
_TOKENS_PER_MILLION = 1_000_000
_AGY_STEP_USD = sum(tokens * rate for tokens, rate in _FLASH_CHARGES) / _TOKENS_PER_MILLION
_AGY_ESTIMATE = _cost.CostContribution(_cost.GEMINI_API_ESTIMATE, _AGY_STEP_USD, (date.fromisoformat("2026-10-29"),))


def _run_usage(
    *,
    stdout: str,
    backend: str = BACKEND_CLAUDE,
    track: bool = False,
    analytics_path: Path | None = None,
    extra_args: tuple[str, ...] = (),
) -> tuple[FakeGitHubClient, AgentResult]:
    gh = FakeGitHubClient()
    with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, analytics_path), \
            patch.object(analytics_settings, _TRAJECTORY_PATH_ATTR, None), \
            patch.object(analytics_settings, _TRACK_SKILLS_ATTR, track), \
            patch.object(_agent_runner, _RUN_AGENT_ATTR) as run_mock:
        run_mock.return_value = AgentResult(
            session_id="sess-usage",
            last_message="",
            exit_code=0,
            timed_out=False,
            stdout=stdout,
            stderr="",
        )
        tracked_result = engine_usage._run_agent_tracked(
            gh, _tracked_budget(gh, _USAGE_HELPER_ISSUE_NUMBER),
            agent_role=ROLE_DEVELOPER,
            stage=STAGE_IMPLEMENTING,
            backend=backend,
            prompt=_IGNORED_PROMPT,
            cwd=_FAKE_WT,
            agent_spec=backend,
            extra_args=extra_args,
            review_round=2,
            retry_count=1,
        )
    return gh, tracked_result


def _assert_usage_metrics(
    case: unittest.TestCase,
    metrics: _usage_metrics.UsageMetrics,
) -> None:
    case.assertEqual(metrics.backend, BACKEND_CLAUDE)
    case.assertEqual(metrics.input_tokens, _CLAUDE_INPUT_TOKENS)
    case.assertEqual(metrics.output_tokens, _CLAUDE_OUTPUT_TOKENS)
    case.assertEqual(metrics.cache_read_tokens, _CLAUDE_CACHE_READ_TOKENS)
    case.assertEqual(
        metrics.cache_write_tokens,
        _CLAUDE_CACHE_WRITE_TOKENS,
    )
    case.assertEqual(list(metrics.models), [_CLAUDE_MODEL])
    case.assertEqual(metrics.turns, 2)
    case.assertEqual(metrics.cost_source, "reported")
    case.assertAlmostEqual(metrics.cost_usd, _REPORTED_COST_USD)


class RunUsageSurfacedTest(unittest.TestCase):
    """Per-issue usage plumbing: `_run_agent_tracked` returns an `AgentResult`
    whose `usage` field carries the same `UsageMetrics` `record_agent_exit`
    parsed for the analytics record -- surfaced even when the sink is off,
    left `None` when the usage parse fails (fail-open), and never disturbing
    the analytics record or the `skill_triggered` audit events."""

    def test_agent_result_optional_fields_default(self) -> None:
        # Both optional fields are defaulted so every construction a backend
        # makes stays valid: an untracked result carries no usage, and a
        # result nobody said otherwise about came from a process that ran.
        agent_result = AgentResult(
            session_id="s", last_message="", exit_code=0,
            timed_out=False, stdout="", stderr="",
        )
        self.assertIsNone(agent_result.usage)
        self.assertTrue(agent_result.invoked)

    def test_result_carries_usage_without_sink(self) -> None:
        # Sink OFF: the parsed metrics still reach the caller off `.usage`,
        # proving the plumbing is independent of the observability sink.
        gh, agent_result = _run_usage(
            stdout=_claude_stdout(total_cost_usd=_REPORTED_COST_USD),
            analytics_path=None,
        )
        self.assertIsInstance(agent_result.usage, _usage_metrics.UsageMetrics)
        _assert_usage_metrics(self, agent_result.usage)
        # The lifecycle audit still fired even with the sink disabled.
        self.assertIn(
            EVENT_AGENT_EXIT, {event[_EVENT_KEY] for event in gh.recorded_events},
        )

    def test_usage_reflects_spec_fallback_model(self) -> None:
        # The surfaced metrics are the SAME object the record used, so the
        # codex spec-fallback model path (extra_args -> `_configured_model`
        # -> `fallback_model`) is visible on `.usage` too.
        _, agent_result = _run_usage(
            stdout=_codex_stdout_no_model(),
            backend=BACKEND_CODEX,
            extra_args=("-m", _CODEX_MODEL),
        )
        self.assertIsNotNone(agent_result.usage)
        self.assertEqual(list(agent_result.usage.models), [_CODEX_MODEL])
        self.assertEqual(agent_result.usage.cost_source, "estimated")

    def test_parse_failure_leaves_none_and_fails_open(self) -> None:
        path = _analytics_path(self, "usage-failopen-")
        with patch.object(
            _usage_metrics,
            "parse_agent_usage",
            side_effect=RuntimeError("boom"),
        ), self.assertLogs(analytics_sink.log, level="ERROR"):
            github, agent_result = _run_usage(
                stdout=_claude_stdout(),
                analytics_path=path,
            )
        self.assertEqual(agent_result.session_id, "sess-usage")
        self.assertIsNone(agent_result.usage)
        self.assertEqual(_analytics_records(path, event=EVENT_AGENT_EXIT), [])
        self.assertIn(
            EVENT_AGENT_EXIT,
            {
                event[_EVENT_KEY]
                for event in github.recorded_events
            },
        )

    def test_analytics_and_skill_events_unchanged(self) -> None:
        path = _analytics_path(self, "usage-unchanged-")
        github, agent_result = _run_usage(
            stdout=_claude_stdout_with_skills(
                skills=(_DEVELOP_SKILL, _REVIEW_SKILL),
            ),
            track=True,
            analytics_path=path,
        )
        exit_record = _analytics_records(path, event=EVENT_AGENT_EXIT)[0]
        self.assertEqual(exit_record[_EVENT_KEY], EVENT_AGENT_EXIT)
        self.assertEqual(exit_record[_INPUT_TOKENS_KEY], 1000)
        self.assertEqual(
            exit_record[_OUTPUT_TOKENS_KEY],
            _SKILL_OUTPUT_TOKENS,
        )
        self.assertNotIn(_USAGE_KEY, exit_record)
        self.assertEqual(agent_result.usage.input_tokens, 1000)
        self.assertEqual(
            agent_result.usage.output_tokens,
            _SKILL_OUTPUT_TOKENS,
        )
        skill_events = [
            event
            for event in github.recorded_events
            if event[_EVENT_KEY] == EVENT_SKILL_TRIGGERED
        ]
        self.assertEqual(
            [event[_SKILL_KEY] for event in skill_events],
            [_DEVELOP_SKILL, _REVIEW_SKILL],
        )


class AgentExitUsageEvidenceTest(unittest.TestCase):
    """The `agent_exit` record states what the run's cost and counters mean, read back through the shared owners."""

    def test_record_carries_the_run_evidence(self) -> None:
        # A reported zero is spend of zero on the CLI's own basis, and the
        # cache counters a Claude run reports sit beside its input.
        path = _analytics_path(self, "usage-evidence-")
        _, agent_result = _run_usage(stdout=_claude_stdout(total_cost_usd=0), analytics_path=path)
        record = _analytics_records(path, event=EVENT_AGENT_EXIT)[0]
        usage_fields = agent_result.usage.to_dict()
        self.assertEqual(
            {key: record[key] for key in _RECORDED_USAGE_FIELDS},
            {key: usage_fields[key] for key in _RECORDED_USAGE_FIELDS},
        )
        self.assertEqual(
            _cost.recorded_cost(record),
            _cost.CostEvidence(_cost.COMPLETE, (_cost.CostContribution(_cost.CLI_REPORTED, 0),)),
        )
        self.assertEqual(
            _tokens.non_overlapping_total(record),
            _CLAUDE_INPUT_TOKENS + _CLAUDE_OUTPUT_TOKENS + _CLAUDE_CACHE_READ_TOKENS + _CLAUDE_CACHE_WRITE_TOKENS,
        )

    def test_antigravity_record_priced_at_its_exit(self) -> None:
        # The record is priced over the span the run's duration ends at its
        # exit, so a run on a dated Gemini row is priced at the rates in
        # effect then, and its cache reads count beside its input.
        path = _analytics_path(self, "usage-agy-")
        clock = MagicMock(wraps=datetime)
        clock.now.return_value = _AGY_EXITED_AT
        with patch.object(_price_catalogue, "datetime", clock):
            _run_usage(stdout=_agy.resumed_stream(), backend=_agy.BACKEND, analytics_path=path)
        record = _analytics_records(path, event=EVENT_AGENT_EXIT)[0]
        expected = _cost.CostEvidence(_cost.COMPLETE, (_AGY_ESTIMATE,))
        self.assertEqual(_cost.recorded_cost(record), expected)
        self.assertEqual(
            _tokens.non_overlapping_total(record),
            _agy.INPUT_TOKENS + _agy.OUTPUT_TOKENS + _agy.CACHE_READ_TOKENS,
        )

    def test_unstated_metrics_record_unknown_basis(self) -> None:
        path = _analytics_path(self, "usage-no-evidence-")
        unstated = _usage_metrics.UsageMetrics(
            backend=BACKEND_CLAUDE,
            cache_read_tokens=_CLAUDE_CACHE_READ_TOKENS,
            cost_usd=_REPORTED_COST_USD,
            cost_source=_cost.REPORTED_SOURCE,
        )
        with patch.object(_usage_metrics, "parse_agent_usage", return_value=unstated):
            _run_usage(stdout="", analytics_path=path)
        record = _analytics_records(path, event=EVENT_AGENT_EXIT)[0]
        self.assertNotIn(_cost.COST_EVIDENCE, record)
        self.assertNotIn(_tokens.TOKEN_EVIDENCE, record)
        self.assertEqual(
            _cost.recorded_cost(record),
            _cost.CostEvidence(_cost.UNKNOWN, (_cost.CostContribution(_cost.UNKNOWN_BASIS, _REPORTED_COST_USD),)),
        )
        self.assertIsNone(_tokens.non_overlapping_total(record))
