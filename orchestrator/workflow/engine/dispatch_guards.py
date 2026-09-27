# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Apply pinned-state, cancellation, lifetime, and publication guards before dispatch.

Restart and cancellation precede ordinary stage routing. Stage-owned
reconciliation remains lazily resolved, and a pinned but unlabeled issue
is not greeted again. The developer-report transaction and the
verification-evidence transaction behind it are the reconciliations here that
belong to no stage, so they are bound at module scope rather than resolved
through `stage_targets.py`.
"""
from __future__ import annotations

import importlib
import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.base_sync import recovery_holds as _recovery_holds
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_transaction as _report_transaction,
    run_limit_dispatch as _run_limit_dispatch,
    stage_targets as _stage_targets,
    verification_transaction as _verification_transaction,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")



def _pinned_state_refuses(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    *,
    observed_closed: bool = False,
) -> bool:
    """True when what this issue's own pinned comment records stops the tick.

    ONE read, eight questions, because the read is what costs -- a comment
    walk per labelled issue per dispatch, on top of the one that issue's own
    handler makes.

    The first is a restart an operator has authorized. A settled cancellation
    whose `rejected` has been taken off is a fresh cycle waiting to be
    projected, and so is one this orchestrator already began and left
    half-applied -- a restart writes its target label before it retires the
    marker, so a tick that crashed in between finds a live-looking label over
    a record that still says cancelled.

    The second is a live late adjudication. An oversized committed candidate is
    adjudicated under ``workflow:decomposing``, and while that question is open
    the label is not a state anything else may set. A hand relabel cannot be
    refused where it is written -- the orchestrator never sees that write -- so
    it is caught here, the one place a label becomes a handler call: the issue
    is put back and left for the next tick rather than dispatched to whichever
    stage the new label named, which for ``ready`` or ``implementing`` would
    publish a candidate nobody adjudicated.

    The third is a child of a split whose snapshot has since been reclaimed.
    That one has to be asked HERE rather than inside a stage, because the issue
    it is about is one the dispatcher would otherwise have nothing to do with:
    a consumer that ended wears ``done`` or ``rejected``, reopening leaves the
    label where it was, and both are terminal no-ops below. Asking before the
    table also means a relabel straight to another stage cannot route around
    it. It costs nothing extra on the wire in the steady state -- the guard
    asks this host before it asks the remote.

    The fourth is an owner whose cycle a close already ended and whose cleanup
    has not finished. Cancellation is irreversible within a cycle, so a human
    who reopens the issue gets a fresh one -- but not while the old one still
    holds a branch, a ref, or a held pull request, because both labels an
    adjudication can be wearing name a handler that would act on the issue
    rather than settle it.

    The fifth is an unlabeled issue this orchestrator has already met. What an
    unlabeled issue reaches is the pickup handler, which GREETS one, and a
    pinned comment is the record of having been greeted -- so it is asked LAST
    and answered off the read alone. The one unlabeled issue it must not stop
    is the restart, which is answered four questions above it and returns
    before this one is reached.

    The restart and the unfinished cleanup are asked FIRST, because they are
    the ones that have to RUN rather than merely answer, and the three below
    them can refuse indefinitely. The reuse guard HOLDS a dispatch -- writing
    nothing, on purpose -- for as long as an ancestor's ref cannot be asked
    about, and an owner of its own cancelled cycle nested under such an
    ancestor would spend that entire outage never reconciling its own held PR,
    branch, or ref. Nothing is lost by the order: neither a cancelled cycle
    nor a restart mid-transaction starts any work, so neither question below
    is about anything either is going to do, and both are asked again on the
    tick after the ending or the fresh cycle is written.

    The restart comes ahead of the cancellation refusal within that pair, and
    only one of the two can be about a given issue: an issue with a marker
    standing, or with the authorizing gesture on its surface, is one the
    refusal would answer by handing it `rejected` again -- undoing the
    authorization the restart is halfway through honoring.

    The adjudication and the reclaimed snapshot step aside for the label the
    adjudication actually sits on, which is where every one of its own ticks
    is spent, and where an ancestor's snapshot is not what the issue is
    working from -- but only once the record PROVES the adjudication is this
    issue's own, and never past the reading that asks whether that record can
    be acted on at all. The label alone proves nothing: a child of a split
    closed while it was being decomposed comes back with ``decomposing`` exactly
    where it was and no generation at all, and its ancestor's ref may well
    have been reclaimed while it was closed. Waving that through on the label
    would spawn the decomposer against the reuse instructions in its body,
    naming a ref that is gone. So the read is taken first and the label is
    answered out of it. Imported at call time like the handlers below, since
    the stage tree imports this module.

    The sixth is the size gate's own unfinished business, and it is
    asked here for the reason the others are: it belongs to no one stage. A
    pair frozen for a pull request the remote already carries is durable and
    the count that follows it is not, so a tick that died in between leaves a
    record naming both commits with no number on it -- and the handler about
    to run would spawn a reviewer, resume a developer, or read a pull request
    still standing where the gate froze it, while the record goes on freezing
    the branch out of the base refresh. Taking the reading first is what makes
    the freeze a resumable step rather than a window; scoped by the record's
    own source stage, so it is answered on the stage it was entered on and
    nowhere else.

    The seventh is a developer report this issue recorded and never
    finished publishing, which belongs to no one stage for the same reason:
    the record outlives the run that wrote it, and the handler about to run
    would spawn a reviewer over a report nobody put on the pull request.
    Verification evidence recorded and never made current is answered right
    behind it, for the same reason and about the report it names. Where both
    sit among the reconciliations above them, and why, is on
    `_record_stops_the_tick` below, which is where they are ordered.

    The spent agent-run ledger is asked between those two groups, and the
    place is the whole point of it. Behind the pair that RUN, because a
    cancelled cycle still holding a branch and a restart an operator
    authorized are endings rather than work, and a park that outranked them
    would leave both owed for as long as the issue is stopped -- which here is
    for good. Ahead of everything else, because every road below is a stage's,
    and a stage reading `awaiting_human` answers it with the park it was
    written against: a resume on the next reply, a hold waiting on guidance, a
    classifier that refuses a command carrying none. None of those is an
    answer to an issue that has spent every run it may ever have.
    """
    late_relabel = importlib.import_module(_stage_targets._LATE_RELABEL_OWNER)
    state = late_relabel._dispatch_state(gh, issue)
    if state is None:
        return True
    late_close_observation = importlib.import_module(_stage_targets._LATE_CLOSE_OBSERVATION_OWNER)
    if observed_closed:
        # The poll read this issue closed and the worker has refetched it
        # since. A reopen in that window would leave the fresh object saying
        # open with a live cycle under it, so the reading is applied here
        # rather than re-derived from the object the guard is about to read.
        late_close_observation._mark_observed_close(gh, issue, state)
    if _cycle_stops_the_tick(gh, spec, issue, label, state):
        return True
    if _run_limit_dispatch._run_limit_holds_the_tick(
        gh, spec, issue, state,
        _run_limit_dispatch._spent_work_has_ended(gh, issue, state, label, observed_closed),
    ):
        return True
    if label == WorkflowLabel.DECOMPOSING and late_relabel._adjudicating(state):
        # The adjudication steps past the guards below because they are the
        # other stages' -- but not past the one that asks whether its own
        # record can be read. The publication group is the whole of what this
        # mode settles by and the one thing it cannot re-derive, so a partial
        # one is refused here rather than read as a candidate nothing had
        # published and routed back to `implementing` with the evidence
        # retired behind it. Nor past a standing auto-rebase anchor: a
        # measured generation is left for the decomposer the handler spawns,
        # and a replay no push published is no candidate for it to split.
        return _anchor_holds_the_tick(
            gh, spec, issue, label, state,
        ) or importlib.import_module(
            _stage_targets._LATE_RECONCILE_OWNER,
        )._reconciles_published_work(gh, spec, issue, label, state)
    return _record_stops_the_tick(gh, spec, issue, label, state)


def _record_stops_the_tick(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    state,
) -> bool:
    """Decide whether a live cycle permits dispatch on the issue's label.

    The caller first handles cancelled or reclaimed records, which stop the
    tick regardless of its label. Stage owners are imported at call time
    because the stage tree imports this module back.

    An auto-rebase anchor still standing is asked second, ahead of the
    reconciliation. The refresh settles an interrupted rebase before any
    handler runs, but a failed base fetch or a pull request that would not
    read returns before its recovery does -- and the handler about to be
    reached would spawn an agent over a replay no push has published. Whether
    that holds the tick is the base sync's to say; it sits below this
    layer, so it is bound at module scope.

    It is asked again BEHIND the reconciliation, because the late claim that
    released it may be the very record the reconciliation spends. A pair the
    size gate froze on an interrupted rebase's own head is one: settled here
    by the leased push it earns, it leaves the pull request carrying the
    replay and the anchor still pinned, and the handler behind would run
    before the recovery that finalizes it.

    A developer report this issue recorded and never finished publishing is
    answered last of the reconciliations, and behind that one for a reason: its
    own evidence asks whether the commit the report is about reached the pull
    request, and the reconciliation above is what settles a push that had been
    frozen and never counted. Asked first, it would read a candidate mid-gate
    as one whose code was never published and stand down every tick. Asked
    here, the world it proves is the one the tick that recorded it meant to
    hand on.

    Behind the SECOND anchor reading too, for the half of that reason the
    reconciliation alone does not cover: a pair settled by the leased push it
    earns leaves the pull request carrying the replay and the anchor still
    pinned, so a report published between the two would go onto work no
    recovery has finalized -- and its own evidence would prove that world
    sound, since the commit did reach the thread.

    It stays ahead of the reuse guard and the handler, because both are roads
    that carry on over a report nobody published -- and the reviewer at the end
    of them is the reader the report was written for.

    Verification evidence this issue recorded and has not made current is
    answered directly behind it, and for the same reason one step further on:
    evidence answers for a review subject naming the developer report, so a
    report still owed is a subject about to move and must settle first. It
    stays ahead of the reuse guard and the handler too, so whatever reads the
    evidence behind them reads it settled or honestly still owed.
    """
    late_relabel = importlib.import_module(_stage_targets._LATE_RELABEL_OWNER)
    if late_relabel._holds_the_label(gh, issue, state):
        log.warning(
            "repo=%s issue=#%s was relabelled %r while its committed candidate "
            "was under adjudication; not dispatching it",
            spec.slug, issue.number, label,
        )
        return True
    if _anchor_holds_the_tick(gh, spec, issue, label, state):
        return True
    late_reconcile = importlib.import_module(_stage_targets._LATE_RECONCILE_OWNER)
    if late_reconcile._reconciles_published_work(
        gh, spec, issue, label, state,
    ) or _anchor_holds_the_tick(gh, spec, issue, label, state):
        return True
    if _report_transaction._reconciles_pending_report(
        gh, spec, issue, label, state,
    ) or _verification_transaction._reconciles_pending_evidence(
        gh, spec, issue, label, state,
    ):
        return True
    late_reuse = importlib.import_module(_stage_targets._LATE_REUSE_OWNER)
    return (
        late_reuse._refuses_reuse(gh, spec, issue, state)
        or _greeted_already(spec, issue, label, state)
    )


def _anchor_holds_the_tick(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    state,
) -> bool:
    """Whether a standing auto-rebase anchor stops this tick, answered if so.

    Whether it holds, and what a held tick is owed, are the base sync's to say -- a missing checkout restored where the
    refresh drives the label, and the refresh's own ineligible answer where it
    does not. This is where the two meet, so every place the dispatcher asks
    it takes the same road.
    """
    checkout = _worktree_paths._worktree_path(spec, issue.number)
    if not _recovery_holds._recovery_holds_dispatch(
        issue, label, state, checkout,
    ):
        return False
    log.info(
        "repo=%s issue=#%s carries an auto-rebase anchor no recovery has "
        "ended; holding the %r handler so no agent runs over an "
        "unpublished replay",
        spec.slug, issue.number, label,
    )
    _recovery_holds._answers_a_held_anchor(gh, spec, issue, state, label)
    return True


def _greeted_already(
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    state: PinnedState,
) -> bool:
    """True when an unlabeled issue is one this orchestrator has already met.

    What an unlabeled issue reaches is the pickup handler, and what pickup
    does is GREET one: it posts the "picking this up" comment, baselines the
    drift hash over a thread it assumes nobody has worked, and mints the
    issue's pinned comment. Every one of those is a first-contact act.

    An issue that already carries a pinned comment has been through it, so
    greeting it again writes a SECOND one -- and `read_pinned_state` answers
    with the first authenticated comment it finds, so the new record is
    invisible from the moment it is written while the old one goes on
    deciding. What the old one carries is a finished workflow: a `pr_number`
    and a branch nothing will reconcile, a watermark over comments the fresh
    greeting has not read, a terminal somebody reached. Two records, one
    unreachable, is worse than either.

    So an issue whose workflow label a human took off is left exactly where
    they left it, and said so once a tick. The way back into the workflow is
    applying a workflow label, which is the same way an outsider's issue is
    driven by hand. The one unlabeled issue this does NOT stop is the restart,
    which is answered two guards above and never reaches here.
    """
    if label is not None or state.comment_id is None:
        return False
    log.info(
        "repo=%s issue=#%s carries a pinned comment and no workflow label; "
        "leaving it where it was rather than greeting it a second time",
        spec.slug, issue.number,
    )
    return True


def _cycle_stops_the_tick(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: str | None,
    state: PinnedState,
) -> bool:
    """Whether a late cycle's own business is the whole of this dispatch.

    The two guards that RUN rather than merely answer, kept together because
    only one of them can be about a given issue and the order between them is
    the whole reason: a restart applies its target label before it retires its
    marker, so a tick that crashed in between finds a live-looking label over
    a record that still says cancelled -- and the refusal below would answer
    that by handing the issue `rejected` again, undoing the authorization the
    restart is halfway through honoring.

    Imported at call time like every other stage owner this module reaches,
    since the stage tree imports this module.
    """
    late_restart = importlib.import_module(_stage_targets._LATE_RESTART_OWNER)
    if late_restart._restarts(gh, spec, issue, label, state):
        return True
    late_cancellation = importlib.import_module(_stage_targets._LATE_CANCELLATION_OWNER)
    return late_cancellation._refuses_cancelled(
        gh, spec, issue, label, state,
    )


def _parked_past_the_mark(spec: _config_models.RepoSpec, issue: Issue) -> bool:
    """Whether a control label the closed reading was let past applies again.

    `backlog` / `paused` park an issue outside the state machine, and the one
    thing that may still happen under one is recording a close: an observed
    close ends a late cycle irreversibly, the pass that would record it is the
    one the park would have dropped, and a mark deferred is a mark lost. That
    is the whole of the waiver -- the mark is behind this, and the ending it
    earns is deferred by the same label wherever it is entered.

    So everything past the mark is parked again, and it has to be by asking
    rather than by inference: a record with no late cycle marks nothing at
    all, and the guard above answers `False` for one, which would otherwise
    put a parked issue in front of the very handler the label exists to stop.

    Costs no request: the labels are already on the object this was handed.
    """
    skip_label = hard_skip_control_label(issue)
    if skip_label is None:
        return False
    log.info(
        "repo=%s issue=#%s has %r and owns no cycle a close would end; "
        "skipping everything the park defers",
        spec.slug, issue.number, skip_label,
    )
    return True
