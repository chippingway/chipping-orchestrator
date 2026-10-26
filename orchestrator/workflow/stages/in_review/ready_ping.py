# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ready ping's publication: armed before it is posted, found again rather than posted twice, recorded after.

The ping is a comment, and nothing makes posting it and recording it one
operation: a post GitHub took whose response was lost names no id, a process
can die between the post and the write behind it, and that write can be
refused or never confirmed. Recorded only after, a ping whose record never
landed would be posted again by the next tick, and a human told twice. So the
ping goes out in an order a later tick can always finish from: arm, prepare,
prove, re-read, post, settle (`publishes`).

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
readiness proof was read over (`review_comment._IN_HAND_RECORDS`), every
record a report debt is read from (`report_delivery.REPORT_DEBT`), the final
docs pass's completion (`final_docs_records`), the docs stamps that qualified
the head, and the ping's own two fields: a record that reads otherwise was
moved by no write of this tick's, and refuses the write with nothing put
back, adopted, or repaired. Anything but a candidate measured
or a write confirmed stops the ping there, with the tick's state withheld from
every whole-state write behind it.

Those checkpoints guard the pinned comment and nothing else, and each is a
request: a push, an edit of the issue or the report, or the verification
artifact deleted or edited while they are written is one no record shows. So
the readiness proof the merge gate takes is taken once more behind them
(`publishes`' `proves`): refused or unread, nothing is posted, the arming
stands for the next tick to read, and the settlement prepared is written
nowhere. That proof reads the records the tick holds and the pull request,
and its requests are as long a time for a maintainer to edit the pinned
comment -- the approval, the report records, a final docs pass's completion --
as for a push. So behind it the settlement is prepared once more over the
comment read afresh: a record the ping is decided on that reads otherwise
refuses it the same way, with nothing posted and the arming left standing.
That reading is a request too, and the ping names a head of an open pull
request, so the pull request is read once more behind it, its state and head
together, the last thing asked before the post: one pushed past the head
refuses, and one merged, closed, or unread holds, nothing posted either way.
Whatever is asked last, the request it takes is the one window no reading
closes: a hand edit of the comment landing during that last reading of the
pull request is seen only by the settlement, whose guarded commit then
records nothing over it.

A ping pending over the head the gate would ping is looked for on the issue
thread before anything else is asked of it (`recovers`). A comment of this
orchestrator's carrying the receipt is that ping made -- a post whose response
was lost, or one whose settlement was refused, lost, or never reached -- and
is settled without another post: it is a record of what was said, which needs
no eligibility. A thread nobody could read proves neither, and holds the ping
for a later tick. One that reads without it is a ping never made: the merge
gate asks its eligibility again -- the whole readiness proof over the
evidence among it -- and only then is it posted, under the same receipt and
behind the same last proof and re-reading. A post that raises is looked for
the same way at once, and settled where it landed.

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
from collections.abc import Callable
from dataclasses import dataclass

from orchestrator import config
from orchestrator.github import comments as _github_comments
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    final_docs_records as _final_docs,
    pinned_commit_models as _commit_models,
    report_commits as _commits,
    report_delivery as _report_delivery,
    review_subjects as _review_subjects,
    terminal_reading as _terminal_reading,
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

# What every write of the ping is decided on: the records the readiness proof
# was read over -- a final docs pass's completion among them, which both
# qualifies the head it names and chooses the proof, and every record a
# report debt is read from (`report_delivery.owes_a_report`), which the proof
# reads through the subject guard and the completion's own refusal of a
# report owed -- the docs stamps that qualified the head, and the ping's own
# two fields.
_DECIDED_ON = frozenset((
    *_review_comment._IN_HAND_RECORDS,
    *_report_delivery.REPORT_DEBT,
    _final_docs.FINAL_DOCS,
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

# What the pull request read last answers where it is still open.
_OPEN = "open"

# What a guarded commit comes to that lets the ping go on past it.
_GOES_ON = frozenset((_commit_models.CommitStatus.PREPARED, _commit_models.CommitStatus.COMMITTED))


def recovers(ctx: _models._InReviewContext, head_sha: str) -> bool:
    """Settle a ping pending over `head_sha` that the thread already carries; whether the tick is answered.

    Asked by the merge gate ahead of the readiness proof, since settling a
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


def publishes(ctx: _models._InReviewContext, head_sha: str, proves: Callable[[], bool]) -> None:
    """Tell a human `head_sha` is ready: arm, prepare, prove, re-read, post, settle.

    Asked by the merge gate once every gate in front of the ping has passed,
    the readiness proof has been taken at the ping, and no comment carrying a
    ping pending over `head_sha` was found (`recovers`). That pending ping is
    posted under its own receipt; otherwise one is armed first. `proves` is
    that readiness proof, taken again behind the checkpoints with the comment
    and then the pull request read afresh behind it, immediately ahead of the
    post: it says whether the ping may still go out.
    """
    ping = _Ping.over(ctx, head_sha)
    receipt = _pending_receipt(ctx.state, head_sha) or ping.arms()
    if receipt is not None:
        ping.posts(receipt, proves)


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

    def posts(self, receipt: str, proves: Callable[[], bool]) -> None:
        """Prepare the settlement, prove the ping still stands, re-read the comment, post, and settle where it landed.

        The proof is taken behind the preparation, so nothing the checkpoints
        spent their requests over -- the head, the issue, the report, the
        artifact -- can move unseen between them; the settlement is prepared
        once more behind the proof, so no record the ping is decided on -- a
        completion among them -- is edited on the comment unseen while the
        proof reads; and the pull request is read behind that, the last
        request ahead of the post, so no push or end lands unseen during the
        comment's reading (`still_open`). Refused or unread, nothing is posted
        and the arming stands: the next tick reads the thread without the ping
        and asks again.
        """
        stands = self.prepared("settlement's preparation") and proves()
        if not (stands and self.prepared("re-reading behind the proof") and self.still_open()):
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

    def prepared(self, step: str) -> bool:
        """Whether the settlement measures over the comment read afresh, each record it is decided on as held.

        Nothing is written; `step` names the reading for the log where it
        stops the ping.
        """
        prepared = self.commit.prepares(
            self.stamped(self.commit.staging()), _SETTLING, ledger_entry=True,
        )
        return not _stops(self.ctx, prepared, step)

    def still_open(self) -> bool:
        """Whether the pull request, read last, is still open on the head the ping names.

        By the terminals' own reading, its state and head together: pushed
        past the head it refuses, and merged, closed, or unread it holds for
        the next tick, the terminals answering an end.
        """
        ctx = self.ctx
        linked = _terminal_reading._linked_pull_request(
            ctx.gh, ctx.issue, ctx.state, "reading the pull request last before posting a ready ping",
        )
        if linked.was_read and linked.state == _OPEN and linked.head == self.head:
            return True
        log.info(
            "issue=#%d its pull request, read last, is %s on %s rather than open on %.8s; not posting its ready ping",
            ctx.issue.number, linked.state if linked.was_read else "unread", linked.head, self.head,
        )
        return False

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
