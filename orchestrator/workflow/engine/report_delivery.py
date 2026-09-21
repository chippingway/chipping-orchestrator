# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a finished developer run leaves, recorded before its code goes out.

The run is the only thing that can write this report, and it is gone the moment
the tick that ran it moves on. What happens next to the commit it made is not
quick and not certain: the size gate can freeze it for a human to adjudicate,
the push can fail, the process can die -- and on every one of those roads the
report exists nowhere but in the memory of a call that is about to return. So it
is recorded HERE, ahead of the gate and ahead of the push, where the only cost
of being wrong is a pinned write nothing reads.

What is recorded is the run's own half and no more. Which pull request the
report goes onto, on which branch, standing on which commit, is settled by the
publication that follows and is bound onto the record there. The requirements
revision is the exception and belongs to the run: it is the issue content this
session was actually handed, so a report held back by a failed push is still
stamped with the requirements it answers rather than with an edit it never saw.

A run that produced no report outcome records nothing at all where it did not
COMPLETE: a result no process produced -- what a caller synthesizes to publish
committed work an earlier run left is the orchestrator's own sentence, not a
developer's -- and every launch a shutdown, a timeout, a provider refusal or a
nonzero exit ended. Nothing here holds such a run, and a report an earlier run
delivered is still there to be bound onto the pull request its code reaches.

A run that DID complete and handed over no usable report is not that. Every
developer prompt teaches the contract, so what a finished run with no report
leaves is the contract broken rather than a road this workflow answers -- and
publishing it would send a reviewer an implementation nobody described, with no
session left to ask. So it is held here too, exactly as an unrecordable report
is: nothing published, the commit in the worktree, and a reply that resumes the
session that can still write one.

A report this build cannot record HOLDS the tick instead, parked for a human.
That is the one answer left: the record is what every later tick works from, so
a report that cannot be written is one nothing can publish -- and the run that
wrote it has ended, so nothing here can ask for a shorter one. Published
anyway, the work would reach review with no report and the record of what the
developer said would be gone. Held here, before the size gate and the push,
nothing is published at all: the commit stays in the worktree, the branch is
untouched, and a reply resumes the session that can write the report again.

What that resumed session comes back with is a report rather than a commit, and
`report_redelivery` beside this owner is what keeps it from being read as a
question: a reading about a LATER run and the branch it ran over, where this
owner is what one finished run's own report becomes.

The route is the caller's, because a stage knows which road produced the run
and this owner cannot: it is recorded on the transaction so that whatever
finishes one -- here, or a poll later through the reconciliation -- closes the
bookkeeping of the road it came from.

The revision moves past every report this issue has already recorded -- the
settled one, any transaction still outstanding, and any delivery still waiting
to be bound -- and the receipt is spelled from it. That is what keeps a second
report on the same commit a transaction of its own: a retry finds its own
comment by its receipt, so two reports sharing one would leave the later one
reading the earlier one's comment as its own publication, edited beyond
recognition.

The implementing stage's publication seam is what calls in, between proving a
clean tree and the size gate, and so do the two dispositions an open pull
request's fix loop runs: the requirements-drift one its review stages share,
which names the revision its resume was handed, and the reviewer-requested one
the `fixing` label covers. The binding that exchanges a delivery for the
transaction it becomes, once the push has reached a pull request, is
`report_binding`'s.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    guards as _guards,
    prompt_delivery as _prompt_delivery,
    report_delivery_state as _delivery_state,
    report_outcome_models as _outcome_models,
    report_outcomes as _outcomes,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_consumed_values import (
    advance_consumed as _advance_consumed,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_PARK_REASON = "park_reason"

_AWAITING_HUMAN = "awaiting_human"

# The debt of a report this workflow could not deliver, kept apart from the park
# that announced it: the flags are single, so a later park -- a resumed run that
# timed out, a question -- replaces the reason, and the debt must outlive it.
OWED_REPORT = "developer_report_owed"

# What a report this workflow cannot get onto the pull request is parked
# under. One reason for both roads that take it -- a report that cannot be
# recorded before the push, and one that cannot be bound to the publication
# after it -- because both are answered the same way: the session that wrote
# the report is gone, so what clears either is a human, and a reply resumes a
# developer that can write the report again.
UNDELIVERABLE_REPORT = "report_undeliverable"

# Work a COMPLETED run committed that no record of this issue's describes.
# Kept apart from the debt above, which any road that cannot deliver a report
# writes: a record of an EARLIER run is still a record, so the debt alone
# cannot tell an issue whose report is merely undelivered from one whose newest
# commits nobody has described at all. Only a fresh report retires it, since
# only a report written over the branch as it stands describes them -- and
# while it stands, the reply a park earns publishes nothing and the review is
# held for the report the work is missing.
UNREPORTED_WORK = "developer_report_unreported_work"

# The fresh review budget a requirements edit earned on an approved pull
# request, recorded where the publication that edit produced is still owed.
# `in_review` resets the round before it hands the issue back, because the
# approval was earned against requirements that are gone -- and a publication
# still owed then lands on `validating`, where a fix that reaches the pull
# request ordinarily spends a round. Spent from the budget that reset just
# made, the delayed road would hand the next reviewer one round less than the
# road where the same push landed at once. Retired with the debt it is about,
# by the settlement that ends it.
OWED_ROUND_RESET = "developer_report_owed_round_reset"

# How a transaction minted here is named. The revision is what makes it
# unique per issue, and the spelling is one the report header carries verbatim.
_RECEIPT = "issue-{issue}-report-{revision}"

# What "nothing was published" leaves standing, on each road that records a
# report. The implementing seam is the first publication of all, so there is no
# pull request yet and saying so is the whole of it. A requirements-drift
# resume under review is the other way round: the work it was asked about is
# already on an open pull request, and all a park here withholds is whatever
# that run has just added -- so the initial notice would tell a human the pull
# request they are reading does not exist.
_NOTHING_OPENED = (
    "the commit is still in the worktree, the branch is untouched, and no "
    "pull request was opened"
)

_NOTHING_ADDED = (
    "whatever this run committed is still in the worktree, the branch is "
    "untouched, and the pull request still stands on the commit it already "
    "carried"
)

# The roads that record a report for work an open pull request already carries.
# The fix loop is one of them: it runs under its own label, and the pull
# request the round is about was open before the round began.
_UNDER_REVIEW = frozenset((
    WorkflowLabel.VALIDATING, WorkflowLabel.IN_REVIEW, WorkflowLabel.FIXING,
))

_UNRECORDABLE_PARK = (
    "{mentions} this issue's developer run finished with a completion report "
    "this orchestrator cannot record on its pinned comment -- most likely one "
    "far past what a single comment holds -- so nothing was published: "
    "{withheld}. The report is recorded before any code goes out, "
    "because that record is the only thing a later tick could publish it "
    "from: a report that cannot be written is one this workflow has no way to "
    "put on a pull request, and publishing the code anyway would hand review "
    "an implementation with no report and no record of what the run said. "
    "Reply and the orchestrator resumes the session; the report it writes "
    "then is the one that gets published."
)


# The refusals that are not a contract violation: no process produced the
# result at all, or the one that did never got to the end of its own run. Each
# is a failure answered elsewhere, and none of them is a developer declining to
# report. Public for the stage that has to remember which commit such a run
# left, since a recovery of that commit later is owed no report either.
INCOMPLETE_RUNS = frozenset((
    _outcome_models._ReportRefusal.NOT_INVOKED,
    _outcome_models._ReportRefusal.INTERRUPTED,
    _outcome_models._ReportRefusal.TIMED_OUT,
    _outcome_models._ReportRefusal.PROVIDER_FAILURE,
    _outcome_models._ReportRefusal.NONZERO_EXIT,
))

_UNREPORTED_PARK = (
    "{mentions} this issue's developer run finished with committed work and "
    "no completion report this orchestrator can publish -- no report outcome "
    "at all, one that reached for the contract and missed, or one naming a "
    "report this orchestrator cannot hold against its own repository, whether "
    "because it is somebody else's or because the reading that would have "
    "proved it could not be taken. Nothing was published: {withheld}. "
    "Handing this work to review would send a reviewer an "
    "implementation nobody described, with no record of what was done and no "
    "session left to ask. Reply and the orchestrator resumes the session; the "
    "report it writes then is the one that gets published, and it needs no "
    "new commit to deliver it."
)


def owes_a_report(state: _pinned_state.PinnedState) -> bool:
    """Whether this issue still owes a pull request the report of a run.

    Both records, because the debt passes from one to the other and is
    discharged only at the end: a report a run delivered is owed until it is
    bound to a publication, and the transaction it becomes is owed until that
    publication carries it. A caller asking either alone would hand a reviewer
    an implementation whose report is sitting in the other.

    Asked of what the records CLAIM rather than of what they mean, so a record
    a hand edit truncated counts as a debt rather than as an issue that owes
    nothing. Neither claim is left unanswered: the binding parks a delivery it
    cannot read, and the reconciliation ahead of every handler parks a
    transaction it cannot -- both with the record untouched for whoever
    repairs or abandons it.

    The third is the debt every undeliverable park records as `OWED_REPORT`
    beside its reason, for the roads with no record to leave. Not the reason
    alone: any later park -- a resumed run that timed out -- replaces it, and
    the report that finally comes back would read as a question. Both are
    retired the moment a report IS recorded.
    """
    return (
        _delivery_state.carries_delivered_report(state)
        or _record_state.carries_pending_report(state)
        or state.get(_PARK_REASON) == UNDELIVERABLE_REPORT
        or bool(state.get(OWED_REPORT))
    )


def recording_stops_the_tick(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    route: WorkflowLabel | _records.HandedRun,
) -> bool:
    """Record what a finished run wrote, or hold the tick over what it wrote.

    True is a tick this owner ended, and there are two ways to end one: a run
    that finished on a report this build cannot record, and a run that
    finished and handed over no usable report at all. Both park and record
    nothing. False is the ordinary run whose report is now on the pinned
    comment, and every result no developer run produced.

    The write is this owner's rather than the caller's, and that is the whole
    point of the step: what makes the report recoverable is that it is DURABLE
    before the size gate reads the candidate and before the push sends it, so
    a tick that dies anywhere past the call comes back to an issue that can
    still say what its developer reported.

    A record this build will not store HOLDS rather than waving the code
    through. The record is what every later tick would publish from, so a
    report that cannot be written is one nothing can ever put on a pull
    request -- and the run that wrote it has ended, so there is nobody left to
    ask for a shorter one. Held here the cost is bounded and visible: nothing
    is published, the commit is still in the worktree, and the notice says
    what happened. Published instead, the reviewer would be handed work with
    no report while the only copy of what the developer said went out of
    memory with the tick.

    A record that IS stored retires the park this owner may have taken, since
    what that park asked for was exactly a report it could record -- and left
    standing it would hold the publication it was about to make possible.

    Either notice names what THIS road withheld. The implementing seam has no
    pull request yet, while a resume under review has one that stands exactly
    where it stood -- and a human reading the initial wording under their own
    open pull request would be told it was never opened.

    Both of them also record that this run's WORK is undescribed. A record an
    earlier run left is no account of commits made since, so a road that read
    the debt alone would publish them under a report written before they
    existed; only a report written over the branch as it stands retires it,
    which is the report the reply to either notice brings.

    And both carry the input the caller said this run's prompt delivered into
    the park's own write, so an issue left awaiting a human is never left
    awaiting one over feedback that still reads as unanswered.
    """
    handed = route if isinstance(route, _records.HandedRun) else _records.HandedRun(route)
    withheld = (
        _NOTHING_ADDED if handed.route in _UNDER_REVIEW else _NOTHING_OPENED
    )
    delivered = _delivered_report(gh, issue, state, agent_result, handed)
    if delivered is None:
        return _unreported_run_holds(gh, issue, state, agent_result, handed)
    if not _delivery_state.record_delivered_report(state, delivered):
        log.error(
            "issue=#%d wrote a developer report this build cannot record; "
            "publishing nothing and holding for a human", issue.number,
        )
        state.set(UNREPORTED_WORK, True)
        parks_an_undeliverable_report(
            gh, issue, state,
            _UNRECORDABLE_PARK.format(
                mentions=config.HITL_MENTIONS, withheld=withheld,
            ),
            consumed=handed.watermarks,
        )
        return True
    log.info(
        "issue=#%d recorded developer report revision %d before publishing "
        "the code it is about", issue.number, delivered.report_revision,
    )
    if state.get(_PARK_REASON) == UNDELIVERABLE_REPORT:
        state.set(_PARK_REASON, None)
    for owing in (OWED_REPORT, UNREPORTED_WORK):
        if state.get(owing):
            state.set(owing, None)
    gh.write_pinned_state(issue, state)
    return False


def _unreported_run_holds(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    handed: _records.HandedRun,
) -> bool:
    """Hold a completed run that handed over no report, or let the tick carry on.

    The contract every developer prompt teaches is that finished work ends on
    a report outcome, and that a run with a question, a disagreement, or
    nothing to say emits none and makes no commit. So a run that COMPLETED,
    left commits, and handed over no usable report is a contract violation
    rather than a road this workflow has an answer for -- and published
    anyway, the reviewer at the end of it is handed an implementation nobody
    described, with no record of what was done and no way to ask for one: the
    session is over.

    Held, nothing is published at all and a reply resumes the developer, which
    can write the report the work is missing. The park is what remembers the
    debt, since there is no report to record, and `UNREPORTED_WORK` beside it
    is what remembers that the commits this run made are the undescribed ones:
    a report an earlier run left describes the branch before them, so a road
    reading the debt alone would publish them under it.

    What the notice says was withheld is the ROAD's, since the two roads hold
    back different things: a pull request that was never opened, and one that
    stands where it stood. `handed` carries that road, and the input the run's
    prompt delivered, which rides the park's own write: a park durable over
    feedback still marked unread is one the next tick resumes the developer
    over again, with no human having said anything.

    A run that did NOT complete is left alone. A launch nothing invoked, a
    shutdown kill, a timeout, a provider refusal and a nonzero exit are
    failures other roads answer, and a report is not what any of them is
    missing. A result no process produced is the first of those: the contract
    has nobody to hold to it, since a caller that synthesizes one to publish
    committed work an earlier run left is writing the orchestrator's own
    sentence rather than reading a developer declining to report.
    """
    if _outcomes._report_outcome_of_run(agent_result) in INCOMPLETE_RUNS:
        return False
    log.error(
        "issue=#%d finished a developer run with committed work and no "
        "report this workflow can publish; publishing nothing and holding "
        "for a human", issue.number,
    )
    state.set(UNREPORTED_WORK, True)
    parks_an_undeliverable_report(
        gh, issue, state,
        _UNREPORTED_PARK.format(
            mentions=config.HITL_MENTIONS,
            withheld=(
                _NOTHING_ADDED if handed.route in _UNDER_REVIEW
                else _NOTHING_OPENED
            ),
        ),
        consumed=handed.watermarks,
    )
    return True


def parks_an_undeliverable_report(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    notice: str,
    *,
    consumed: tuple = (),
) -> None:
    """Announce a report this workflow cannot deliver, once, and hold it.

    Announced once per attempt, not once per issue. What is asked is whether
    this owner's park is still STANDING -- its reason on the comment and the
    issue still waiting on a human -- because that is the state a second
    notice would say nothing new about. A reply clears the waiting before the
    developer is resumed, so a report that fails to be delivered again is a
    fresh failure of a fresh attempt, and the human who asked for it hears
    about it.

    Its own reason, because that is the only thing that tells a later tick
    whose park it is standing over, and because the recovery is particular: a
    reply resumes the developer, which writes its report again. Nothing here
    retires it -- the resume that answers the reply is what clears the flags,
    exactly as it does for every other park a stage takes.

    Public because every road that cannot deliver a report takes it, each with
    its own notice; what they share is the flag, the reason, the debt, and the
    silence.

    A park still standing gets no second notice, but everything else this owner
    owes happens anyway, the WRITE included. What a caller staged is the reason
    it has to: the consumed pairs below are one such thing, and so is anything
    the road behind them released into the same state -- a recorded report a
    checkout can no longer publish, say. Skipped on the strength of the park
    already saying what the notice would, that write takes the release with it:
    the caller is told the tick ended, the comment still carries the record,
    and the very next tick publishes the report this road existed to withhold.
    The debt is set here either way, since a park taken before `OWED_REPORT`
    existed carries the reason alone.

    It is BOUNDED, like every park that ends an agent run: the run whose
    report failed took minutes, a human may have written in them, and the
    notice lands above that reply. Stamped at the notice, the watermark would
    cross it and the reply would be lost; walked through our own identified
    comments instead, it stays unread for the resume that answers this park.

    `consumed` is what the run's prompt already delivered, and it rides THIS
    write rather than a caller's afterwards. The park is durable the moment
    this returns, and a process dying between it and a caller's own write
    would leave the issue awaiting a human over input still marked unread --
    which the next tick reads as fresh feedback and resumes the developer on
    again, without a human having said anything and at the cost of another
    run.

    It is applied forward-only and BEFORE the notice, which is what the bounded
    walk needs: that walk starts at the issue-action boundary and crosses our
    own comments from there, so a boundary raised past the reply this round
    answered lets it cross our notice too. Raised afterwards it could not, and
    the notice would be handed to the next prompt as somebody's guidance.
    """
    _advance_consumed(state, consumed)
    if state.get(_PARK_REASON) == UNDELIVERABLE_REPORT and state.get(_AWAITING_HUMAN):
        log.warning(
            "issue=#%d still owes a developer report this workflow cannot "
            "deliver; holding the tick without a second notice", issue.number,
        )
    else:
        _guards._park_awaiting_human(
            gh, issue, state, notice, reason=UNDELIVERABLE_REPORT, bounded=True,
        )
        state.set(_PARK_REASON, UNDELIVERABLE_REPORT)
    state.set(OWED_REPORT, True)
    gh.write_pinned_state(issue, state)


def _delivered_report(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    route: WorkflowLabel | _records.HandedRun,
) -> _records.DeliveredReport | None:
    """The record one run's report outcome earns, or None where it earns none.

    None is every run that did not finish on a report: one that timed out, was
    interrupted, failed in its provider, exited nonzero, came back with a
    question, or reached for the contract and missed. None of those is a report
    anybody wrote, and recording one would publish a transcript under a header
    saying it is this issue's completion report.

    The bookkeeping and the consumed input the caller froze travel with it
    unread: what this owner knows about them is that the write which settles
    the report is the one that has to apply them, because on a road with no
    size gate behind it nothing else closes the round, and feedback a round
    answered may not be recorded as read until the report answering it lands.

    They travel with what this record SUPERSEDES as well, and that is why the
    merge is here rather than at a caller. A record still outstanding is a
    handover nothing confirmed, so none of what it owes has been written
    anywhere -- and this record replaces it: the delivery is dropped by the
    write that records this one, and the transaction by the binding behind it.
    Minted on the caller's pairs alone, a report that supersedes an unsettled
    one publishes and closes only its own road's bookkeeping, leaving a round
    nobody spent, bookmarks nobody cleared, and feedback a developer already
    answered reading as fresh. Carried, the one write that settles this report
    closes both handovers, which is the same exactly-once the frozen pair buys
    a replay.

    The settled report is not superseded by any of this: it is what the pull
    request already carries, and what it owed was written by the settlement
    that put it there.

    The requirements revision is the one the RUN was handed, never one
    computed here: a human editing the issue while the agent worked leaves the
    current content one revision further on than anything this session ever
    saw. A caller that snapshotted it names it on the `HandedRun` it passes;
    otherwise it is read off the pinned baseline the drift check ahead of the
    spawn put there.

    The revision moves past every report this issue has already recorded: the
    settled one, any transaction still outstanding, and any delivery still
    waiting to be bound. A settlement replaces the current report, so a
    revision that did not move forward would put an older report on the pull
    request's own record of what it carries -- and a transaction still
    outstanding may already have posted its comment and lost the response, so
    a report minted at its revision would carry its receipt too and read that
    comment as its own, edited beyond recognition. The delivery is the third
    for the road that overwrites one: the reply a park earns brings a report
    rather than a commit, and minted at the revision the record it replaces
    already used it would take that record's receipt with it. A record nobody
    can read counts as nothing here, which is the same answer every reader in
    this domain gives it.
    """
    carried = _carried_by_outcome(
        gh, _outcomes._report_outcome_of_run(agent_result),
    )
    if carried is None:
        return None
    # The records this one replaces, oldest first: a transaction is bound
    # before any delivery standing beside it, since the binding drops the
    # delivery it came from in the write that records it.
    superseded = tuple(outstanding for outstanding in (
        _record_state.read_pending_report(state),
        _delivery_state.read_delivered_report(state),
    ) if outstanding is not None)
    revision = 1 + max(
        (report.report_revision for report in (
            _settlement.read_current_report(state), *superseded,
        ) if report is not None),
        default=0,
    )
    handed = route if isinstance(route, _records.HandedRun) else _records.HandedRun(route)
    requirements = handed.requirements_revision or state.get(
        _prompt_delivery.PINNED_USER_CONTENT_HASH,
    )
    return _records.DeliveredReport(
        receipt=_RECEIPT.format(issue=issue.number, revision=revision),
        report_revision=revision,
        route=handed.route,
        requirements_revision=requirements if isinstance(requirements, str) else "",
        spends=_carried_on(
            [record.spends for record in superseded], handed.spends,
        ),
        watermarks=_carried_on(
            [record.watermarks for record in superseded], handed.watermarks,
        ),
        **carried,
    )


def _carried_on(superseded: list, handed: tuple) -> tuple:
    """One value per field, over every record a new one supersedes.

    The pairs are ``((field, value), ...)`` and each field is written once, so
    the merge is a mapping filled in the order it is handed: a field an
    outstanding record names and this run names again keeps THIS run's reading
    of it. Every one of these pairs was computed against a comment the
    superseded record wrote nothing to, so the later value already accounts for
    whatever the earlier one would have closed.

    The watermarks need no such care -- they are applied as a forward-only
    ratchet -- but they are merged through the same rule, because one rule over
    one shape is what keeps the two halves from drifting apart.
    """
    carried: dict = {}
    for pairs in (*superseded, handed):
        carried.update(pairs)
    return tuple(carried.items())


def _carried_by_outcome(
    gh: _client.GitHubClient, outcome: _outcome_models._ReportOutcome,
) -> dict | None:
    """What one report outcome contributes to a record, or None for no report.

    A READY report is a publication and carries its text. A VERIFIED one is an
    assertion about a report that is already somewhere, and carries the exact
    place and the digest read there -- nothing about it is believed here, and
    the transaction it becomes re-reads that location before anything settles.

    A verification this owner cannot hold against THIS repository is refused
    where it is read. The location is exact in both halves and still names a
    place anywhere on GitHub, and the publication it would be bound to is on
    this repository -- so a record made from it would re-read somebody else's
    thread and settle on what it found there. Which pull request it names is
    bound and refused where the publication is known, since no pull request
    exists to compare it against yet.

    That comparison is the one reading on this road that leaves the process:
    it completes a repository PyGithub may hold only a URL for, so it can fail
    the way any request can. Raised, it would leave a finished run's report
    neither recorded nor parked -- the tick would die carrying the only copy
    of what the developer said, with the commit in a worktree nothing has said
    anything about. So a reading nobody could take answers the same as one that
    named another repository: no record, and the run held for a human, which is
    the one road from here that loses nothing.
    """
    if isinstance(outcome, _outcome_models._ReadyReport):
        return {"mode": _records.ReportMode.PUBLISH, "report": outcome.report}
    if not isinstance(outcome, _outcome_models._VerifiedReport):
        return None
    try:
        own_repository = gh.is_own_repository(outcome.location.slug)
    except Exception:
        log.exception(
            "could not hold a verified report's repository (%s) against this "
            "one; recording no report for it", outcome.location.slug,
        )
        return None
    if not own_repository:
        log.error(
            "a developer verified a report this orchestrator cannot hold "
            "against its own repository (%s); recording no report for it",
            outcome.location.slug,
        )
        return None
    return {
        "mode": _records.ReportMode.VERIFY,
        "location": ReportLocation(
            pr_number=outcome.location.pull_number,
            comment_id=outcome.location.comment_id,
        ),
        "content_revision": outcome.revision,
    }
