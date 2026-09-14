# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue and pull-request comments stamped and tracked as orchestrator output.

The hidden marker survives eviction from the bounded id ledger. Both identify
our comments without treating a shared token account as exclusively automated.
Callers persist the modified ledger; prompt_context owns trusted thread reads."""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState

_ORCH_COMMENT_ID_CAP = 500

_ORCH_COMMENT_MARKER = "<!--orchestrator-comment-->"


def _orchestrator_ids(state: PinnedState) -> set[int]:
    """Set of comment ids the orchestrator itself posted on this issue/PR.
    Used to filter the orchestrator's own messages out of "new feedback"
    scans without falling back to author-login matching -- a PAT shared
    with a human reviewer's GitHub account would otherwise have its real
    review comments swallowed as bot noise (and the PR pinged ready for
    human merge over them).
    """
    raw = state.get("orchestrator_comment_ids") or []
    return {int(comment_id) for comment_id in raw}


def _track_orchestrator_comment(state: PinnedState, comment_id: int) -> None:
    """Record that this orchestrator posted one comment, once.

    Idempotent, because the ledger is a SET of ids kept in a bounded list and
    a second entry for one comment buys nothing while costing a slot. Callers
    layer -- a road that posts through a wrapped client and then through
    `_post_issue_comment` records the same id twice -- so an id already here
    keeps the position it has: what the bound evicts is the oldest comment
    rather than the least recently re-recorded.
    """
    raw = state.get("orchestrator_comment_ids")
    ids = list(raw) if isinstance(raw, list) else []
    identified = int(comment_id)
    if identified in ids:
        return
    ids.append(identified)
    if len(ids) > _ORCH_COMMENT_ID_CAP:
        ids = ids[-_ORCH_COMMENT_ID_CAP:]
    state.set("orchestrator_comment_ids", ids)


def _with_orch_marker(body: str) -> str:
    """Append the hidden orchestrator-comment marker to `body` (idempotent).

    Every orchestrator-posted comment carries this marker so the
    user-content hash can identify bot comments even after their id has
    been evicted from the bounded `orchestrator_comment_ids` cap. The
    marker is an HTML comment, invisible in rendered Markdown.
    """
    if _ORCH_COMMENT_MARKER in body:
        return body
    return f"{body}\n\n{_ORCH_COMMENT_MARKER}"


def _post_issue_comment(
    gh: GitHubClient, issue: Issue, state: PinnedState, body: str,
):
    """Post an issue comment AND record its id in pinned state so future
    `_handle_in_review` ticks recognize it as orchestrator-authored even when
    the PAT login is shared with a human reviewer. Caller is still responsible
    for `gh.write_pinned_state` -- this only mutates the in-memory state.

    The body is augmented with `_ORCH_COMMENT_MARKER` so the user-content
    hash can identify bot comments by marker (id-cap-resistant) in
    addition to by id (works for tracked-and-not-yet-evicted comments).
    """
    issue_comment = gh.comment(issue, _with_orch_marker(body))
    cid = getattr(issue_comment, "id", None)
    if cid is not None:
        _track_orchestrator_comment(state, int(cid))
    return issue_comment


def _post_pr_comment(
    gh: GitHubClient, pr_number: int, state: PinnedState, body: str,
):
    """PR-conversation comment counterpart to `_post_issue_comment`. Both
    surfaces share the IssueComment id namespace, so a single id list covers
    them. Inline review comments and PR review summaries live in different id
    spaces but the orchestrator never posts to those, so they need no entry.

    The body is augmented with `_ORCH_COMMENT_MARKER` for the same reason
    as `_post_issue_comment`: the user-content hash needs to identify
    bot comments even after their id has been evicted from the bounded
    `orchestrator_comment_ids` cap. PR-conversation comments do not feed
    into `_compute_user_content_hash` directly (the hash reads
    `issue.get_comments()`, not the PR's), but marker symmetry across
    surfaces keeps the filter rules uniform and avoids accidental
    inconsistency when a future tweak does start reading PR comments.
    """
    pr_comment = gh.pr_comment(pr_number, _with_orch_marker(body))
    cid = getattr(pr_comment, "id", None)
    if cid is not None:
        _track_orchestrator_comment(state, int(cid))
    return pr_comment
