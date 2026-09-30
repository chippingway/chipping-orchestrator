# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Provider-refusal verdict owner tests: the transient one and the wider one."""

from __future__ import annotations

import json
import unittest

from orchestrator.agents import provider_failures as _provider_failures
from orchestrator.agents.models import AgentResult
from tests.agents import agent_test_values as _agent_cases


def _claude_result_event(result_text: str, **result_fields) -> str:
    """One terminal result frame, optionally carrying the `is_error` flag."""
    return json.dumps(
        {
            _agent_cases._TYPE_FIELD: _agent_cases._RESULT_FIELD,
            _agent_cases._RESULT_FIELD: result_text,
            **result_fields,
        }
    )


def _agent_result(
    last_message: str = "", *, exit_code: int = 0, stdout: str = "",
) -> AgentResult:
    return AgentResult(
        session_id=None,
        last_message=last_message,
        exit_code=exit_code,
        timed_out=False,
        stdout=stdout,
        stderr="",
    )


# `(result text, is_error, exit code, transient?)`.
_STRUCTURED_VERDICT_CASES = (
    (_agent_cases._OVERLOADED_RESULT, True, 0, True),
    (_agent_cases._OVERLOADED_RESULT, False, 1, False),
    (_agent_cases._OVERLOADED_MENTION, False, 0, False),
    # Flagged, but not a refusal a retry on a fresh session recovers from.
    ("Error: No such file or directory (os error 2)", True, 1, False),
)


class TransientProviderFailureTest(unittest.TestCase):
    """A provider refusal arrives through the same final-message field an
    agent's own answer does, so every stage that reads that field as the
    agent's words asks this first. It must recognize the observed
    `API Error: 529 Overloaded` and its 5xx siblings, refuse to reclassify a
    run that merely wrote about one, and leave every other failure alone.
    """

    def test_structured_flag_outranks_exit_code(self) -> None:
        # `is_error` is the backend's own verdict on whether the result text is
        # the run's outcome or its subject, so it outranks the exit code in
        # BOTH directions: a flagged refusal is transient even on a clean exit,
        # and a successful answer quoting the refusal stays an answer even on a
        # dirty one.
        for result_text, is_error, exit_code, expected in _STRUCTURED_VERDICT_CASES:
            with self.subTest(result_text=result_text, is_error=is_error):
                flagged = _agent_result(
                    result_text,
                    exit_code=exit_code,
                    stdout=_claude_result_event(
                        result_text, **{_agent_cases._IS_ERROR_FIELD: is_error},
                    ),
                )
                self.assertEqual(
                    _provider_failures.is_transient_provider_failure(flagged),
                    expected,
                )

    def test_marker_needs_nonzero_exit_unflagged(self) -> None:
        # No structured verdict at all (a backend that emits none) and a result
        # event from a CLI that omits the flag both fall back to the exit code,
        # which is what keeps a clean run from being reclassified on its prose.
        for stdout in ("", _claude_result_event(_agent_cases._OVERLOADED_RESULT)):
            with self.subTest(has_result_event=bool(stdout)):
                failed = _agent_result(
                    _agent_cases._OVERLOADED_RESULT, exit_code=1, stdout=stdout,
                )
                self.assertTrue(_provider_failures.is_transient_provider_failure(failed))
                succeeded = _agent_result(
                    _agent_cases._OVERLOADED_RESULT, exit_code=0, stdout=stdout,
                )
                self.assertFalse(_provider_failures.is_transient_provider_failure(succeeded))

    def test_marker_is_prefix_over_server_errors(self) -> None:
        # Matched as a PREFIX so a dev writing about the outage mid-answer is
        # left alone, and only over the server-side family: a 4xx is a request
        # this account may not make and a 429 is quota, neither of which a
        # retry on a fresh session recovers.
        transient = (
            _agent_cases._OVERLOADED_RESULT,
            "API Error: 500 Internal server error",
            "API Error: 502 Bad Gateway",
            "API Error: 503 Service Unavailable",
            "API Error: 504 Gateway Timeout",
            "  api error: overloaded_error",
        )
        for last_message in transient:
            with self.subTest(last_message=last_message):
                self.assertTrue(
                    _provider_failures.is_transient_provider_failure(
                        _agent_result(last_message, exit_code=1),
                    ),
                )
        left_alone = (
            "",
            _agent_cases._OVERLOADED_MENTION,
            "Should I prefer ruff or black for this?",
            "API Error: 400 Bad Request",
            "API Error: 401 Unauthorized",
            "API Error: 429 Too Many Requests",
        )
        for last_message in left_alone:
            with self.subTest(last_message=last_message):
                self.assertFalse(
                    _provider_failures.is_transient_provider_failure(
                        _agent_result(last_message, exit_code=1),
                    ),
                )


# Refusals of every kind the provider answers a turn with, 4xx included.
_REFUSALS = (
    _agent_cases._OVERLOADED_RESULT,
    "API Error: 400 Bad Request",
    "API Error: 401 Unauthorized",
    "  api error: 429 Too Many Requests",
)


class ProviderRefusalTest(unittest.TestCase):
    """Whether a run got to its prompt at all, whatever a retry could do.

    Asked by a caller settling what a run was handed, where a refusal read as
    an answer drops a human's words: so every `API Error:` counts, and the
    prefix decides on a clean exit too where the backend gave no flag.
    """

    def test_every_refusal_counts_on_any_exit(self) -> None:
        for last_message in _REFUSALS:
            for exit_code in (0, 1):
                with self.subTest(last_message=last_message, exit_code=exit_code):
                    self.assertTrue(
                        _provider_failures.is_provider_refusal(
                            _agent_result(last_message, exit_code=exit_code),
                        ),
                    )

    def test_the_agents_own_words_are_left_alone(self) -> None:
        # A mention mid-answer is prose, and a flagged `is_error: false` turn
        # quoting a refusal back is an answer however it opens.
        unflagged = ("", _agent_cases._OVERLOADED_MENTION, "Should I prefer ruff or black for this?")
        for last_message in unflagged:
            with self.subTest(last_message=last_message):
                self.assertFalse(
                    _provider_failures.is_provider_refusal(
                        _agent_result(last_message, exit_code=1),
                    ),
                )
        quoted = _agent_result(
            _REFUSALS[-1],
            stdout=_claude_result_event(
                _REFUSALS[-1], **{_agent_cases._IS_ERROR_FIELD: False},
            ),
        )
        self.assertFalse(_provider_failures.is_provider_refusal(quoted))

    def test_a_flagged_refusal_counts(self) -> None:
        refusal = "API Error: 401 Unauthorized"
        flagged = _agent_result(
            refusal,
            stdout=_claude_result_event(
                refusal, **{_agent_cases._IS_ERROR_FIELD: True},
            ),
        )
        self.assertTrue(_provider_failures.is_provider_refusal(flagged))
        self.assertFalse(_provider_failures.is_transient_provider_failure(flagged))
