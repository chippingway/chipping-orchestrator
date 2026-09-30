# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A persisted change request handed to the one developer it owes.

No live reviewer round persists a verdict yet, so no live round hands one
here: the dormant disposition service (`review_disposition`) does, right behind
proving the request still carried, its subject standing, and its evidence
settled.
What is here is that handoff, entered directly: through the very decision
the request was persisted from, in the tick its reviewer returned
(`hands_the_request_over`), and from the persisted request alone on a later
tick, which holds no decision (`hands_the_waiting_request_over`) -- either way
on the pull request its subject names.

It starts with the feedback post. The one durable copy of that feedback is the
id it lands as -- the anchor a failed run's `/orchestrator continue` replays --
so a post that failed, left no id, or had no pull request to go on relabels
and launches nothing, and the verdict is left waiting, never handed, for
whatever finishes it to post again. A post GitHub accepted and whose response
was lost reads the same way, since a feedback post carries no receipt to find
it by, so that retry leaves the feedback on the pull request twice. The whole
subject is held to what stands once more behind that post, the comment read
behind it -- a push or a later report landing during it is a subject nobody
reviewed, and the handoff's write would put the older report records back over
the newer; so is the issue pointed at another pull request, and a later
revision superseding the evidence the request claims -- and only then is the
verdict written as handed at the lifetime agent-run count, with the post's id
as its anchor (`review_verdicts.hands_off`), in the write that stages the
pinned feedback anchor too, and the issue relabelled to `workflow:fixing`. So
whichever request fails behind that write leaves a verdict whose feedback is
already posted and anchored, the verdict itself recording which comment that
is. The room that write and the launch's charge need was reserved when the
verdict was recorded.

The handed write and the relabel are requests too, so the launch is held to
what stands -- the subject, the evidence the request claims, the run ledger,
and the anchor, over the comment read again -- before the relabel announces
it, and once more right before the developer is launched (`_launch_stands`): a
relabel made where the launch it announces is already ruled out would leave
the issue on `workflow:fixing` with nobody launched. A moved subject drops the
verdict and its anchor. So is the run ledger: the start of the developer the
request owes, recorded at the count it was handed at
(`run_ledger_values.AGENT_RUN_OWED_STARTED`), is that developer already
launched -- by a tick that died behind it, or by another road -- and the
verdict is retired rather than handed to a second developer, ahead of any
drop a subject that developer's own push moved would make, so its anchor
stays for that developer's replay; while any other run charged meanwhile, a
reviewer's say, is no such launch. That reading is requests old again by the
time the run circuit charges the launch, and the charge a write old by the
time it is started, so the launch goes to the circuit owed once, behind a hold
of its own (`review_launch_hold`): every reading the circuit writes from has
to be of the comment the handoff read, not one pinned in its place, and show
no start of that developer, the verdict still the one handed, the anchor still
naming its post, and the report records, the pull request pointer, and the
claimed evidence where the handoff last read them, and the whole subject is
resolved again right behind the charge, the start written over the comment
read behind that, and what else another road wrote on a reading the launch
stands on carried onto the state the developer's run is written back from.
Whatever moved refuses the launch there, with nothing started or written over
it, and the next entry retires, drops, or holds the verdict as what moved
says. Only the writes behind the developer's run retire the verdict otherwise,
since its drop is staged ahead of the launch, whose charge writes only its own
fields.

A verdict already handed is finished by a later entry from that write on: its
feedback is posted and anchored, so it is never posted again, and the relabel
and the launch are what a tick that died on them left owed -- unless the run
ledger records the start of the developer it owes at the count it was handed
at, which is that developer already launched and only the verdict to retire.
A charge the run circuit reserved and never started -- its start refused, the
tick dying before the spawn -- recorded no start, and the launch is still
owed: the circuit honors that reservation for the launch it was taken
for rather than charging again. Either launch is made only behind the feedback
anchor the handoff was written beside, still naming the comment the verdict
records it posted: the fixing stage clears the anchor with the round's other
bookmarks, and without it no failed run can replay the feedback, while one
naming any other comment would replay that comment to the developer as this
reviewer's feedback -- so a handoff that lost it, whose anchor names another
comment, or recorded before handoffs anchored their post, naming none, is
held, with nothing relabelled, launched, or written (`_launch_stands`).
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_record_values as _record_values,
    review_subjects as _review_subjects,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.stages.implementing import worktree as _dev_worktree
from orchestrator.workflow.stages.validating import (
    models as _models,
    requested_changes as _requested_changes,
    review_claims as _claims,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_launch_hold as _launch_hold,
    review_verdicts as _verdicts,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def hands_the_request_over(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    decision: _models._ReviewerDecision,
) -> None:
    """Hand a persisted change request to its developer through the decision it was returned as, in that tick.

    For a caller that has just held it to what stands; `state` is the pinned
    comment as that caller last read or wrote it. Only a change request is
    handed to a developer, and only through the decision it was persisted
    from -- the round, verdict, subject, and feedback the record keeps
    (`ReturnedVerdict.said`): the feedback posted and the words the developer
    is resumed on are the decision's, so another round's decision, an
    approval, or other words would post and hand on what the persisted request
    never said. And only on the pull request that subject names: its feedback
    is posted there and its fix pushed there, so a run naming another pull
    request is none this request can go on. Anything else hands nothing over.
    The verdict this road holds is the one `state` carries as it starts, so a
    verdict another road put in its place meanwhile is never the one it drops.
    """
    run = decision.run
    returned = (run.round_n, decision.verdict, run.subject.recorded(), decision.feedback)
    owned = _verdicts.read_returned_verdict(state)
    ours = owned is not None and owned.said() == returned
    on_its_own = (decision.verdict, run.pr_number) == (_verdicts.CHANGES_REQUESTED, run.subject.pr_number)
    if ours and on_its_own:
        _hands_it_off(_models._RequestedChanges(
            gh, spec, issue, state, run.wt, run.round_n, run.pr_number, decision.feedback,
        ), owned)
        return
    log.warning(
        "issue=#%d carries no change request its reviewer's run on PR #%s "
        "could hand over; handing nothing", issue.number, run.pr_number,
    )


def hands_the_waiting_request_over(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> None:
    """Hand the change request the pinned comment has waiting to its developer, on a later tick holding no decision.

    For a caller that has just held it to what stands (`review_disposition.
    waiting_verdict_ready`); `state` is the pinned comment as that caller last
    read or wrote it. The process keeps nothing between ticks, so the request
    is handed over from the record alone -- its round, its feedback, and the
    pull request its subject names -- in the checkout the issue's developer
    resumes in: a verdict whose feedback post failed is posted again, and one
    already handed resumes where that handoff stopped, without posting again.
    Anything but a change request waiting hands nothing over.
    """
    owned = _verdicts.read_returned_verdict(state)
    if owned is None or owned.verdict != _verdicts.CHANGES_REQUESTED:
        log.info(
            "issue=#%d has no change request of its reviewer's waiting to hand "
            "over; handing nothing", issue.number,
        )
        return
    _hands_it_off(_models._RequestedChanges(
        gh, spec, issue, state,
        wt=_dev_worktree._ensure_resume_worktree(spec, issue, state),
        round_n=owned.round_n,
        pr_number=_review_subjects.ReviewSubject.identity_recorded_in(owned.subject)[0],
        feedback=owned.feedback,
    ), owned)


def _hands_it_off(context: _models._RequestedChanges, owned: _verdicts.ReturnedVerdict) -> None:
    """Hand `owned` off behind its posted feedback, or find where that handoff got to, then relabel and launch.

    A verdict not yet handed is handed behind its feedback post
    (`_posts_the_feedback`), in one write that records the post as its anchor
    at the run count it found. One already handed has its feedback posted and
    anchored, so it is not posted again: the relabel or the launch behind that
    write is what a tick that died on it left owed, where it is still owed at
    all. Either way the relabel is made only where the launch it announces
    would be made now (`_launch_stands`): that write, or the tick that read
    the comment, is a request long enough for another road to clear the
    anchor or launch the developer, and a relabel over either would leave the
    issue on `workflow:fixing` with nobody launched.
    """
    gh, issue, state = context.gh, context.issue, context.state
    handed = owned
    if owned.handed is None:
        posted = _posts_the_feedback(context, owned)
        if posted is None:
            return
        _verdicts.hands_off(state, _run_ledger_values._runs_used(state), posted)
        gh.write_pinned_state(issue, state)
        handed = _verdicts.read_returned_verdict(state)
    else:
        log.info(
            "issue=#%d finds its reviewer's change request already posted and "
            "anchored; resuming that handoff", issue.number,
        )
    if _launch_stands(context, handed):
        gh.set_workflow_label(issue, WorkflowLabel.FIXING)
        _launches_the_developer(context, handed)


def _posts_the_feedback(context: _models._RequestedChanges, owned: _verdicts.ReturnedVerdict) -> int | None:
    """Post the reviewer's feedback and hold the request to what stands behind it; the post's id, or None to stop.

    Only a post identified by the id it landed as goes on: that id is the
    anchor the handoff is written beside, so a post that failed, and one that
    left no id, hold the verdict unhanded with nothing written. The post is a
    request of its own, long enough for a push, a later report, a repoint of
    the issue's pull request, or a later evidence revision to land, so the
    comment is read against the one the post was made over -- the ledger
    entry it staged is this road's own, not another road's -- and the request
    is dropped where anything it stands on moved (`_still_stands`). The post
    stages no anchor: that goes down only with the handoff behind this
    reading (`review_verdicts.hands_off`), so a drop here keeps whatever
    anchor the comment carries -- one another road wrote meanwhile included
    -- rather than writing this road's over it.
    """
    posted_over = dict(context.state.data)
    posted = _requested_changes._post_reviewer_feedback(context)
    if posted is None:
        log.warning(
            "issue=#%d holding its reviewer's change request until its feedback "
            "is posted on PR #%s under an id the handoff can anchor",
            context.issue.number, context.pr_number,
        )
        return None
    return posted if _still_stands(context, owned, posted_over, None) else None


def _launches_the_developer(context: _models._RequestedChanges, handed: _verdicts.ReturnedVerdict) -> None:
    """Launch the developer the change request `handed` owes, over what stands as it is launched.

    The relabel ahead of this is a request long enough for another road to
    push, settle a later report, clear the anchor, or launch that developer,
    and the run's own writes are composed over the state in hand: launched
    over the older records, the developer would answer words the pull request
    no longer carries and its writes would put those records back over the
    newer. So the launch is held to what stands once more (`_launch_stands`).
    The launch is charged and started over readings of its own, later still,
    so it goes to the run circuit owed once at the count the request was
    handed at, behind a hold measured from the comment this check left on the
    state (`review_launch_hold.owed_launch`), which refuses it on those
    readings where anything it stands on moved since. Otherwise the drop is
    staged ahead of the launch, whose charge writes only its own fields, so
    only the writes behind the run retire the verdict.
    """
    if not _launch_stands(context, handed):
        return
    owed = _launch_hold.owed_launch(context, handed)
    _verdicts.drops_the_verdict(context.state, only=handed)
    attempt = _requested_changes._run_requested_fix(context, owed=owed)
    _requested_changes._finish_requested_fix(context, attempt)


def _launch_stands(context: _models._RequestedChanges, handed: _verdicts.ReturnedVerdict) -> bool:
    """Whether the launch the change request `handed` owes is still this road's to make, over the comment read again.

    Asked before the relabel that announces the launch and again right
    before the launch itself, each over the comment as it stands then. The
    start of the developer the request owes, recorded at the count it was
    handed at (`run_ledger_values._owed_started`), is that developer's launch,
    whoever made it -- a tick that died behind it, or another road behind this
    one's writes -- and its run is the fixing stage's to answer, so the
    verdict is retired rather than handed to a second developer: asked of the
    reading in hand first, before the subject is, since that developer's own
    push moves the head, and a request dropped as a moved subject would take
    with it the anchor that developer's replay needs; and asked again of the
    comment read behind the subject -- ahead of any drop that reading would
    make, for the same reason (`_still_stands`) -- since the run circuit
    counts a start carried onto the state in hand as the caller's own. The
    retirement is a write composed over the comment read again
    (`review_comment._records_stand`), so a later report or anything else
    another road wrote since is kept, not written back over -- only where the
    comment still carries that verdict, and nothing where it will not read.
    Any other run charged since the handoff -- a reviewer's, or another
    road's of another launch -- recorded no such start, and neither did a
    charge still standing as the run circuit's unstarted reservation, which
    reached no process: the launch is still owed, and the circuit honors that
    reservation for the launch it was taken for rather than charging a second
    run. Between the two, the subject and the evidence the request claims are
    held to what stands, the comment read behind them, and a moved one drops
    the request with its anchor (`_still_stands`). And the launch is made only behind the feedback anchor
    that reading carries, naming the very comment the verdict records it was
    handed over with (`ReturnedVerdict.anchor`): it is the one durable copy of
    the feedback a failed run's `/orchestrator continue` replays, and the
    fixing stage clears it with the round's other bookmarks, so a handoff that
    lost it -- or whose anchor another write pointed at some other comment,
    which that replay would hand the developer as this reviewer's feedback, or
    spelled as anything but a whole comment id, which that replay refuses --
    is held, and so is one recorded before handoffs anchored their post, which
    names none to vouch for: nothing relabelled, launched, or written, the
    verdict left waiting as it was.
    """
    gh, issue, state = context.gh, context.issue, context.state
    stood = _run_ledger_values._owed_started(state) != handed.handed and _still_stands(
        context, handed, dict(state.data), handed.anchor,
    )
    if _run_ledger_values._owed_started(state) == handed.handed:
        log.info(
            "issue=#%d the developer its reviewer's change request was handed to "
            "was already launched; retiring the verdict", issue.number,
        )
        if _review_comment._records_stand(
            gh, issue, state, dict(state.data), persisted=True,
        ) is not None and _verdicts.drops_the_verdict(state, only=handed):
            gh.write_pinned_state(issue, state)
        return False
    # Read as the fixing stage's replay reads it: a float or a flag spelled
    # over the same number is an anchor that replay refuses. A verdict handed
    # before handoffs anchored their post names none, and no pinned anchor --
    # not even none -- can be vouched for as its feedback.
    anchor = _record_values.as_recorded_number(state.get(_verdicts._FEEDBACK_ANCHOR))
    if not stood or (handed.anchor is not None and anchor == handed.anchor):
        return stood
    log.warning(
        "issue=#%d its reviewer's change request was handed beside feedback "
        "comment %s and the pinned anchor names %r; holding the handoff rather "
        "than launching a developer no failed run could replay that feedback to",
        issue.number, handed.anchor, state.get(_verdicts._FEEDBACK_ANCHOR),
    )
    return False


def _still_stands(
    context: _models._RequestedChanges,
    held: _verdicts.ReturnedVerdict,
    measured_over: dict,
    anchored: int | None,
) -> bool:
    """Whether the subject and the evidence `held` stands on still stand, the request dropped where either moved.

    The comment is read again against `measured_over`, the comment the state
    in hand was last read or written as, behind the subject resolved again
    (`review_coverage._verdict_still_stands`), and the claim is judged over
    that reading: anything short of the very evidence it claims, settled, is
    a later revision superseding it. A proved move drops the request in a
    write composed over that reading, so the newer records are kept rather
    than the ones the request read -- and only the verdict this road holds
    (`review_verdicts.drops_the_verdict`), since one another road put in its
    place is that road's to finish. The feedback's anchor goes with it where
    it still names `anchored`, the post this road's handoff wrote it for: it
    names words about a subject nobody is handing on, and a later park's
    retry replaying them would hand a developer a review of work the pull
    request no longer carries. An anchor another road wrote since is carried
    onto the state by that reading, and stays. So is the start of the
    developer a handed `held` owes, recorded at the count it was handed at,
    and that start comes first: that developer's own push moves the head
    during these requests, and its run is the one that anchor's replay
    answers, so nothing is dropped and the caller retires the verdict as
    launched (`_launch_stands`). A comment or a
    subject nobody could read proves nothing and writes nothing, and the
    request waits as it was.
    """
    gh, issue, state = context.gh, context.issue, context.state
    stood = _review_coverage._verdict_still_stands(gh, issue, state, held.subject, measured_over)
    if stood and held.evidence is not None:
        stood = _claims.claim_standing(state, held.evidence) is _claims.ClaimStanding.SETTLED
    launched = held.handed is not None and _run_ledger_values._owed_started(state) == held.handed
    if stood is False and not launched:
        log.info(
            "issue=#%d the subject, or the evidence, its reviewer's change request "
            "stands on moved before its developer was launched; dropping the verdict",
            issue.number,
        )
        _verdicts.drops_the_verdict(state, only=held)
        if anchored is not None and state.get(_verdicts._FEEDBACK_ANCHOR) == anchored:
            state.set(_verdicts._FEEDBACK_ANCHOR, None)
        gh.write_pinned_state(issue, state)
    return bool(stood)
