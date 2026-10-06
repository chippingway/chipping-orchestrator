# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The park a handed change request's developer launch takes where it may have run, and what moves it on instead.

A handed request whose developer launch the run ledger cannot rule out
(`review_handoffs.HandedLaunch.owed`) is never launched again: its start is
written before the spawn, so the developer may have run and had its result
discarded -- a live pause does exactly that -- or never been spawned, and a
second launch may pay for a second run over feedback one already answered.
The fixing tick's recovery (`review_resume.finishes_a_handed_request`) asks
first whether the request has moved on with nothing on the comment to show it
(`has_moved_on`): the evidence it claims no longer the settled evidence, a
commit the checkout carries that its pull request has not got, loose work in
the checkout, or a remote that moved past it -- a review nobody is asking
about any more, or a developer's work the stage's own bounce publishes or
holds over. A branch nobody could read proves nothing either way.

Where nothing shows the work, the launch parks under `agent_execution_failed`
(`parks`), the verdict dropped in the park's own write, so `/orchestrator
continue` replays the reviewer's feedback to a fresh developer session through
the anchor it was handed over with. So the park is taken only behind that
anchor: one something cleared is put back in the park's own write, and one
naming another comment holds the launch, with nothing posted ahead of the
notice and no park behind it -- judged behind the notice on the comment as
read there, so another road's repoint is kept.

The park's write is one guarded commit (`engine/pinned_commit.py`) under the
tick-state guard every validating reviewer write lands through (`review_writes.
lands`), declared as `PARK`: it owns the park's flags, the verdict it drops,
the anchor it puts back, and the ledger entry and thread read its notice adds,
and it is decided on the report, pull-request, verdict, and evidence records
the request stands on, the anchor, the park's flags, and the run ledger the
launch was read off as possibly started, each as the comment spells it. It is
prepared before the notice, with what posting that notice writes reserved at
its widest, so a comment that will not read, moved under those records, or
has no room for the park posts nothing. Behind the notice the subject is
resolved again, the branch read again, and the comment read last; a move
there drops the verdict for the stage's own road, a subject or branch nobody
could read holds it, and a park another road recorded there is kept as it
wrote it, with the verdict waiting. That write is committed over the reading
behind the notice, so a record another road moves after it, or a field it
owns that another road moved, refuses it with nothing written, as does a
comment that moved under the edit; an edit GitHub never confirmed lands
nothing anyone acts on. The run ledger read behind the notice is asked again
whether the launch may have started (`review_handoffs.HandedLaunch.owed`): one
that reads as the launch owed again parks nothing, so the request waits handed
beside the charge that ledger carries, for the next entry to launch. The park's event goes out only once its record is
down, and a refused or unconfirmed park leaves the verdict for a later tick,
whose notice asks again.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    report_commits as _commits,
    report_record_values as _record_values,
)
from orchestrator.workflow.stages.implementing import state as _implementing_state
from orchestrator.workflow.stages.validating import (
    review_claims as _claims,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_handoffs as _handoffs,
    review_parks as _parks,
    review_verdicts as _verdicts,
    review_writes as _review_writes,
    stranded as _stranded,
)
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")

_PARK_EXECUTION_FAILED = _implementing_state._PARK_EXECUTION_FAILED

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

_ANCHOR = _verdicts._FEEDBACK_ANCHOR

# The park's write: its flags with the ledger entry and thread read its notice
# adds, the verdict it drops, and the anchor it puts back; decided on what the
# request stands on, that anchor, the flags, and the run ledger.
PARK = _commits.ReportWrite(
    owned=_review_writes._PARKED | {_verdicts.RETURNED_VERDICT, _ANCHOR},
    decided_on=_review_writes.VERDICT_STANDS_ON | _review_writes._PARK_FLAGS | _handoffs.RUN_LEDGER | {_ANCHOR},
)

_UNFINISHED = (
    "the developer this reviewer's change request was handed to may have been "
    "started and left no result, so nothing says whether it ever ran, and the "
    "reviewer's feedback was not handed on a second time. Reply "
    "`/orchestrator continue` to hand that feedback to a fresh developer session."
)


def has_moved_on(
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    handed: _verdicts.ReturnedVerdict,
    wt: Path,
) -> bool | None:
    """Whether a handed request whose launch may have run has moved on: its claim superseded, or work on the branch.

    The evidence it claims no longer the settled evidence is a review nobody
    is asking about any more, and a commit the checkout at `wt` carries that
    its pull request has not got is work a developer did, which the stage's
    own bounce publishes -- and so is loose work in the checkout, or a remote
    that moved past it, which that bounce holds over with a notice of its own.
    False only where the branch is proved to carry nothing unpublished, and
    None where it could not be read (`stranded._StrandedEvidence.unread`): a
    fetch, a status, or a count that did not return proves nothing either
    way, so the verdict waits, with nothing written, for a later reading.
    """
    claim = handed.evidence
    if claim is not None and _claims.claim_standing(state, claim) is not _claims.ClaimStanding.SETTLED:
        return True
    branch = _stranded._stranded_evidence(spec, wt, state, issue)
    return None if branch.unread else not branch.settled


def parks(launch: _handoffs.HandedLaunch, moved_on: Callable[[], bool | None]) -> None:
    """Park `launch`, which may have run and left nothing to show, under `agent_execution_failed`, in one commit.

    `moved_on` is the caller's reading of whether the request has moved on
    with nothing on the comment to show it (`has_moved_on`) -- its claim
    superseded, or a commit on the branch its pull request has not got -- or
    None where the branch could not be read, which the caller took ahead of
    the park and which is taken again behind its notice.

    Only behind the feedback anchor `/orchestrator continue` replays: the
    pinned one naming the post the verdict records, or none -- something
    cleared it -- which the park's own write puts back. One naming another
    comment, or spelled as no whole id, would replay some other comment as
    this reviewer's feedback, and a verdict naming no post vouches for none,
    so either holds the launch with nothing posted or written. The park is
    prepared before its notice as the guarded commit it lands as
    (`_prepares`), and settled and committed behind it (`_lands`); its event
    goes out only once that commit is down.
    """
    context = launch.context
    if not _vouches(launch.handed, context.state.get(_ANCHOR)):
        log.warning(
            "issue=#%d its handed change request names feedback comment %s and "
            "the pinned anchor names %r; holding its launch rather than parking "
            "it where no continue could replay that feedback",
            context.issue.number, launch.handed.anchor, context.state.get(_ANCHOR),
        )
        return
    measured = dict(context.state.data)
    if not _prepares(launch):
        return
    posted = _parks._posts_the_notice(context.gh, context.issue, context.state, _UNFINISHED)
    lands = _lands(launch, measured, posted, moved_on)
    if lands is None or not _lands_the_park(launch):
        log.error(
            "issue=#%d wrote nothing behind the notice of its launch's park: its "
            "pinned comment would not read, moved what the park was decided on, "
            "or has no room beside what moved there", context.issue.number,
        )
        return
    if lands:
        context.gh.emit_event(
            "park_awaiting_human",
            issue_number=context.issue.number,
            stage=stage_name(context.gh.workflow_label(context.issue)),
            reason=_PARK_EXECUTION_FAILED,
        )


def _lands_the_park(launch: _handoffs.HandedLaunch) -> bool:
    """Land what the park settled on the state in hand, in its guarded commit (`PARK`); whether it landed."""
    context = launch.context
    return _review_writes.lands(context.gh, context.issue, context.state, PARK)


def _holds(launch: _handoffs.HandedLaunch, moved: bool | None) -> bool:
    """Whether what the park read behind its notice holds it for a later tick, with the request kept handed.

    A branch nobody could read (`moved` None) proves nothing either way, and a
    run ledger -- laid over the state in hand by that reading -- that rules
    out every start of this launch (`HandedLaunch.owed`) is a launch owed
    again, whose standing charge the next entry honors rather than parks.
    """
    return moved is None or launch.owed()


def _vouches(handed: _verdicts.ReturnedVerdict, pinned: object) -> bool:
    """Whether the anchor `pinned` is the post `handed` records, or none: something cleared it."""
    if handed.anchor is None:
        return False
    return pinned is None or _record_values.as_recorded_number(pinned) == handed.anchor


def _prepares(launch: _handoffs.HandedLaunch) -> bool:
    """Whether the park's commit would land now, its notice reserved; measured over the fresh comment, never written.

    Staged on a copy of the state in hand: the verdict handed dropped, the
    anchor put back as the verdict records it, and the park's flags set, with
    the ledger entry and thread read posting the notice adds reserved at their
    widest (`report_commits.ReportCommit.prepares`). A comment that will not
    read, was replaced, moved a record the park is decided on, or has no room
    for it posts nothing.
    """
    context = launch.context
    commit = _commits.ReportCommit(context.gh, context.issue, context.state)
    staged = commit.staging()
    _verdicts.drops_the_verdict(staged, only=launch.handed)
    staged.data.update({
        _ANCHOR: launch.handed.anchor,
        _AWAITING_HUMAN: True,
        _PARK_REASON: _PARK_EXECUTION_FAILED,
    })
    prepared = commit.prepares(staged, PARK, notice=True)
    if prepared.status is _commit_models.CommitStatus.PREPARED:
        return True
    log.error(
        "issue=#%d could not prepare the park of its handed change request's "
        "launch over the pinned comment (%s); posting and writing nothing",
        context.issue.number, prepared.refusal.value,
    )
    return False


def _lands(
    launch: _handoffs.HandedLaunch,
    measured: dict,
    posted: int | None,
    moved_on: Callable[[], bool | None],
) -> bool | None:
    """Settle the park's write behind its notice, which was `posted` as that id or None; whether it lands.

    The notice is a request of its own, so the subject is resolved again
    and the comment read against `measured`, the comment as the tick held
    it, carrying what moved. A moved subject, or a report, pull-request,
    verdict, or evidence record moved there, is a review nobody is asking
    about any more, and so is what `moved_on` reads again -- a claim
    superseded, or a commit that reached the branch while the notice was
    posted, which the stage's own bounce publishes -- read ahead of the
    comment, so the reading the park's commit is captured over is the last
    request before it, and a verdict another road put in place during the
    branch's own requests is kept: the verdict is dropped for the stage's
    own road, with no park. A park another road recorded there is that
    road's to answer, and is kept as it wrote it: no park lands over it,
    and the verdict waits. The anchor is held on that reading too: pointed
    at another comment it holds the launch, as does a subject or a branch
    nobody could read, or a notice nothing identified -- the verdict kept
    for a later tick. So is the run ledger, which the park was decided on as
    the tick read it: one that reads there as the launch owed again -- its
    start written away, its charge standing unstarted under this launch's
    own fingerprint -- lands no park, and the verdict waits handed beside
    that charge for the next entry to launch, honoring it. The anchor is judged, and carried, as that reading
    found it, and put back only by the commit that lands the park: staged
    on the state in hand ahead of that reading, a restore would read as
    this tick's own move over a repoint another road made behind the
    notice, or back beside a verdict and anchor another road dropped there.
    None where the comment will not read, which writes nothing.
    """
    context = launch.context
    stands = _review_coverage._subject_still_stands(context.gh, context.issue, context.state, launch.handed.subject)
    # The branch is read ahead of the comment: its own requests are long
    # enough for another road to write there, so the reading the park's
    # commit is captured over has to be the last request before it.
    moved = moved_on()
    reread = _review_comment._records_stand(context.gh, context.issue, context.state, measured, persisted=True)
    if reread is None:
        return None
    # The anchor as that reading spelled it, its absence included.
    context.state.data.pop(_ANCHOR, None)
    spelled = reread.read.get(_ANCHOR, _review_comment._ABSENT)
    if spelled is not _review_comment._ABSENT:
        context.state.set(_ANCHOR, spelled)
    if _review_comment._moved(reread.read, measured, _review_writes.VERDICT_STANDS_ON):
        stands = False
    if stands is False or moved:
        log.info(
            "issue=#%d what its handed change request stands on moved behind "
            "the park notice; dropping the verdict for the stage's own road", context.issue.number,
        )
        _verdicts.drops_the_verdict(context.state, only=launch.handed)
        return False
    if (
        not (stands and posted is not None)
        or _holds(launch, moved)
        or context.state.get(_AWAITING_HUMAN)
        or not _vouches(launch.handed, context.state.get(_ANCHOR))
    ):
        log.warning(
            "issue=#%d landed no park of its handed change request's launch: its "
            "anchor moved, its subject or branch would not read, its notice left no "
            "id, another park stands, or its run ledger shows the launch owed again",
            context.issue.number,
        )
        return False
    _verdicts.drops_the_verdict(context.state, only=launch.handed)
    context.state.data.update({
        _ANCHOR: launch.handed.anchor,
        _AWAITING_HUMAN: True,
        _PARK_REASON: _PARK_EXECUTION_FAILED,
    })
    return True
