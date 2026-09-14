# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Release candidate holds and close the exact publication superseded by a late split.

Published work is re-read on both sides of the notice preparation before
closure. The completed supersession is recorded only after its proof and
external effects succeed.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split.obligations import LateResourceKind, LateResourceState
from orchestrator.workflow.stages.decomposition import (
    late_hold_release as _late_hold_release,
    late_publication as _late_publication,
    late_split_notices as _late_split_notices,
    late_supersession_reading as _late_supersession_reading,
    late_supersession_state as _late_supersession_state,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.models import _SplitPlan

log = logging.getLogger("orchestrator.workflow")



_DISAGREEING_PUBLICATION_PARK = (
    "the committed candidate for this issue was split and its snapshot and "
    "children are safe, but {disagreement}. So no child was activated and "
    "the branch was not reclaimed: what the recorded verdict was taken over "
    "is not what that pull request carries now, and finishing the split "
    "behind it would hand the work to children -- and delete the branch it "
    "points at -- over a change nobody adjudicated. Reconcile the pull "
    "request by hand, and the next tick settles the same recorded verdict."
)


def _superseded(
    context: _LateContext, plan: _SplitPlan, snapshot_ref: str,
) -> bool:
    """Close the pull request this candidate stands on, or park.

    Only the pull request this generation was entered on or actually HELD.
    `pr_number` is whichever one the issue currently records and may name an
    implementation somebody else opened; the publication entry and the hold's
    own record each name one this cycle acted on, and superseding anything
    else would close a change nobody adjudicated.

    The hold comes off first, so a pull request that ends up closed does not
    also end up wearing a "do not merge" notice forever. A release that failed
    on a still-open pull request parks on its own, which is what stops this
    from closing a change whose description is not back where it belongs.

    Run on every pass, including one where the ledger already reads
    `reconciled`. That entry records what an EARLIER pass did, and a pull
    request is not a thing that stays where it was put: a human who reopens it
    between that write and the resume would otherwise have the resume skip
    straight past, report settled, and let the children loose beside a change
    still carrying the superseded work. Re-asking costs one fetch and one
    comment listing, and neither step repeats anything -- the notice is gated
    on this generation's own marker already on the thread, and a pull request
    that is not open is left exactly as it is.

    Which pull request that IS is decided by the side of publication the
    generation was entered on, and by the ENTRY rather than by the hold beside
    it -- both can name the same pull request, since a generation entered past
    the first push holds the one the work is already on. That one goes through
    the proof one owner down: its head unmoved and its state its human's,
    because the transaction behind this deletes the branch and hands the work
    to children, and a change superseded over a commit nobody adjudicated is
    one nothing takes back. A generation entered before publication has only
    the hold's record to go on, and that names the plan pull request this
    cycle marked. A record with neither has no pull request to close, and the
    absence is the answer: its candidate has never been on one.
    """
    if context.generation.publication.is_complete:
        return _superseded_publication(context, plan, snapshot_ref)
    number = context.generation.plan_pr_number
    if number is None:
        return True
    settled = _released_hold(context) and _closed_over_notice(
        context, number, _late_split_notices._supersession_notice(context, plan, snapshot_ref),
    )
    if not settled:
        return _late_supersession_state._unsuperseded(context, number)
    _late_supersession_state._recorded_resource(
        context,
        LateResourceKind.PLAN_PR,
        str(number),
        LateResourceState.RECONCILED,
    )
    return True


def _released_hold(context: _LateContext) -> bool:
    """Take this cycle's hold off before anything closes what wears it.

    A pull request closed while it still carries a "do not merge" notice
    carries it for good, and the description that notice displaced is the only
    copy there was -- so the release runs first, and a failure stops the close
    rather than shortening it. Which failures stop anything is the release's
    own answer: one on a pull request a human has already settled reports
    nothing, since a hold nobody can merge under is untidy and no more.

    A generation that took no hold releases nothing and answers yes. What says
    which pull request to close is the record beside it, and that says so with
    or without a notice on it.
    """
    release = _late_hold_release._release_hold(
        context.gh, context.issue, context.generation,
    )
    context.generation = release.generation
    return not release.failed


def _superseded_publication(
    context: _LateContext, plan: _SplitPlan, snapshot_ref: str,
) -> bool:
    """Close the pull request this split's candidate was measured on, or park.

    The verdict was a claim about what THAT pull request would come to with
    the candidate in it, and a split answers it by replacing the work rather
    than pushing it -- so the pull request is closed over a notice that says
    where the work went, exactly as a held plan one is. Without it the
    transaction hands the issue to `umbrella`, activates the children, and
    reclaims the branch, leaving an open change carrying superseded work with
    nothing on it saying so and no branch behind it.

    Proved before it is closed, and the proof is the settlement's own: the
    entry the gate froze names the pull request and the head it was standing
    on, neither of which can be re-derived. A pull request nothing could read
    is a park with a durable retry. One a human has since MERGED or CLOSED is
    a change they settled while the adjudication was open, and closing it over
    a supersession -- or letting children loose beside a merge -- is not this
    tick's to do. One somebody PUSHED to is the same refusal one field over:
    what the verdict was taken over is not what the pull request carries now.

    The hold comes off first, for the reason the caller takes it off before
    closing a held pull request: a change closed while it still wears a "do
    not merge" notice wears it for good. The release is where the refusals
    that matter are decided, so one it reports parks here rather than being
    stepped over.

    That the entry names a pull request at all is the caller's gate, which
    routes here on the whole group being readable. The check below is the
    floor under it, closing nothing where a record could not name one.

    The reading carries this adjudication's own receipt with it, because the
    step behind this one is not the last: a tick that closed the pull request
    and died before the retirement comes back to a `closed` reading it cannot
    tell from a human's without the thread. Read as an external settlement it
    would park for good, with the children blocked behind a supersession this
    transaction had already made. What the receipt answers is the STATE and
    only that: the head is proved on that path exactly as on the open one,
    because a close does not stop anybody pushing to the branch behind it.

    What that reading licenses, and what it may not be spent on, is the owner
    below.
    """
    number = context.generation.publication.published_pr_number
    if number is None:
        return True
    if not _released_hold(context):
        return _late_supersession_state._unsuperseded(context, number)
    return _proved_and_closed(
        context, number, _late_split_notices._supersession_notice(context, plan, snapshot_ref),
    )


def _proved_and_closed(
    context: _LateContext, number: int, notice: str,
) -> bool:
    """Prove the publication is still the one, then supersede it.

    The reading here is not what the close is made against, and that is the
    other half of the rule the caller states. The receipt costs a comment
    listing, which is a round-trip of its own standing between the state and
    head read beside it and the write those two license -- so the state and
    the head are asked ONCE MORE by the owner below, immediately in front of
    that write and with no listing behind them. A change a human settled or
    somebody pushed to inside this window is therefore left untouched: no
    notice on it, no close, and a park. Discovering it one step later would
    mean marking and closing a change nobody adjudicated and only then
    refusing to finish.

    A pull request already closed over this adjudication's own receipt is the
    one shape that writes nothing at all, and it is recognized here rather
    than below. `supersede_pr` would post no second notice and close nothing
    already closed, so both the confirming read and the write would be spent
    on a call with no effect -- and the state this reading proved is the
    evidence that says so. Every other way of being closed was refused a
    statement earlier, so reaching this line closed means closed by us.
    """
    reading = _late_publication._read_publication(
        context.gh, context.issue, number, _late_split_notices._supersession_marker(context),
    )
    if reading.refused:
        return _late_supersession_state._unsuperseded(context, number)
    unsettled = _late_supersession_reading._publication_is_still_the_one(context, reading, number)
    if unsettled:
        return _late_supersession_state._parked_publication(
            context, number, unsettled, _DISAGREEING_PUBLICATION_PARK,
        )
    if reading.state == _late_publication.CLOSED:
        return _late_supersession_state._recorded_supersession(context, number)
    return _closed_publication(context, number, notice, reading.superseded)


def _closed_publication(
    context: _LateContext, number: int, notice: str, said: bool,
) -> bool:
    """Confirm the publication has not moved, then close it, then record it.

    The confirming read is what separates this from a close made on evidence
    one round-trip old. What it asks is the state and the head and nothing
    else -- no receipt, since the caller already read that one -- so it is the
    last thing to reach GitHub before the write it licenses, and the window
    left is the write itself.

    `said` is that receipt, carried down rather than looked up again. The
    helper below would otherwise scan the thread for it before posting, which
    is a request standing between this confirmation and the close it
    authorizes -- long enough for a human to settle the change, and the notice
    would then land on a settlement somebody else made and report success.
    Nothing can move the answer in between: the marker counts only on a
    comment of OURS, and this pass has posted none since the caller looked.

    A publication that moved inside the first window is left exactly as its
    human put it. Nothing is posted onto it and nothing is closed: a change
    somebody settled while this was reading is theirs, and a branch somebody
    pushed to is not the one the verdict was taken over.
    """
    confirmed = _late_publication._read_publication(
        context.gh, context.issue, number,
    )
    if confirmed.refused:
        return _late_supersession_state._unsuperseded(context, number)
    overtaken = _late_supersession_reading._publication_is_still_the_one(context, confirmed, number)
    if overtaken:
        return _late_supersession_state._parked_publication(
            context, number, overtaken, _DISAGREEING_PUBLICATION_PARK,
        )
    if not _superseded_pull_request(context, confirmed, notice, said):
        return _late_supersession_state._unsuperseded(context, number)
    return _late_supersession_state._recorded_supersession(context, number)


def _superseded_pull_request(
    context: _LateContext,
    confirmed: _late_publication._PublicationReading,
    notice: str,
    said: bool,
) -> bool:
    """Hand one just-confirmed pull request its supersession, and nothing else.

    `said` goes with the call so the helper spends no request of its own
    looking for a receipt this pass already read. What is left between the
    confirmation above and the write is nothing at all.

    Guarded for the reason the plan road guards its fetch: by the time this
    runs the children are already live, so an exception would strand them
    behind a traceback instead of behind a retry. A reading that carried no
    pull request carried a refusal, which the caller has already answered --
    this is the floor under it, superseding nothing it was handed nothing for.
    """
    if confirmed.pull_request is None:
        return False
    try:
        return context.gh.supersede_pr(
            confirmed.pull_request,
            notice=notice,
            marker=_late_split_notices._supersession_marker(context),
            carries_marker=said,
        )
    except Exception:
        log.exception(
            "issue=#%d could not supersede the publication it had confirmed",
            context.issue.number,
        )
        return False


def _closed_over_notice(
    context: _LateContext, number: int, notice: str,
) -> bool:
    """Fetch the held pull request and hand it its supersession.

    The fetch is guarded here rather than left to the helper, because a
    PyGithub pull request is lazy and the request that can fail is as likely
    to be this one as the write behind it -- and by the time this runs the
    children are already live, so an exception would strand them behind a
    traceback instead of behind a retry.
    """
    try:
        held = context.gh.get_pr(number)
    except Exception:
        log.exception(
            "issue=#%d could not read held PR #%d to supersede it",
            context.issue.number, number,
        )
        return False
    return context.gh.supersede_pr(
        held, notice=notice, marker=_late_split_notices._supersession_marker(context),
    )
