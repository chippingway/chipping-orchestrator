# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex terminal-turn reader tests: which turn decides, and what its error said."""

from __future__ import annotations

import unittest

from orchestrator.agents import codex_events as _codex_events
from tests.agents import codex_stream_cases as _streams

_LIMIT = _streams.ROLLOUT_LIMIT_MESSAGE
# What the CLI and a shell around it may print beside the stream.
_NOISE_LINES = (
    "Reading additional input from stdin...",
    '{"type":"turn.started"',
    "[1, 2]",
    "42",
    "",
)


class CodexTurnFailureTest(unittest.TestCase):
    """A failed Codex turn leaves its final message empty, so the failure is
    read off the JSONL stream -- and only off the turn event the run closed on.
    """

    def test_captured_failure_reads_message_alone(self) -> None:
        self.assertEqual(
            _codex_events.codex_turn_failure(_streams.CAPTURED_LIMIT_STDOUT),
            _codex_events.CodexTurnFailure(_streams.CAPTURED_LIMIT_MESSAGE, None),
        )

    def test_only_the_closing_turn_event_decides(self) -> None:
        no_failure = (
            "",
            # A mid-turn error the turn went on to complete past.
            _streams.codex_jsonl(_streams.stream_error(_LIMIT), _streams.turn_completed()),
            # A failed turn a later one in the same stream completed.
            _streams.codex_jsonl(
                _streams.turn_failed(_LIMIT),
                _streams.turn_started(),
                _streams.turn_completed(),
            ),
            # An error with no closing turn event at all.
            _streams.codex_jsonl(_streams.turn_started(), _streams.stream_error(_LIMIT)),
            # A failed turn a later one set aside without ever closing.
            *_streams.LIMIT_THEN_UNFINISHED_TURN_STDOUTS,
        )
        for stdout in no_failure:
            with self.subTest(stdout=stdout):
                self.assertIsNone(_codex_events.codex_turn_failure(stdout))
        failed_last = _streams.codex_jsonl(
            _streams.turn_completed(), _streams.turn_failed(_LIMIT),
        )
        self.assertEqual(
            _codex_events.codex_turn_failure(failed_last),
            _codex_events.CodexTurnFailure(_LIMIT, None),
        )

    def test_error_code_in_either_serde_shape(self) -> None:
        # `(codex_error_info value, code read)`; a mapping is a variant with
        # fields, keyed by its name.
        code_cases = (
            (_streams.USAGE_LIMIT_CODE, _streams.USAGE_LIMIT_CODE),
            ({"http_connection_failed": {"http_status_code": 502}}, "http_connection_failed"),
            (None, None),
            ("", None),
            (["usage_limit_exceeded"], None),
        )
        for error_info, expected_code in code_cases:
            with self.subTest(error_info=error_info):
                stdout = _streams.codex_jsonl(
                    _streams.turn_failed(_LIMIT, codex_error_info=error_info),
                )
                turn_failure = _codex_events.codex_turn_failure(stdout)
                self.assertEqual(turn_failure, _codex_events.CodexTurnFailure(_LIMIT, expected_code))

    def test_malformed_lines_are_skipped(self) -> None:
        noisy = "\n".join((*_NOISE_LINES, _streams.CAPTURED_LIMIT_STDOUT, "trailing-noise"))
        self.assertEqual(
            _codex_events.codex_turn_failure(noisy),
            _codex_events.CodexTurnFailure(_streams.CAPTURED_LIMIT_MESSAGE, None),
        )
        # A closing line cut off mid-write is no closing event.
        truncated = _streams.CAPTURED_LIMIT_STDOUT[:-10]
        self.assertIsNone(_codex_events.codex_turn_failure(truncated))
        # A closing event whose error is not the object the CLI prints still
        # reports the failed turn, with nothing read from the error.
        for error_payload in (None, _LIMIT, {_streams.MESSAGE_FIELD: 7}):
            with self.subTest(error_payload=error_payload):
                stdout = _streams.codex_jsonl({_streams.TYPE_FIELD: "turn.failed", "error": error_payload})
                self.assertEqual(
                    _codex_events.codex_turn_failure(stdout),
                    _codex_events.CodexTurnFailure("", None),
                )


if __name__ == "__main__":
    unittest.main()
