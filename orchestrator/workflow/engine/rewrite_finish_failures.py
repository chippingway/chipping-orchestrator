# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The configured verification a landed base rewrite's head failed, kept until the pull request carries it.

A failed run records no evidence, so the notice on the pull request is the
whole of what makes the failure actionable: the failing command, how it
failed, and the tail of what it printed (`rewrite_finish_notices.failure`).
A notice posted only best effort would be lost with a post that failed, and
repeated by a retry that ran the commands again. So the finish's evidence
write records the notice itself on the pinned comment first, beside the
head it is about (`auto_base_rebase_failed_verification`), before anything
is posted, and the record stays until the retirement that routes the head
clears it (`rewrite_finish_writes.retirement`).

Publishing it (`publishes`) reads the pull request's conversation and posts
the notice only where no comment of ours already carries it: the notice's
whole text is its identity, as a park notice's sentence is, and the author
is held to this orchestrator (`github.comments.authored_by_us`), since text
on a public thread is trivially copied. So a post whose response was lost is
found where it landed, and a retry after a write that did not land posts
nothing a second time. A finish that finds the record for its own landed
head runs nothing again and publishes the notice it recorded
(`rewrite_finish_evidence`). A thread nobody could read, or a post that
raised, holds the route with the record standing for the next tick.

The record is additive and read fail-closed: absent or `null` is none, and
anything but an object naming a commit and a notice is read as none, which a
retry answers by deciding afresh.
"""
from __future__ import annotations

import logging

from orchestrator.github import comments as _github_comments
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish

log = logging.getLogger("orchestrator.workflow")

# The failure notice a landed head is owed and its pull request may not carry
# yet: the head it is about, and the notice's whole text.
FAILED_VERIFICATION = "auto_base_rebase_failed_verification"

_HEAD = "head"

_NOTICE = "notice"


def records(state: PinnedState, head: str, notice: str) -> None:
    """Stage the failure `notice` of `head` on `state`; the caller writes."""
    state.set(FAILED_VERIFICATION, {_HEAD: head, _NOTICE: notice})


def recorded(state: PinnedState, head: str) -> str | None:
    """The failure notice `state` records for `head`, or None for none readable about it."""
    record = state.get(FAILED_VERIFICATION)
    if not isinstance(record, dict) or record.get(_HEAD) != head:
        return None
    notice = record.get(_NOTICE)
    return notice if isinstance(notice, str) and notice else None


def publishes(finish: LandedFinish, notice: str | None) -> FinishOutcome | None:
    """Put `notice` on `finish`'s pull request once; None where it stands there, HELD where that is unknown.

    Its comment is entered in the ledger of this orchestrator's comments on
    the tick's state, which the retirement behind the route lands -- a post
    whose id came back, or one an earlier tick landed and the thread shows.
    Nothing is read or posted for no notice.
    """
    if notice is None:
        return None
    gh = finish.gh
    try:
        thread = gh.pr_conversation_thread(gh.get_pr(finish.pr_number))
    except Exception:
        log.exception(
            "issue=#%d could not read PR #%d for the notice of the failed verification of %.8s; holding the route",
            finish.issue.number, finish.pr_number, finish.head,
        )
        return FinishOutcome.HELD
    posted = _posted(thread, notice, getattr(gh, "_bot_login", None))
    if posted is None:
        try:
            _comments._post_pr_comment(gh, finish.pr_number, finish.state, notice)
        except Exception:
            log.exception(
                "issue=#%d could not post the notice of the failed verification of %.8s to PR #%d; "
                "holding the route",
                finish.issue.number, finish.head, finish.pr_number,
            )
            return FinishOutcome.HELD
    else:
        _comments._track_orchestrator_comment(finish.state, posted)
    return None


def _posted(thread: list, notice: str, bot_login: str | None) -> int | None:
    """The id of the comment of ours on `thread` that carries `notice`, or None."""
    return next(
        (
            posted.id for posted in thread
            if notice in (posted.body or "") and _github_comments.authored_by_us(posted, bot_login=bot_login)
        ),
        None,
    )
