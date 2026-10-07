# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a landed auto rebase leaves its pull request owing.

An auto rebase publishes a commit no developer report is about: the report the
issue last settled names the head the push was leased against. Left there, the
reviewer road refuses that report and parks for a human whose reply only
restarts a report of a commit this orchestrator made itself. So every finish
that routes a landed rebase to `validating` first stages the rewrite as report
DEBT (`workflow/engine/report_rewrite_debt.py`) -- the pull request, its
branch, the anchor the push replaced, and the exact head that landed -- and the
validating hold asks the developer for that head's report with no human
involved. The finish of a rebase the tick published itself stages it through
the workflow's own owner (`workflow/engine/rewrite_finish_debt.py`); this is
the crash recovery's, and the two word and measure the debt alike.

Staged here and made durable by the finish's own announcement write, which goes
out ahead of the write that clears the attempt and ahead of the relabel, so no
road reaches `validating` over a landed head with its debt unrecorded. The
window before that write -- a push that landed and a process that died before
the mark -- is held by the attempt record itself: its anchor and the replay it
names are the debt's two heads, the anchor keeps every stage handler back, and
the recovery that finishes the route stages the same debt. A replay of that
write, the route an announced finish still owes included, leaves the claim
unchanged -- save under a mark an earlier build wrote with no debt beside it,
where the claim this stages is new and is written before that route relabels.

The room the debt needs is measured on the WHOLE write that will carry it, not
on the debt alone: the announcement write also puts down the notice's ledger
entry, the reset round, and the mark, and a claim that fits without them can
still carry that write past what GitHub accepts. A proved debt that does not
fit stops the finish before it announces anything: the caller parks for a
human to make room, with the push kept and the attempt standing, and the reply
brings the recovery back to record the debt and finish the route.

Only a head this attempt PUBLISHED is recorded, so a no-op, a refused push, a
reset, and a foreign update of the pull request -- none of which reaches a
finish -- assert nothing and leave whatever debt already stands exactly as it
is. A standing claim the rewrite cannot be carried onto -- another pull request
or branch, a head somebody else pushed in between, a claim nobody can read --
is refused by the debt's own owner and left standing; that is no head this
orchestrator can show it made, so the route still goes on, and the reviewer
road refuses the stale report it finds there as it would with no claim at all.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
)
from orchestrator.git.base_sync.state import _PENDING_ANNOUNCED_SHA, _REVIEW_ROUND, log
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState

# Why a landed head's route stops short of review, in the operator's own terms.
_UNRECORDED = (
    "{mentions} PR #{pr} now stands on `{published}`, which the orchestrator's "
    "auto rebase pushed over `{replaced}`, and the report debt that head is "
    "owed does not fit on this issue's pinned state comment. Routed to "
    "`workflow:validating` without it, the reviewer would be handed the report "
    "of the head it replaced, so the route stops here with the push kept and "
    "nothing routed. Remove records this issue no longer needs from the pinned "
    "state comment, then reply on this issue with anything to finish the route."
)


def _records_the_rewrite(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext,
    replaced: str,
    published: str,
    *,
    announcing: bool,
) -> str:
    """Stage the report debt a landed rebase of `replaced` onto `published` leaves; the park notice where it cannot.

    "" where the route may go on: the debt is staged, replayed, or refused as
    a claim nobody can show this orchestrator made. Otherwise the notice the
    caller parks with, having written and routed nothing -- a proved debt the
    comment has no room for.

    `replaced` is the anchor the push was leased against, which is the head
    the pull request provably stood on when it landed, and `published` the
    commit it landed. The branch is resolved the way the push and the recovery
    snapshot resolve it, so the claim names the branch the settled report's
    subject does.

    `announcing` says the caller's next write is its announcement, and the
    room is measured on that write (`_announcement`); the caller makes it
    durable. Otherwise the mark is already on the comment, and a claim new to
    it is written here at once, since that caller's next write may come only
    after its relabel.

    Either way the claim has to stage on the comment as it stands too, and a
    refusal there is answered as the one on the measured write is. The
    announcement resets the round, so a round wider than everything it adds
    makes that write the narrower of the two -- and a debt the comment cannot
    take now is one the route would otherwise go on without.
    """
    # Lazy for the reason every upward reach in this package is: the debt is
    # the workflow's record, in the layer above this one.
    from orchestrator.workflow.engine import report_rewrite_debt as _rewrite_debt
    rewrite = _rewrite_debt.RewriteDebt(
        pr_number=context.pr_number,
        branch=_naming._resolve_branch_name(
            context.state, context.spec, context.issue.number,
        ),
        previous_head=replaced,
        rewritten_head=published,
    )
    carried = context.state.get(_rewrite_debt.REWRITE_DEBT)
    measured = _announcement(context.state, published) if announcing else PinnedState(
        data=dict(context.state.data),
    )
    if not _rewrite_debt.records_rewrite(measured, rewrite):
        return _refusal(context, measured, rewrite)
    if not _rewrite_debt.records_rewrite(context.state, rewrite):
        return _refusal(context, context.state, rewrite)
    if not announcing and context.state.get(_rewrite_debt.REWRITE_DEBT) != carried:
        context.gh.write_pinned_state(context.issue, context.state)
    return ""


def _announcement(state: PinnedState, published: str) -> PinnedState:
    """The pinned write a finish's announcement of `published` makes, taken before anything is announced.

    Everything either finish has put on the comment by then: the ledger entry
    of the notice it posts, reserved at the widest id a comment is recorded
    at, the round both reset ahead of their mark, and the mark. The writes
    past it clear the attempt's heads, so none of them carries more.
    """
    # Lazy for the reason the debt owner is: the ledger and the widest id it
    # is measured at are the workflow's.
    from orchestrator.workflow.engine import (
        comments as _comments,
        report_record_values as _record_values,
    )
    announced = PinnedState(data=dict(state.data))
    _comments._reserve_comment_slot(announced, _record_values.MAX_RECORDED_NUMBER)
    announced.set(_REVIEW_ROUND, 0)
    announced.set(_PENDING_ANNOUNCED_SHA, published)
    return announced


def _refusal(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext,
    measured: PinnedState,
    rewrite,
) -> str:
    """The park notice a refused debt owes, or "" where the route may go on without it."""
    from orchestrator.workflow.engine import report_rewrite_room as _rewrite_room
    if not _rewrite_room.outgrows_the_comment(measured, rewrite):
        log.warning(
            "issue=#%d auto rebase published %s over %s on PR #%d and the "
            "report debt standing there cannot be carried onto it; leaving "
            "it as it is",
            context.issue.number, rewrite.rewritten_head[:8],
            rewrite.previous_head[:8], context.pr_number,
        )
        return ""
    log.error(
        "issue=#%d auto rebase published %s on PR #%d and the report debt it "
        "is owed does not fit on the pinned state comment; holding the route",
        context.issue.number, rewrite.rewritten_head[:8], context.pr_number,
    )
    return _UNRECORDED.format(
        mentions=config.HITL_MENTIONS,
        pr=context.pr_number,
        published=rewrite.rewritten_head,
        replaced=rewrite.previous_head,
    )
