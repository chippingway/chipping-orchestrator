# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The parks a returned reviewer's verdict takes when it may not be acted on.

Two refusals stop a verdict of a subject that still stands, and both are the
reviewer's round to redo rather than a developer's to answer. An approval that
relies on no evidence that passed and is current (`unverified_approvals`)
parks under `reviewer_unverified` before the verify gate, the approval record,
or the squash. A verdict the pinned comment has no room to persist, with the
evidence transaction its commands were minted as, parks under
`reviewer_unrecorded` before anything is published or acted on: a disposition
nothing durable backs would be answered again by a second reviewer the moment
the tick died, which is the rerun the persisted verdict exists to prevent.

Neither retries itself. A bare `/orchestrator continue` buys a fresh reviewer
(`awaiting._reviewer_retry_awaiting_action`), and a reply with words in it is
requirements the report never saw, which reach the developer first as on every
reviewer-side park. Each park drops the verdict it refuses in its own write.

A park is measured before its notice is posted, at the widest it writes -- the
notice's ledger entry and the watermark it stamps at the widest id, beside the
flags -- since a notice posted over a write GitHub then refuses leaves neither
a verdict nor a park durable, and the next tick's reviewer answers the round
again. A comment with no room for the park beside what the returned run staged
takes it over the comment as it stands instead: the run's usage and session go
unrecorded, a smaller loss than a park that never lands. One with no room even
for that posts and writes nothing, and says so. The comment is read once more
behind the notice, the park's last request, and whatever report or evidence
records another road moved meanwhile are carried onto the park's write rather
than written back over.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    report_record_state as _report_record_state,
    report_record_values as _record_values,
)
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_comment as _review_comment,
    review_verdicts as _verdicts,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_RETRY = "reply `/orchestrator continue` to run a fresh reviewer."

_UNRECORDED = (
    "the reviewer's verdict, or the verification evidence it reported, could "
    "not be recorded on the pinned comment -- which has no room for it, or "
    "for feedback in text it cannot carry -- so neither was acted on. Free "
    f"room on the pinned comment, then {_RETRY}"
)

_LAST_REVIEW_SESSION_ID = "last_review_session_id"

# What a record the comment does not carry reads as, apart from one it carries
# as `null`.
_ABSENT = object()


def parks_unverified(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    refusal: str,
) -> None:
    """Park an approval that relies on no valid evidence, dropping the verdict it left."""
    words = (
        "the reviewer approved without the verification evidence an approval "
        f"requires: {refusal}. The approval was not acted on; {_RETRY}"
    )
    _parks(gh, issue, state, run, (_state._REASON_REVIEWER_UNVERIFIED, words))


def parks_unrecorded(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
) -> None:
    """Park a verdict the pinned comment has no room to persist, acting on nothing."""
    _parks(gh, issue, state, run, (_state._REASON_REVIEWER_UNRECORDED, _UNRECORDED))


def _parks(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    park: tuple[str, str],
) -> None:
    """File one reviewer-side park under `park`'s reason and words, in one write, where it fits."""
    reason, words = park
    parked = _room_for_the_park(gh, issue, state, reason)
    if parked is None:
        log.error(
            "issue=#%d has no room on its pinned comment even for the %s park; "
            "posting and writing nothing", issue.number, reason,
        )
        return
    _guards._park_awaiting_human(
        gh,
        issue,
        parked,
        f"{config.HITL_MENTIONS} {words}",
        reason=reason,
        agent_role="reviewer",
        session_id=state.get(_LAST_REVIEW_SESSION_ID),
        review_round=run.round_n,
        retry_count=_guards._safe_int(state.get("retry_count")),
        pr_number=_guards._safe_int(run.pr_number),
        bounded=True,
    )
    # Re-set behind the guard, which clears whatever reason it found: the
    # awaiting-human branch reads it to hand the retry to a fresh reviewer.
    parked.set(_state._PARK_REASON, reason)
    # The notice is a request of its own; a report or evidence another road
    # settled during it is carried onto the park, whose write keeps it.
    if keeps_the_standing_records(gh, issue, parked) is None:
        return
    gh.write_pinned_state(issue, parked)


def keeps_the_standing_records(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool | None:
    """Carry onto `state` every report and evidence record the comment moved; False where one did, None unread.

    For a write about to go down over records another road may have recorded
    or settled since they were read -- a park's, or an approval's. Only those
    records are carried: nothing this road stages writes them, so any that
    differ are another road's, while what it did stage -- a verdict dropped,
    the park's own fields -- is left as staged.
    """
    durable = _review_comment._read(gh, issue, state, "keep the records another road settled")
    if durable is None:
        return None
    moved = _review_comment._moved(durable.data, state.data, _review_comment._STANDING_RECORDS)
    for field in moved:
        written = durable.data.get(field, _ABSENT)
        if written is _ABSENT:
            state.data.pop(field, None)
        else:
            state.set(field, written)
    return not moved


def _room_for_the_park(gh: GitHubClient, issue: Issue, state: PinnedState, reason: str) -> PinnedState | None:
    """The state the park goes down on: the one in hand, else the comment as it stands; None for neither.

    Either with the verdict's drop staged, which is part of the park's write.
    """
    _verdicts.drops_the_verdict(state)
    if _park_fits(state, reason):
        return state
    durable = _review_comment._read(gh, issue, state, "park a verdict with no room for what its run staged")
    if durable is None:
        return None
    _verdicts.drops_the_verdict(durable)
    return durable if _park_fits(durable, reason) else None


def _park_fits(state: PinnedState, reason: str) -> bool:
    """Whether the comment has room for a park on `state`, measured at its widest."""
    widest = _record_values.MAX_RECORDED_NUMBER
    reserved = PinnedState(comment_id=state.comment_id, state_data=dict(state.data))
    _comments._reserve_comment_slot(reserved, widest)
    reserved.set("awaiting_human", True)
    reserved.set(_state._PARK_REASON, reason)
    reserved.set("last_action_comment_id", widest)
    return _report_record_state.fits_the_comment(reserved.data)
