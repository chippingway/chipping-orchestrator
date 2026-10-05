# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a finished developer run leaves, recorded before its code goes out.

The run is the only thing that can write this report, and it is gone the moment
the tick that ran it moves on. What happens next to the commit it made is not
quick and not certain: the size gate can freeze it for a human to adjudicate,
the push can fail, the process can die -- and on every one of those roads the
report exists nowhere but in the memory of a call that is about to return. So it
is recorded HERE, ahead of the gate and ahead of the push, where the only cost
of being wrong is a pinned write nothing reads. What is recorded -- the run's
own half, its revision and its receipt -- is minted by `report_minting`.

The record lands through this domain's guarded commit (`report_commits`),
decided on the report records the tick read and on the requirements baseline a
record may be stamped with. The revision was minted past those records, so a
record another road wrote since refuses the write; so does a park or a debt
flag another road moved where this write moves it too. Every field the write
does not own is the fresh comment's. The record's own reading is asked of the
record alone, and so is whether any comment could carry it; the room the record,
the push, the stale-approval hand-back, the binding and the settlement will each
need is asked of the very candidate the commit sends, never of the comment the
tick read, so room another road gave back since is room. Only a record that lands lets the tick on to the
gate and the push. A write refused for any reason but the record itself ends
the tick with nothing parked, nothing published, and nothing written: the
refusal withholds the tick's state from every whole-state write behind it, so
the stage that called in cannot put back the records the refusal kept. The
commit stays in the worktree, and the next tick finds whatever the comment then
says. A write that went out unconfirmed ends the tick too, its state withheld
the same way since nobody can say what the comment now carries, and the record,
if it landed, is the one the next tick binds -- no developer runs again, and no
revision is minted past it.

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
wrote it has ended, so nothing here can ask it for another. Published anyway,
the work would reach review with no report and the record of what the
developer said would be gone. Held here, before the size gate and the push,
nothing is published at all: the commit stays in the worktree, the branch is
untouched, and a reply resumes the session that can write the report again.
The notice says which refusal held it -- a quoted receipt marker, a report past
its own ceiling, a pinned comment with no room for it, or a record this build's
reader refuses for anything else -- because each is answered differently, and
`report_refusal_notices` is what words it. A comment the fresh reading finds
too full for the record is the room refusal too, measured there. The park is a
guarded commit of its own, prepared before its notice is posted with the
notice's own writes reserved, so a park the comment cannot carry posts nothing;
one refused only after its notice went out leaves that notice unrecorded.

What that resumed session comes back with is a report rather than a commit, and
`report_redelivery` beside this owner is what keeps it from being read as a
question: a reading about a LATER run and the branch it ran over, where this
owner is what one finished run's own report becomes.

The route is the caller's, because a stage knows which road produced the run
and this owner cannot: it is recorded on the transaction so that whatever
finishes one -- here, or a poll later through the reconciliation -- closes the
bookkeeping of the road it came from.

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
from orchestrator.workflow.engine import (
    guards as _guards,
    report_commits as _commits,
    report_delivery_state as _delivery_state,
    report_minting as _minting,
    report_outcome_models as _outcome_models,
    report_outcomes as _outcomes,
    report_record_state as _record_state,
    report_records as _records,
)
from orchestrator.workflow.engine.pinned_commit_models import CommitOutcome, CommitRefusal, CommitStatus
from orchestrator.workflow.engine.report_consumed_values import (
    CONSUMABLE_FIELDS as _CONSUMABLE_FIELDS,
    advance_consumed as _advance_consumed,
)
from orchestrator.workflow.engine.report_record_room import (
    CommentOverflow,
    LaterWrites,
    MeasuredWrite,
    RecordingRefusal,
)
from orchestrator.workflow.engine.report_refusal_notices import (
    explains_the_refusal as _explains_the_refusal,
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

# What recording a report writes: the delivery, and the park and the two debt
# flags a recorded report retires. Decided on everything the record was minted
# from.
_RECORDING = _commits.ReportWrite(
    owned=frozenset((
        _records.DELIVERED_REPORT, _PARK_REASON, OWED_REPORT, UNREPORTED_WORK,
    )),
    decided_on=_minting.MINTED_FROM,
)

# What this owner's park writes: its two flags, the debt, the work no report
# describes, and whatever a run's consumed input advances -- the watermarks
# among them keeping another road's moves beside these, as the ledger the
# notice enters does. Decided on what the refusal behind it was decided on.
_PARKING = _commits.ReportWrite(
    owned=frozenset((
        _AWAITING_HUMAN, _PARK_REASON, OWED_REPORT, UNREPORTED_WORK,
        *_CONSUMABLE_FIELDS,
    )),
    decided_on=_minting.MINTED_FROM,
)

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

    True is a tick this owner ended, and there are three ways to end one: a
    run that finished on a report this build cannot record, and a run that
    finished and handed over no usable report at all, both of which park and
    record nothing -- and a record whose write did not land as asked, which
    parks nothing and publishes nothing. False is the ordinary run whose
    report is now on the pinned comment, and every result no developer run
    produced.

    The write is this owner's rather than the caller's, and that is the whole
    point of the step: what makes the report recoverable is that it is DURABLE
    before the size gate reads the candidate and before the push sends it, so
    a tick that dies anywhere past the call comes back to an issue that can
    still say what its developer reported. It is a guarded commit
    (`report_commits`), and the record is durable only where it lands: the
    gate and the push are let through on nothing less. A comment that would
    not read, was replaced, or moved under the report records this one was
    minted from or under the flags it retires ends the tick, and the next one
    decides afresh over whatever the comment carries. A write sent and never
    confirmed ends it too, the caller's state left as it was and withheld
    from every whole-state write behind it, since whether the record landed,
    and what another road wrote past it, only a later reading can say: where
    it landed, the next tick binds it, with no second run and no second
    revision.

    A record this build will not store HOLDS rather than waving the code
    through. The record is what every later tick would publish from, so a
    report that cannot be written is one nothing can ever put on a pull
    request -- and the run that wrote it has ended, so there is nobody left to
    ask for another. Held here the cost is bounded and visible: nothing is
    published, the commit is still in the worktree, and the notice says what
    happened. Published instead, the reviewer would be handed work with no
    report while the only copy of what the developer said went out of memory
    with the tick.

    What happened is the refusal the record's own writer gave, never a guess
    at it. A report quoting a receipt marker is asked for again without the
    literal text, one past its ceiling for a shorter one, and one the comment
    has no room for is told which write measured too large, by how much, and
    whether rewriting the report can give that back -- which only a written-out
    report's text, escaped as the comment stores it, ever does -- while any
    other refusal is an invalid record, worded without a claim about
    length or room it has no measurement for. A reply asking for the wrong
    correction buys a run that is refused again.

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
    commit = _commits.ReportCommit(gh, issue, state)
    delivered = _minting.delivered_report(gh, issue, state, agent_result, handed)
    if delivered is None:
        return _unreported_run_holds(commit, agent_result, handed)
    refusal = _records_the_report(commit, delivered)
    if refusal is None:
        return False
    if isinstance(refusal, RecordingRefusal):
        staged = commit.staging()
        staged.set(UNREPORTED_WORK, True)
        parks_the_debt(commit, staged, _explains_the_refusal(
            issue.number, delivered, refusal,
            _NOTHING_ADDED if handed.route in _UNDER_REVIEW else _NOTHING_OPENED,
        ), handed.watermarks)
    return True


def _records_the_report(
    commit: _commits.ReportCommit, delivered: _records.DeliveredReport,
) -> RecordingRefusal | CommitOutcome | None:
    """Land one run's record over the fresh comment: None where it landed, or what stopped it.

    A `RecordingRefusal` is the record's own -- refused by its reading, or by
    the room it and every write after it would need, measured over the
    candidate the commit would send, or over the comment the tick holds where
    no comment at all could carry the record -- and is what the park explains.
    A comment that will not carry the candidate at all is that room refusal
    too, measured for the record's own write. Any
    other answer is the commit's: a comment that would not read, was replaced,
    or moved under the records this report was minted from or the fields it
    writes, which no rewrite of the report answers and the next tick reads
    afresh -- and a write sent and never confirmed, which may have landed.
    """
    # What no comment's room changes is asked here, of the record alone: its
    # own reading, and whether any comment could carry it. The room of THIS
    # comment is asked of the candidate the commit sends, over the reading it
    # lands on -- space another road gave back since the tick read the comment
    # is room, and space it took is not.
    alone = _pinned_state.PinnedState()
    refusal = _delivery_state.stage_delivered_report(alone, delivered)
    if isinstance(refusal, CommentOverflow):
        refusal = _delivery_state.stage_delivered_report(commit.staging(), delivered) or refusal
    if refusal is not None:
        return refusal
    staged = commit.staging()
    staged.set(_records.DELIVERED_REPORT, alone.get(_records.DELIVERED_REPORT))
    if staged.get(_PARK_REASON) == UNDELIVERABLE_REPORT:
        staged.set(_PARK_REASON, None)
    for owing in (OWED_REPORT, UNREPORTED_WORK):
        if staged.get(owing):
            staged.set(owing, None)
    landed = commit.lands(staged, _RECORDING.admitting(
        lambda fresh: _delivery_state.stage_delivered_report(fresh, delivered),
    ))
    if not isinstance(landed, CommitOutcome):
        return landed
    if landed.refusal is CommitRefusal.OVERFLOW:
        return CommentOverflow(
            write=MeasuredWrite.RECORD, later=LaterWrites(),
            size=landed.length, limit=_pinned_state.MAX_PINNED_BODY,
        )
    if landed.status is CommitStatus.COMMITTED:
        log.info(
            "issue=#%d recorded developer report revision %d before "
            "publishing the code it is about",
            commit.issue.number, delivered.report_revision,
        )
        return None
    log.error(
        "issue=#%d did not land developer report revision %d on its pinned "
        "comment (%s); publishing nothing, for a later tick to settle from "
        "what the comment carries", commit.issue.number,
        delivered.report_revision,
        (landed.refusal or landed.status).value,
    )
    return landed


def _unreported_run_holds(
    commit: _commits.ReportCommit,
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
        "for a human", commit.issue.number,
    )
    staged = commit.staging()
    staged.set(UNREPORTED_WORK, True)
    parks_the_debt(commit, staged, _UNREPORTED_PARK.format(
        mentions=config.HITL_MENTIONS,
        withheld=(
            _NOTHING_ADDED if handed.route in _UNDER_REVIEW
            else _NOTHING_OPENED
        ),
    ), handed.watermarks)
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
    silence. This is the stages' park, written over the whole state the
    caller holds; a refused recording or binding takes the same park through
    the guarded commit instead (`parks_the_debt`).

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
    if not _park_stands(issue, state):
        _guards._park_awaiting_human(
            gh, issue, state, notice, reason=UNDELIVERABLE_REPORT, bounded=True,
        )
        state.set(_PARK_REASON, UNDELIVERABLE_REPORT)
    state.set(OWED_REPORT, True)
    gh.write_pinned_state(issue, state)


def parks_the_debt(
    commit: _commits.ReportCommit,
    staged: _pinned_state.PinnedState,
    notice: str,
    consumed: tuple = (),
    *,
    publication: bool = False,
) -> None:
    """Take `parks_an_undeliverable_report`'s park through this domain's guarded commit.

    The park a refused recording or binding takes, written over the fresh
    comment rather than over the tick's whole state: `staged` is the tick's
    state as the road behind the refusal left it, and what the park writes --
    its flags, the debt, the work no report describes, the consumed input --
    lands beside every field another road moved meanwhile. Everything else is
    exactly that park's: once per attempt, bounded, the consumed input applied
    forward-only before the notice, and the debt set whether or not a notice is
    posted.

    The notice is the one effect the park makes before its record, so the
    record is prepared first, with the ledger entry and the watermark posting
    that notice adds reserved at their widest: a comment that will not read,
    was replaced, moved under the report records the refusal was decided on,
    or has no room for the park and its notice both posts nothing. Preparing
    is not landing, though. A comment another road moves between the two, or
    an edit GitHub refuses or never confirms, leaves the notice on the thread
    and no park recorded behind it; the tick still ends, with nothing it holds
    written (`report_commits`), and the road that took the park meets the
    same refusal again on a later tick and parks then.

    `publication` is a park decided on the publication a binding was made
    against as well as on the report records: one another road has since
    pointed at another pull request or receipt is a refusal of a publication
    that is no longer the issue's, so it posts and parks nothing, and the next
    tick decides over the publication the comment then names.
    """
    parking = _PARKING.on_the_publication() if publication else _PARKING
    _advance_consumed(staged, consumed)
    staged.set(OWED_REPORT, True)
    if not _park_stands(commit.issue, staged):
        staged.set(_AWAITING_HUMAN, True)
        staged.set(_PARK_REASON, UNDELIVERABLE_REPORT)
        if commit.prepares_a_notice(staged, parking).reading is None:
            log.error(
                "issue=#%d could not prepare the park over the developer "
                "report it owes; posting nothing", commit.issue.number,
            )
            return
        _guards._park_awaiting_human(
            commit.gh, commit.issue, staged, notice,
            reason=UNDELIVERABLE_REPORT, bounded=True,
        )
        staged.set(_PARK_REASON, UNDELIVERABLE_REPORT)
    landed = commit.lands(staged, parking)
    if landed.status is not CommitStatus.COMMITTED:
        log.error(
            "issue=#%d did not land the park over the developer report it "
            "owes (%s); holding the tick", commit.issue.number,
            (landed.refusal or landed.status).value,
        )


def _park_stands(issue: Issue, state: _pinned_state.PinnedState) -> bool:
    """Whether this owner's park is still standing, which a second notice says nothing new about."""
    standing = bool(
        state.get(_PARK_REASON) == UNDELIVERABLE_REPORT and state.get(_AWAITING_HUMAN),
    )
    if standing:
        log.warning(
            "issue=#%d still owes a developer report this workflow cannot "
            "deliver; holding the tick without a second notice", issue.number,
        )
    return standing
