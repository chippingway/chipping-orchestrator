# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Detect requirement changes and route the workflow against the new baseline.

The content_hash owner defines which text is human guidance. This owner persists
the first or normalized baseline, resumes implementation with the changed text,
and clears split claims before routing pre-implementation drift to decomposition.

What a resume consumes is decided by one frozen read, which `drift_delivery.py`
beside this owner freezes with the prompt built from it -- on an open pull
request as much as before one, over that road's second surface as well. No road
here reads a thread's TIP: a tip crosses the context a bounded excerpt dropped,
a reply written while the agent was out, and a run no developer ever read the
prompt through. A reroute that invokes nobody at all -- the `documenting`
unwind -- records the requirements revision for itself and nothing about the
conversation, since a label change delivers no words."""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    messages as _messages,
    prompt_notes as _prompt_notes,
)
from orchestrator.workflow.state import WorkflowLabel

_USER_CONTENT_HASH = "user_content_hash"


def _detect_user_content_change(
    gh: GitHubClient, issue: Issue, state: PinnedState, *, answered=None,
) -> str | None:
    """Return the new hash if the user-visible content drifted since the
    prior stored value, or None when unchanged.

    On the FIRST call for an issue (no prior hash in pinned state), persist
    the current value via `gh.write_pinned_state` immediately. Doing it
    in-memory only would lose the baseline whenever the calling handler's
    early-return path (awaiting-human-with-no-new-comments, debounce,
    child-waiting-on-deps, …) skips its own state write; the very next
    edit would then be classified as the new baseline and silently
    absorbed. The cost is one extra write per legacy issue still missing
    the field on first encounter; in steady state the hash is already set
    and this branch never fires.

    Legacy-hash normalization: an issue whose baseline was written by the
    pre-issue-#729 algorithm (which counted a bare `/orchestrator continue`
    comment) compares unequal to the new `current` even when the requirements
    did not change. Before reporting drift, recompute with the OLD algorithm
    (`include_bare_continue=True`); if that reproduces the stored baseline the
    delta is purely the algorithm change, so persist the new baseline and report
    no drift. This keeps a bare continue outstanding at deploy time from firing
    one false "issue body/content changed" route.

    `answered` is what a park waiting on a human had already read -- the
    frozen comments at or below its watermark. Replies past that watermark
    are answers to the park, and the frozen reply batch is what delivers,
    filters, and settles them; counted as an edit here they would take the
    drift road instead, which quotes them inside a conversation excerpt of
    its own and settles them under a record the park's own resume never made
    -- the command the batch reserves and the marker it refuses included. So
    on a parked tick only a change the replies do not explain -- the title,
    the body, a comment the park had already read -- is drift.
    """
    orchestrator_ids = _comments._orchestrator_ids(state)
    current = _content_hash._compute_user_content_hash(issue, orchestrator_ids)
    prior = state.get(_USER_CONTENT_HASH)
    if not isinstance(prior, str):
        state.set(_USER_CONTENT_HASH, current)
        gh.write_pinned_state(issue, state)
        return None
    if current == prior:
        return None
    legacy = _content_hash._compute_user_content_hash(
        issue, orchestrator_ids, include_bare_continue=True,
    )
    if legacy == prior:
        state.set(_USER_CONTENT_HASH, current)
        gh.write_pinned_state(issue, state)
        return None
    if answered is not None and prior in {
        _content_hash._compute_user_content_hash(
            issue, orchestrator_ids, include_bare_continue=legacy_mode, comments=answered,
        )
        for legacy_mode in (False, True)
    }:
        return None
    return current


def _build_user_content_change_prompt(
    issue: Issue, comments_text: str,
) -> str:
    """Resume prompt that quotes the updated title, body, AND the current
    conversation so the dev session can re-evaluate against the new
    requirements.

    Used by handlers that detect a user content drift mid-implementation:
    the dev session is locked to whichever backend wrote `dev_session_id`,
    so we cannot re-decompose, but we CAN feed the new context to the
    existing session and let it commit any additional work. Including the
    comments thread matters because the hash also drifts when the human
    adds acceptance criteria as a NEW comment (not just a body edit), and
    quoting only title/body would leave the dev unaware of the new comment
    it's supposed to react to.
    """
    title = (issue.title or "").strip() or f"#{issue.number}"
    body = (issue.body or "").strip() or "(no body)"
    quoted = _messages._as_blockquote(body)
    convo = comments_text or "(no prior comments)"
    return (
        "The human edited the issue while you were working on it. Re-read the "
        "updated title, body, and conversation below, decide whether your "
        "existing work still satisfies the new requirements, and COMMIT any "
        "additional changes needed in your current worktree. Do NOT push -- "
        "the orchestrator pushes and re-runs the reviewer.\n\n"
        f"Updated issue title: {title!r}\n\n"
        f"Updated issue body:\n\n{quoted}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{_prompt_notes._COMMIT_STYLE_NOTE}\n\n"
        f"{_prompt_notes._DEVELOPER_REPORT_NOTE}\n\n"
        "If you committed a change, or your report has to change to answer "
        "the edit, end with a report outcome. If instead your existing commits "
        "already satisfy the new requirements, no further code change is "
        "needed, and nothing your report says has to change, end your final "
        "message with EXACTLY this marker, alone on its own line:\n\n"
        "  ACK: <one-line justification>\n\n"
        "Use `ACK:` ONLY when you are certain the existing work covers the "
        "edit -- the orchestrator treats it as an explicit acknowledgement "
        "and stays on the current label without parking -- and never in the "
        "same message as a report outcome. If you have a "
        "clarification question or are unsure, do NOT use `ACK:`; reply "
        "with the question and the orchestrator will park awaiting a human "
        "reply (same as a regular agent question).\n\n"
        f"{_prompt_notes._FOREGROUND_ONLY_NOTE}"
    )


def _drift_to_decomposing_notice(orphan_children: list) -> str:
    """Build the reroute notice, including any orphaned child numbers."""
    if not orphan_children:
        return (
            ":pencil2: issue content changed; re-running decomposer "
            "against the updated body."
        )
    orphan_list = ", ".join(
        f"#{child_number}" for child_number in orphan_children
    )
    return (
        ":pencil2: issue content changed; re-running decomposer "
        "against the updated body. The previously-tracked children "
        f"({orphan_list}) will be ORPHANED -- the orchestrator no "
        "longer tracks them; please close any that no longer apply to "
        "the updated requirements."
    )


def _reset_decomposition_for_drift(
    state: PinnedState, new_hash: str,
) -> None:
    """Clear manifest/session state while retaining the locked agent spec."""
    state.set(_USER_CONTENT_HASH, new_hash)
    # A fresh decomposer session must keep the pinned backend so an agent-spec
    # configuration change cannot retarget an issue already in flight.
    state.set("decomposer_session_id", None)
    _clear_drift_manifest(state)


def _clear_drift_manifest(state: PinnedState) -> None:
    """Empty manifest tracking, so half-finished decomposition recovery reads
    the intentional reroute as one rather than as a crashed split.

    The seal that calls a child register FINAL goes with the count it is a
    fact about: a manifest being thrown away takes every claim about what it
    made with it, and one left behind would let a later split short of its
    own count read as complete.
    """
    state.set("children", [])
    state.set("dep_graph", {})
    state.set("expected_children_count", None)
    state.set("split_ledger_sealed", None)
    state.set("umbrella", None)
    state.set("awaiting_human", False)
    state.set("park_reason", None)


def _route_drift_to_decomposing(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    new_hash: str,
    orphan_children: list,
) -> None:
    """Route an issue back to `decomposing` after a pre-implementation
    user-content drift, clearing the locked decomposer session and any
    in-flight manifest state so the next tick spawns a fresh decomposer
    against the updated body.

    `orphan_children` is the parent's previously-tracked children list
    (empty for `ready` / blocked-child cases): existing children are NOT
    closed on GitHub by this helper, but their record is dropped from the
    parent's pinned state so the new manifest does not collide with them.
    The notice posted on the issue lists the orphan numbers explicitly so
    the operator can close any that no longer apply.

    Caller writes pinned state (`gh.write_pinned_state`) after returning.
    """
    notice = _drift_to_decomposing_notice(orphan_children)
    _comments._post_issue_comment(gh, issue, state, notice)
    _reset_decomposition_for_drift(state, new_hash)
    gh.set_workflow_label(issue, WorkflowLabel.DECOMPOSING)
