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
measures on the comment as it stands alone. A finish held to the dormant
settled-evidence policy that routes its head (`rewrite_finish_models.routes_a_relabel`) --
a continuation relabels nothing -- measures beside both the record of the relabel its
route lands behind them (`rewrite_finish_announced.relabels_once`), since that
record is written too before the retirement clears; the coordinator reserves
it again on the checkpoint it prepares over the fresh comment
(`rewrite_finish._checkpoints`). A proved debt short of either
room stops the finish before it says anything: the caller parks for a human
to make room (`unrecorded`), with the push kept and the attempt standing. A
finish held to the dormant settled-evidence policy asks first whether that
park already stands -- unless a reply it was handed answers it -- or its
notice was said, past the watermark or that reply, ahead of a park write that
did not land (`noticed`) -- holding where the conversation would not read --
and files the event of a park said that way, naming the landed head and the
notice, only where the event stream does not carry that park's own
(`files_the_park`), so it is neither said nor filed twice.

A standing claim the rewrite cannot be carried onto -- another pull request or
branch, a head somebody else pushed in between, a claim nobody can read -- is
refused by the debt's own owner and left as it is. That is no head this
orchestrator can show it made, so the finish goes on, and the reviewer road
refuses the stale report it finds there as it would with no claim at all.
`report_rewrite_room` is what tells that refusal from one for room.

Every landing is finished through this one owner -- the publication of a
rebase this tick made, the recovery's retry of a replay nothing published,
and a push the recovery found already landed -- so a landing finished on any
road owes and parks alike.
"""
from __future__ import annotations

import copy
import logging

from orchestrator import config
from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.github import events as _github_events
from orchestrator.github.comments import authored_by_us
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    owed_events as _owed_events,
    prompt_delivery as _prompt_delivery,
    report_record_values as _record_values,
    report_rewrite_debt as _rewrite_debt,
    report_rewrite_room as _rewrite_room,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish, routes_a_relabel
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")

# The event a park files, and why a debt with no room parks.
_PARKED = "park_awaiting_human"

_PARKED_FOR_THE_DEBT = _base_sync_state._REASON_AUTO_BASE_REBASE_UNRECORDED_DEBT

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


def announcement(state: PinnedState, head: str, *, announced: bool = False, relabels: bool = False) -> PinnedState:
    """The writes that announce and route `head`, as `state` would make them, taken before anything is announced.

    Everything the announcement puts on the comment: the ledger entry of the
    notice it follows, reserved at the widest id a comment is recorded at, the
    record of its event -- which the write ahead of the event lands on its own
    too -- the round reset ahead of the mark, and the mark; none of it where
    the mark is `announced` already. `relabels`, for a finish held to the
    dormant settled-evidence policy that routes its head
    (`rewrite_finish_models.routes_a_relabel`), adds the record of the
    relabel its route makes behind them (`rewrite_finish_announced.relabels_once`). The
    retirement past them only clears, so none of them carries more.
    """
    written = PinnedState(state_data=copy.deepcopy(state.data))
    if not announced:
        _comments._reserve_comment_slot(written, _record_values.MAX_RECORDED_NUMBER)
        written.set(_base_sync_state._PENDING_ANNOUNCED_EVENT, head)
        written.set(_base_sync_state._REVIEW_ROUND, 0)
        written.set(_base_sync_state._PENDING_ANNOUNCED_SHA, head)
    if relabels:
        written.set(_base_sync_state._PENDING_RELABELLED, head)
    return written


def fits(finish: LandedFinish, *, announced: bool) -> bool:
    """Whether the comment as the tick holds it has room for `finish`'s debt on the write it rides; nothing is staged.

    Asked ahead of the evidence the finish decides before it announces, so a
    debt the comment has no room for parks before anything runs or is
    recorded for the head; the checkpoint measures it again on the comment as
    that leaves it.
    """
    staged = PinnedState(state_data=copy.deepcopy(finish.state.data))
    measured = announcement(staged, finish.head, announced=announced, relabels=routes_a_relabel(finish))
    return stages(finish, staged, measured)


def stages(finish: LandedFinish, staged: PinnedState, measured: PinnedState) -> bool:
    """Stage `finish`'s debt on `staged`, measured on `measured` first; False only where there is no room for it.

    `measured` is the write the debt rides, staged with the debt too, and
    `staged` the comment as it stands. The debt is the anchor the landing
    replaced and the head it published, on its branch. A refusal for anything
    but room leaves both as they were and answers True: the finish goes on
    without the claim.
    """
    rewrite = _rewrite_debt.RewriteDebt(
        pr_number=finish.pr_number,
        branch=finish.landed.candidate.branch,
        previous_head=finish.anchor,
        rewritten_head=finish.head,
    )
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


def noticed(finish: LandedFinish, staged: PinnedState) -> FinishOutcome | int | None:
    """Where the park a debt with no room takes stands for `finish` already: what to stop at, a notice said, or None.

    For a finish held to the dormant settled-evidence policy, so a park is
    neither said nor filed twice. A reply the finish was handed that the
    watermark has not passed answers the park standing, so only a notice said
    behind that reply counts: a park made over it before that never landed
    is found there, and a reply newer than every notice parks anew. With no
    such reply, PARKED where the tick's state carries the park standing:
    nothing is posted, filed, or written again. HELD, logged, where the
    issue's conversation would not read: nobody can say whether its notice
    was said, so nothing is said again. The id of this very park notice of
    ours the conversation carries past the reply or the watermark -- one a
    finish posted ahead of a park write that did not land, its answer lost or
    not -- laid on `staged` as a post of it would be, the watermark moved to
    it and the comment entered in the ledger, so the park lands over it with
    nothing posted again (`files_the_park`). None where none was said.
    """
    watermark = finish.state.get(_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID) or 0
    floor = max(watermark, finish.retry or 0)
    flags = (
        finish.state.get(_base_sync_state._AWAITING_HUMAN),
        finish.state.get(_base_sync_state._PARK_REASON),
    )
    if floor == watermark and flags == (True, _PARKED_FOR_THE_DEBT):
        log.info(
            "issue=#%d already parked for its debt over %.8s; posting nothing again", finish.issue.number, finish.head,
        )
        return FinishOutcome.PARKED
    try:
        thread = finish.gh.comments_after(finish.issue, floor, state_comment_id=finish.state.comment_id)
    except Exception:
        log.exception("issue=#%d could not be read for a debt park notice already posted; holding", finish.issue.number)
        return FinishOutcome.HELD
    posted = [
        comment.id for comment in thread
        if unrecorded(finish) in (comment.body or "")
        and authored_by_us(comment, bot_login=getattr(finish.gh, "_bot_login", None))
    ]
    if not posted:
        return None
    staged.set(_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID, posted[-1])
    _comments._track_orchestrator_comment(staged, posted[-1])
    return posted[-1]


def files_the_park(finish: LandedFinish, notice: int) -> FinishOutcome | None:
    """File the `park_awaiting_human` event of the park whose notice `notice` was said (`noticed`); None to go on.

    A notice whose post landed with its answer lost went out with no event
    behind it, so the event stream is asked first and the event filed --
    attributed as a park files it, naming the landed head and the notice as
    such a finish's park does -- only where the stream carries no event of
    this very park: one naming that notice, which no earlier park of the
    issue, of this head or another, does. HELD, logged, where the stream
    would not read, so nothing is filed twice. With no audit log the notice
    said is taken as its event filed, save one this process owes over this
    park's notice text (`owed_events.unfiled`): once at most, never twice.
    """
    issue_number = finish.issue.number
    named = {"reason": _PARKED_FOR_THE_DEBT, "sha": finish.head, "notice_id": notice}
    found = _github_events.filed(finish.gh, _PARKED, issue_number=issue_number, **named)
    if found is None:
        log.warning("issue=#%d could not read the event stream back for its debt park; holding", issue_number)
        return FinishOutcome.HELD
    named_and_said = {**named, "said": unrecorded(finish)}
    if not found and _owed_events.unfiled(finish.gh, _PARKED, issue_number=issue_number, **named_and_said):
        stage = stage_name(finish.gh.workflow_label(finish.issue))
        finish.gh.emit_event(_PARKED, issue_number=issue_number, stage=stage, **named)
        _owed_events.pays(finish.gh, _PARKED, issue_number=issue_number, **named_and_said)
    return None


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
