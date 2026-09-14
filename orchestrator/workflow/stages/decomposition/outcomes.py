# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Run settlement and manifest outcomes for a finished decomposer reply.

The pause and timeout settlement runs before the caller's worktree check.
It folds usage only for an uninterrupted run and leaves a live pause intact.
After the caller proves the read-only checkout, the reply reaches the
manifest dispositions below.

A reply either carries a usable manifest or it does not, and both halves of
that split are dispositions the issue leaves this tick on. `single` posts the
sizing rationale and the context the decomposer already gathered, then hands
the issue to `ready` -- the comment rather than a body edit, because rewriting
the body would move the user-content hash and re-decompose the issue on the
next tick. `split` creates the children and leaves the parent waiting on them.

Everything else parks awaiting a human, and the park distinguishes two cases
the parse cannot: a malformed manifest is the agent getting the contract wrong,
while no manifest at all is the agent asking a question -- or saying nothing,
which is a backend failure wearing a question's clothes. Only the silent case
carries stderr diagnostics, because an operator answering a real question does
not need to read subprocess noise to do it.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    agent_diagnostics as _agent_diagnostics,
    comments as _comments,
    guards as _guards,
    messages as _messages,
    prompts as _prompts,
    usage as _usage,
)
from orchestrator.workflow.stages.decomposition import (
    manifest as _manifest,
    split as _split,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _park_unparsed_manifest(
    gh: GitHubClient, issue: Issue, state: PinnedState,
    decomposer_result: AgentResult, error: str | None,
) -> None:
    """Park awaiting human when the decomposer produced no usable manifest.

    Either a malformed manifest (`error` set) OR no manifest at all
    (question / silence, `error` None). Both park; the resume on the next
    comment runs through the awaiting_human branch of `_handle_decomposing`.
    """
    last_msg = decomposer_result.last_message or ""
    if error is None:
        stripped = last_msg.strip()
        raw = stripped or "(decomposer produced no final message)"
        quoted = _messages._as_blockquote(raw)
        # Only attach stderr diagnostics on the silent path -- a
        # real content question from the decomposer doesn't need
        # the operator wading through subprocess noise.
        diag = (
            "" if stripped
            else _agent_diagnostics._format_stderr_diagnostics(
                decomposer_result, "Decomposer",
            )
        )
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} decomposer needs your input to "
            f"proceed:\n\n{quoted}{diag}",
            reason="decomposer_question" if stripped else "decomposer_silent",
        )
        if not stripped:
            log.warning(
                "issue=#%s decomposer produced no final message; "
                "exit_code=%d timed_out=%s stderr_tail=%r",
                issue.number,
                decomposer_result.exit_code,
                decomposer_result.timed_out,
                _agent_diagnostics._stderr_log_tail(decomposer_result),
            )
    else:
        quoted = _messages._as_blockquote(last_msg.strip())
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} decomposer manifest invalid "
            f"({error}); manual adjudication needed.\n\n"
            f"_Last decomposer message:_\n\n{quoted}",
            reason="decomposer_invalid_manifest",
        )
    gh.write_pinned_state(issue, state)


def _finalize_single_decision(
    gh: GitHubClient, issue: Issue, state: PinnedState, parsed: dict,
) -> None:
    """Finalize a `single` manifest: post the rationale and flip to `ready`.

    Surface the decomposer's rationale AND the context it already gathered
    (affected files, implementation notes) so the develop agent that picks
    this up in `implementing` starts from that groundwork instead of
    re-deriving it. The builder tolerates missing / malformed optional
    fields -- the single decision is already valid, so no cosmetic field
    should park it.
    """
    _comments._post_issue_comment(
        gh, issue, state,
        _prompts._build_single_decision_comment(parsed),
    )
    state.set("decomposed_at", _usage._now_iso())
    gh.set_workflow_label(issue, WorkflowLabel.READY)
    gh.write_pinned_state(issue, state)


def _dispatch_decomposer_manifest(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    decomposer_result: AgentResult,
) -> None:
    """Parse the decomposer's final message and route on the outcome.

    Parks awaiting human on an invalid / silent / question manifest,
    finalizes a `single` decision to `ready`, or creates the `split`
    children and finalizes the parent to `blocked` / `umbrella`.
    """
    last_msg = decomposer_result.last_message or ""
    parsed, error = _manifest._parse_manifest(last_msg)

    if parsed is None:
        _park_unparsed_manifest(gh, issue, state, decomposer_result, error)
        return

    if parsed["decision"] == "single":
        _finalize_single_decision(gh, issue, state, parsed)
        return

    # decision == "split".
    split_plan = _split._create_child_issues(
        gh,
        issue,
        state,
        parsed[_state._CHILDREN],
        bool(parsed.get(_state._UMBRELLA)),
    )
    if split_plan is None:
        return
    _split._finalize_split(gh, issue, state, split_plan)



def _settle_decomposer_run(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    decomposer_result: AgentResult,
) -> bool:
    """Fold this run's usage and park on a live pause or timeout.

    Returns True when the caller must return (paused or timed out), False
    to continue to the dirty-worktree check and manifest dispatch. None of
    these paths preserve the decompose worktree: the caller's `finally`
    tears it down on return. The read-only dirty/commits park (which DOES
    preserve the worktree) stays inline in `_handle_decomposing` so
    `keep_worktree` is set BEFORE the park's side effects run.
    """
    # Live pause: an operator applied `paused` / `backlog` while the
    # decomposer ran (fresh spawn or awaiting-human resume). Dispatch only
    # saw the pre-run labels, so re-check a freshly fetched issue and return
    # WITHOUT folding usage, parking on timeout, creating child issues,
    # relabeling, or writing pinned state -- durable GitHub state stays
    # exactly as the prior tick left it and the next tick re-runs the
    # decomposer once the label is removed. The read-only decompose worktree
    # is torn down by the caller's `finally` as on any normal exit and
    # recreated on the re-run.
    if _guards._paused_during_agent_run(gh, issue):
        return True

    state.set("last_agent_action_at", _usage._now_iso())
    # Fold this run's usage into the per-issue counters at the convergence
    # of the fresh-spawn and awaiting-human resume branches, so a real
    # resume exit is counted exactly once and the no-new-comment resume
    # (which returned above without running the agent) never touches the
    # counters. Interrupted runs are excluded entirely: the read-only
    # dirty/commits park below still writes pinned state (to preserve the
    # inspection worktree), so folding a killed run's usage first would
    # persist a counter the interrupted contract says must not accrue. The
    # clean-interrupted case is additionally short-circuited by the
    # `_ignore_if_interrupted` guard in `_handle_decomposing`.
    if not decomposer_result.interrupted:
        _usage._accumulate_issue_usage(state, decomposer_result.usage)

    if decomposer_result.timed_out:
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} decomposer timed out after "
            f"{config.AGENT_TIMEOUT}s, manual intervention needed.",
            reason="decomposer_timeout",
        )
        gh.write_pinned_state(issue, state)
        return True
    return False
