# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round that finished on a report, and the write that closes it.

Every developer prompt this stage sends teaches the report contract, so a fix
round can end on `REPORT: READY` or `REPORT: VERIFIED` exactly as an initial
implementation can. When it does, the round owes a publication this tick cannot
guarantee: the push can fail, the post can fail, the process can die between
them.

So what such a round consumed and what its route spent do not close here. Both
ride the RECORD of the report -- durable before the size gate and before the
push -- and the write that completes the transaction is the one that applies
them, whether that is this tick's binding or the reconciliation ahead of a later
handler. Settled here instead, a crash in that window leaves the feedback
answered and the reviewer round spent for a report nobody published, with the
`pending_fix_*` replay source cleared along with them.

A mark rides beside that bookkeeping for the one thing the settlement cannot do:
move a label. It says THIS transaction settled, so the tick that finds the round
finished acts on evidence rather than on an inference from the settled report
and the head a pull request happens to carry -- both of which outlive every
transaction. It is cleared by the relabel that closes the round, and placed
against the comment through `round_marks` before that relabel is taken.

The park a failed push filed comes down in that same write, and for the same
reason the mark does: the retry that finally lands that push is durable before
the publication it carries is, so a relabel taken over the park hands a
reviewer an issue that still says it is waiting on a human.

Every other outcome a fix round reaches -- the `ACK:`, the question, the
timeout, the dirty tree -- writes no report at all, and those close their own
bookkeeping directly in `resume`. Telling the two apart is the whole of what
this owner is asked first.

`report_recovery` beside it is the other end of the same contract: the road a
tick that died in the publication window comes back to, which re-proves the
checkout rather than remembering a receipt and reaches the same hand-back.
"""
from __future__ import annotations

import logging

from orchestrator import config as _config
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import (
    report_binding as _report_binding,
    report_delivery as _report_delivery,
    report_outcomes as _report_outcomes,
    report_records as _report_records,
)
from orchestrator.workflow.stages.fixing import (
    models as _models,
    report_publication as _publication,
    round_marks as _round_marks,
    state as _state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    state as _dev_state,
)
from orchestrator.workflow.stages.validating import state as _validating_state
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The mark this route's settlement raises, recorded beside the bookkeeping it
# closes so the one write that completes a publication carries both. It is the
# only thing that says a fixing round's report SETTLED while the label never
# moved -- the settled report and the publication receipt are persistent, so a
# head a pull request is standing on proves nothing about this transaction.
_SETTLES_THE_ROUND = ((_state._SETTLED_ROUND, True),)

# The parks a landed publication is itself the answer to. Two reasons rather
# than the transient set, because what membership claims here is narrower than
# "a condition that may resolve with nobody commenting". `push_failed` is
# filed by the very push a recorded report rides, so a settlement proving that
# push landed has answered exactly the thing the notice asked about; and
# `stranded_unproved` is filed by the no-feedback bounce over a branch it could
# not place, so a round reaching a relabel at all has taken the reading that
# park was waiting for. The other transient reasons are about a SESSION or a
# reviewer run -- an `agent_timeout` park belongs to whichever round left it,
# and a later round can leave one over feedback this report says nothing about.
# Retired from here, that round's question would come down with a publication
# that is no answer to it, and the feedback it was parked over is already
# recorded as delivered.
_PARKS_A_PUBLICATION_ANSWERS = frozenset((
    _validating_state._REASON_PUSH_FAILED, _state._REASON_UNPROVED_BRANCH,
))

# What a reply that reached for the report contract and missed is held under.
# The run is over, so nothing here clears on its own: what it asks for is a
# session resumed to say the same thing in the shape the contract names.
_MISREAD_PARK = (
    "{mentions} this issue's developer run answered the pull request feedback "
    "with a message that reaches for the completion-report contract and does "
    "not keep it -- most often an `ACK:` line written beside a report, which "
    "the two readings contradict each other on. Nothing was published: any "
    "commit the run made is still in the worktree, the branch is untouched, "
    "and no report went onto the pull request. Read either half alone this "
    "would be wrong in a way nothing later could undo -- the `ACK:` returns "
    "the pull request to review as needing no change, and the report claims "
    "work nobody published. Reply and the orchestrator resumes the session; "
    "the answer it gives then is the one that counts."
)

# What a round that committed and did not FINISH is held under. The engine's
# own notice speaks for a developer that finished and declined to report, and
# would tell this human their session wrote something it never did.
_UNFINISHED_PARK = (
    "{mentions} this issue's developer left committed work on the branch "
    "answering the pull request feedback and did not finish -- a nonzero "
    "exit, a provider refusal, or a launch nothing invoked -- so no "
    "completion report of that work exists. Nothing was published: whatever "
    "this run committed is still in the worktree, the branch is untouched, "
    "and the pull request still stands on the commit it already carried. Work "
    "a review round earns reaches the pull request with the report of it or "
    "not at all, because a reviewer handed a commit nobody described has no "
    "account of what was done and no session left to ask. Reply and the "
    "orchestrator resumes the session; the report it writes then is the one "
    "that gets published, and it publishes this commit with it."
)

# What a report nothing left on this issue can move is held under. The wait
# is real either way; what the park adds is that somebody is told about it and
# that a reply is enough to end it.
_STALLED_PARK = (
    "{mentions} this issue still owes its pull request a developer report, and "
    "no road left on this workflow can get it there: there is no unread "
    "feedback to answer, nothing on the branch left to publish, and the "
    "publication itself declines -- most often because the issue was edited "
    "after the report was written, so the report answers requirements that "
    "have moved. Nothing was discarded: the report is still on the pinned "
    "comment and the pull request stands exactly where it did. Reply and the "
    "orchestrator resumes the session; the report it writes then answers the "
    "issue as it stands, supersedes the one that could not, and is the one "
    "that gets published. It needs no new commit to deliver it."
)

# What a round that committed over a report the issue still owes is held
# under. The run is over, so what this asks for is a fresh report written over
# the branch as it now stands -- which the reply's resume writes and which
# supersedes the record nothing could bind.
_UNDESCRIBED_PARK = (
    "{mentions} this issue's developer run committed work while a report an "
    "earlier run wrote is still owed to the pull request, and answered the "
    "feedback with no report of its own. Nothing was published: the commit is "
    "still in the worktree, the branch is untouched, and the earlier report is "
    "still on the pinned comment exactly as it was. That report describes the "
    "branch as it stood before this commit, so publishing it against the new "
    "head would hand a reviewer a description of work it does not cover -- and "
    "a report is the one thing this orchestrator cannot write for itself. "
    "Reply and the orchestrator resumes the session; the report it writes then "
    "describes the branch as it stands, supersedes the one that could not, and "
    "is the one that gets published."
)


def _holds_for_a_human(
    ctx: _models._FixingContext, run: _models._FixingResumeRun,
) -> bool:
    """The two replies this round may act on no half of, held for a human.

    True is a tick this call ended. Both roads announce once and hold the work
    exactly where it is: nothing published, any commit still in the worktree,
    the branch untouched, and a reply that resumes the session.

    A reply that reached for the report CONTRACT and missed is the first, which
    is what a run that used the markers without ending on either outcome is.
    `run.reported` is the one reading of that result this stage takes, taken
    where the run is built rather than parsed again here, so the two halves of
    the question cannot come back from two different readings of one message.
    The commonest miss is an `ACK:` line written beside a report, and the two
    halves of such a message say opposite things: read on the `ACK:` the pull
    request goes back to review as needing no change, and read on the report it
    claims work this orchestrator would then publish undescribed. A run that
    ALSO committed is the sharpest version -- left to the publication tail it
    pushes the commit and relabels with no report on the pull request at all.

    A round that COMMITTED over a report the issue already owed is the second.
    A delivered record carries no commit: what it is ABOUT is the branch as its
    own run left it, and the only thing on the comment that says so is that
    nothing has been committed over it since -- so a round that moves the head
    while an earlier tick's report is still owed makes that report
    undescriptive of the branch, and every road that publishes afterwards would
    bind it to a commit it never saw. Three readings, all of which have to
    hold: the debt is an EARLIER tick's (a round that wrote its own report
    replaces the record at a fresh revision, so report and commit are one run's
    and bind together), the head MOVED (a round that committed nothing
    republishes exactly the branch the standing report was written over), and
    the head READ, since a probe that answered nothing is no evidence of a
    commit and the disposition behind this refuses to push blind anyway.

    A run nobody heard the end of is asked all three like any other, which is
    why its head is read at all: a timeout is a way to commit, and the park it
    earns has a RECOVERY that pushes what the run left. Read as a run that
    committed nothing, that work would reach the pull request under a report
    written before it existed -- and the road that publishes it reads only the
    debt, which the earlier report still satisfies.

    The work is then recorded as UNDESCRIBED, which is what stops every later
    road binding over it, and the reply the park earns resumes the developer:
    the report that session writes describes the branch as it stands and
    supersedes the one that could not.

    The two are asked INDEPENDENTLY and only the notice picks between them,
    because a reply can be both: a malformed message is no report, so a run
    that wrote one and committed has left work over a standing record exactly
    as a plain question would. Answered on the misread alone, that round parks
    with the flag down and the old delivery still bindable -- and the commit,
    once some later road carries it to the pull request, gets the earlier
    round's report published over it. The notice is the misread one there,
    since the reply is what the human has to fix and the report their reply
    earns retires both.
    """
    misread = not run.reported and _report_outcomes._reached_for_a_report(
        run.dev_result,
    )
    undescribed = (
        not run.reported
        and bool(run.after_sha)
        and run.after_sha != run.before_sha
        and _report_delivery.owes_a_report(ctx.state)
    )
    if not misread and not undescribed:
        return False
    if undescribed:
        ctx.state.set(_report_delivery.UNREPORTED_WORK, True)
    _report_delivery.parks_an_undeliverable_report(
        ctx.gh, ctx.issue, ctx.state,
        (_MISREAD_PARK if misread else _UNDESCRIBED_PARK).format(
            mentions=_config.HITL_MENTIONS,
        ),
    )
    return True


def _is_report_only(
    ctx: _models._FixingContext, run: _models._FixingResumeRun,
) -> bool | None:
    """Whether this run's whole answer is the report it wrote, or None.

    The shape a fix prompt asks for by name: a reviewer item that wants report
    content only is answered in the report, with no commit for it. Read as an
    ordinary no-commit reply it would park as a question, and the report the
    round was asked for would sit unpublished on the pinned comment behind a
    human's reply.

    Every reading here is POSITIVE, which is the whole of what makes this road
    safe. What it has to establish is that the code this report describes is
    the code the pull request already carries, and no absence proves that: a
    HEAD nobody could read comes back empty, and a stranded-commit probe
    answers False both for a branch in sync and for a fetch that failed, a
    remote that moved, or a divergence nothing could count. Read as "nothing to
    publish", either would bind a report against the head the preflight
    happened to see and hand a reviewer a description of work that is not
    there.

    So: the run completed, its checkout named a head, that head is the one the
    run started on, that head is what the pull request is standing on, and the
    tree PROVED clean. A head that MOVED is a code change and belongs on the
    publication road; a head ahead of the pull request is a commit the push
    tail still owes it; and a tree is asked through `is_clean` rather than
    through the file list beside it, since that list answers empty for a status
    nobody could read -- an unread checkout is work nobody can see the shape
    of, which is the one thing a report may never be published over.

    The pull request is READ AGAIN for that comparison, and this road is the
    only one that has to. Every other publication here names a commit some
    push of this tick's just landed, which the size gate leases against the
    head it was proved on -- so a remote that moved under it refuses the push
    rather than the report. A report-only round pushes nothing at all: its
    evidence is that the head never moved, and the copy the preflight fetched
    says that of a pull request anybody may have pushed to in the minutes the
    developer was out. Compared against that copy, an untouched local checkout
    still matches, and a report describing the commit the round began on goes
    onto a pull request that has since moved past it -- with the issue handed
    back to the reviewer over a head nothing describes.

    A reading nobody could TAKE answers NONE rather than False, and that is
    three readings rather than one: a pull request reading this poll could not
    take, a HEAD the checkout would not name, and a tree status that
    established nothing. None of them is about the round. The report is valid
    and the branch is wherever it was; what is missing is an answer, and a
    later poll asks for it again -- so the caller holds everything where it
    stands, nothing published and nothing parked. Sent down the no-commit road
    instead, a valid report earns a park saying its developer asked a
    question, the human answering it is answering nothing, and the tick that
    finally publishes hands the issue to review under a park no settlement
    owns and no reviewer runs behind.

    The pull request reading is the WHOLE one, taken through
    `report_publication` rather than spelled here, so this road and the
    binding behind it ask one question rather than two that can disagree: the
    thread open, on this issue's own branch in this repository, and standing
    on the head the run left. Every member of it is a lazy request, so a
    reading that fails anywhere inside it -- the fetch, the state, the ref,
    the head repository, the sha -- answers None rather than raising out of
    the tick.

    False is what is left, and every one of those IS about the round: a head
    that moved, which is a code change and belongs on the publication road; a
    pull request this report may not go onto; and a tree this host PROVED is
    carrying something loose. The last of those is the one no later poll takes
    back, so a caller routes it through the terminal park `report_recovery`
    owns rather than through the question road, which no reply ends either.
    """
    if run.dev_result.timed_out or (
        run.after_sha and run.after_sha != run.before_sha
    ):
        return False
    if not run.after_sha:
        log.info(
            "issue=#%d could not read the checkout's head to say whether its "
            "report describes the published one; holding it for a tick that "
            "can", ctx.issue.number,
        )
        return None
    standing = _publication._stands_on(ctx, run.after_sha)
    if standing.unread:
        return None
    if standing.pull_request is None:
        return False
    tree = _worktree_status._worktree_status(run.worktree)
    return tree.is_clean if tree.readable else None


def _recording_stops_the_tick(
    ctx: _models._FixingContext,
    run: _models._FixingResumeRun,
    consumed: tuple,
    owed: _late_gate_models._Spends,
) -> bool:
    """Record this round's report, or hold the round that owes one.

    True is a tick this call ended, and there are two of those. A report this
    build cannot record parks with the commit still in the worktree and
    nothing published. So does a run that committed and did not FINISH: the
    engine leaves an incomplete run alone -- a nonzero exit, a provider
    refusal and a launch nothing invoked are failures other roads answer, and
    on the roads it serves nothing is published either way -- while this road
    publishes, so a commit pushed for such a run would reach the next reviewer
    with no account of it anywhere and no session left to ask. It is parked as
    the missing report it also is, in this road's own words rather than the
    engine's, which would tell a human their session wrote something it never
    did. The work is recorded as UNDESCRIBED beside the debt, because a record
    an earlier run left describes the branch before these commits.

    Both groups are handed over rather than derived here. `consumed` is the
    pairs the caller FROZE before it settled them, so the record names exactly
    what was applied rather than what is left to apply -- derived after the
    settlement it would be empty, and the recovery that reads this record back
    would have nothing to put the feedback beyond. `owed` is the route
    bookkeeping, which is not applied anywhere yet: the publication it belongs
    to is not this tick's to guarantee, so the write that COMPLETES the
    transaction is what closes it.

    The REQUIREMENTS revision is named for the same reason, off the snapshot
    the run took ahead of its own spawn rather than off the pinned baseline.
    The settlement re-reads the issue and refuses a report whose requirements
    have moved since the session that wrote it -- which is the whole guard
    against publishing an answer to questions nobody asked. Left empty, that
    comparison is taken against a baseline this very tick rewrote minutes
    later, so a reply that arrived while the developer worked reads as
    requirements the developer saw: the settlement finds no movement,
    publishes, and hands the reviewer a head over a comment the round's own
    frozen pairs deliberately left unread.

    The mark rides with it because one write applies them. A settlement can
    close `pending_fix_at`, the bookmarks and `review_round`, and it cannot
    move a label -- so without the mark the tick that finds the round finished
    would have to INFER it from the settled report and the head the pull
    request happens to carry, and neither of those says anything about this
    transaction: both outlive it, so a manual relabel onto `workflow:fixing`
    would be read as a round that just settled and bounce straight back to the
    reviewer without reading the feedback it was moved there to answer.

    The silent-park streak comes down here too, and here is the EARLIEST it
    can: a run that handed over a usable report is a session that spoke
    coherently, which is the whole of what that counter watches for, and every
    other road holding the same evidence -- the `ACK:` fast path, the push --
    drops it the moment it has it. Set BEFORE the recording, it rides that
    write and every write behind it, so a tick dying anywhere past this line
    comes back to a streak already down. Left to the publication instead, a
    round whose whole answer was its report drops nothing at all: the push
    that would have reset it never happens, and one later transient failure
    rotates a session this round proved healthy.
    """
    if run.reported:
        ctx.state.set(_dev_state._SILENT_PARK_COUNT, 0)
    if _report_delivery.recording_stops_the_tick(
        ctx.gh, ctx.issue, ctx.state, run.dev_result,
        _report_records.HandedRun(
            route=WorkflowLabel.FIXING,
            requirements_revision=run.requirements_revision,
            watermarks=consumed,
            spends=owed.fields + _SETTLES_THE_ROUND,
        ),
    ):
        return True
    if run.reported:
        return False
    ctx.state.set(_report_delivery.UNREPORTED_WORK, True)
    _report_delivery.parks_an_undeliverable_report(
        ctx.gh, ctx.issue, ctx.state,
        _UNFINISHED_PARK.format(mentions=_config.HITL_MENTIONS),
    )
    return True


def _hands_the_round_back(ctx: _models._FixingContext) -> None:
    """Retire the mark that round settled on, then send the reviewer the head.

    One owner for both halves because they are one act, and the ORDER is the
    whole of what makes the pair safe. The mark is durable and the relabel is
    not atomic with it, so one of the two windows has to be chosen: retired
    first, a tick that dies before the label moves leaves a round whose mark is
    down and whose issue is still on `workflow:fixing` -- and the no-feedback
    bounce behind it hands the reviewer the head on the very next poll.
    Relabelled first, that same death leaves a raised mark under a label that
    has moved on, and NOTHING later can tell it from a round that has just
    settled: a manual return to `workflow:fixing` carries no route anchor, owes
    no report, and reads back a handoff this stage itself settled under, so the
    mark would be spent on it and the feedback it was moved there to answer
    never scanned.

    So the write is this owner's and it lands first. Callers stage whatever
    else they owe into the state before calling; nothing they add afterwards
    would be durable in the window this ordering protects.

    The transaction this hand-back closes is STAMPED into that same write,
    where a mark was raised and the reading above could place it -- both, which
    is why the stamp is asked for through `round_marks` rather than taken here:
    that reading places every road reaching a relabel on its own reasons too,
    and those close no transaction at all. The mark is cleared by this write
    and the handoff beside it is persistent, so a comment whose round closed
    here goes on carrying a readable `workflow:fixing` handoff with both
    anchors already closed -- and a mark written back onto it by hand would
    otherwise be correlated into a second hand-back over whatever landed in
    between. What the stamp says is which transaction this was, so the next
    mark is a claim about one rather than about whatever settlement is still
    lying there.

    The parks a landed publication ANSWERS are staged here rather than by any
    of them, because the road that files one is never the road that settles it.
    A `push_failed` park is filed by the very push a recorded report rides, and
    the silent retry that finally lands that push writes its receipt durably
    BEFORE it publishes -- so a tick dying in between comes back to a comment
    still saying a human is owed an answer, beside a record the recovery ahead
    of the next handler binds, publishes and hands straight back. Relabelled
    over that park, the issue reaches `workflow:validating` still
    `awaiting_human`: a recovery poll nobody needed, and one nothing can end at
    all once the checkout it would retry against is gone. The `stranded_unproved`
    park the no-feedback bounce files comes down here for the same reason from
    the other end: it is waiting for a reading of the branch, and a round that
    reaches this relabel at all is one where that reading was taken. Only THOSE
    parks come down, and the narrowness is the point: a question park, a
    base-sync retry
    park and this stage's own report parks are each waiting on a person, and a
    round ending is no reply to them -- while an `agent_timeout` park belongs to
    whichever round left it, so a LATER round that timed out over feedback this
    report says nothing about would have its question retired by a publication
    that never answered it, with the feedback it was parked over already
    recorded as delivered. The one it does retire comes down with the mark and
    for the mark's reason: the round is over either way, and what a refused
    relabel withholds is only the move.

    Every road that can reach a relabel with the mark RAISED comes through here
    -- this round's own publication, the recovery's binding, the no-feedback
    bounce that republishes a stranded commit, and the tick that finds a round
    settled elsewhere -- so the mark is PLACED here rather than at any of them,
    and the relabel is what a mark that cannot be placed withholds. A
    settlement stamps the label it read afresh, which is the label a human who
    moved the issue while the developer ran has put it on -- and this owner can
    be reached on the very tick that recorded that move. Relabelled anyway, the
    live road takes the issue straight off the label that human chose while a
    later tick reading the identical comment would leave it alone: the same
    settlement would mean one thing when the tick survives to relabel and
    another when it dies first, since the recovery reading the identical
    comment on a later poll would leave the label alone. The mark comes down either way, because it is
    this round's and this round is over; what a refusal withholds is only the
    move.
    """
    places = _round_marks._places_the_round_in_hand(ctx.state)
    if places:
        _round_marks._stamps_the_round_handed_back(ctx.state)
    if ctx.state.get(_state._PARK_REASON) in _PARKS_A_PUBLICATION_ANSWERS:
        ctx.state.set(_state._AWAITING_HUMAN, False)
        ctx.state.set(_state._PARK_REASON, None)
    ctx.state.set(_state._SETTLED_ROUND, None)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    if places:
        ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)


def _holds_an_unpublished_report(
    ctx: _models._FixingContext, candidate: str = "",
) -> _models._ReportHold:
    """Put this round's report on the pull request; say where it is still owed.

    Bound to the publication first and posted second, in the engine's own two
    steps: the binding is one local write, so a post GitHub refuses leaves a
    transaction the reconciliation ahead of a later handler can finish rather
    than a delivery nothing would go back for.

    `candidate` is the commit the CALLER proved, and it is the only subject
    this binding will take. The receipt this stage writes on a landed push is
    deliberately not read here: it is persistent, so on any tick that did not
    push it names an older round's commit -- and a report bound to that one
    describes work the developer never did, on a pull request that may well be
    standing on it for reasons of its own. Each caller scopes the proof to its
    own attempt instead: the push tail names the commit its run left, the
    bounce reads the receipt its own push has just written, a report-only round
    names the head its pull request already stands on, and the recovery names a
    clean checkout it re-proved against that head.

    An empty candidate binds nothing. There is no commit to be about, so the
    report stays owed for a road that can name one.

    Work this issue records as UNDESCRIBED binds nothing either, whatever the
    caller proved. A delivered record carries no commit of its own: what it is
    ABOUT is the branch as its run left it, and the only thing that says so is
    that nothing has been committed over it since. Once something has, every
    road that publishes would otherwise bind that report to a commit it never
    saw. Held instead, the code may still go out and the review waits for a
    report written over the branch as it stands.

    Which publication that commit may be published onto is the one whole
    reading in `report_publication`, taken afresh and shared with the
    report-only road above so that the two cannot disagree. It holds
    `candidate` to the thread's own head, and it is the LAST moment anything
    can be: whoever proved this commit proved it earlier in the tick, against
    a pull request read earlier still, and a push landing in between moves the
    head off it. It holds the thread to being OPEN, to this issue's own
    branch, and to this repository -- a number alone brought the object back,
    and a second thread on another branch or a fork's carries this
    repository's ref names over somebody else's commits while standing on the
    very commit a caller proved. Bound to one of those, the subject would name
    this record's branch and repository over a thread nobody meant: the report
    posted there, the debt cleared, the handoff recorded, and nothing on the
    comment saying so.

    The DESCRIPTION comes back with it, off the same object and under the same
    boundary, because one report this workflow cannot both keep and manage is
    a `REPORT: VERIFIED` naming that very body: binding it there spends the
    description GitHub honours the closing reference in, and the line saying
    which session wrote the branch, on a report a comment could have carried.
    The binding refuses that one and parks with the delivery intact -- but
    only if it is TOLD, and the reading defaults to "the description is safe",
    so a caller that stays silent settles the report and hands the reviewer a
    pull request that no longer closes its issue. The object the report is
    POSTED onto is that same fresh one, so what the binding refuses and what
    it writes to are one reading.

    A reading this tick could not take holds everything where it stands. The
    report is valid and the record is intact; what is missing is an answer,
    and a later tick asks again. Bound on the defaults instead, a description
    nobody read would be spent exactly as an unread head would be. It is the
    one refusal here the answer names for itself (`unread`), because the road
    behind a caller matters only for that one: every other refusal is a
    reading that call TOOK, and the tick carries on to whatever answers it,
    while a request that failed may buy nothing at all -- least of all a
    notice telling a human the issue is stuck.

    `owed` holds the caller's relabel, which is what keeps a reviewer from
    being sent to a head whose report nothing on the pull request carries.
    """
    if not candidate or ctx.state.get(_report_delivery.UNREPORTED_WORK):
        return _models._ReportHold(
            owed=_report_delivery.owes_a_report(ctx.state),
        )
    standing = _publication._stands_on(ctx, candidate)
    if standing.pull_request is None:
        return _models._ReportHold(
            owed=_report_delivery.owes_a_report(ctx.state),
            unread=standing.unread,
        )
    _report_binding.binds_and_publishes(
        ctx.gh, ctx.issue, ctx.state, _report_binding.ReportPublication(
            pull_request=standing.pull_request,
            repo_slug=ctx.spec.slug,
            branch=_naming._resolve_branch_name(
                ctx.state, ctx.spec, ctx.issue.number,
            ),
            commit=candidate,
            describes_the_issue=standing.describes_the_issue,
        ),
    )
    return _models._ReportHold(
        owed=_report_delivery.owes_a_report(ctx.state),
    )


def _holds_a_stalled_report(ctx: _models._FixingContext) -> None:
    """Announce a report no road left on this issue can move, once.

    Reached by the no-feedback bounce, which is the last road of the tick:
    nothing unread, a branch PROVED to be carrying nothing the pull request
    has not got, and a report still owed. Every road that could have moved it
    has already declined, so the alternative is an issue finding those same
    three answers on every poll and doing nothing with any of them --
    silently, for as long as the pull request stays open.

    The middle one is a proof rather than a silence, and the bounce asks it
    ahead of this: a branch nothing could PLACE is a publication this host may
    yet make, so it holds under the reading it is waiting for and the next
    quiet poll publishes the commit, the report bound to it, and the round
    behind both. Answered here instead, a reading that comes back a poll later
    would find a park only a human clears.

    The way in that no other road covers is a transaction the engine will not
    settle because the REQUIREMENTS it was written against have moved: a human
    commented after the report was recorded, the publication stands down for a
    drift resume, and this stage has none. What supersedes such a report is
    another report, and what brings one is the reply this park asks for.

    A park anybody else has taken is left exactly as it is. The issue is
    already waiting on a human, which is what this would have asked for, and
    replacing the reason would answer their question on their behalf.
    """
    if ctx.state.get(_state._AWAITING_HUMAN):
        return
    _report_delivery.parks_an_undeliverable_report(
        ctx.gh, ctx.issue, ctx.state,
        _STALLED_PARK.format(mentions=_config.HITL_MENTIONS),
    )


def _finishes_a_reported_round(
    ctx: _models._FixingContext,
    owed: _late_gate_models._Spends,
    candidate: str,
) -> None:
    """Put this round's report on the pull request and close the round on it.

    A report still owed afterwards holds the relabel: the code is out and the
    report it is about is not, and a reviewer sent to that head would be
    reading an implementation nothing on the pull request describes. The round
    is not closed either -- what closes it is the write that completes the
    transaction, here or in the reconciliation ahead of a later handler.

    A reading the binding could not TAKE is owed the same as those and buys
    less: no publication, no relabel, no round spent, and no WRITE. It is the
    one refusal the hold names for itself, and it is answered ahead of the
    write below because the attempt behind it staged nothing -- so the comment
    that write would leave is the one already on the issue, a request spent
    saying nothing that can only lose a race with whoever wrote in between.
    The same answer the recovery gives on the other side of this binding; a
    later poll asks again and everything is where it was.

    The caller's own `owed` is applied either way. A round whose report rode a
    record has had these very fields written by the settlement already, so
    re-applying the frozen values is a no-op; a round that published without
    owing a report of its own has nothing else that would close them.

    A publication that DID settle closes the round through the same hand-back
    the recovery takes, so the mark it raised is placed before the label moves.
    This is the road where that matters most: a developer runs for minutes, and
    a human who moves the issue in that window is recorded by the settlement
    this call just made.
    """
    hold = _holds_an_unpublished_report(ctx, candidate)
    if hold.unread:
        return
    if hold.owed:
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    _late_gate_models._spend(ctx.state, owed)
    _hands_the_round_back(ctx)
