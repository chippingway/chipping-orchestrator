# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The stderr an agent run leaves behind when it leaves no usable message, and
the provider's words where a Codex usage limit stopped it.

One behavior carries the weight here: the redactor runs over the raw text
before any budget trims it, so a secret straddling the cut cannot survive as a
fragment the redactor no longer recognizes -- in the park comment a human
reads, or in the shorter tail a WARNING line carries.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from orchestrator.agents.models import AgentResult
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


def _agent_result(stderr: str) -> AgentResult:
    return AgentResult(
        session_id=_AGENT_SESSION_ID, last_message="", exit_code=1,
        timed_out=False, stdout="", stderr=stderr,
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


if __name__ == "__main__":
    unittest.main()
