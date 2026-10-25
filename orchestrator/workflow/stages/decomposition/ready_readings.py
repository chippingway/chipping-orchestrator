# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the `ready` decision reads off GitHub between the claimed record and its effects.

Three readings, each a request of its own. The thread (`thread`) is read whole
-- every comment but the pinned one -- and handed to everything the decision
takes off it: the requirements fingerprint, the consumed-comment ratchet, and
this orchestrator's own receipts on it. One read serves all three because a
comment landing between two reads would otherwise be consumed by a ratchet that
never compared it, or compared by a fingerprint nothing consumed; a thread
nobody could read proves nothing either way, and holds the decision.

The issue itself is fetched again (`fresh`) ahead of each effect -- a pickup
announced, a checkpoint landed, a relabel, a notice, a launch -- because the
dispatcher's hold check is as old as the tick, and an operator who applies
`paused` or `backlog` while those requests run has asked for them to stop
(`held`). An issue GitHub would not answer for proves no hold is off, and
holds too. The fetched issue is also the newest title and body the decision
can compare, and the object every later effect is made on. Ahead of the
handoff's effects -- the pickup, and the relabel to `implementing` -- it is
compared too (`compared`): a title or body edited behind any earlier request
of the tick is drift the moment a fetch shows it, never a pickup announced or
an implementation started over requirements already read as changed.

A receipt (`found`) is a sentence or a hidden marker this orchestrator posted,
found on a thread reading: the whole text is matched, the author has to be
this orchestrator (`github.comments.authored_by_us`), and the comment has to
carry the evidence it was generated -- the hidden marker every post of ours
carries, or an id our ledger records -- since the text is plain on a public
thread, and the token account may be a human's too, whose quotation of it
taken for ours would discharge an effect nobody made and drop that human's
words from the requirements as ours.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github import comments as _github_comments
from orchestrator.github.client import GitHubClient
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, drift as _drift

log = logging.getLogger("orchestrator.workflow")


def thread(gh: GitHubClient, issue: Issue, state: PinnedState) -> list | None:
    """The issue thread read once, every comment but the pinned one; None where GitHub did not answer."""
    try:
        return list(gh.comments_after(issue, None, state_comment_id=state.comment_id))
    except Exception:
        log.exception(
            "issue=#%d could not read its thread for the ready decision; holding it with nothing done",
            issue.number,
        )
        return None


def fresh(gh: GitHubClient, issue: Issue) -> Issue | None:
    """The issue as GitHub answers for it now, where no `paused` or `backlog` hold stands on it; None otherwise.

    Fetched afresh, never the object the tick was dispatched with, whose
    labels, title, and body are as old as the tick. An issue nobody could
    fetch holds as well: the effect waits for a tick that can say the hold is
    off.
    """
    try:
        fetched = gh.get_issue(issue.number)
    except Exception:
        log.exception("issue=#%d could not be read for a hold ahead of a ready effect; holding it", issue.number)
        return None
    skip_label = hard_skip_control_label(fetched)
    if skip_label is None:
        return fetched
    log.info("issue=#%d carries %r; the ready decision goes no further until it is removed", issue.number, skip_label)
    return None


def held(gh: GitHubClient, issue: Issue) -> bool:
    """Whether a `paused` or `backlog` hold stands on the issue as GitHub answers for it now (`fresh`)."""
    return fresh(gh, issue) is None


def compared(
    gh: GitHubClient, issue: Issue, state: PinnedState, comments: list,
) -> tuple[Issue | None, str | None]:
    """The issue fetched afresh (`fresh`) where its requirements still read as `state`'s baseline over `comments`.

    Otherwise None, beside the fingerprint the requirements moved to where
    they moved -- for the decision to reroute on -- and beside None where a
    hold stands or GitHub would not answer. The fetch that asks for a hold
    answers the newest title and body as well, and an edit it shows is drift
    whatever request it landed behind, so no effect is made over requirements
    the tick has already read as changed.
    """
    current = fresh(gh, issue)
    if current is None:
        return None, None
    moved = _drift._detect_user_content_change(gh, current, state, reading=comments)
    if moved is None:
        return current, None
    return None, moved


def found(gh: GitHubClient, state: PinnedState, comments: list, receipt: str) -> int | None:
    """The id of the last comment of ours on `comments` carrying `receipt`, generated by us; None for none.

    Ours is authored by this orchestrator's account and carries the hidden
    marker every post of ours does, or an id `state`'s ledger records.
    """
    own = getattr(gh, "_bot_login", None)
    ledger = _comments._orchestrator_ids(state)
    said = [
        posted.id for posted in comments
        if receipt in (posted.body or "")
        and _github_comments.authored_by_us(posted, bot_login=own)
        and (_comments._ORCH_COMMENT_MARKER in (posted.body or "") or posted.id in ledger)
    ]
    return max(said) if said else None
