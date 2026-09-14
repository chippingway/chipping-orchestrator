# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The stderr an agent run leaves behind when it leaves no usable message.

One behavior carries the weight here: the redactor runs over the raw stderr
before either budget trims it, so a secret straddling the cut cannot survive
as a fragment the redactor no longer recognizes -- in the park comment a human
reads, or in the shorter tail a WARNING line carries.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine import agent_diagnostics

_AGENT_SESSION_ID = "s"
_REDACTION_MARKER = "***"


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


if __name__ == "__main__":
    unittest.main()
