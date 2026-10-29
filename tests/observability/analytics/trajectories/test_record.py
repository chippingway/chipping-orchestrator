# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Analytics trajectory core recording tests."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.observability.analytics.trajectories import models as trajectory_models
from orchestrator.observability.usage import cost_evidence as _cost, token_evidence as _tokens
from tests.observability.analytics.analytics_jsonl_helpers import (
    read_records as _read_records,
)
from tests.observability.analytics.analytics_trajectory_cases import (
    CLAUDE_TRAJECTORY_INPUT_TOKENS,
    CLAUDE_TRAJECTORY_OUTPUT_TOKENS,
    CODEX_TRAJECTORY_INPUT_TOKENS,
    CODEX_TRAJECTORY_OUTPUT_TOKENS,
    claude_multistep_stdout as _claude_multistep_stdout,
    claude_trajectory_stdout as _claude_trajectory_stdout,
    codex_trajectory_stdout as _codex_trajectory_stdout,
)
from tests.observability.analytics.trajectories import (
    trajectories_test_support as _support,
)

_AGENT_EXIT = _support.AGENT_EXIT


_AGENT_TRAJECTORY = _support.AGENT_TRAJECTORY


_ANALYTICS_FILENAME = _support.ANALYTICS_FILENAME


_ANALYTICS_FILENAME_ALTERNATE = _support.ANALYTICS_FILENAME_ALTERNATE


_BACKEND_KEY = _support.BACKEND_KEY


_BASH_TOOL_NAME = _support.BASH_TOOL_NAME


_CLAUDE = _support.CLAUDE


_CLAUDE_MODEL = _support.CLAUDE_MODEL


_CODEX = _support.CODEX


_CONTENT_KEY = _support.CONTENT_KEY


_EVENT_KEY = _support.EVENT_KEY


_INPUT_TOKENS_KEY = _support.INPUT_TOKENS_KEY


_KIND_KEY = _support.KIND_KEY


_NAME_KEY = _support.NAME_KEY


_OUTPUT_KEY = _support.OUTPUT_KEY


_OUTPUT_TOKENS_KEY = _support.OUTPUT_TOKENS_KEY


_PROMPT_TEXT = _support.PROMPT_TEXT


_REDACTION_MARKER = _support.REDACTION_MARKER


_RUN_USAGE_KEY = _support.RUN_USAGE_KEY


_STEPS_KEY = _support.STEPS_KEY


_TOOL_CALL_KIND = _support.TOOL_CALL_KIND


_TOOL_ID_KEY = _support.TOOL_ID_KEY


_TOOL_RESULT_KIND = _support.TOOL_RESULT_KIND


_TRAJECTORY_FILENAME = _support.TRAJECTORY_FILENAME


_TRUNCATED_KEY = _support.TRUNCATED_KEY


_TURN_KEY = _support.TURN_KEY


_TURNS_KEY = _support.TURNS_KEY


_USER_INPUT_KEY = _support.USER_INPUT_KEY


_TYPE_KEY = "type"


_COMMAND_KEY = "command"


_TEXT_KEY = "text"


_ASSISTANT_MESSAGE_KIND = "assistant_message"


_USER_MESSAGE_KIND = "user_message"


_COST_SOURCE_KEY = "cost_source"


_ESTIMATED_COST = "estimated"


_TRUNCATION_EDGE_CHARS = 5


_LONG_TEXT_CHARS = 100


_EVIDENCE_TURN_COUNT = 3


_COST_PLACES = 12


def _discover_codex_tools() -> list[str]:
    from orchestrator.skills import discovery

    return list(discovery.discover_codex_tools())


def _codex_usage_projection(record: dict) -> tuple:
    usage = record[_RUN_USAGE_KEY]
    return (
        _BACKEND_KEY in usage,
        usage[_INPUT_TOKENS_KEY],
        usage[_OUTPUT_TOKENS_KEY],
        usage[_COST_SOURCE_KEY],
        usage["cost_usd"],
    )


def _text_turn_stdout(secret: str) -> str:
    frames = [
        {_TYPE_KEY: "system", "subtype": "init", "tools": [_BASH_TOOL_NAME]},
        {
            _TYPE_KEY: "assistant",
            "message": {
                "id": "m1",
                _CONTENT_KEY: [
                    {_TYPE_KEY: _TEXT_KEY, _TEXT_KEY: "B" * _LONG_TEXT_CHARS},
                    {
                        _TYPE_KEY: "tool_use",
                        _NAME_KEY: _BASH_TOOL_NAME,
                        "id": "tu1",
                        "input": {_COMMAND_KEY: "ls"},
                    },
                ],
            },
        },
        {
            _TYPE_KEY: "user",
            "message": {
                _CONTENT_KEY: [
                    {_TYPE_KEY: _TOOL_RESULT_KIND, "tool_use_id": "tu1", _CONTENT_KEY: "ok"},
                    {_TYPE_KEY: _TEXT_KEY, _TEXT_KEY: f"leak {secret}"},
                ]
            },
        },
        {_TYPE_KEY: "result", "result": "done"},
    ]
    return "\n".join(json.dumps(frame) for frame in frames)


class RecordAgentExitClaudeTrajectoryTest(_support.RecordAgentExitTrajectorySupport):
    """What one claude run writes with the sink off and with it on."""

    def test_sink_off_writes_no_trajectory_or_input(self) -> None:
        # Default off: a prompt is passed but, with the trajectory sink
        # disabled, no trajectory file is created and the baseline
        # `agent_exit` record never carries `user_input`.
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            a_path = temp_root / _ANALYTICS_FILENAME
            self._emit(
                stdout=_claude_trajectory_stdout(),
                prompt="please implement the feature",
                traj_path=None,
                analytics_path=a_path,
            )
            # Only the analytics file exists -- no trajectory file anywhere.
            self.assertEqual(
                sorted(entry.name for entry in temp_root.iterdir()),
                [_ANALYTICS_FILENAME],
            )
            recs = _read_records(a_path)
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0][_EVENT_KEY], _AGENT_EXIT)
            self.assertNotIn(_USER_INPUT_KEY, recs[0])

    def test_sink_on_writes_redacted_trajectory(self) -> None:
        # Sink on: a single `agent_trajectory` record carries the redacted
        # user_input, the offered tools, the ordered steps with their
        # tool_call input / tool_result content, and the final output --
        # alongside (not replacing) the baseline `agent_exit` record.
        with tempfile.TemporaryDirectory() as td:
            a_path = Path(td) / _ANALYTICS_FILENAME
            t_path = Path(td) / _TRAJECTORY_FILENAME
            self._emit(
                stdout=_claude_trajectory_stdout(
                    tool_input={_COMMAND_KEY: "echo hi"},
                    tool_result="hi",
                    final_output="implemented",
                ),
                prompt="implement X",
                traj_path=t_path,
                analytics_path=a_path,
            )
            self._assert_baseline_exit_record(a_path)
            record = self._read_single_trajectory(t_path)
            self._assert_trajectory_identity(record)
            self._assert_trajectory_steps(record)
            self._assert_trajectory_usage(record)
            self.assertNotIn(_TRUNCATED_KEY, record)

    def _assert_baseline_exit_record(self, path: Path) -> None:
        records = _read_records(path)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record[_EVENT_KEY], _AGENT_EXIT)
        self.assertEqual(
            record[_INPUT_TOKENS_KEY],
            CLAUDE_TRAJECTORY_INPUT_TOKENS,
        )
        self.assertNotIn(_USER_INPUT_KEY, record)
        self.assertNotIn(_RUN_USAGE_KEY, record)

    def _read_single_trajectory(self, path: Path) -> dict:
        records = _read_records(path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][_EVENT_KEY], _AGENT_TRAJECTORY)
        return records[0]

    def _assert_trajectory_identity(self, record: dict) -> None:
        expected = {
            _EVENT_KEY: _AGENT_TRAJECTORY,
            "repo": _support.REPO,
            "issue": _support.AGENT_EXIT_ISSUE_NUMBER,
            "stage": _support.STAGE_IMPLEMENTING,
            "agent_role": _support.DEVELOPER,
            _BACKEND_KEY: _CLAUDE,
            "session_id": _support.SESSION_ID,
            "review_round": _support.TRAJECTORY_REVIEW_ROUND,
            "retry_count": _support.TRAJECTORY_RETRY_COUNT,
            _USER_INPUT_KEY: "implement X",
            "tools": ["Read", _BASH_TOOL_NAME],
            _OUTPUT_KEY: "implemented",
        }
        self.assertEqual(
            {key: record[key] for key in expected},
            expected,
        )

    def _assert_trajectory_steps(self, record: dict) -> None:
        steps = record[_STEPS_KEY]
        tool_call = steps[0]
        self.assertEqual(
            {
                "kinds": [step[_KIND_KEY] for step in steps],
                "tool_name": tool_call[_NAME_KEY],
                _TOOL_RESULT_KIND: steps[1][_CONTENT_KEY],
                "tool_turn": tool_call[_TURN_KEY],
            },
            {
                "kinds": [_TOOL_CALL_KIND, _TOOL_RESULT_KIND],
                "tool_name": _BASH_TOOL_NAME,
                _TOOL_RESULT_KIND: "hi",
                "tool_turn": 0,
            },
        )
        self.assertIn("echo hi", tool_call[_CONTENT_KEY])
        # Tool results become the next turn's input; only the billed call
        # carries the current turn index.
        self.assertNotIn(_TURN_KEY, steps[1])

    def _assert_trajectory_usage(self, record: dict) -> None:
        run_usage = record[_RUN_USAGE_KEY]
        expected_run = {
            _INPUT_TOKENS_KEY: CLAUDE_TRAJECTORY_INPUT_TOKENS,
            _OUTPUT_TOKENS_KEY: CLAUDE_TRAJECTORY_OUTPUT_TOKENS,
            "models": [_CLAUDE_MODEL],
            _TURNS_KEY: 1,
            _COST_SOURCE_KEY: _ESTIMATED_COST,
        }
        self.assertNotIn(_BACKEND_KEY, run_usage)
        self.assertEqual(
            {key: run_usage[key] for key in expected_run},
            expected_run,
        )

        turns = record[_TURNS_KEY]
        expected_turn = {
            _TURN_KEY: 0,
            "model": _CLAUDE_MODEL,
            _INPUT_TOKENS_KEY: CLAUDE_TRAJECTORY_INPUT_TOKENS,
            _OUTPUT_TOKENS_KEY: CLAUDE_TRAJECTORY_OUTPUT_TOKENS,
            _COST_SOURCE_KEY: _ESTIMATED_COST,
        }
        self.assertEqual(len(turns), 1)
        self.assertEqual(
            {key: turns[0][key] for key in expected_turn},
            expected_turn,
        )


class RecordAgentExitTrajectoryTimelineTest(_support.RecordAgentExitTrajectorySupport):
    """The step timeline each backend's stream is reconstructed into."""

    def test_codex_trajectory_record(self) -> None:
        # The codex backend dispatches through the same path: command +
        # aggregated_output become the tool_call / tool_result, the trailing
        # agent_message rides along as an assistant_message turn, and that
        # same last agent_message is the output.
        with tempfile.TemporaryDirectory() as td:
            t_path = Path(td) / _TRAJECTORY_FILENAME
            self._emit(
                stdout=_codex_trajectory_stdout(),
                prompt="codex prompt",
                traj_path=t_path,
                analytics_path=t_path.parent / _ANALYTICS_FILENAME_ALTERNATE,
                backend=_CODEX,
            )
            rec = _read_records(t_path)[0]
            steps = rec[_STEPS_KEY]
            self.assertEqual(
                (
                    rec[_EVENT_KEY],
                    rec[_BACKEND_KEY],
                    rec[_USER_INPUT_KEY],
                    rec[_OUTPUT_KEY],
                ),
                (_AGENT_TRAJECTORY, _CODEX, "codex prompt", "codex done"),
            )
            self.assertEqual(
                [
                    (step[_KIND_KEY], step[_CONTENT_KEY])
                    for step in steps
                ],
                [
                    (_TOOL_CALL_KIND, "ls -la"),
                    (_TOOL_RESULT_KIND, "command output"),
                    (_ASSISTANT_MESSAGE_KIND, "codex done"),
                ],
            )
            # The text turn carries no tool name / id.
            self.assertEqual(
                (steps[2][_NAME_KEY], steps[2][_TOOL_ID_KEY]),
                (None, None),
            )
            # codex exposes no offered-tools frame, so the trajectory record
            # backfills the best-effort baseline out-of-band.
            self.assertEqual(rec["tools"], _discover_codex_tools())
            # run_usage is codex's only usage surface: the denormalized
            # run-level totals, present even though per-turn detail is not.
            self.assertEqual(
                _codex_usage_projection(rec),
                (
                    False,
                    CODEX_TRAJECTORY_INPUT_TOKENS,
                    CODEX_TRAJECTORY_OUTPUT_TOKENS,
                    "unknown-price",
                    None,
                ),
            )
            # No priced model in the stream -> unknown-price, no cost.
            # codex usage frames are cumulative, not per-turn: the per-turn
            # array is dropped and no step carries a `turn` index.
            self.assertNotIn(_TURNS_KEY, rec)
            self.assertTrue(all(_TURN_KEY not in step for step in steps))

    def test_text_turns_redacted_capped_and_recorded(self) -> None:
        # New timeline items -- assistant / user text turns -- are stored as
        # their own steps and get the same treatment as tool payloads: stream
        # order preserved, secrets masked, over-long text head/tail truncated,
        # and `name` / `tool_id` null (text turns carry no tool metadata).
        secret = "sk-ant-TEXTLEAK-0123456789"
        with (
            tempfile.TemporaryDirectory() as td,
            patch.dict(os.environ, {"ANTHROPIC_API_KEY": secret}),
            patch.object(
                trajectory_models,
                "TRAJECTORY_FIELD_HEAD",
                _TRUNCATION_EDGE_CHARS,
            ),
            patch.object(
                trajectory_models,
                "TRAJECTORY_FIELD_TAIL",
                _TRUNCATION_EDGE_CHARS,
            ),
        ):
            t_path = Path(td) / _TRAJECTORY_FILENAME
            self._emit(
                stdout=_text_turn_stdout(secret),
                prompt=_PROMPT_TEXT,
                traj_path=t_path,
                analytics_path=t_path.parent / _ANALYTICS_FILENAME_ALTERNATE,
            )
            steps = _read_records(t_path)[0][_STEPS_KEY]
            self.assertEqual(
                [step[_KIND_KEY] for step in steps],
                [_ASSISTANT_MESSAGE_KIND, _TOOL_CALL_KIND, _TOOL_RESULT_KIND, _USER_MESSAGE_KIND],
            )
            # Long assistant text head/tail truncated; no tool metadata.
            self.assertLess(
                len(steps[0][_CONTENT_KEY]),
                _LONG_TEXT_CHARS,
            )
            self.assertIn("chars elided", steps[0][_CONTENT_KEY])
            self.assertIsNone(steps[0][_NAME_KEY])
            self.assertIsNone(steps[0][_TOOL_ID_KEY])
            # Secret masked in the user text turn and nowhere survives.
            self.assertEqual(steps[3][_KIND_KEY], _USER_MESSAGE_KIND)
            self.assertIn(_REDACTION_MARKER, steps[3][_CONTENT_KEY])
            self.assertNotIn(secret, json.dumps(_read_records(t_path)[0]))


if __name__ == "__main__":
    unittest.main()


class RecordAgentExitUsageEvidenceTest(_support.RecordAgentExitTrajectorySupport):
    """The trajectory's `run_usage` states the run's evidence as the `agent_exit` record does, and each turn its own."""

    def test_run_and_turn_evidence_on_both_records(self) -> None:
        # The CLI-reported zero is the run's cost on both records, while each
        # turn keeps its own API estimate: a run-level figure reaches no turn.
        exit_record, trajectory = self._emit_both(total_cost_usd=0)
        run_usage = trajectory[_RUN_USAGE_KEY]
        for evidence_key in (_cost.COST_EVIDENCE, _tokens.TOKEN_EVIDENCE):
            self.assertEqual(run_usage[evidence_key], exit_record[evidence_key])
        self.assertEqual(
            _cost.recorded_cost(run_usage),
            _cost.CostEvidence(_cost.COMPLETE, (_cost.CostContribution(_cost.CLI_REPORTED, 0),)),
        )
        turn_costs = [_cost.recorded_cost(turn) for turn in trajectory[_TURNS_KEY]]
        self.assertEqual({(cost.completeness, cost.basis) for cost in turn_costs}, {
            (_cost.COMPLETE, _cost.ANTHROPIC_API_ESTIMATE),
        })
        self.assertEqual(
            _tokens.non_overlapping_total(run_usage),
            sum(_tokens.non_overlapping_total(turn) for turn in trajectory[_TURNS_KEY]),
        )

    def test_turn_estimates_fold_to_the_run_estimate(self) -> None:
        trajectory = self._emit_both()[1]
        run_cost = _cost.recorded_cost(trajectory[_RUN_USAGE_KEY])
        folded = _cost.reduce_costs(_cost.recorded_cost(turn) for turn in trajectory[_TURNS_KEY])
        self.assertEqual(
            (folded.completeness, folded.basis, folded.contributions[0].rates_verified_on),
            (run_cost.completeness, run_cost.basis, run_cost.contributions[0].rates_verified_on),
        )
        self.assertAlmostEqual(folded.complete_usd, run_cost.complete_usd, places=_COST_PLACES)

    def _emit_both(self, total_cost_usd: float | None = None) -> tuple[dict, dict]:
        with tempfile.TemporaryDirectory() as sink_dir:
            analytics_path = Path(sink_dir) / _ANALYTICS_FILENAME
            trajectory_path = Path(sink_dir) / _TRAJECTORY_FILENAME
            self._emit(
                stdout=_claude_multistep_stdout(
                    n_steps=_EVIDENCE_TURN_COUNT,
                    result_text="ok",
                    total_cost_usd=total_cost_usd,
                ),
                traj_path=trajectory_path,
                analytics_path=analytics_path,
            )
            return _read_records(analytics_path)[0], _read_records(trajectory_path)[0]
