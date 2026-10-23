# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ready ping's publication: armed before it is posted, found again rather than posted twice, recorded after.

The ping is a comment, and nothing makes posting it and recording it one
operation: a post GitHub took whose response was lost names no id, a process
can die between the post and the write behind it, and that write can be
refused or never confirmed. Recorded only after, a ping whose record never
landed would be posted again by the next tick, and a human told twice. So the
ping goes out in an order a later tick can always finish from: arm, prepare,
post, settle (`publishes`).

Arming lands `ready_ping_pending` -- the head the ping names and a receipt
minted for it -- as a checkpoint of its own, and the comment carries that
receipt in a hidden marker. Only a write GitHub confirmed licenses the post:
refused or unconfirmed, nothing is posted, and the next tick reads whether the
arming landed. The settlement -- `ready_ping_sha` stamped on the head, the
pending record dropped, and the comment's id entered in the ledger of this
orchestrator's comments -- is prepared over the comment before the post, with
that ledger entry reserved at its widest, so a comment that would not take it
-- unreadable, replaced, moved, or full -- is told nothing; and it is landed
behind the post. Both writes are guarded commits over the reading the tick
last confirmed (`report_commits.ReportCommit`), decided on the records the
approval was read over (`review_comment._IN_HAND_RECORDS`), the docs stamps
that qualified the head, and the ping's own two fields: a record that reads
otherwise was moved by no write of this tick's, and refuses the write with
nothing put back, adopted, or repaired. Anything but a candidate measured or a
write confirmed stops the ping there, with the tick's state withheld from
every whole-state write behind it.

A ping pending over the head the gate would ping is looked for on the issue
thread before anything else is asked of it (`recovers`). A comment of this
orchestrator's carrying the receipt is that ping made -- a post whose response
was lost, or one whose settlement was refused, lost, or never reached -- and
is settled without another post: it is a record of what was said, which needs
no eligibility. A thread nobody could read proves neither, and holds the ping
for a later tick. One that reads without it is a ping never made: the merge
gate asks its eligibility again, and only then is it posted, under the same
receipt. A post that raises is looked for the same way at once, and settled
where it landed.

The receipt is what tells a retry from a fresh approval. A fresh approval
retires the pending record beside `ready_ping_sha`
(`review_subjects.record_approved`), so the ping it earns on the very head an
earlier one named is armed with a receipt of its own, and a comment the
earlier one left on the thread is never taken for it. A pending record of any
other shape names no ping, and the next arming replaces it.

The ping moves no watermark: it is no park, and its ledger entry and the
hidden orchestrator marker every post carries are what keep a later feedback
scan from reading it as a human's.
"""
from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass

from orchestrator import config
from orchestrator.github import comments as _github_comments
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    pinned_commit_models as _commit_models,
    report_commits as _commits,
    review_subjects as _review_subjects,
)
from orchestrator.workflow.stages.in_review import models as _models
from orchestrator.workflow.stages.validating import review_comment as _review_comment

log = logging.getLogger("orchestrator.workflow")

_READY_PING_SHA = _review_subjects._READY_PING_SHA

_PENDING = _review_subjects._READY_PING_PENDING

# The members of the pending record: the head the ping names, and its receipt.
_HEAD = "sha"

_RECEIPT = "receipt"

# How many random bytes a receipt is minted from, and how it is spelled: two
# lowercase hex digits a byte.
_RECEIPT_BYTES = 8

_RECEIPT_SPELLING = re.compile("[0-9a-f]{16}")

# The hidden marker a ping's comment carries its receipt in. Closed right after
# the receipt, so one receipt that is a prefix of another claims no comment of it.
_MARKER = "<!--orchestrator-ready-ping:receipt={receipt}-->"

# What every write of the ping is decided on: the records the approval was read
# over, the docs stamps that qualified the head, and the ping's own two fields.
_DECIDED_ON = frozenset((
    *_review_comment._IN_HAND_RECORDS,
    "docs_checked_sha",
    "docs_verdict",
    _READY_PING_SHA,
    _PENDING,
))

# The arming, which owns the pending record alone.
_ARMING = _commits.ReportWrite(owned=frozenset((_PENDING,)), decided_on=_DECIDED_ON)

# The settlement, which owns the stamp, the pending record it drops, and the
# ledger entry the comment adds.
_SETTLING = _commits.ReportWrite(
    owned=frozenset((_READY_PING_SHA, _PENDING, _comments._ORCH_COMMENT_IDS)),
    decided_on=_DECIDED_ON,
)

# What a guarded commit comes to that lets the ping go on past it.
_GOES_ON = frozenset((_commit_models.CommitStatus.PREPARED, _commit_models.CommitStatus.COMMITTED))


def recovers(ctx: _models._InReviewContext, head_sha: str) -> bool:
    """Settle a ping pending over `head_sha` that the thread already carries; whether the tick is answered.

    Asked by the merge gate ahead of the approval's re-read, since settling a
    ping already made posts nothing. A thread nobody could read answers the
    tick too, with nothing posted or written: it proves neither that the ping
    was made nor that it was not. False where no ping is pending over the head,
    or the thread reads without it.
    """
    receipt = _pending_receipt(ctx.state, head_sha)
    if receipt is None:
        return False
    readable, landed = _found(ctx, receipt)
    if not readable:
        log.info(
            "issue=#%d could not read its thread for the ready ping pending over %.8s; "
            "holding the ping for a later tick", ctx.issue.number, head_sha,
        )
        return True
    if landed is None:
        return False
    log.info(
        "issue=#%d finds the ready ping pending over %.8s already on its thread; not posting it again",
        ctx.issue.number, head_sha,
    )
    _Ping.over(ctx, head_sha).settles(landed)
    return True


def publishes(ctx: _models._InReviewContext, head_sha: str) -> None:
    """Tell a human `head_sha` is ready: arm, prepare, post, settle.

    Asked by the merge gate once every gate in front of the ping has passed,
    the approval has been read again at the ping, and no comment carrying a
    ping pending over `head_sha` was found (`recovers`). That pending ping is
    posted under its own receipt; otherwise one is armed first.
    """
    ping = _Ping.over(ctx, head_sha)
    receipt = _pending_receipt(ctx.state, head_sha) or ping.arms()
    if receipt is not None:
        ping.posts(receipt)


def _pending_receipt(state: PinnedState, head_sha: str) -> str | None:
    """The receipt of the ping `state` records as pending over `head_sha`; None for none, or one of another shape."""
    pending = state.get(_PENDING)
    if not isinstance(pending, dict) or pending.get(_HEAD) != head_sha:
        return None
    receipt = pending.get(_RECEIPT)
    if isinstance(receipt, str) and _RECEIPT_SPELLING.fullmatch(receipt):
        return receipt
    return None


def _found(ctx: _models._InReviewContext, receipt: str) -> tuple[bool, int | None]:
    """Whether the issue thread read, and the id of a comment of ours on it carrying `receipt`.

    The thread is read whole save the pinned comment, which is told by
    identity: the marker is hidden, so only its author tells this
    orchestrator's ping from a copy anybody could paste.
    """
    gh, issue = ctx.gh, ctx.issue
    marker = _MARKER.format(receipt=receipt)
    try:
        thread = gh.comments_after(issue, None, state_comment_id=ctx.state.comment_id)
    except Exception:
        log.exception("issue=#%d could not read its thread for a ready ping", issue.number)
        return False, None
    own = getattr(gh, "_bot_login", None)
    return True, next(
        (
            posted.id for posted in thread
            if marker in (posted.body or "")
            and _github_comments.authored_by_us(posted, bot_login=own)
        ),
        None,
    )


def _stops(ctx: _models._InReviewContext, outcome: _commit_models.CommitOutcome, write: str) -> bool:
    """Whether `outcome`, of the ping's `write`, stops it: anything but a candidate measured or a write landed.

    Logged, with the tick's state withheld from every whole-state write
    behind it: a refusal wrote nothing, and an answer that was lost may or
    may not have landed, which only a later reading can say.
    """
    if outcome.status in _GOES_ON:
        return False
    ctx.state.withheld = True
    log.warning(
        "issue=#%d its ready ping's %s came back %s; going no further, with the pinned comment left as "
        "it stands for the next tick to read",
        ctx.issue.number, write, (outcome.refusal or outcome.status).value,
    )
    return True


@dataclass(frozen=True)
class _Ping:
    """One ping over `head`: the tick deciding it, and the commit its writes land through."""

    ctx: _models._InReviewContext
    head: str
    commit: _commits.ReportCommit

    @classmethod
    def over(cls, ctx: _models._InReviewContext, head_sha: str) -> _Ping:
        """The ping `ctx`'s tick decides over `head_sha`, landing over the reading the tick last confirmed."""
        return cls(ctx, head_sha, _commits.ReportCommit(ctx.gh, ctx.issue, ctx.state))

    def arms(self) -> str | None:
        """Land a fresh receipt for the ping as a checkpoint; the receipt, or None where it did not land."""
        receipt = secrets.token_hex(_RECEIPT_BYTES)
        staged = self.commit.staging()
        staged.set(_PENDING, {_HEAD: self.head, _RECEIPT: receipt})
        if _stops(self.ctx, self.commit.lands(staged, _ARMING), "arming"):
            return None
        return receipt

    def posts(self, receipt: str) -> None:
        """Prepare the settlement, post the ping under `receipt`, and settle it where it landed."""
        prepared = self.commit.prepares(
            self.stamped(self.commit.staging()), _SETTLING, ledger_entry=True,
        )
        if _stops(self.ctx, prepared, "settlement's preparation"):
            return
        ctx = self.ctx
        words = (
            f":bell: {config.HITL_MENTIONS} PR #{ctx.pr_number} is ready for review/merge."
            f"\n\n{_MARKER.format(receipt=receipt)}"
        )
        try:
            _comments._post_issue_comment(ctx.gh, ctx.issue, ctx.state, words)
        except Exception:
            log.exception("issue=#%d could not post its ready ping", ctx.issue.number)
            landed = _found(ctx, receipt)[1]
            if landed is not None:
                self.settles(landed)
            return
        self.settles(None)

    def settles(self, landed: int | None) -> None:
        """Land the ping as made, entering `landed` -- a comment found rather than posted -- in the ledger."""
        state = self.ctx.state
        if landed is not None:
            _comments._track_orchestrator_comment(state, landed)
        settled = self.commit.lands(self.stamped(state), _SETTLING)
        _stops(self.ctx, settled, "settlement")

    def stamped(self, state: PinnedState) -> PinnedState:
        """`state` with this ping recorded as made, and nothing left pending."""
        state.set(_READY_PING_SHA, self.head)
        state.set(_PENDING, None)
        return state
