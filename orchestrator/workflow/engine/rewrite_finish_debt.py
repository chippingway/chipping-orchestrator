# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report debt a landed base rewrite leaves its pull request owing, staged only where its write has room.

A rewrite this orchestrator published moves the pull request onto a head no
developer report is about, so the finish records it as report debt
(`report_rewrite_debt`) -- the pull request, the branch the push went to, the
anchor it was leased against, and the head that landed -- before anything
routes the issue to a reviewer who would otherwise refuse the report of the
head it replaced.

The room that debt needs is measured on the WHOLE write that carries it
(`announcement`): the announcement also puts down the notice's ledger entry,
reserved at the widest id a comment is recorded at, the reset round, and the
mark, and a claim that fits without them can still carry that write past what
GitHub accepts. It is measured on the comment as it stands as well, since a
round wider than everything the announcement adds makes that write the
narrower of the two, and a debt the comment cannot take now is one the route
would otherwise go on without. A finish whose announcement is already out
measures on the comment as it stands alone. A proved debt short of either
room stops the finish before it says anything: the caller parks for a human
to make room (`unrecorded`), with the push kept and the attempt standing.

A standing claim the rewrite cannot be carried onto -- another pull request or
branch, a head somebody else pushed in between, a claim nobody can read -- is
refused by the debt's own owner and left as it is. That is no head this
orchestrator can show it made, so the finish goes on, and the reviewer road
refuses the stale report it finds there as it would with no claim at all.
`report_rewrite_room` is what tells that refusal from one for room.

The text and the measurement are the ones the auto rebase's own finish makes
(`git/base_sync/report_debt.py`), so a landing finished on either road owes
and parks alike.
"""
from __future__ import annotations

import copy
import logging

from orchestrator import config
from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_record_values as _record_values,
    report_rewrite_debt as _rewrite_debt,
    report_rewrite_room as _rewrite_room,
)
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

log = logging.getLogger("orchestrator.workflow")

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


def owed(finish: LandedFinish) -> _rewrite_debt.RewriteDebt:
    """The debt `finish`'s landing leaves: the anchor it replaced and the head it published, on its branch."""
    return _rewrite_debt.RewriteDebt(
        pr_number=finish.pr_number,
        branch=finish.landed.candidate.branch,
        previous_head=finish.anchor,
        rewritten_head=finish.head,
    )


def announcement(state: PinnedState, head: str) -> PinnedState:
    """The write that announces `head`, as `state` would make it, taken before anything is announced.

    Everything that write puts on the comment: the ledger entry of the notice
    it follows, reserved at the widest id a comment is recorded at, the round
    reset ahead of the mark, and the mark. The writes past it only clear, so
    none of them carries more.
    """
    announced = PinnedState(state_data=copy.deepcopy(state.data))
    _comments._reserve_comment_slot(announced, _record_values.MAX_RECORDED_NUMBER)
    announced.set(_base_sync_state._REVIEW_ROUND, 0)
    announced.set(_base_sync_state._PENDING_ANNOUNCED_SHA, head)
    return announced


def stages(finish: LandedFinish, staged: PinnedState, measured: PinnedState) -> bool:
    """Stage `finish`'s debt on `staged`, measured on `measured` first; False only where there is no room for it.

    `measured` is the write the debt rides, staged with the debt too, and
    `staged` the comment as it stands. A refusal for anything but room leaves
    both as they were and answers True: the finish goes on without the claim.
    """
    rewrite = owed(finish)
    for reading in (measured, staged):
        if not _rewrite_debt.records_rewrite(reading, rewrite):
            return not _for_want_of_room(finish, reading, rewrite)
    return True


def unrecorded(finish: LandedFinish) -> str:
    """The park notice of a landed head whose debt the pinned comment has no room for."""
    return _UNRECORDED.format(
        mentions=config.HITL_MENTIONS,
        pr=finish.pr_number,
        published=finish.head,
        replaced=finish.anchor,
    )


def _for_want_of_room(
    finish: LandedFinish, reading: PinnedState, rewrite: _rewrite_debt.RewriteDebt,
) -> bool:
    """Whether the debt owner refused `rewrite` over `reading` for nothing but the comment's room; logged."""
    if not _rewrite_room.outgrows_the_comment(reading, rewrite):
        log.warning(
            "issue=#%d auto rebase published %.8s over %.8s on PR #%d and the report debt standing "
            "there cannot be carried onto it; leaving it as it is",
            finish.issue.number, finish.head, finish.anchor, finish.pr_number,
        )
        return False
    log.error(
        "issue=#%d auto rebase published %.8s on PR #%d and the report debt it is owed does not "
        "fit on the pinned state comment; holding the route",
        finish.issue.number, finish.head, finish.pr_number,
    )
    return True
