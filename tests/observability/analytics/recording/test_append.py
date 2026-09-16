# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record envelope, the JSONL line one append writes, and what
intercepts it."""

import contextlib
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from orchestrator.observability.analytics.recording import events
from tests.observability.analytics.analytics_jsonl_helpers import (
    read_lines as _read_lines,
)
from tests.observability.analytics.analytics_reload_helpers import reload_analytics as _reload

_STAGE_KEY = 'stage'


_ISSUE_KEY = "issue"


_EVENT_KEY = "event"


_EVENT_VALUE = 'x'


_REQUIRED_BASE_FIELDS_ISSUE = 42


_REPO_SHORT = "o/r"


_STAGE_IMPLEMENTING = "implementing"


_STAGE_ENTER = "stage_enter"


_ANALYTICS_LOG_PATH = "ANALYTICS_LOG_PATH"


_ANALYTICS_RETENTION_DAYS = "ANALYTICS_RETENTION_DAYS"


_APPEND_RECORD_MEMBER = "append_record"


_PARK_AWAITING_HUMAN = "park_awaiting_human"


_REASON_KEY = "reason"


_REASON_AGENT_TIMEOUT = "agent_timeout"


_ROUTE_KEY = "route"


_TEST_ROUTE = "escalate"


_TEST_ISSUE = 42


_TEST_PR_NUMBER = 101


_TEST_REVIEW_ROUND = 2


_TEST_RETRY_COUNT = 1


_TEST_DIRTY_FILES = 3


_TEST_CONFLICT_ROUND = 1


@contextlib.contextmanager
def _analytics_sink(retention: str | None = None):
    """Re-parse the analytics knobs against a temporary `analytics.jsonl`
    sink, yielding the path every append below lands in.
    """
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "analytics.jsonl"
        env = {_ANALYTICS_LOG_PATH: str(path)}
        if retention is not None:
            env[_ANALYTICS_RETENTION_DAYS] = retention
        _reload(env)
        yield path


class AnalyticsAppendTest(unittest.TestCase):
    """`build_record` produces the documented base fields and
    `append_record` writes one well-formed JSONL line per call.
    """

    def test_record_has_required_base_fields(self) -> None:
        rec = events.build_record(
            repo=_REPO_SHORT,
            issue=_REQUIRED_BASE_FIELDS_ISSUE,
            event=_STAGE_ENTER,
            stage=_STAGE_IMPLEMENTING,
        )
        self.assertIn("ts", rec)
        self.assertEqual(rec["repo"], _REPO_SHORT)
        self.assertEqual(rec[_ISSUE_KEY], _REQUIRED_BASE_FIELDS_ISSUE)
        self.assertEqual(rec[_EVENT_KEY], _STAGE_ENTER)
        self.assertEqual(rec[_STAGE_KEY], _STAGE_IMPLEMENTING)
        parsed = datetime.fromisoformat(rec["ts"])
        self.assertIsNotNone(parsed.tzinfo)

    def test_stage_omitted_when_none(self) -> None:
        rec = events.build_record(
            repo=_REPO_SHORT,
            issue=1,
            event="pr_opened",
        )
        self.assertNotIn(_STAGE_KEY, rec)

    def test_none_valued_extras_are_dropped(self) -> None:
        rec = events.build_record(
            repo=_REPO_SHORT,
            issue=1,
            event="agent_spawn",
            session_id=None,
            retry_count=2,
        )
        self.assertNotIn("session_id", rec)
        self.assertEqual(rec["retry_count"], 2)

    def test_append_writes_one_line_per_record(self) -> None:
        with _analytics_sink() as path:
            events.append_record(
                events.build_record(
                    repo=_REPO_SHORT,
                    issue=1,
                    event=_STAGE_ENTER,
                    stage=_STAGE_IMPLEMENTING,
                )
            )
            events.append_record(
                events.build_record(
                    repo=_REPO_SHORT,
                    issue=2,
                    event="pr_opened",
                    pr_number=5,
                )
            )
            self.assertTrue(path.exists())
            lines = _read_lines(path)
            self.assertEqual(len(lines), 2)
            rec0 = json.loads(lines[0])
            self.assertEqual(rec0[_ISSUE_KEY], 1)
            self.assertEqual(rec0[_EVENT_KEY], _STAGE_ENTER)
            self.assertEqual(rec0[_STAGE_KEY], _STAGE_IMPLEMENTING)
            rec1 = json.loads(lines[1])
            self.assertEqual(rec1["pr_number"], 5)
            self.assertNotIn(_STAGE_KEY, rec1)

    def test_creates_missing_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "a" / "b" / "c" / "analytics.jsonl"
            _reload({_ANALYTICS_LOG_PATH: str(path)})
            events.append_record(
                events.build_record(repo=_REPO_SHORT, issue=1, event=_EVENT_VALUE),
            )
            self.assertTrue(path.exists())

    def test_append_is_append_only(self) -> None:
        # Repeated appends must accumulate, never overwrite prior records.
        with _analytics_sink() as path:
            for issue_num in range(5):
                events.append_record(
                    events.build_record(
                        repo=_REPO_SHORT,
                        issue=issue_num,
                        event=_EVENT_VALUE,
                    )
                )
            lines = _read_lines(path)
            self.assertEqual(len(lines), 5)
            issues = [json.loads(line)[_ISSUE_KEY] for line in lines]
            self.assertEqual(issues, list(range(5)))


def _assert_park_fields(test: unittest.TestCase, rec: dict) -> None:
    expected = {
        "repo": _REPO_SHORT,
        _ISSUE_KEY: _TEST_ISSUE,
        _EVENT_KEY: _PARK_AWAITING_HUMAN,
        _STAGE_KEY: _STAGE_IMPLEMENTING,
        _REASON_KEY: _REASON_AGENT_TIMEOUT,
        _ROUTE_KEY: _TEST_ROUTE,
        "agent_role": "implementer",
        "backend": "codex",
        "session_id": "sess-xyz",
        "review_round": _TEST_REVIEW_ROUND,
        "retry_count": _TEST_RETRY_COUNT,
        "pr_number": _TEST_PR_NUMBER,
        "dirty_files": _TEST_DIRTY_FILES,
        "conflict_round": _TEST_CONFLICT_ROUND,
    }
    for field, expected_val in expected.items():
        test.assertEqual(rec.get(field), expected_val)
    test.assertIsNotNone(datetime.fromisoformat(rec["ts"]).tzinfo)


def _assert_null_dropped(test: unittest.TestCase, rec: dict) -> None:
    for key in (_STAGE_KEY, _REASON_KEY, _ROUTE_KEY, "review_round", "agent_role"):
        test.assertNotIn(key, rec)
    test.assertEqual(rec["repo"], _REPO_SHORT)
    test.assertEqual(rec[_ISSUE_KEY], _TEST_ISSUE)
    test.assertEqual(rec[_EVENT_KEY], _PARK_AWAITING_HUMAN)


class ParkAwaitingHumanRecordTest(unittest.TestCase):
    """`record_park_awaiting_human` appends exactly one compact record with
    the expected envelope, drops nulls, and rejects comments or secrets.
    """

    def test_park_record_appends_compact_line(self) -> None:
        with _analytics_sink() as path:
            events.record_park_awaiting_human(
                repo=_REPO_SHORT,
                issue=_TEST_ISSUE,
                stage=_STAGE_IMPLEMENTING,
                reason=_REASON_AGENT_TIMEOUT,
                route=_TEST_ROUTE,
                agent_role="implementer",
                backend="codex",
                session_id="sess-xyz",
                review_round=_TEST_REVIEW_ROUND,
                retry_count=_TEST_RETRY_COUNT,
                pr_number=_TEST_PR_NUMBER,
                dirty_files=_TEST_DIRTY_FILES,
                conflict_round=_TEST_CONFLICT_ROUND,
            )
            self.assertTrue(path.exists())
            lines = _read_lines(path)
            self.assertEqual(len(lines), 1)
            _assert_park_fields(self, json.loads(lines[0]))

    def test_park_record_drops_nulls(self) -> None:
        with _analytics_sink() as path:
            events.record_park_awaiting_human(
                repo=_REPO_SHORT,
                issue=_TEST_ISSUE,
                stage=None,
                reason=None,
                route=None,
                review_round=None,
                agent_role=None,
            )
            self.assertTrue(path.exists())
            lines = _read_lines(path)
            self.assertEqual(len(lines), 1)
            _assert_null_dropped(self, json.loads(lines[0]))

    def test_park_record_round_trips_route(self) -> None:
        with _analytics_sink() as path:
            events.record_park_awaiting_human(
                repo=_REPO_SHORT,
                issue=_TEST_ISSUE,
                stage=_STAGE_IMPLEMENTING,
                reason=_REASON_AGENT_TIMEOUT,
                route=_TEST_ROUTE,
            )
            self.assertTrue(path.exists())
            lines = _read_lines(path)
            self.assertEqual(len(lines), 1)
            rec = json.loads(lines[0])
            self.assertEqual(rec.get(_ROUTE_KEY), _TEST_ROUTE)

    def test_park_record_rejects_forbidden_inputs(self) -> None:
        forbidden_inputs = (
            "comment",
            "message",
            "prompt",
            "report",
            "report_body",
            "command_output",
            "stdout",
            "stderr",
            "secret",
            "token",
        )
        for field_name in forbidden_inputs:
            with self.subTest(field=field_name), self.assertRaises(TypeError):
                events.record_park_awaiting_human(
                    repo=_REPO_SHORT,
                    issue=_TEST_ISSUE,
                    stage=_STAGE_IMPLEMENTING,
                    reason=_REASON_AGENT_TIMEOUT,
                    **{field_name: "unexpected_payload"},
                )

    def test_park_record_rejects_invalid_args(self) -> None:
        with self.assertRaises(TypeError):
            events.record_park_awaiting_human(_REPO_SHORT, _TEST_ISSUE)
        with self.assertRaises(TypeError):
            events.record_park_awaiting_human(issue=_TEST_ISSUE)
        with self.assertRaises(TypeError):
            events.record_park_awaiting_human(repo=_REPO_SHORT)

    def test_park_record_filesystem_fails_open(self) -> None:
        disk_full = patch.object(Path, "open", side_effect=OSError("disk full"))
        with _analytics_sink(), disk_full:
            events.record_park_awaiting_human(
                repo=_REPO_SHORT,
                issue=_TEST_ISSUE,
                stage=_STAGE_IMPLEMENTING,
                reason=_REASON_AGENT_TIMEOUT,
            )


class AppendInterceptionTest(unittest.TestCase):
    """A recorder's own append is dispatched on the owner that defines it, so
    patching it there is what intercepts an internal write.
    """

    def test_internal_append_routes_via_the_owner(self) -> None:
        captured: list[dict] = []
        with patch.object(events, _APPEND_RECORD_MEMBER, captured.append):
            events.record_stage_enter(
                repo=_REPO_SHORT,
                issue=1,
                stage=_STAGE_IMPLEMENTING,
            )
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][_EVENT_KEY], _STAGE_ENTER)

    def test_internal_park_routes_via_owner(self) -> None:
        captured: list[dict] = []
        with patch.object(events, _APPEND_RECORD_MEMBER, captured.append):
            events.record_park_awaiting_human(
                repo=_REPO_SHORT,
                issue=1,
                stage=_STAGE_IMPLEMENTING,
                reason=_REASON_AGENT_TIMEOUT,
            )
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][_EVENT_KEY], _PARK_AWAITING_HUMAN)
