# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Every comment the orchestrator posts, and every comment it reads back.

The write side stamps ``_ORCH_COMMENT_MARKER`` onto each body and records the
returned id in pinned state, because recognizing the orchestrator's own
messages later needs both: the id list is exact but bounded by
``_ORCH_COMMENT_ID_CAP``, and the marker survives eviction from it. Neither can
be replaced by author-login matching -- a PAT shared with a human reviewer's
account would have that reviewer's real comments swallowed as bot noise.

The read side is the one choke point every conversation-carrying agent prompt
draws its thread text from, so the ``ALLOWED_ISSUE_AUTHORS`` trust filter is
applied here. An untrusted author's comment is dropped whole rather than
trimmed, which is what keeps an outsider on a public repo from steering a
coding agent through the issue thread. It has two spellings because a caller
that derives anything ELSE from the same thread -- a watermark over what its
prompt just quoted -- has to do both from one snapshot, and that caller passes
the comments rather than the issue. The same caller is why the per-comment
filter takes ids to retain past the allowlist: an orchestrator rebuilding a
conversation it is half of needs its own side of it, and a deployment that
lists its humans and not its bot account would otherwise hand a fresh agent
the answers without the questions. Only the recorded ids are admissible there
-- the marker above identifies the same comments to the scans that DROP them,
where a forged one costs its author their own comment rather than admitting it.

The tracked-repository awareness block sits beside the thread read because both
are bounded, non-secret context folded into the same agent prompts. So is the
paragraph break the thread read joins its quoted comments with: ``prompts.py``
assembles its own sections around that quote with the same break, and one
definition is what keeps the two reading as a single document.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models, settings as config
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import is_trusted_author
from orchestrator.github.pinned_state import PinnedState

_ORCH_COMMENT_ID_CAP = 500

_ORCH_COMMENT_MARKER = "<!--orchestrator-comment-->"

# The blank line between quoted comments is the paragraph break the prompt
# builders assemble their own sections with, so it keeps one definition.
_SECTION_SEP = "\n\n"

_TRACKED_REPOS_CAP = 20

# The default for every reader that has no recorded orchestrator ids to offer,
# which is every one but the conversation rebuild in the discussion stage.
_NO_RETAINED_IDS: frozenset = frozenset()


def _build_tracked_repos_context(
    current: _config_models.RepoSpec, specs: list[_config_models.RepoSpec]
) -> str:
    """Render the 'other tracked repos' awareness block, or '' when there is
    nothing useful to say.

    Returns '' when `EXPOSE_TRACKED_REPOS` is off or there is at most one
    tracked repo -- so the default single-repo deployment sees zero added
    tokens and zero behavior change. For a multi-repo deployment it lists each
    *other* repo (the `current` one is excluded from the list) on one line with
    its slug, durable `target_root` checkout, and base branch, capped at
    `_TRACKED_REPOS_CAP` with an `… and N more` overflow line.

    The framing is deliberately stage-neutral: it says only that the sibling
    checkouts are read-only references and says nothing about whether the agent
    may write in its own working directory -- that grant (or withholding) is
    owned by the surrounding stage prompt, not by this list. No secrets are
    disclosed: only operator-configured slugs, base branches, and paths the
    agent could already read; never tokens or remote URLs.
    """
    if not config.EXPOSE_TRACKED_REPOS or len(specs) <= 1:
        return ""
    others = [repo_spec for repo_spec in specs if repo_spec.slug != current.slug]
    if not others:
        return ""
    lines = [
        f"- {repo_spec.slug} — source at {repo_spec.target_root} "
        f"(base `{repo_spec.base_branch}`)"
        for repo_spec in others[:_TRACKED_REPOS_CAP]
    ]
    overflow = len(others) - _TRACKED_REPOS_CAP
    if overflow > 0:
        lines.append(f"- … and {overflow} more")
    listing = "\n".join(lines)
    return (
        "This orchestrator also tracks the repositories below. Their source is "
        "checked out locally for cross-repo reference only -- treat every path "
        "listed here as read-only and do NOT modify, commit, or push in any of "
        "them. (Whether you may write in your own working directory is governed "
        "by the rest of this prompt, not by this list.) Your task is on "
        f"`{current.slug}`.\n\n{listing}"
    )


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


def _quote_comment_line(comment: object, label: str = "") -> str:
    """Quote one already-selected comment as `@author[label]: body`.

    Shared by the resume/followup prompt builders and the stage handlers that
    fold fresh issue or PR comments into an agent prompt; `label` inserts a
    surface tag (e.g. ` (PR comment)`) after the author.
    """
    author = comment.user.login if comment.user else "user"
    body = comment.body or ""
    return f"@{author}{label}: {body}"


def _prompt_comment_chunk(
    issue_comment: object, retained_ids: frozenset = _NO_RETAINED_IDS,
) -> str | None:
    """Format one non-state issue comment for an agent prompt, or drop it.

    `retained_ids` are comment ids this orchestrator recorded at the moment it
    posted them, so a body they name is one it wrote itself and is kept
    whatever the allowlist says about the account the token belongs to. That
    matters for a prompt rebuilding a conversation the orchestrator is half of:
    with `ALLOWED_ISSUE_AUTHORS` set and the bot's own login absent from it --
    the shape a deployment lands on by writing down only its humans -- an
    agent would otherwise read the answers without the questions they answer.

    Recorded ids are the only admissible evidence here. The `_ORCH_COMMENT_MARKER`
    that identifies the same comments to the scans that DROP them is an HTML
    comment anyone can paste, which is harmless when it only silences the
    pasted comment and an allowlist bypass when it admits one.
    """
    body = getattr(issue_comment, "body", None) or ""
    if "<!--orchestrator-state" in body:
        return None
    user = getattr(issue_comment, "user", None)
    posted_here = getattr(issue_comment, "id", None) in retained_ids
    if not (posted_here or is_trusted_author(user)):
        return None
    login = user.login if user else "user"
    return f"@{login}: {body}"


def _thread_text(
    issue_comments,
    max_chars: int = 4000,
    *,
    retained_ids: frozenset = _NO_RETAINED_IDS,
) -> str:
    """Render an already-read list of comments as agent-prompt conversation.

    Taking the comments rather than the issue is what lets a caller build the
    text and whatever else it derives from the same thread out of ONE read: a
    stage that reads twice shows an agent a comment that landed between the
    two and then records a watermark below it, which on a stage that reads no
    comment twice means the agent is sent it again next tick.
    """
    chunks: list[str] = []
    for issue_comment in issue_comments:
        chunk = _prompt_comment_chunk(issue_comment, retained_ids)
        if chunk is not None:
            chunks.append(chunk)
    text = _SECTION_SEP.join(chunks)
    return text[-max_chars:] if len(text) > max_chars else text


def _recent_comments_text(issue: Issue, max_chars: int = 4000) -> str:
    """Conversation text fed to every agent prompt (implement, review,
    documentation, decompose, question, discussion, and the drift-resume
    prompt).

    An untrusted author's comment is dropped whole -- its body and any URLs
    it contains never reach the prompt -- so once `ALLOWED_ISSUE_AUTHORS`
    is set an outsider on a public repo cannot smuggle workflow-driving
    instructions into a coding agent through the issue thread. With no
    allowlist configured `is_trusted_author` trusts every author, so the
    default single-user deployment sees the full thread unchanged.

    Nothing is retained past that filter here: this convenience reads the
    thread itself, so a caller holding recorded orchestrator ids passes them
    to `_thread_text` with the snapshot it already has.
    """
    return _thread_text(issue.get_comments(), max_chars)
