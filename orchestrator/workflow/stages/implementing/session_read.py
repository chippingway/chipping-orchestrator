# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the pinned state says about the dev session, and what a run's text says
about its health.

`_read_dev_session` is the read every spawn and resume starts from: it returns
the full configured agent command string as the durable role identity, so a
`DEV_AGENT` flip between ticks cannot retarget an in-flight issue at a backend
that never ran on it. `_pinned_session_id` reads the pinned conversation off
the comment whatever command that read resolves, for the retirement guard that
must name every pin it clears. The three classifiers beside them read the other
direction -- the CLI's own words -- and each answers exactly one recovery
question: was the session GC'd, did its transcript outgrow the context window,
is the account out of quota. The last is asked of both places a quota stop
arrives: the final message a Claude notice takes, and the failure record a
backend that keeps one classified its failure channels into. They sit with the reads because all are
about the same session and none of them may act: each returns a verdict its
caller disposes.

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
    after a `DEV_AGENT` env flip between ticks. A plain `"codex"` or
    `"claude"` is a current spec like any other: it re-parses to
    `(backend, ())`, and persisting it again is a no-op rewrite.

    Only `dev_agent` and `dev_session_id` are read. When no `dev_agent`
    is pinned -- the issue has never been spawned, or a late restart
    dropped the pin with its cycle -- this returns the current config's
    `(DEV_AGENT_SPEC, DEV_AGENT, DEV_AGENT_ARGS, None)` for the imminent
    fresh spawn to use AND persist, whatever else the comment carries.
    """
    stored = state.get(_state._DEV_AGENT)
    if stored:
        return _stored_dev_session(state, stored)
    return (
        config.DEV_AGENT_SPEC,
        config.DEV_AGENT,
        config.DEV_AGENT_ARGS,
        None,
    )


def _pinned_session_id(state: PinnedState) -> str | None:
    """The conversation id `dev_session_id` holds, whether or not `_read_dev_session` resolves it.

    That read resolves the pin only under a pinned `dev_agent`, so a pin
    standing without one would be hidden from it while still on the comment;
    the retirement guard reads the field itself, so no pin it clears goes
    unnamed.
    """
    pinned = state.get(_state._DEV_SESSION_ID)
    return str(pinned) if pinned else None


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


def _is_session_limit(agent_result: AgentResult) -> bool:
    """True iff the run stopped on an exhausted account quota.

    Two channels carry that stop. A backend that keeps a failure record names
    it there (`terminal_failure.quota_exhausted`): Antigravity's arrives on
    its terminal error and stderr diagnostics with the final message left
    empty, so no reading of `last_message` could find it, and the record is
    trusted whatever the run left beside it -- an unfinished tool step
    included. Otherwise the stop is a Claude session/usage/weekly-quota notice
    ("You've hit your session limit ...", "You've hit your weekly limit ...")
    returned as the final message, matched as a PREFIX of the normalized
    message so a dev reply that merely mentions a limit mid-answer is not
    caught -- backend-agnostic on purpose, since the phrasings are distinctive
    enough that a non-Claude backend echoing them would still be a quota stop.

    Neither is a real agent question: the only recovery is to wait for the
    reset and retry, however far away that reset is.
    """
    failure = agent_result.terminal_failure
    if failure is not None and failure.quota_exhausted:
        return True
    msg = (agent_result.last_message or "").strip().lower().replace("’", "'")
    return any(
        msg.startswith(marker) for marker in _state._CLAUDE_SESSION_LIMIT_MESSAGE_MARKERS
    )
