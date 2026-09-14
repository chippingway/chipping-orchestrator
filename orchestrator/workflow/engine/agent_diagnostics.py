# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
r"""What a park comment and a log line say about an agent run that produced no
usable message: its stderr and the exit code beside it.

Two budgets over one tail, because the two readers are different -- a park
comment quotes 1KB for a human who came to the issue to find out what broke,
and a WARNING quotes 400 characters so the line still fits a screen. Both run
the shared redactor over the RAW stderr before trimming to either budget: a
secret straddling the cut would otherwise be sliced into a fragment the
redactor no longer recognizes, and the fragment is the part that leaks. The
same ordering is why the redaction precedes `rstrip` -- a multi-line env value
ending in `\n` (an SSH or PEM key) would no longer match its environment value
verbatim once the trailing newline is eaten.

The comment block renders through `messages._as_blockquote`, the one quoting
form every agent output an issue carries is rendered with, so a diagnostic
block reads the same as the last-message body it is appended under.
"""
from __future__ import annotations

from orchestrator.agents.models import AgentResult
from orchestrator.config import credentials as _credentials
from orchestrator.workflow.engine import messages as _messages

_STDERR_TAIL_BUDGET = 1024


def _format_stderr_diagnostics(
    agent_result: AgentResult, label: str = "Agent",
) -> str:
    r"""Render a stderr/exit-code diagnostic block to append to a park comment.

    Returns "" when the agent produced no stderr -- callers can concatenate
    unconditionally without a trailing dead section. Otherwise returns a
    block beginning with two newlines so it slots cleanly after an existing
    `_Last … message:_` body.

    Redaction happens on the raw stderr before any trimming: a multi-line
    secret env value (e.g. an SSH/PEM key whose env-var value ends in `\\n`)
    echoed at the end of stderr would otherwise have its trailing newline
    stripped first, so `str.replace` would no longer find the env value
    verbatim and the secret would leak.
    """
    tail = _credentials.redact_secrets(agent_result.stderr or "").rstrip()
    if not tail:
        return ""
    if len(tail) > _STDERR_TAIL_BUDGET:
        tail = tail[-_STDERR_TAIL_BUDGET:]
    quoted = _messages._as_blockquote(tail)
    return (
        f"\n\n_{label} stderr (last 1KB):_\n\n{quoted}\n\n"
        f"_{label} exit code:_ {agent_result.exit_code}"
    )


def _stderr_log_tail(agent_result: AgentResult, max_chars: int = 400) -> str:
    r"""Short stderr tail for log lines -- tighter than the park-comment cap
    so a single WARNING fits on one screen.

    Redact before trimming for the same reason as `_format_stderr_diagnostics`:
    a multi-line secret value ending in `\\n` would not match `str.replace`
    if `rstrip` ate the trailing newline first.
    """
    tail = _credentials.redact_secrets(agent_result.stderr or "").rstrip()
    if len(tail) > max_chars:
        tail = tail[-max_chars:]
    return tail
