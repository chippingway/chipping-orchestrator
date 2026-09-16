# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Event chokepoint tests for real and in-memory GitHub clients.

Verifies that `GitHubIssueMixin.emit_event` and `_WorkflowStateService.emit_event`
fan out every emitted `park_awaiting_human` event to the analytics recorder,
while ignoring other event families (which either have dedicated producers or
are audit-only). Covers audit-off, both-on, analytics-off, analytics-failure,
single-emission guarantee, and agreement between real and fake clients.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.observability.analytics import settings as analytics_settings
from orchestrator.observability.analytics.recording import events as _recording_events
from tests.support.fakes import FakeGitHubClient

_REPO_SLUG = "chippingway/orchestrator"
_ISSUE_NUMBER = 1836
_STAGE = "implementing"
_REASON = "agent_timeout"
_PARK_EVENT = "park_awaiting_human"
_ANALYTICS_PATH_ATTR = "ANALYTICS_LOG_PATH"
_EVENT_PATH_ATTR = "EVENT_LOG_PATH"
_ANALYTICS_JSONL = "analytics.jsonl"
_EVENTS_JSONL = "events.jsonl"
_EVENT_KEY = "event"
_STAGE_KEY = "stage"
_REASON_KEY = "reason"
_REPO_KEY = "repo"
_ISSUE_KEY = "issue"
_PR_KEY = "pr_number"
_TEST_PR_NUMBER = 99

_TEST_EXTRAS = MappingProxyType({
    "route": "standard",
    "agent_role": "implementer",
    "backend": "codex",
    "session_id": "sess-test-123",
    "review_round": 2,
    "retry_count": 1,
    _PR_KEY: 42,
    "dirty_files": 3,
    "conflict_round": 0,
})

_NON_PARK_FAMILIES = (
    ("stage_enter", {_STAGE_KEY: "implementing"}),
    ("agent_exit", {"agent_role": "implementer"}),
    ("agent_spawn", {"agent_role": "implementer"}),
    ("skill_triggered", {"skill": "pytest"}),
    ("review_verdict", {"verdict": "approved"}),
)


def _analytics_file(td: str) -> Path:
    return Path(td, _ANALYTICS_JSONL)


def _audit_file(td: str) -> Path:
    return Path(td, _EVENTS_JSONL)


def _make_real_client(repo_slug: str = _REPO_SLUG) -> GitHubClient:
    client = GitHubClient.__new__(GitHubClient)
    client._repo_slug = repo_slug
    client.recorded_events = []
    return client


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _assert_park_rec(test: unittest.TestCase, rec: dict, extras: dict) -> None:
    test.assertEqual(rec[_EVENT_KEY], _PARK_EVENT)
    test.assertEqual(rec[_REPO_KEY], _REPO_SLUG)
    test.assertEqual(rec[_ISSUE_KEY], _ISSUE_NUMBER)
    test.assertEqual(rec[_STAGE_KEY], _STAGE)
    test.assertEqual(rec[_REASON_KEY], _REASON)
    for key, expected_val in extras.items():
        test.assertEqual(rec.get(key), expected_val)


def _assert_sinks_agree(
    test: unittest.TestCase,
    audit_records: list[dict],
    analytics_records: list[dict],
) -> None:
    test.assertEqual(len(audit_records), 1)
    test.assertEqual(len(analytics_records), 1)
    audit_rec = audit_records[0]
    analytics_rec = analytics_records[0]
    test.assertEqual(audit_rec[_EVENT_KEY], _PARK_EVENT)
    test.assertEqual(analytics_rec[_EVENT_KEY], _PARK_EVENT)
    test.assertEqual(audit_rec[_REPO_KEY], analytics_rec[_REPO_KEY])
    test.assertEqual(audit_rec[_ISSUE_KEY], analytics_rec[_ISSUE_KEY])
    test.assertEqual(audit_rec[_STAGE_KEY], analytics_rec[_STAGE_KEY])
    test.assertEqual(audit_rec[_REASON_KEY], analytics_rec[_REASON_KEY])
    test.assertEqual(audit_rec[_PR_KEY], analytics_rec[_PR_KEY])


class IssueEventsFanoutTest(unittest.TestCase):
    """The `emit_event` chokepoint fans out `park_awaiting_human` to analytics."""

    def test_fake_and_real_clients_agree(self) -> None:
        for client_name, client in (
            ("real", _make_real_client()),
            ("fake", FakeGitHubClient(repo_slug=_REPO_SLUG)),
        ):
            with self.subTest(client=client_name), tempfile.TemporaryDirectory() as td:
                analytics_path = _analytics_file(td)
                with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, analytics_path):
                    client.emit_event(
                        _PARK_EVENT,
                        issue_number=_ISSUE_NUMBER,
                        stage=_STAGE,
                        reason=_REASON,
                        **_TEST_EXTRAS,
                    )
                records = _read_jsonl(analytics_path)
                self.assertEqual(len(records), 1)
                _assert_park_rec(self, records[0], _TEST_EXTRAS)

    def test_audit_disabled_analytics_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            analytics_path = _analytics_file(td)
            audit_path = _audit_file(td)
            client = _make_real_client()
            with (
                patch.object(config, _EVENT_PATH_ATTR, None),
                patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, analytics_path),
            ):
                client.emit_event(
                    _PARK_EVENT,
                    issue_number=_ISSUE_NUMBER,
                    stage=_STAGE,
                    reason=_REASON,
                )
            self.assertFalse(audit_path.exists())
            self.assertEqual(len(_read_jsonl(analytics_path)), 1)

    def test_both_sinks_enabled_write_one_to_each(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            analytics_path = _analytics_file(td)
            audit_path = _audit_file(td)
            client = FakeGitHubClient(repo_slug=_REPO_SLUG)
            with (
                patch.object(config, _EVENT_PATH_ATTR, audit_path),
                patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, analytics_path),
            ):
                client.emit_event(
                    _PARK_EVENT,
                    issue_number=_ISSUE_NUMBER,
                    stage=_STAGE,
                    reason=_REASON,
                    pr_number=_TEST_PR_NUMBER,
                )
            _assert_sinks_agree(
                self,
                _read_jsonl(audit_path),
                _read_jsonl(analytics_path),
            )

    def test_analytics_disabled_audit_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            audit_path = _audit_file(td)
            sentinel = _analytics_file(td)
            client = _make_real_client()
            with (
                patch.object(config, _EVENT_PATH_ATTR, audit_path),
                patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, None),
            ):
                client.emit_event(
                    _PARK_EVENT,
                    issue_number=_ISSUE_NUMBER,
                    stage=_STAGE,
                    reason=_REASON,
                )
            self.assertFalse(sentinel.exists())
            self.assertEqual(len(_read_jsonl(audit_path)), 1)

    def test_analytics_failure_is_logged(self) -> None:
        for client_name, client in (
            ("real", _make_real_client()),
            ("fake", FakeGitHubClient(repo_slug=_REPO_SLUG)),
        ):
            with (
                self.subTest(client=client_name),
                patch.object(
                    _recording_events,
                    "record_park_awaiting_human",
                    side_effect=RuntimeError("disk full"),
                ),
                self.assertLogs("orchestrator.github", level="WARNING") as captured,
            ):
                client.emit_event(
                    _PARK_EVENT,
                    issue_number=_ISSUE_NUMBER,
                    stage=_STAGE,
                    reason=_REASON,
                )
                self.assertTrue(any("analytics record failed" in msg for msg in captured.output))
                self.assertEqual(len(client.recorded_events), 1)

    def test_non_park_events_do_not_fan_out(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            analytics_path = _analytics_file(td)
            client = _make_real_client()
            with (
                patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, analytics_path),
                patch.object(_recording_events, "record_park_awaiting_human") as park_mock,
            ):
                for family_spec in _NON_PARK_FAMILIES:
                    client.emit_event(
                        family_spec[0],
                        issue_number=_ISSUE_NUMBER,
                        **family_spec[1],
                    )
                park_mock.assert_not_called()
            self.assertFalse(analytics_path.exists())

    def test_single_producer_emission(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            analytics_path = _analytics_file(td)
            client = _make_real_client()
            with patch.object(analytics_settings, _ANALYTICS_PATH_ATTR, analytics_path):
                client.emit_event(
                    _PARK_EVENT,
                    issue_number=_ISSUE_NUMBER,
                    stage=_STAGE,
                    reason=_REASON,
                )
            self.assertEqual(len(_read_jsonl(analytics_path)), 1)


if __name__ == "__main__":
    unittest.main()
