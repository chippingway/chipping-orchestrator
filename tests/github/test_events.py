# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Audit-record construction and the optional JSONL sink."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.github import events as _events

_TS_KEY = "ts"
_REPO_SLUG = "chippingway/orchestrator"
_EVENT_NAME = "agent_spawn"
_STAGE = "implementing"
_ISSUE_NUMBER = 949
_LOG_FILE_NAME = "events.jsonl"


def _record(event: str) -> dict:
    return {"repo": _REPO_SLUG, "issue": _ISSUE_NUMBER, "event": event}


class BuildEventRecordTest(unittest.TestCase):
    """Records carry the schema operators parse existing audit logs with."""

    def test_base_fields_and_second_precision_stamp(self) -> None:
        record = _events.build_event_record(
            repo=_REPO_SLUG,
            issue_number=_ISSUE_NUMBER,
            event=_EVENT_NAME,
            stage=_STAGE,
        )
        stamped = datetime.fromisoformat(record.pop(_TS_KEY))
        self.assertEqual(stamped.tzinfo, UTC)
        self.assertEqual(stamped.microsecond, 0)
        self.assertEqual(
            record,
            {
                "repo": _REPO_SLUG,
                "issue": _ISSUE_NUMBER,
                "event": _EVENT_NAME,
                "stage": _STAGE,
            },
        )

    def test_absent_stage_and_none_extras_are_dropped(self) -> None:
        # Consumers read a missing key as "not applicable to this event", so
        # a `None` extra must never reach the log as an explicit null.
        record = _events.build_event_record(
            repo=_REPO_SLUG,
            issue_number=_ISSUE_NUMBER,
            event=_EVENT_NAME,
            session_id=None,
            retry_count=0,
        )
        self.assertNotIn("stage", record)
        self.assertNotIn("session_id", record)
        self.assertEqual(record["retry_count"], 0)


class WriteEventRecordTest(unittest.TestCase):
    """The JSONL sink is opt-in, append-only, and never breaks a tick."""

    def test_unset_path_appends_nothing(self) -> None:
        with (
            patch.object(config, "EVENT_LOG_PATH", None),
            patch.object(_events, "append_event_line") as append_mock,
        ):
            _events.write_event_record(_record(_EVENT_NAME))
            append_mock.assert_not_called()

    def test_events_append_in_order_with_sorted_keys(self) -> None:
        first = _record("stage_enter")
        second = _record("agent_exit")
        with tempfile.TemporaryDirectory() as work_dir:
            # A nested path pins that the sink creates its parent directory.
            event_path = Path(work_dir) / "audit" / _LOG_FILE_NAME
            with patch.object(config, "EVENT_LOG_PATH", event_path):
                _events.write_event_record(first)
                _events.write_event_record(second)
            written = event_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            written,
            [json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)],
        )

    def test_sink_failure_is_logged_and_swallowed(self) -> None:
        # A full disk or an unwritable audit path must degrade to a warning:
        # the emitting tick keeps running rather than raising through
        # `GitHubClient.emit_event`.
        sink_error = OSError("no space left on device")
        with (
            patch.object(config, "EVENT_LOG_PATH", Path(_LOG_FILE_NAME)),
            patch.object(_events, "append_event_line", side_effect=sink_error),
            self.assertLogs(_events.log, level="WARNING") as captured,
        ):
            _events.write_event_record(_record(_EVENT_NAME))
            warnings = captured.output
        self.assertIn("could not write event log", warnings[0])


if __name__ == "__main__":
    unittest.main()
