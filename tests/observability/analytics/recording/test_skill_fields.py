# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Analytics agent-exit skill-field tests."""

import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.observability.analytics import (
    settings as analytics_settings,
    sink as analytics_sink,
)
from orchestrator.observability.analytics.recording import agent_exit as _agent_exit_records
from orchestrator.observability.usage import skills as _usage_skills
from tests.observability.analytics.analytics_jsonl_helpers import (
    read_records as _read_records,
)
from tests.observability.analytics.analytics_recording_cases import (
    agent_exit_result as _agent_exit_result,
    claude_stdout_with_skills as _claude_stdout_with_skills,
)

_ANALYTICS_FILENAME = 'a.jsonl'


AGENT_EXIT_ISSUE_NUMBER = 7


SKILL_STREAM_INPUT_TOKENS = 1_000


SKILL_STREAM_OUTPUT_TOKENS = 500


_REPO = "owner/repo"


_CLAUDE = "claude"


_DEVELOP = "develop"


_REVIEW = "review"


_STAGE_IMPLEMENTING = "implementing"


_DEVELOPER = "developer"


_AGENT_EXIT = "agent_exit"


_ANALYTICS_LOG_PATH = "ANALYTICS_LOG_PATH"


_TRACK_SKILL_TRIGGERS = "TRACK_SKILL_TRIGGERS"


_INPUT_TOKENS = "input_tokens"


_OUTPUT_TOKENS = "output_tokens"


_SKILLS_TRIGGERED = "skills_triggered"


_SKILLS_TRIGGERED_COUNT = "skills_triggered_count"


_SKILLS_AVAILABLE = "skills_available"


_SKILL_LEVELS = "skill_levels"


_SKILLS_EVIDENCE = "skills_evidence"


_SKILLS_INCIDENTAL = "skills_incidental"


_SKILLS_INCIDENTAL_COUNT = "skills_incidental_count"


_SKILL_FIELD_KEYS = (
    _SKILLS_TRIGGERED,
    _SKILLS_TRIGGERED_COUNT,
    _SKILLS_AVAILABLE,
    _SKILL_LEVELS,
    _SKILLS_EVIDENCE,
    _SKILLS_INCIDENTAL,
    _SKILLS_INCIDENTAL_COUNT,
)


class _RecordAgentExitSkillSupport(unittest.TestCase):
    """`record_agent_exit` folds skill triggers into the `agent_exit`
    record only when `TRACK_SKILL_TRIGGERS` is on, never leaks the `Skill`
    args or raw stdout, and keeps emitting the baseline usage/cost record
    even when the skill parse raises (its own fail-open guard)."""

    def _emit(
        self,
        path,
        *,
        stdout,
        backend=_CLAUDE,
        track=True,
    ) -> list[dict]:
        with (
            patch.object(analytics_settings, _ANALYTICS_LOG_PATH, path),
            patch.object(analytics_settings, _TRACK_SKILL_TRIGGERS, track),
        ):
            _agent_exit_records.record_agent_exit(
                repo=_REPO,
                issue=AGENT_EXIT_ISSUE_NUMBER,
                stage=_STAGE_IMPLEMENTING,
                agent_role=_DEVELOPER,
                backend=backend,
                agent_spec=_CLAUDE,
                resume_session_id=None,
                result=_agent_exit_result(stdout),
                duration_s=float(0),
                review_round=0,
                retry_count=1,
            )
        return _read_records(path)

    def _record(
        self,
        *,
        stdout,
        track=True,
        parse=None,
        backend=_CLAUDE,
    ):
        """Call `record_agent_exit` with the sink disabled and return its
        value -- the de-duplicated triggered list the caller emits events
        from. `parse` optionally stubs the skill extractor.
        """
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(analytics_settings, _ANALYTICS_LOG_PATH, None))
            stack.enter_context(patch.object(analytics_settings, _TRACK_SKILL_TRIGGERS, track))
            if parse is not None:
                stack.enter_context(patch.object(_usage_skills, "parse_agent_skills", parse))
            return _agent_exit_records.record_agent_exit(
                repo=_REPO,
                issue=AGENT_EXIT_ISSUE_NUMBER,
                stage=_STAGE_IMPLEMENTING,
                agent_role=_DEVELOPER,
                backend=backend,
                agent_spec=backend,
                resume_session_id=None,
                result=_agent_exit_result(stdout),
                duration_s=float(0),
                review_round=0,
                retry_count=1,
            )


class RecordAgentExitSkillFieldsTest(_RecordAgentExitSkillSupport):
    def test_switch_off_drops_all_skill_fields(self) -> None:
        # Default-off: a skill-bearing stream still records usage but none
        # of the three skill keys appear -- shape-compatible with today.
        with tempfile.TemporaryDirectory() as td:
            records = self._emit(
                Path(td) / _ANALYTICS_FILENAME,
                stdout=_claude_stdout_with_skills(skills=(_DEVELOP,)),
                track=False,
            )
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["event"], _AGENT_EXIT)
        self.assertEqual(rec[_INPUT_TOKENS], SKILL_STREAM_INPUT_TOKENS)
        for key in _SKILL_FIELD_KEYS:
            self.assertNotIn(key, rec)

    def test_switch_on_records_triggered_fields(self) -> None:
        # develop fires twice and review once: the de-duplicated list keeps
        # first-seen order, the count sums every invocation, and the
        # uncaptured offered set leaves `skills_available` dropped.
        with tempfile.TemporaryDirectory() as td:
            records = self._emit(
                Path(td) / _ANALYTICS_FILENAME,
                stdout=_claude_stdout_with_skills(
                    skills=(_DEVELOP, _DEVELOP, _REVIEW),
                ),
                track=True,
            )
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec[_SKILLS_TRIGGERED], [_DEVELOP, _REVIEW])
        self.assertEqual(rec[_SKILLS_TRIGGERED_COUNT], 3)
        # A claude `Skill` call is a confirmed load, so every triggered name
        # carries `confirmed` evidence and there are no incidental references.
        self.assertEqual(
            rec[_SKILLS_EVIDENCE],
            {_DEVELOP: "confirmed", _REVIEW: "confirmed"},
        )
        self.assertNotIn(_SKILLS_INCIDENTAL, rec)
        self.assertNotIn(_SKILLS_INCIDENTAL_COUNT, rec)
        self.assertNotIn(_SKILLS_AVAILABLE, rec)
        self.assertEqual(rec[_INPUT_TOKENS], SKILL_STREAM_INPUT_TOKENS)

    def test_switch_on_no_triggers_matches_off_shape(self) -> None:
        # Switch on but the stream triggered nothing: all three skill keys
        # stay dropped, so the record is shape-identical to the off case.
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            off = self._emit(
                temp_root / "off.jsonl",
                stdout=_claude_stdout_with_skills(skills=(_DEVELOP,)),
                track=False,
            )
            on_none = self._emit(
                temp_root / "on.jsonl",
                stdout=_claude_stdout_with_skills(skills=()),
                track=True,
            )
        self.assertTrue(set(_SKILL_FIELD_KEYS).isdisjoint(on_none[0]))
        self.assertEqual(set(off[0]), set(on_none[0]))

    def test_args_and_stdout_absent_from_record(self) -> None:
        # Privacy: the `Skill` tool's `args` can echo issue/user content; the
        # record carries the skill NAME but never the args payload nor the
        # raw stdout. Mirrors the usage-sink redaction contract.
        marker = "ghp_LEAKED_SKILL_ARG_PAYLOAD_DO_NOT_STORE"
        stdout = _claude_stdout_with_skills(
            skills=(_DEVELOP,),
            args_marker=marker,
        )
        with tempfile.TemporaryDirectory() as td:
            rec = self._emit(
                Path(td) / _ANALYTICS_FILENAME,
                stdout=stdout,
                track=True,
            )[0]
        self.assertEqual(rec[_SKILLS_TRIGGERED], [_DEVELOP])
        self.assertNotIn(marker, json.dumps(rec))
        self.assertNotIn(stdout, json.dumps(rec))
        self.assertTrue({"args", "stdout", "prompt"}.isdisjoint(rec))

    def test_real_init_records_available_field(self) -> None:
        # The offered-set wiring exercised end-to-end through the real claude
        # extractor (no stub): a `system`/`init` frame carrying a `skills`
        # array lands as `skills_available`, independent of what triggered.
        # That frame names no source directory, so the provenance key is
        # dropped rather than guessed for the names it did report.
        with tempfile.TemporaryDirectory() as td:
            records = self._emit(
                Path(td) / _ANALYTICS_FILENAME,
                stdout=_claude_stdout_with_skills(
                    skills=(_DEVELOP,),
                    offered=(_DEVELOP, _REVIEW),
                ),
                track=True,
            )
        rec = records[0]
        self.assertEqual(rec[_SKILLS_TRIGGERED], [_DEVELOP])
        self.assertEqual(rec[_SKILLS_TRIGGERED_COUNT], 1)
        self.assertEqual(rec[_SKILLS_AVAILABLE], [_DEVELOP, _REVIEW])
        self.assertNotIn(_SKILL_LEVELS, rec)

    def test_available_independent_of_triggered(self) -> None:
        # Offered but nothing triggered: `skills_available` is written while
        # `skills_triggered` / `_count` stay dropped -- the asymmetry that
        # tells "offered but unused" from "never available."
        with tempfile.TemporaryDirectory() as td:
            records = self._emit(
                Path(td) / _ANALYTICS_FILENAME,
                stdout=_claude_stdout_with_skills(
                    skills=(),
                    offered=(_DEVELOP, _REVIEW),
                ),
                track=True,
            )
        rec = records[0]
        self.assertEqual(rec[_SKILLS_AVAILABLE], [_DEVELOP, _REVIEW])
        self.assertNotIn(_SKILLS_TRIGGERED, rec)
        self.assertNotIn(_SKILLS_TRIGGERED_COUNT, rec)

    def test_parse_failure_keeps_baseline_record(self) -> None:
        # A skill-parser bug must NOT drop the usage/cost record: the inner
        # fail-open guard logs and falls through with the skill fields unset.
        with (
            tempfile.TemporaryDirectory() as td,
            patch.object(
                _usage_skills,
                "parse_agent_skills",
                side_effect=RuntimeError("boom"),
            ),
            self.assertLogs(analytics_sink.log, level="ERROR"),
        ):
            records = self._emit(
                Path(td) / _ANALYTICS_FILENAME,
                stdout=_claude_stdout_with_skills(skills=(_DEVELOP,)),
                track=True,
            )
        self.assertEqual(len(records), 1)
        rec = records[0]
        # Baseline usage fields survived the skill-parse failure...
        self.assertEqual(rec["event"], _AGENT_EXIT)
        self.assertEqual(rec[_INPUT_TOKENS], SKILL_STREAM_INPUT_TOKENS)
        self.assertEqual(rec[_OUTPUT_TOKENS], SKILL_STREAM_OUTPUT_TOKENS)
        # ...and the skill fields were left off.
        for key in _SKILL_FIELD_KEYS:
            self.assertNotIn(key, rec)
