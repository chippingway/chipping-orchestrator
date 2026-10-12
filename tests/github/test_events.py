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
_REPO_SLUG = "chippingway/chipping-orchestrator"
_EVENT_NAME = "agent_spawn"
_STAGE = "implementing"
_ISSUE_NUMBER = 949
_LOG_FILE_NAME = "events.jsonl"
_LOG_PATH = "EVENT_LOG_PATH"
_REBASED = "base_rebased"
_FILED_HEAD = "c1c2c3c4c5c6c7c8c9c0c1c2c3c4c5c6c7c8c9c0"
_OTHER_HEAD = "d1d2d3d4d5d6d7d8d9d0d1d2d3d4d5d6d7d8d9d0"


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
            patch.object(config, _LOG_PATH, None),
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
            with patch.object(config, _LOG_PATH, event_path):
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
            patch.object(config, _LOG_PATH, Path(_LOG_FILE_NAME)),
            patch.object(_events, "append_event_line", side_effect=sink_error),
            self.assertLogs(_events.log, level="WARNING") as captured,
        ):
            _events.write_event_record(_record(_EVENT_NAME))
            warnings = captured.output
        self.assertIn("could not write event log", warnings[0])


class _Client:
    """A client's in-memory tail of recorded events, and the repository it records them for."""

    _repo_slug = _REPO_SLUG

    def __init__(self, *recorded: dict) -> None:
        self.recorded_events = list(recorded)


def _filed(client: _Client, sha: str) -> bool:
    """Whether `client`'s stream carries a `base_rebased` for issue #949 naming `sha`."""
    return _events.filed(client, _REBASED, issue_number=_ISSUE_NUMBER, sha=sha)


class FiledEventTest(unittest.TestCase):
    """An event already on the stream is found -- in the client's tail, or in the audit log's -- and no other is."""

    def test_an_event_is_found_where_it_was_filed(self) -> None:
        # A process lost after filing an event comes back with an empty tail:
        # the audit log is what still carries it, read from its end, a line
        # that does not parse passed over.
        filed = {**_record(_REBASED), "sha": _FILED_HEAD}
        with tempfile.TemporaryDirectory() as work_dir:
            event_path = Path(work_dir) / _LOG_FILE_NAME
            event_path.write_text(f"not json\n{json.dumps(filed)}\n")
            with patch.object(config, _LOG_PATH, event_path):
                found = (_filed(_Client(), _FILED_HEAD), _filed(_Client(), _OTHER_HEAD))
        in_memory = _filed(_Client(filed), _FILED_HEAD)
        self.assertEqual((*found, in_memory), (True, False, True))

    def test_nothing_is_found_without_a_log(self) -> None:
        with patch.object(config, _LOG_PATH, None):
            self.assertFalse(_filed(_Client(), _FILED_HEAD))


if __name__ == "__main__":
    unittest.main()
