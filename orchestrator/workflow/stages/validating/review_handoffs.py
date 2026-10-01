# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A persisted change request handed to the one developer it owes, whether that launch is still owed, and its park.

No live reviewer round persists a verdict yet, so no live round hands one
here: the disposition service (`review_disposition`) does, right behind
proving the request still carried, its subject standing, and its evidence
settled -- reached so far only by the recovery of a record an issue already
carries (`review_resume`) -- and so does that recovery itself, where a
request's developer launch is still owed (`HandedLaunch.owed`).
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
it, and once more right before the developer is launched (`HandedLaunch.stands`): a
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
-- where the issue is not on `workflow:fixing` already -- and the launch are
what a tick that died on them left owed -- unless the run ledger records the
start of the developer it owes at the count it was handed at, which is that
developer already launched and only the verdict to retire. A charge the run
circuit reserved and never started -- its start refused, the tick dying before
the spawn -- recorded no start, and the launch is still owed: the circuit
honors that reservation for the launch it was taken for rather than charging
again. Either launch is made only behind the feedback anchor the handoff was
written beside, still naming the comment the verdict records it posted: the
fixing stage clears the anchor with the round's other bookmarks, and without
it no failed run can replay the feedback, while one naming any other comment
would replay that comment to the developer as this reviewer's feedback -- so a
handoff that lost it, whose anchor names another comment, or recorded before
handoffs anchored their post, naming none, is held, with nothing relabelled,
launched, or written (`HandedLaunch.stands`). The recovery writes back an
anchor something cleared, from the verdict's own, before it asks
(`review_resume`). The checkout a later entry launches in is restored only
behind the relabel, once that check has held the request to its subject: a
moved subject is dropped over GitHub's readings alone, so a checkout that
will not restore never keeps a stale request pinned.

Whether a handed verdict's developer was launched at all is read off the run
ledger, which the run circuit writes before any process is spawned
(`HandedLaunch.owed`). The launch is owed while nothing there says it may have
started: no charge since the handoff, a charge still RESERVED under this
launch's own fingerprint -- nobody spawned it, and the circuit honors it for
the launch it was taken for -- or another road's run, a reviewer's, under a
fingerprint of its own. It may have started where the ledger records the start
of the launch owed at the count the request was handed at, or at a later one
(`run_ledger_values.AGENT_RUN_OWED_STARTED`), and where the ledger cannot say:
that record spelled as no count, or the latest charge at or past the handed
count STARTED under the very fingerprint the developer's own launch is charged
under (`implementing/execution._first_launch_fingerprint`) with no start of
the owed launch recorded -- at that count too, since a charge reserved before
the handoff is counted in it, and starting that charge later moves the count
no further -- or standing with a record no reader takes, which may be that
very launch: STARTED, or in a phase no reader takes, under that fingerprint,
any charge under a fingerprint gone or spelled as none -- even one RESERVED,
which the circuit could not honor and would charge again -- or a run count
below the handed count, which only ever rises and so cannot show what was
charged since. Such a launch is never made again: its start is written before
the spawn, so the developer may have run and had its result discarded -- a
live pause does exactly that -- or never been spawned, and a second launch may
pay for a second run over feedback one already answered. The same reading
holds every launch this owner makes: asked of the comment read again right
before the launch (`HandedLaunch.stands`), and handed to the run circuit's
hold (`review_launch_hold`), which asks it of every reading the launch is
charged and started from -- save the launch's own continuations, whose start
the state in hand already carries -- so a start of that identity landing
behind the relabel, or behind the last of those readings, launches nobody.

Where nothing shows the work a launch that may have started left, it parks
under `agent_execution_failed` (`HandedLaunch.parks`), the verdict dropped in
the park's own write, so `/orchestrator continue` replays the reviewer's
feedback to a fresh developer session through the anchor it was handed over
with. So the park is taken only behind that anchor: one something cleared is
put back in the park's own write, and one naming another comment holds the
launch, with nothing posted ahead of the notice and no park behind it -- judged
behind the notice on the comment as read there, so another road's repoint is
kept. It is measured before its notice with the helpers the verdict parks use
(`review_parks`), and lands only behind an identified notice over the subject
resolved again and the comment read again: a push, a later report or evidence
revision, a verdict another road put in place, or what the caller reads again
-- a commit that reached the branch -- moved there drops the verdict for the
stage's own road instead, a subject nobody could read holds it, and a park
another road recorded there is kept as it wrote it, with the verdict waiting.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_record_state as _report_record_state,
    report_record_values as _record_values,
    review_subjects as _review_subjects,
    run_ledger_models as _run_ledger_models,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.stages.implementing import (
    execution as _execution,
    state as _implementing_state,
    worktree as _dev_worktree,
)
from orchestrator.workflow.stages.validating import (
    models as _models,
    requested_changes as _requested_changes,
    review_claims as _claims,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_launch_hold as _launch_hold,
    review_parks as _parks,
    review_verdicts as _verdicts,
)
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")

_PARK_EXECUTION_FAILED = _implementing_state._PARK_EXECUTION_FAILED

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

# What a park of a handed request's launch stands on in the comment beside its
# subject: the report's records, the pull request the issue points at, the
# verdict itself, and the verification evidence.
_HELD_TO = (*_review_comment._VERDICT_RECORDS, *_review_comment._EVIDENCE_RECORDS)

_UNFINISHED = (
    "the developer this reviewer's change request was handed to may have been "
    "started and left no result, so nothing says whether it ever ran, and the "
    "reviewer's feedback was not handed on a second time. Reply "
    "`/orchestrator continue` to hand that feedback to a fresh developer session."
)


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
    That checkout is restored only once the handoff has held the request to
    what stands (`_hands_it_off`): a request whose subject moved is dropped
    over GitHub's readings alone, so a checkout that will not restore never
    keeps a stale one pinned.
    Anything but a change request waiting hands nothing over.
    """
    owned = _verdicts.read_returned_verdict(state)
    if owned is None or owned.verdict != _verdicts.CHANGES_REQUESTED:
        log.info(
            "issue=#%d has no change request of its reviewer's waiting to hand "
            "over; handing nothing", issue.number,
        )
        return
    launch = HandedLaunch.of(gh, spec, issue, state, owned)
    _hands_it_off(launch.context, owned, restores=True)


def _hands_it_off(
    context: _models._RequestedChanges, owned: _verdicts.ReturnedVerdict, *, restores: bool = False,
) -> None:
    """Hand `owned` off behind its posted feedback, or find where that handoff got to, then relabel and launch.

    A verdict not yet handed is handed behind its feedback post
    (`_posts_the_feedback`), in one write that records the post as its anchor
    at the run count it found. One already handed has its feedback posted and
    anchored, so it is not posted again: the relabel or the launch behind that
    write is what a tick that died on it left owed, where it is still owed at
    all. Either way the relabel is made only where the launch it announces
    would be made now (`HandedLaunch.stands`): that write, or the tick that read
    the comment, is a request long enough for another road to clear the
    anchor or launch the developer, and a relabel over either would leave the
    issue on `workflow:fixing` with nobody launched. An issue already on that
    label -- the fixing stage's recovery of an owed launch -- is not relabelled
    at all: the write would announce a stage entry nothing made. Where
    `restores`, `context` names the issue's checkout where it stands, restored
    only behind that relabel (`_launches_the_developer`), so a request whose
    subject moved is dropped first, over GitHub's readings alone.
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
    if HandedLaunch(context, handed).stands():
        # Already on it -- the fixing stage's own recovery -- the label is where
        # the launch needs it, and writing it again would announce a stage entry
        # nothing made, and could refuse the launch over a write it never needed.
        if gh.workflow_label(issue) != WorkflowLabel.FIXING:
            gh.set_workflow_label(issue, WorkflowLabel.FIXING)
        _launches_the_developer(context, handed, restores=restores)


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


def _launches_the_developer(
    context: _models._RequestedChanges, handed: _verdicts.ReturnedVerdict, *, restores: bool,
) -> None:
    """Launch the developer the change request `handed` owes, over what stands as it is launched.

    The relabel ahead of this, where one is made, is a request long enough for
    another road to push, settle a later report, clear the anchor, or launch
    that developer, and the run's own writes are composed over the state in
    hand: launched over the older records, the developer would answer words
    the pull request no longer carries and its writes would put those records
    back over the newer. So the launch is held to what stands once more
    (`HandedLaunch.stands`).
    The launch is charged and started over readings of its own, later still,
    so it goes to the run circuit owed once at the count the request was
    handed at, behind a hold measured from the comment this check left on the
    state (`review_launch_hold.owed_launch`), which refuses it on those
    readings where anything it stands on moved since. Otherwise the drop is
    staged ahead of the launch, whose charge writes only its own fields, so
    only the writes behind the run retire the verdict. Where `restores`, the
    checkout the developer resumes in is restored first -- a request of its
    own, which that last check reads behind.
    """
    if restores:
        restored = _dev_worktree._ensure_resume_worktree(context.spec, context.issue, context.state)
        context = context.in_checkout(restored)
    launch = HandedLaunch(context, handed)
    if not launch.stands():
        return
    owed = _launch_hold.owed_launch(context, handed, launch.owed)
    _verdicts.drops_the_verdict(context.state, only=handed)
    attempt = _requested_changes._run_requested_fix(context, owed=owed)
    _requested_changes._finish_requested_fix(context, attempt)



class HandedLaunch:
    """The developer launch one handed change request owes: whether it stands, whether it is owed, and its park.

    `context` is what the request hands its developer, which `of` builds over
    the issue's checkout where it stands, nothing restored or created: for a
    recovery that only reads the launch, and for a later tick's handoff, which
    restores that checkout only once the request is held to what stands
    (`hands_the_waiting_request_over`).
    """

    def __init__(self, context: _models._RequestedChanges, handed: _verdicts.ReturnedVerdict) -> None:
        self.context = context
        self.handed = handed

    @classmethod
    def of(
        cls,
        gh: GitHubClient,
        spec: config.RepoSpec,
        issue: Issue,
        state: PinnedState,
        handed: _verdicts.ReturnedVerdict,
    ) -> HandedLaunch:
        """The launch `handed` owes, on the pull request its subject names."""
        return cls(_models._RequestedChanges(
            gh, spec, issue, state,
            wt=_worktree_paths._worktree_path(spec, issue.number),
            round_n=handed.round_n,
            pr_number=_review_subjects.ReviewSubject.identity_recorded_in(handed.subject)[0],
            feedback=handed.feedback,
        ), handed)

    def stands(self) -> bool:
        """Whether the launch this request owes is still this road's to make, over the comment read again.

        Asked before the relabel that announces the launch -- or where it
        would stand, on an issue already on `workflow:fixing` -- and again
        right before the launch itself, each over the comment as it stands
        then. The start of the developer the request owes, recorded at the
        count it was handed at (`run_ledger_values._owed_started`), is that
        developer's launch, whoever made it -- a tick that died behind it, or
        another road behind this one's writes -- and its run is the fixing
        stage's to answer, so the verdict is retired rather than handed to a
        second developer: asked of the reading in hand first, before the
        subject is, since that developer's own push moves the head, and a
        request dropped as a moved subject would take with it the anchor that
        developer's replay needs; and asked again of the comment read behind
        the subject -- ahead of any drop that reading would make, for the same
        reason (`_still_stands`) -- since the run circuit counts a start
        carried onto the state in hand as the caller's own. The retirement is
        a write composed over the comment read again
        (`review_comment._records_stand`), so a later report or anything else
        another road wrote since is kept, not written back over -- only where
        the comment still carries that verdict, and nothing where it will not
        read. Any other run charged since the handoff -- a reviewer's, or
        another road's of another launch -- recorded no such start, and
        neither did a charge still standing as the run circuit's unstarted
        reservation, which reached no process: the launch is still owed, and
        the circuit honors that reservation for the launch it was taken for
        rather than charging a second run. Between the two, the subject and
        the evidence the request claims are held to what stands, the comment
        read behind them, and a moved one drops the request with its anchor
        (`_still_stands`); and that reading has to rule out every other start
        of this launch too (`owed`) -- a charge of its very identity STARTED
        meanwhile with no owed count holds it. And the launch is made only
        behind the feedback anchor that reading carries, naming the very
        comment the verdict records it was handed over with
        (`ReturnedVerdict.anchor`): it is the one durable copy of the feedback
        a failed run's `/orchestrator continue` replays, and the fixing stage
        clears it with the round's other bookmarks, so a handoff that lost it
        -- or whose anchor another write pointed at some other comment, which
        that replay would hand the developer as this reviewer's feedback, or
        spelled as anything but a whole comment id, which that replay refuses
        -- is held, and so is one recorded before handoffs anchored their
        post, which names none to vouch for: nothing relabelled, launched, or
        written, the verdict left waiting as it was.
        """
        context, handed = self.context, self.handed
        state = context.state
        stood = _run_ledger_values._owed_started(state) != handed.handed and _still_stands(
            context, handed, dict(state.data), handed.anchor,
        )
        if _run_ledger_values._owed_started(state) == handed.handed:
            log.info(
                "issue=#%d the developer its reviewer's change request was handed to "
                "was already launched; retiring the verdict", context.issue.number,
            )
            if _review_comment._records_stand(
                context.gh, context.issue, state, dict(state.data), persisted=True,
            ) is not None and _verdicts.drops_the_verdict(state, only=handed):
                context.gh.write_pinned_state(context.issue, state)
            return False
        if stood and not self.owed():
            log.warning(
                "issue=#%d its run ledger shows a start of the developer its "
                "reviewer's change request owes that it cannot tell from that "
                "launch; holding the handoff rather than launching a second one",
                context.issue.number,
            )
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
            context.issue.number, handed.anchor, state.get(_verdicts._FEEDBACK_ANCHOR),
        )
        return False

    def owed(self, reading: PinnedState | None = None) -> bool:
        """Whether the run ledger on `reading` rules out every start of this launch, so it is still owed.

        `reading` is a comment the run circuit is about to charge from
        (`review_launch_hold`); the state in hand where there is none. Not
        where a start of the launch owed at the handed count or a later one is
        recorded, nor where that record is spelled as no count -- `null`
        included -- nor where the run count reads below the handed count: the
        count only ever rises, so one that fell -- its own field unread and the
        other meter behind, say -- cannot show what was charged since the
        handoff. Nor where the charge standing may be this very launch: STARTED,
        or in a phase no reader takes, under the fingerprint this launch is
        charged under, or standing under a fingerprint no reader takes, gone
        included -- RESERVED too, since the run circuit cannot honor that for
        this launch and would charge it again. Each may be this developer, run
        or not, and a charge whose record cannot be read is never ruled out as
        it. A charge reserved before the handoff is counted in the handed count,
        so its later start moves that count no further, and is read the same.
        None standing, an unstarted reservation under this launch's own
        fingerprint -- which the circuit honors rather than charging again --
        or a charge another road took under a fingerprint of its own -- a
        reviewer's -- leaves it owed.
        """
        state = self.context.state if reading is None else reading
        at = self.handed.handed
        started = _run_ledger_values._owed_started(state)
        if state.carries(_run_ledger_values.AGENT_RUN_OWED_STARTED) and (started is None or started >= at):
            return False
        if _run_ledger_values._runs_used(state) < at:
            return False
        if not state.carries(_run_ledger_values.AGENT_RUN_RESERVATION):
            return True
        named = _run_ledger_values._fingerprint(state)
        this_launch = _execution._first_launch_fingerprint(state, stage_name(WorkflowLabel.FIXING))
        return named is not None and (
            named != this_launch
            or _run_ledger_values._reservation(state) is _run_ledger_models.RunPhase.RESERVED
        )

    def parks(self, moved_on: Callable[[], bool | None]) -> None:
        """Park this launch, which may have run and left nothing to show, under `agent_execution_failed`, in one write.

        `moved_on` is the caller's reading of whether the request has moved on
        with nothing on the comment to show it -- its claim superseded, or a
        commit on the branch its pull request has not got -- or None where the
        branch could not be read, which the caller took ahead of the park and
        which is taken again behind its notice.

        Only behind the feedback anchor `/orchestrator continue` replays: the
        pinned one naming the post the verdict records, or none -- something
        cleared it -- which the park's own write puts back. One naming another
        comment, or spelled as no whole id, would replay some other comment as
        this reviewer's feedback, and a verdict naming no post vouches for none,
        so either holds the launch with nothing posted or written. The park is
        measured before its notice at its own write, and settled behind it
        (`_lands`).
        """
        context = self.context
        state = context.state
        if not self._vouches(state.get(_verdicts._FEEDBACK_ANCHOR)):
            log.warning(
                "issue=#%d its handed change request names feedback comment %s and "
                "the pinned anchor names %r; holding its launch rather than parking "
                "it where no continue could replay that feedback",
                context.issue.number, self.handed.anchor, state.get(_verdicts._FEEDBACK_ANCHOR),
            )
            return
        measured = dict(state.data)
        state.set(_verdicts._FEEDBACK_ANCHOR, self.handed.anchor)
        if not _parks._park_fits(state, _PARK_EXECUTION_FAILED, self.handed):
            log.error(
                "issue=#%d has no room on its pinned comment for the park of its "
                "handed change request's launch; posting and writing nothing", context.issue.number,
            )
            return
        posted = _parks._posts_the_notice(context.gh, context.issue, state, _UNFINISHED)
        lands = self._lands(measured, posted, moved_on)
        if lands is None or not _report_record_state.fits_the_comment(state.data):
            log.error(
                "issue=#%d wrote nothing behind the notice of its launch's park: its "
                "pinned comment would not read, or has no room beside what moved there",
                context.issue.number,
            )
            return
        context.gh.write_pinned_state(context.issue, state)
        if lands:
            context.gh.emit_event(
                "park_awaiting_human",
                issue_number=context.issue.number,
                stage=stage_name(context.gh.workflow_label(context.issue)),
                reason=_PARK_EXECUTION_FAILED,
            )

    def _vouches(self, pinned: object) -> bool:
        """Whether the anchor `pinned` is the post this verdict records, or none: something cleared it."""
        if self.handed.anchor is None:
            return False
        return pinned is None or _record_values.as_recorded_number(pinned) == self.handed.anchor

    def _lands(
        self,
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
        comment, so the reading the park's write is composed over is the last
        request before it, and a verdict another road put in place during the
        branch's own requests is kept: the verdict is dropped for the stage's
        own road, with no park. A park another road recorded there is that
        road's to answer, and is kept as it wrote it: no park lands over it,
        and the verdict waits. The anchor is held on that reading too: pointed
        at another comment it holds the launch, as does a subject or a branch
        nobody could read, or a notice nothing identified -- the verdict kept
        for a later tick. The anchor is judged, and carried, as that reading
        found it, and put back only by the write that lands the park: staged
        on the state in hand, a restore reads as this tick's own move, and
        would be written over a repoint another road made behind the notice,
        or back beside a verdict and anchor another road dropped there. None
        where the comment will not read, which writes nothing.
        """
        state = self.context.state
        stands = _review_coverage._subject_still_stands(
            self.context.gh, self.context.issue, state, self.handed.subject,
        )
        # The branch is read ahead of the comment: its own requests are long
        # enough for another road to write there, so the reading the park's
        # write is composed over has to be the last request before it.
        moved = moved_on()
        reread = _review_comment._records_stand(
            self.context.gh, self.context.issue, state, measured, persisted=True,
        )
        if reread is None:
            return None
        # The anchor as that reading spelled it, its absence included.
        state.data.pop(_verdicts._FEEDBACK_ANCHOR, None)
        spelled = reread.read.get(_verdicts._FEEDBACK_ANCHOR, _review_comment._ABSENT)
        if spelled is not _review_comment._ABSENT:
            state.set(_verdicts._FEEDBACK_ANCHOR, spelled)
        if _review_comment._moved(reread.read, measured, _HELD_TO):
            stands = False
        if stands is False or moved:
            log.info(
                "issue=#%d what its handed change request stands on moved behind "
                "the park notice; dropping the verdict for the stage's own road",
                self.context.issue.number,
            )
            _verdicts.drops_the_verdict(state, only=self.handed)
            return False
        if (
            not (stands and posted is not None)
            or moved is None
            or state.get(_AWAITING_HUMAN)
            or not self._vouches(state.get(_verdicts._FEEDBACK_ANCHOR))
        ):
            log.warning(
                "issue=#%d landed no park of its handed change request's launch: its "
                "anchor moved, its subject or branch would not read, its notice left no "
                "id, or another park stands", self.context.issue.number,
            )
            return False
        _verdicts.drops_the_verdict(state, only=self.handed)
        state.data.update({
            _verdicts._FEEDBACK_ANCHOR: self.handed.anchor,
            _AWAITING_HUMAN: True,
            _PARK_REASON: _PARK_EXECUTION_FAILED,
        })
        return True


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
    launched (`HandedLaunch.stands`). A comment or a
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
