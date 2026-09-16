# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an append costs when the sink is turned off: nothing on disk."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config as orchestrator_config
from orchestrator.observability.analytics.recording import events as _recording_events
from tests.observability.analytics.analytics_reload_helpers import reload_analytics as _reload

_EVENT_VALUE = 'x'


_REPO_SHORT = "o/r"


_ANALYTICS_LOG_PATH = "ANALYTICS_LOG_PATH"


_LOG_DIR = "LOG_DIR"


def _append_one() -> None:
    _recording_events.append_record(
        _recording_events.build_record(repo=_REPO_SHORT, issue=1, event=_EVENT_VALUE),
    )


class DisabledSinkAppendTest(unittest.TestCase):
    """With the sink disabled, `append_record` is a silent no-op -- no file
    is ever opened, no directory is created on the way to one, and the
    recorder does not raise.
    """

    def test_append_creates_no_file_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sentinel = Path(td) / "must-not-be-created.jsonl"
            _reload({_ANALYTICS_LOG_PATH: ""})
            _append_one()
            self.assertFalse(sentinel.exists())
            # Directory should also stay empty.
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_disabled_sink_does_not_create_log_dir(self) -> None:
        # Important: disabling must not trigger LOG_DIR creation either. The
        # default sink path is derived from that directory, so it is pinned
        # here rather than left to the operator's own.
        with tempfile.TemporaryDirectory() as td:
            log_dir = Path(td) / "logs"
            with patch.object(orchestrator_config, _LOG_DIR, log_dir):
                _reload({_ANALYTICS_LOG_PATH: "off"})
                _append_one()
            self.assertFalse(log_dir.exists())

    def test_park_creates_no_file_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sentinel = Path(td) / "must-not-be-created.jsonl"
            _reload({_ANALYTICS_LOG_PATH: ""})
            _recording_events.record_park_awaiting_human(
                repo=_REPO_SHORT,
                issue=1,
                stage="implementing",
                reason="agent_timeout",
            )
            self.assertFalse(sentinel.exists())
            self.assertEqual(list(Path(td).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
