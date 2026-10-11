# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The stderr an agent run leaves behind when it leaves no usable message, the
reset interval an account-quota stop's failure record kept, and the provider's
words where a Codex usage limit stopped it.

One behavior carries the weight here: the redactor runs over the raw text
before any budget trims it, so a secret straddling the cut cannot survive as a
fragment the redactor no longer recognizes -- in the park comment a human
reads, or in the shorter tail a WARNING line carries. Beside it, the exit code
a park names is the subprocess's own only where a failure record kept it.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from orchestrator.agents.models import AgentResult, TerminalFailure
from orchestrator.agents.provider_failures import CodexUsageLimitFailure
from orchestrator.workflow.engine import agent_diagnostics

_AGENT_SESSION_ID = "s"
_REDACTION_MARKER = "***"
_LIMIT_OPENING = "You've hit your usage limit."
_RESET = "Oct 17th, 2026 1:36 AM"
_NAMED_RESET = "Codex names the reset as"
_NO_RESET = "Codex named no reset time."
_CUT_MARKER = "…"
_QUOTE_PREFIX = "> "
_QUOTE_LENGTH = len(_QUOTE_PREFIX) + agent_diagnostics._PROVIDER_MESSAGE_BUDGET + len(_CUT_MARKER)
# Fills a provider message so the secret written after it straddles the cut.
_PADDING_LENGTH = agent_diagnostics._PROVIDER_MESSAGE_BUDGET - len(_LIMIT_OPENING) - 8
_PADDING = "X" * _PADDING_LENGTH
_RESET_SECRET = "sk-ant-resettimesecretvalue"
_LONG_RESET = "Y" * (agent_diagnostics._RESET_BUDGET + 5)
_SHOWN_LONG_RESET = _LONG_RESET[:agent_diagnostics._RESET_BUDGET]
_QUOTA_STDERR = "error: Individual quota reached. Resets in 2h42m39s."
_QUOTA_SECRET = "sk-ant-quotastderrsecretvalue"
_COUNTED = ", counted from when the run stopped."

# `(reset interval the failure record kept, the line the quota block opens
# with)`: the interval as AGY phrased it, cut to its budget, or none.
_QUOTA_RESET_LINES = (
    ("2h42m39s", f"The quota resets in 2h42m39s{_COUNTED}"),
    (_LONG_RESET, f"The quota resets in {_SHOWN_LONG_RESET}{_CUT_MARKER}{_COUNTED}"),
    (None, "The failure named no reset interval."),
)

# `(provider message, what the reset line says)`: the reset as the provider
# phrased it, redacted where it echoed a secret, cut to its own budget, or none
# where the provider named none.
_RESET_LINES = (
    (f"{_LIMIT_OPENING} Try again at {_RESET}.", f"{_NAMED_RESET} {_RESET} "),
    (f"{_LIMIT_OPENING} Try again at {_RESET_SECRET}.", f"{_NAMED_RESET} {_REDACTION_MARKER} "),
    (f"{_LIMIT_OPENING} Try again at {_LONG_RESET}.", f"{_NAMED_RESET} {_SHOWN_LONG_RESET}{_CUT_MARKER} "),
    (_LIMIT_OPENING, _NO_RESET),
    ("", _NO_RESET),
)


def _usage_limit_block(message: str, **secrets: str) -> str:
    """The usage-limit block for the provider's `message`, `secrets` set in the environment."""
    with patch.dict(os.environ, secrets, clear=False):
        return agent_diagnostics._format_usage_limit_diagnostics(CodexUsageLimitFailure(message))


def _agent_result(stderr: str, terminal_failure: TerminalFailure | None = None) -> AgentResult:
    return AgentResult(
        session_id=_AGENT_SESSION_ID, last_message="", exit_code=1,
        timed_out=False, stdout="", stderr=stderr, terminal_failure=terminal_failure,
    )


class DiagnosticsRedactionTest(unittest.TestCase):
    """Agent stderr is redacted before it is trimmed for a park comment or
    a log line, so a secret cannot survive as a partial value on either
    side of the cut.
    """

    def test_diagnostics_redact_before_truncation(self) -> None:
        # Park comments cap the surfaced tail at 1KB. If we redacted after
        # slicing, a key that spans the cut would survive in the visible
        # tail. Pad noise so the secret would otherwise straddle the cap.
        secret = "sk-ant-spanningthecutboundary123"
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": secret}, clear=False):
            padding = "X" * (agent_diagnostics._STDERR_TAIL_BUDGET - 8)
            block = agent_diagnostics._format_stderr_diagnostics(
                _agent_result(f"{padding}{secret} trailing"), "Agent",
            )
        self.assertNotIn(secret, block)
        self.assertIn(_REDACTION_MARKER, block)
        # The tail budget is still honored on the *redacted* string.
        self.assertIn("trailing", block)

    def test_log_tail_redacts(self) -> None:
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "sk-proj-loglinevaluexyz"}, clear=False,
        ):
            tail = agent_diagnostics._stderr_log_tail(
                _agent_result("auth failed for sk-proj-loglinevaluexyz"),
            )
        self.assertNotIn("sk-proj-loglinevaluexyz", tail)

    def test_diagnostics_redact_multiline_eof_secret(self) -> None:
        # A multi-line secret whose env value itself ends in `\n` (e.g. a
        # PEM/SSH key) echoed at the end of stderr. If rstrip ran first,
        # the trailing newline would be eaten and `str.replace(value,
        # "***")` would no longer match the env value verbatim, leaking
        # the secret into the park comment.
        secret = "-----BEGIN PRIVATE KEY-----\nAAAABBBBCCCCDDDD\n-----END PRIVATE KEY-----\n"
        with patch.dict(os.environ, {"SSH_PRIVATE_KEY": secret}, clear=False):
            block = agent_diagnostics._format_stderr_diagnostics(
                _agent_result(f"boom: {secret}"), "Agent",
            )
        self.assertNotIn("AAAABBBBCCCCDDDD", block)
        self.assertIn(_REDACTION_MARKER, block)

    def test_log_tail_redacts_multiline_secret_at_eof(self) -> None:
        secret = "line1-of-secret-value\nline2-of-secret-value\n"
        with patch.dict(os.environ, {"API_TOKEN": secret}, clear=False):
            tail = agent_diagnostics._stderr_log_tail(_agent_result(f"leaked: {secret}"))
        self.assertNotIn("line2-of-secret-value", tail)


class UsageLimitDiagnosticsTest(unittest.TestCase):
    """A usage-limit stop's provider message is redacted whole, then bounded,
    and the reset the block names is read off the redacted text.
    """

    def test_message_redacted_before_its_budget(self) -> None:
        # The secret straddles the cut and the reset sits past it: the quote
        # stops at the budget with no fragment of either, and the reset is
        # still named.
        secret = "sk-proj-spanningthelimitcut123"
        block = _usage_limit_block(
            f"{_LIMIT_OPENING}{_PADDING}{secret} Try again at {_RESET}.", OPENAI_API_KEY=secret,
        )
        self.assertNotIn("sk-proj", block)
        self.assertIn(f"{_NAMED_RESET} {_RESET} ", block)
        quote = block.rsplit("\n\n", 1)[1]
        self.assertTrue(quote.startswith(f"{_QUOTE_PREFIX}{_LIMIT_OPENING}"))
        self.assertTrue(quote.endswith(_CUT_MARKER))
        self.assertEqual(len(quote), _QUOTE_LENGTH)

    def test_reset_line(self) -> None:
        for message, reset_line in _RESET_LINES:
            with self.subTest(message=message):
                block = _usage_limit_block(message, ANTHROPIC_API_KEY=_RESET_SECRET)
                self.assertIn(reset_line, block)
                self.assertNotIn(_RESET_SECRET, block)
        self.assertTrue(block.endswith(f"{_QUOTE_PREFIX}(Codex sent no message)"))



class QuotaDiagnosticsTest(unittest.TestCase):
    """An account-quota stop's block names the reset interval its failure
    record kept above the redacted stderr, and the exit-code line tells the
    subprocess's own return apart from the normalized one only where that
    record kept it.
    """

    def test_reset_line_above_the_redacted_stderr(self) -> None:
        for reset, reset_line in _QUOTA_RESET_LINES:
            with self.subTest(reset=reset):
                failure = TerminalFailure(0, quota_exhausted=True, quota_reset=reset)
                with patch.dict(os.environ, {"ANTHROPIC_API_KEY": _QUOTA_SECRET}, clear=False):
                    block = agent_diagnostics._format_quota_diagnostics(
                        _agent_result(f"{_QUOTA_STDERR}\nkey {_QUOTA_SECRET}", failure),
                    )
                self.assertTrue(block.startswith(
                    f"\n\n{reset_line}\n\n_Agent stderr (last 1KB):_\n\n{_QUOTE_PREFIX}{_QUOTA_STDERR}\n",
                ))
                self.assertNotIn(_QUOTA_SECRET, block)
                self.assertTrue(block.endswith(
                    "_Agent subprocess exit code:_ 0 · _orchestrator's normalized failure code:_ 1",
                ))

    def test_recordless_result_keeps_plain_exit_code(self) -> None:
        block = agent_diagnostics._format_stderr_diagnostics(_agent_result("boom"))
        self.assertTrue(block.endswith("_Agent exit code:_ 1"))
        self.assertNotIn("subprocess", block)

    def test_timed_out_record_has_no_captured_code(self) -> None:
        # The runner reports `-1` for a process its timeout killed, so a
        # record holding no captured return says so beside the normalized
        # code rather than presenting the sentinel as what the CLI exited with.
        block = agent_diagnostics._format_stderr_diagnostics(
            _agent_result(_QUOTA_STDERR, TerminalFailure(None, quota_exhausted=True)),
        )
        self.assertTrue(block.endswith(
            "_Agent subprocess exit code:_ not captured (the run timed out and was killed) · "
            "_orchestrator's normalized failure code:_ 1",
        ))


if __name__ == "__main__":
    unittest.main()
