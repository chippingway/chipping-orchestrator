# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Trust-filtered thread text, input delivery, and repository context.

Only trusted authors and explicitly retained orchestrator comment ids may enter
a rebuilt conversation. Marker text alone cannot admit a comment. Repository
context contains configured source paths and branches, with a bounded listing.
Process-local delivery snapshots record exact delivered inputs and conservative
settlement watermarks; a snapshot over a read taken by the pinned comment's id
names that comment the same way. A prompt built from one of those reads and
settled from it is one fact rather than two readings that have to agree.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import is_trusted_author
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    prompt_delivery,
)

# The blank line between quoted comments is the paragraph break the prompt
# builders assemble their own sections with, so it keeps one definition.
_SECTION_SEP = "\n\n"

_TRACKED_REPOS_CAP = 20

# What a prompt quotes of a thread at most. Named because the road that
# settles what it delivered is bounded by exactly this number: the omissions a
# delivery record holds a watermark below are the ones this cut.
_EXCERPT_CHARS = 4000

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
    max_chars: int = _EXCERPT_CHARS,
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


def _recent_comments_text(issue: Issue, max_chars: int = _EXCERPT_CHARS) -> str:
    """Conversation text fed to the agent prompts that settle nothing by it
    (documentation, decompose, question, and discussion).

    The validating reviewer is a prompt of the other kind: a round a park's
    reply bought records that reply, so it builds from `_delivered_thread`
    and settles off that same read. So does every requirements-drift resume,
    on an open pull request as much as before one: what the developer is
    quoted there is what the issue goes on to mark answered.

    An untrusted author's comment is dropped whole -- its body and any URLs
    it contains never reach the prompt -- so once `ALLOWED_ISSUE_AUTHORS`
    is set an outsider on a public repo cannot smuggle workflow-driving
    instructions into a coding agent through the issue thread. With no
    allowlist configured `is_trusted_author` trusts every author, so the
    default single-user deployment sees the full thread unchanged.

    Nothing is retained past that filter here: this convenience reads the
    thread itself, so a caller holding recorded orchestrator ids passes them
    to `_thread_text` with the snapshot it already has. A prompt whose
    delivery is going to be RECORDED takes `_delivered_thread` instead, since
    a settlement wants the read its own text was rendered from.
    """
    return _thread_text(issue.get_comments(), max_chars)


def _thread_delivery(
    issue_comments,
    max_chars: int | None = _EXCERPT_CHARS,
    *,
    retained_ids: frozenset = _NO_RETAINED_IDS,
    **naming,
) -> prompt_delivery.PromptDeliverySnapshot:
    """Build a delivery snapshot for an already-read list of comments.

    `naming` carries what the snapshot is told about who wrote what, beyond
    the recorded ids: `pat_login`, `requirements_revision`, the
    `state_comment_id` of a read taken by the pinned comment's identity, and
    the `state` whose watermarks the read was bounded by -- which is what
    keeps an omission already below a cursor from holding that cursor back.
    """
    return prompt_delivery.create_prompt_delivery_snapshot(
        issue_comments=issue_comments,
        max_chars=max_chars,
        retained_ids=retained_ids,
        **naming,
    )


def _delivered_thread(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    max_chars: int = _EXCERPT_CHARS,
) -> prompt_delivery.PromptDeliverySnapshot:
    """One read of an issue thread: the text a prompt quotes, and its record.

    Taking the read here is what keeps those from being two questions.
    `rendered_text` is exactly what `_thread_text` would render over the same
    comments, and the entries beside it name the ones that text is made of, so
    a caller builds its prompt from one and settles the other. Read twice, a
    stage quotes a comment that landed between the reads and then records a
    watermark below it, or records one above a comment it never showed.

    The pinned state comment is left out by its IDENTITY, so a human reply
    quoting its marker is a reply like any other. Our own posts stay in by
    recorded id -- an agent reading the answers without the questions is
    re-grounded on half a thread -- while a body carrying our marker that the
    ledger cannot vouch for is refused, since the marker is text anybody may
    paste.

    The requirements revision is the fingerprint of THIS read -- the baseline
    a later edit is compared against -- so an edit arriving after it is still
    an edit on the next tick. What the excerpt bound dropped is inside that
    fingerprint and outside the watermark, which stops below the first
    omission: a baseline stopping short of the drop would re-open the same
    prompt, bounded the same way, every poll, while the watermark left below
    it keeps the dropped context deliverable by the road that owns it.
    """
    ours = _comments._orchestrator_ids(state)
    read = gh.comments_after(issue, None, state_comment_id=state.comment_id)
    return _thread_delivery(
        read,
        max_chars,
        retained_ids=frozenset(ours),
        state=state,
        state_comment_id=state.comment_id,
        requirements_revision=_content_hash._compute_user_content_hash(
            issue, ours, comments=read,
        ),
    )
