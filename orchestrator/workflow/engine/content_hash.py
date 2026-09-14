# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Stable requirement fingerprints over issue text and human-authored comments.

Pinned records, orchestrator output, bots, untrusted authors, and whole-comment
operator commands are excluded before hashing. The legacy bare-continue mode
lets the drift owner recognize a baseline without inventing a requirements edit."""
from __future__ import annotations

import hashlib

from github.Issue import Issue
from github.IssueComment import IssueComment

from orchestrator.github.comments import is_trusted_author
from orchestrator.github.pinned_state import PINNED_STATE_MARKER
from orchestrator.workflow.engine import (
    comments as _comments,
    messages as _messages,
    run_grant_request as _run_grant_request,
)


def _is_hidden_comment(
    issue_comment: IssueComment, orchestrator_ids: set[int],
) -> bool:
    """True for comments that never count as user-authored requirements:
    orchestrator markers, orchestrator-authored IDs, bots, and untrusted
    authors."""
    body = issue_comment.body or ""
    if PINNED_STATE_MARKER in body or _comments._ORCH_COMMENT_MARKER in body:
        return True
    comment_id = getattr(issue_comment, "id", None)
    if comment_id is not None and int(comment_id) in orchestrator_ids:
        return True
    user = getattr(issue_comment, "user", None)
    if user is not None and getattr(user, "type", None) == "Bot":
        return True
    return not is_trusted_author(user)


def _is_operator_control(issue_comment: IssueComment) -> bool:
    """Whether this whole comment is a command rather than requirements text.

    Asked in both hashing modes, unlike the bare continue below it. Each of
    these commands postdates the legacy algorithm the flag reproduces, so a
    thread carrying one was never hashed with it either way -- and a baseline
    recomputed WITH it would fail to recognize itself and report an operator's
    control as the edit it is not.

    The reason they are filtered at all is the same for both, and sharpest for
    the authorization: the tick that reads one answers it and then hands the
    SAME issue on -- to the stage below on a grant, and to the stage an
    authorized publication continues at on the other -- so a hash counting it
    would meet that handler as a body edit that never happened, resuming a
    developer where a reviewer was owed a round or over the very commit an
    operator just authorized.

    Bare is the whole test. A comment carrying a command ALONGSIDE guidance is
    guidance: it moves the hash, and the drift road that opens is how those
    words reach the agent that has to act on them.
    """
    if _run_grant_request._is_bare_command(issue_comment):
        return True
    return _messages._authorized_oversized_candidate(issue_comment) is not None


def _comment_body_for_hash(
    issue_comment: IssueComment,
    orchestrator_ids: set[int],
    *,
    include_bare_continue: bool,
) -> str | None:
    """Return user-authored requirements text, or None for filtered content."""
    if _is_hidden_comment(issue_comment, orchestrator_ids):
        return None
    body = issue_comment.body or ""
    if _is_operator_control(issue_comment):
        return None
    if include_bare_continue:
        return body
    if _messages._is_bare_orchestrator_continue(issue_comment):
        return None
    return body


def _compute_user_content_hash(
    issue: Issue, orchestrator_ids: set[int],
    *, include_bare_continue: bool = False,
) -> str:
    """SHA-256 over title + body + human-authored comments.

    Used by `_detect_user_content_change` so the orchestrator can react
    when a human edits the issue body or adds acceptance criteria after
    the workflow has already picked it up.

    `include_bare_continue=True` reproduces persisted baselines that counted
    bare `/orchestrator continue` commands as human content.
    `_detect_user_content_change` uses that reading to normalize a baseline
    without reporting drift caused solely by excluding a retry command.
    The default excludes those commands.

    Non-human content is filtered eight ways:

    * pinned-state comment by `PINNED_STATE_MARKER`;
    * orchestrator-posted comments by `_ORCH_COMMENT_MARKER` embedded in
      the body (id-cap-resistant -- the marker stays on the GitHub side
      forever even after the comment's id has been evicted from
      `orchestrator_comment_ids`);
    * legacy orchestrator comments (posted before the marker was
      introduced) by id from `orchestrator_comment_ids`;
    * third-party Bot / App accounts (Dependabot, Renovate, CI bots, ...)
      by GitHub's `user.type == "Bot"` flag. These accounts cannot be
      filtered by the id-list or marker because we never post them, and
      they post structurally (e.g. weekly Dependabot bumps) which would
      otherwise re-trigger drift detection on every tick they post.
    * untrusted authors by `is_trusted_author` when `ALLOWED_ISSUE_AUTHORS`
      is set. This keeps an outsider's comment from shifting the hash and
      re-triggering drift (and the re-decompose / dev-resume it drives) on
      a public repo. With no allowlist configured everyone is trusted, so
      the default deployment's hash is unchanged.
    * a bare `/orchestrator continue` operator command by
      `_is_bare_orchestrator_continue`. The command is an operator control,
      not requirements content: counting it would shift the hash and route
      the nudge through generic "issue body/content changed" drift handling
      instead of the stage's intentional session-limit retry (issue #729).
      A comment carrying the command ALONGSIDE genuine guidance is NOT bare,
      so it still shifts the hash and drives the normal drift/resume path.
    * the two whole-comment operator commands -- `/orchestrator add-agent-runs
      N` and `/orchestrator authorize-oversized <commit>` -- by
      `_is_operator_control`, which says why both are filtered and why they
      are filtered in both hashing modes.

    The orchestrator's OWN comments are dropped by marker/id (above),
    never by login, so a PAT shared with a human reviewer's account does
    not swallow that reviewer's real comments as bot noise. The allowlist
    filter is a separate, opt-in login gate: an operator who enables it is
    expected to list the reviewer login they post under.
    """
    parts = [issue.title or "", issue.body or ""]
    for issue_comment in issue.get_comments():
        comment_body = _comment_body_for_hash(
            issue_comment,
            orchestrator_ids,
            include_bare_continue=include_bare_continue,
        )
        if comment_body is not None:
            parts.append(comment_body)
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
