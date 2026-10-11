# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
r"""What a park comment and a log line say about an agent run that produced no
usable message: its stderr and the exit code beside it, the reset interval
above them where an account quota stopped it, or the provider's own words
where a Codex usage limit did.

Two budgets over one tail, because the two readers are different -- a park
comment quotes 1KB for a human who came to the issue to find out what broke,
and a WARNING quotes 400 characters so the line still fits a screen. Both run
the shared redactor over the RAW stderr before trimming to either budget: a
secret straddling the cut would otherwise be sliced into a fragment the
redactor no longer recognizes, and the fragment is the part that leaks. The
same ordering is why the redaction precedes `rstrip` -- a multi-line env value
ending in `\n` (an SSH or PEM key) would no longer match its environment value
verbatim once the trailing newline is eaten.

A usage-limit stop is quoted the same way and in the same order. Its text is
the provider's verbatim (`provider_failures.CodexUsageLimitFailure`), so it is
redacted whole before it is cut to a budget of its own, and the reset the
notice names is read off that redacted text rather than the raw one.

Where a backend kept a failure record (`AgentResult.terminal_failure`), the
exit code beside the stderr is told apart: the subprocess's own return, and
the failure code the orchestrator normalized the run to. A result without that
record carries the one code, which keeps its plain label rather than being
called the process's return. An account-quota stop that record names is quoted
through the same stderr block, under the reset interval the record kept.

The comment block renders through `messages._as_blockquote`, the one quoting
form every agent output an issue carries is rendered with, so a diagnostic
block reads the same as the last-message body it is appended under.
"""
from __future__ import annotations

from orchestrator.agents import provider_failures as _provider_failures
from orchestrator.agents.models import AgentResult
from orchestrator.config import credentials as _credentials
from orchestrator.workflow.engine import messages as _messages

_STDERR_TAIL_BUDGET = 1024

# The provider's message a usage-limit park quotes, and the reset a quota
# park names -- a Codex date or an Antigravity interval. The provider writes a
# sentence or two and a date, so these bound a stream nobody expected rather
# than the message it ordinarily sends.
_PROVIDER_MESSAGE_BUDGET = 1024
_RESET_BUDGET = 120


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
    return f"\n\n_{label} stderr (last 1KB):_\n\n{quoted}\n\n{_exit_code_line(agent_result, label)}"


def _exit_code_line(agent_result: AgentResult, label: str) -> str:
    """The exit code a park comment names, both of them where the failure record kept the process's own.

    A result without that record carries one code, which may itself be a
    normalized one, so it keeps the plain label rather than claiming to be
    what the subprocess returned. A record whose run the timeout killed holds
    no captured return, since the runner reports a sentinel for a process it
    killed, and the line says so rather than presenting the sentinel as one.
    """
    failure = agent_result.terminal_failure
    if failure is None:
        return f"_{label} exit code:_ {agent_result.exit_code}"
    captured = failure.process_exit_code
    if captured is None:
        captured = "not captured (the run timed out and was killed)"
    return (
        f"_{label} subprocess exit code:_ {captured} · "
        f"_orchestrator's normalized failure code:_ {agent_result.exit_code}"
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


def _bounded(text: str, budget: int) -> str:
    """`text` cut to its first `budget` characters, the cut marked."""
    if len(text) <= budget:
        return text
    kept = text[:budget]
    return f"{kept}…"


def _format_usage_limit_diagnostics(
    stopped: _provider_failures.CodexUsageLimitFailure,
) -> str:
    """Render a Codex usage-limit stop's reset and provider message for a park comment.

    Returns a block beginning with two newlines, as the stderr block does: the
    reset the provider named, or that it named none, then its message quoted.
    The redactor runs over the whole message before either budget cuts it or
    the reset is read off it, so neither the quote nor the line naming the
    reset can carry a secret the provider's text echoed. The reset is kept as
    the provider phrased it, in the local time of the host the CLI ran on.
    """
    message = _credentials.redact_secrets(stopped.message).strip()
    reset_time = _provider_failures.CodexUsageLimitFailure(message).reset_time
    reset_line = "Codex named no reset time."
    if reset_time:
        shown_reset = _bounded(reset_time, _RESET_BUDGET)
        reset_line = f"Codex names the reset as {shown_reset} (the orchestrator host's local time)."
    quoted = _messages._as_blockquote(
        _bounded(message, _PROVIDER_MESSAGE_BUDGET) or "(Codex sent no message)",
    )
    return f"\n\n{reset_line}\n\n_Codex usage-limit message:_\n\n{quoted}"


def _format_quota_diagnostics(agent_result: AgentResult) -> str:
    """Render an account-quota stop's reset interval and failure diagnostics for a park comment.

    Returns a block beginning with two newlines, as the stderr block does: the
    reset interval the failure record kept, or that the failure named none,
    then the stderr block, whose redacted tail carries the CLI's diagnostic
    lines and the terminal error and whose exit-code line tells the
    subprocess's return apart from the normalized one. The interval is the
    CLI's countdown from when the run stopped, not from when the comment is
    read, so the line says which.
    """
    failure = agent_result.terminal_failure
    reset = None if failure is None else failure.quota_reset
    reset_line = "The failure named no reset interval."
    if reset:
        reset_line = f"The quota resets in {_bounded(reset, _RESET_BUDGET)}, counted from when the run stopped."
    return f"\n\n{reset_line}{_format_stderr_diagnostics(agent_result)}"
