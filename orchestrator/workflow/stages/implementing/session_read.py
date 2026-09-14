# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the pinned state says about the dev session, and what a run's text says
about its health.

`_read_dev_session` is the read every spawn and resume starts from: it returns
the full configured agent command string as the durable role identity, so a
`DEV_AGENT` flip between ticks cannot retarget an in-flight issue at a backend
that never ran on it. The three classifiers beside it read the other direction
-- the CLI's own words -- and each answers exactly one recovery question: was
the session GC'd, did its transcript outgrow the context window, is the account
out of quota. They sit with the read because all four are about the same
session and none of them may act: each returns a verdict its caller disposes.

`_as_blockquote` is here because every one of those verdicts ends up quoted
back to a human in the comment the park posts.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.implementing import state as _state


def _as_blockquote(text: str) -> str:
    """Render `text` as a Markdown blockquote (each line prefixed with `> `)."""
    prefixed = text.replace("\n", "\n> ")
    return f"> {prefixed}"


def _stored_dev_session(state: PinnedState, stored) -> tuple:
    stored_spec = str(stored)
    backend, args = config._parse_agent_spec(_state._DEV_AGENT, stored_spec)
    session_id = state.get(_state._DEV_SESSION_ID)
    return (
        stored_spec,
        backend,
        args,
        None if session_id is None else str(session_id),
    )


def _read_dev_session(
    state: PinnedState,
) -> tuple[str, str, tuple[str, ...], str | None]:
    """Return (spec, backend, extra_args, dev_session_id) for an issue.

    `spec` is the full configured agent command string the next run
    will use -- callers persist it verbatim BEFORE invoking `run_agent`
    so the recorded role identity survives a spawn that returns no
    session id (CLI hiccup, missing output file, etc.). Without that,
    a fresh spawn that nevertheless commits would leave `dev_agent`
    unset and a later `DEV_AGENT` flip would silently retarget the next
    resume at a backend that never ran on this issue.

    The pinned `dev_agent` field stores that spec -- e.g. `"codex"`,
    `"claude"`, or `"codex -m gpt-5.5 -c 'model_reasoning_effort=\"xhigh\"'"`
    -- as the durable role identity. Re-parsing it here means in-flight
    resumes use the same backend AND args the fresh spawn used, even
    after a `DEV_AGENT` env flip between ticks.

    Backward compatibility:
      * Legacy bare-backend values (`"codex"` / `"claude"`) re-parse to
        `(backend, ())` -- no args -- which is what those deployments
        had at the time they were spawned. `spec` is the same bare
        string; persisting it again is a no-op rewrite.
      * Legacy `codex_session_id` (written before `dev_agent` existed)
        yields `spec="codex"`. A config flip to claude cannot strand
        that session -- it stays on codex with no args.
      * When the issue has never been spawned, returns the current
        config's `(DEV_AGENT_SPEC, DEV_AGENT, DEV_AGENT_ARGS, None)`
        for the imminent fresh spawn to use AND persist.
    """
    stored = state.get(_state._DEV_AGENT)
    if stored:
        return _stored_dev_session(state, stored)
    legacy = state.get(_state._CODEX_SESSION_ID)
    if legacy is not None:
        return "codex", "codex", (), str(legacy)
    return (
        config.DEV_AGENT_SPEC,
        config.DEV_AGENT,
        config.DEV_AGENT_ARGS,
        None,
    )


def _is_stale_session_failure(
    backend: str, agent_result: AgentResult,
) -> bool:
    """True iff `agent_result` is a deterministic stale-session failure.

    Only claude is matched today: codex's resume CLI does not expose a
    comparable stable stderr marker, so codex still relies on the silent-
    park-count fallback. If/when codex grows one, add it here.
    """
    if backend != "claude":
        return False
    stderr = (agent_result.stderr or "").lower()
    if not stderr:
        return False
    return any(marker in stderr for marker in _state._CLAUDE_STALE_SESSION_STDERR_MARKERS)


def _is_context_overflow_failure(
    backend: str, agent_result: AgentResult,
) -> bool:
    """True iff `agent_result` is a Claude context-overflow resume failure.

    Only claude is matched today: codex's resume CLI does not expose a
    comparable stable marker. The marker is checked as a PREFIX of the
    stripped, lowercased last agent message -- so an agent that merely
    mentions the phrase mid-answer is not misclassified -- and as a substring
    of stderr, where the CLI may print the same diagnostic when it produces
    no result event at all.
    """
    if backend != "claude":
        return False
    msg = (agent_result.last_message or "").strip().lower()
    if any(msg.startswith(marker) for marker in _state._CLAUDE_CONTEXT_OVERFLOW_MARKERS):
        return True
    stderr = (agent_result.stderr or "").lower()
    return any(marker in stderr for marker in _state._CLAUDE_CONTEXT_OVERFLOW_MARKERS)


def _is_session_limit_message(agent_result: AgentResult) -> bool:
    """True iff the result message is a Claude session/usage-quota notice.

    A non-empty quota notice ("You've hit your session limit ...") is not a
    real agent question: the session is healthy and the only recovery is to
    wait for the reset and retry. Matched as a PREFIX of the normalized last
    agent message so a dev reply that merely mentions a session limit
    mid-answer is not caught. Backend-agnostic on purpose -- the phrasings are
    distinctive enough that a non-Claude backend echoing them would still be a
    quota stop, and `_on_question` (the sole caller) has no backend in hand.
    """
    msg = (agent_result.last_message or "").strip().lower().replace("’", "'")
    return any(
        msg.startswith(marker) for marker in _state._CLAUDE_SESSION_LIMIT_MESSAGE_MARKERS
    )
