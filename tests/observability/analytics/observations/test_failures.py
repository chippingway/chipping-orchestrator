# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One failure boundary around a reply's whole recording, from its framing through its append.

Whatever step fails before the append -- framing the reply, redacting, or
serializing -- the recorder raises nothing, writes no partial record, and
records a diagnostic naming the step, the counts it had reached, and the
failure's type, never the text the step could not finish with. Where that
diagnostic cannot be written either, or the append itself is refused --
taking a snapshot or a refused reply's diagnostic with it -- it warns once
and writes nothing more; and so it does where the sink's settings will not
read at all.
"""
from __future__ import annotations

import json
from dataclasses import replace
from types import MappingProxyType, SimpleNamespace
from unittest.mock import MagicMock, patch

from orchestrator.observability.analytics import settings as analytics_settings, sink
from orchestrator.observability.analytics.observations import bounds, recorder, records
from tests.observability.analytics.observations import observation_test_support as _support

_CHANNEL = "orchestrator.analytics"

_REDACTOR = "orchestrator.config.credentials.redact_secrets"

# A reply whose snapshot reads: whatever is recorded instead is the failure's.
_REPLY = _support.reply(f"Done.\n{_support.snapshot_line()}")

_READ = MappingProxyType({"found": 1, "readable": 1})

_UNREAD = MappingProxyType({})

# Each step's failure: its category, the counts it had reached, the type it
# failed with, and the test's method failing it.
_STEP_FAILURES = (
    ("parse_failed", _UNREAD, "RuntimeError", "_outcome_fails"),
    ("redaction_failed", _READ, "RuntimeError", "_redaction_fails"),
    ("serialization_failed", _READ, "TypeError", "_serialization_fails"),
)

# What a failure's diagnostic is read as.
_DIAGNOSED = ("event", "category", "counts", "error", "source", "item", "excerpt")


class _FailsOnce:
    """`real`, failing with `error` the first time it is called."""

    def __init__(self, real, error: Exception) -> None:
        self._real = real
        self._errors = [error]

    def __call__(self, *args, **kwargs):
        """Raise the error once; answer as `real` ever after."""
        if self._errors:
            raise self._errors.pop()
        return self._real(*args, **kwargs)


def _outcome_unfound(message: str) -> int:
    raise RuntimeError(f"cannot find an outcome in {len(message)} characters")


def _diagnosed(record: dict) -> dict:
    """What a failure's diagnostic says, every field it should carry and the one it should not."""
    return {key: record.get(key) for key in _DIAGNOSED}


def _expected(category: str, counts: dict, error: str) -> dict:
    """The diagnostic of a step that failed in `category` with `error`, having reached `counts`: no excerpt."""
    return {
        "event": "observation_diagnostic",
        "category": category,
        "counts": counts,
        "error": error,
        "source": _support.SOURCE,
        "item": "task-snapshot",
        "excerpt": None,
    }


class StepFailureTest(_support.SinkCase):
    """Each step's failure, diagnosed by the step it failed in."""

    def test_each_failed_step_is_diagnosed(self) -> None:
        for category, counts, error, failing in _STEP_FAILURES:
            with self.subTest(category=category):
                self.path.unlink(missing_ok=True)
                getattr(self, failing)()
                diagnosed = [_diagnosed(record) for record in self.written()]
                self.assertEqual(diagnosed, [_expected(category, counts, error)])
                self.assertNotIn(_support.DESCRIPTION, self.path.read_text(encoding="utf-8"))

    def _outcome_fails(self) -> None:
        recorder.record_task_snapshot(_support.RUN, recorder.ObservedReply(_REPLY, _outcome_unfound), self.path)

    def _redaction_fails(self) -> None:
        with patch(_REDACTOR, side_effect=RuntimeError("redactor unavailable")):
            self.record(_REPLY)

    def _serialization_fails(self) -> None:
        encoder = SimpleNamespace(dumps=_FailsOnce(json.dumps, TypeError("not serializable")))
        with patch.object(records, "json", encoder):
            self.record(_REPLY)


class LostDiagnosticTest(_support.SinkCase):
    """A diagnostic that cannot be written either: one warning, and nothing more."""

    def test_a_lost_diagnostic_warns_once(self) -> None:
        # An append refused for good, or once on a refused reply's diagnostic,
        # takes what it carried and is not tried again; and a record past its
        # limit with every text dropped -- an identifier kept whole rather than
        # cut -- serializes no diagnostic either. One warning each, and nothing
        # raised or written.
        cases = (
            ("append", self._record_onto_a_directory),
            ("append", self._missing_diagnostic_refused_once),
            ("serialization", self._identifier_overflows),
        )
        for step, failing in cases:
            with self.subTest(step=step), self.assertLogs(_CHANNEL, level="WARNING") as logged:
                failing()
                self.assertEqual(len(logged.output), 1)
                self.assertIn(f"to {step}_failed", logged.output[0])
            self.assertEqual(self.written(), [])

    def test_an_unreadable_sink_warns_once(self) -> None:
        # Where the sink's own settings will not read, nothing is asked of the
        # reply, written, or raised.
        settings = SimpleNamespace(live_settings=MagicMock(side_effect=OSError("settings unavailable")))
        with patch.object(recorder, "analytics_config", settings), self.assertLogs(_CHANNEL, level="WARNING") as logged:
            self.assertEqual(self.record(_REPLY), [])
            self.assertEqual(len(logged.output), 1)

    def _record_onto_a_directory(self) -> None:
        with patch.object(analytics_settings, "ANALYTICS_LOG_PATH", self.path.parent):
            self.record(_REPLY)

    def _missing_diagnostic_refused_once(self) -> None:
        with patch.object(sink, "write_jsonl_lines", _FailsOnce(sink.write_jsonl_lines, OSError("disk full"))):
            self.record("The developer supplied no attachment.")

    def _identifier_overflows(self) -> None:
        self.record(_REPLY, replace(_support.RUN, requirements_revision="f" * bounds.RECORD_BYTES))
