# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A persisted change request handed to the one developer it owes, and whether that launch is still owed.

A live reviewer round's change request reaches here through the disposition
service (`review_disposition`), right behind proving the request still
carried, its subject standing, and its evidence settled -- in the tick its
reviewer returned, or in a later one that finishes the request waiting
(`review_resume`) -- and so does that recovery itself, where a request's
developer launch is still owed (`HandedLaunch.owed`).
What is here is that handoff, entered directly: through the very decision
the request was persisted from, in the tick its reviewer returned
(`hands_the_request_over`), and from the persisted request alone on a later
tick, which holds no decision (`hands_the_waiting_request_over`) -- either way
on the pull request its subject names.

Either way the words posted and handed on are the reviewer's findings as a
human is shown them (`review_findings`): the decision's, formatted as the
request was persisted, or the record's, formatted again on a later tick
(`HandedLaunch.of`). A request persisted before its findings were formatted
still carries its verification declaration raw, so recovering it posts --
where its feedback was never posted -- and resumes its developer on the
concise findings, each check not shown passing kept as its diagnostic. The
record's feedback stays exactly as persisted, and the record is what every
comparison here is made against; a post an earlier handoff made stays as it
was posted, and the `/orchestrator continue` replaying it quotes its findings
formatted (`feedback_posts`).

It starts with the feedback post, and the handoff's own write is prepared
before it: the guarded commit (`engine/pinned_commit.py`) that writes the
verdict as handed is laid over the comment read afresh and measured, the
request at its widest handoff and its launch's charge beside it
(`ReturnedVerdict.fits_beside`), so a comment another road filled, moved, or
replaced since posts nothing, and the verdict waits. The one durable copy of
that feedback is the id the post lands as -- the anchor a failed run's
`/orchestrator continue` replays -- so a post that failed, left no id, or had
no pull request to go on relabels and launches nothing, and the verdict is
left waiting, never handed, for whatever finishes it to post again. A later
tick's handoff, which holds no decision, first looks for the post an earlier
one made on the pull request for this very request -- in the words it posts,
below them the receipt naming its round, subject, and evidence claim, or in
the words a tick before receipts posted it in, only where such a post stands
behind the report and evidence the request was reviewed over and no landed
handoff accounts for it (`feedback_posts.finds`) -- one GitHub accepted whose
response was lost, or one a refused handoff left unanchored -- and takes it
rather than posting twice.
The whole subject is held to what stands once more behind that post, the
comment read behind it -- a push or a later report landing during it is a
subject nobody reviewed, and the handoff's write would put the older report
records back over the newer; so is the issue pointed at another pull request,
and a later revision superseding the evidence the request claims -- and only
then is the verdict written as handed at the lifetime agent-run count, with
the post's id as its anchor (`review_verdicts.hands_off`), in the commit that
stages the pinned feedback anchor too, and the issue relabelled to
`workflow:fixing`. That commit is captured over the reading behind the post and
decided on the report, pull-request, verdict, and evidence records, the
anchor, the run ledger the handed count is read off, and the park's flags,
each as that reading spells them (`_HANDOFF`), and asks of the very candidate
it sends the room its preparation asked -- the request as handed, beside its
launch's charge: another road that moves one after it -- a later report, a
repoint, another verdict, evidence recorded or settled, the anchor written, a
run charged, a park recorded -- or fills the comment past that room refuses
it, with nothing written over that road's write, relabelled, or launched, and
the next entry finds the post and hands the request over again where it still
stands and has room. So does an edit GitHub never confirmed, which the next
entry finds handed or not and finishes either way.
So whichever request fails behind that commit leaves a verdict whose feedback
is already posted and anchored, the verdict itself recording which comment
that is.

A park another road records is a human's to answer -- a report it could not
deliver, say -- and a developer launched under it would answer nobody's ask,
the writes behind its run settling the park away. So every reading the
request is held to behind its requests -- behind the post, ahead of the
relabel, right before the launch (`_still_stands`), and each the run circuit
charges and starts the launch from (`review_launch_hold`) -- holds it where a
park stands there, or its flags moved, with nothing written, relabelled,
charged, or launched, and the park left exactly as that road wrote it; the
request waits for the reply that clears it.

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
says. Otherwise the developer's run retires the verdict, and only in a
guarded commit decided on the verdict, the pull request the issue points at,
the start of its launch, the feedback anchor, and the park's flags as the
tick read them (`review_writes.ANSWERED`): the report domain's commit
recording the run's report, which writes the retirement itself
(`report_records.HandedRun.retires` and `decided_on`), the commit landing a
park the round takes instead -- a timeout's, a question's, a tree's or a
push's it could not publish, or the report it still owes, which writes the
retirement itself as well (`report_delivery.parks_the_debt`) -- or, where no
report was recorded first, the hand-back behind the relabel
(`requested_changes._finish_requested_fix`).
Until then the request is the one durable obligation the run leaves, so a
commit GitHub took and never confirmed leaves the result and the retirement
both on the comment or neither, and the ticks behind answer it as they would a
confirmed one -- never a request retired with nothing recorded, which the
fixing stage would hand back for a review nobody asked for. The retirement is
prepared over the comment read afresh right behind the run
(`HandedLaunch.retires`): a verdict another road put in this one's place, a
repoint, a start written away, the anchor repointed, or a park recorded there
-- then, or ahead of the record or the park -- means nothing of that result is
written, posted, pushed, relabelled, or spent, and the hand-back is refused
where another road wrote a verdict while the label moved back, nothing
settled behind it. A run that wrote nothing -- paused live, killed by the
shutdown sweep, or refused at the circuit -- retires nothing. A drop of a moved subject (`_DROP`) and a retirement of a
launched one (`_RETIRE`) are guarded commits too, decided on the verdict held
and the start of the launch it owes as the comment spells them -- and a drop
on the records the request stands on and its anchor besides -- so a verdict
another road put in its place, or a start recorded or written away
meanwhile, refuses them with nothing written, and a later entry decides
again over the comment as it stands. A drop clears the anchor only where the
verdict it dropped was this road's: one another road put in its place may
record that very post as its own anchor.

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
under `agent_execution_failed`, the verdict dropped in the park's own guarded
commit, so `/orchestrator continue` replays the reviewer's feedback to a
fresh developer session through the anchor it was handed over with
(`review_launch_park`).
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import is_shutdown_sweep_interrupted
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    report_commits as _commits,
    report_record_values as _record_values,
    review_findings as _findings,
    review_subjects as _review_subjects,
    run_ledger_models as _run_ledger_models,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.stages.implementing import execution as _execution, worktree as _dev_worktree
from orchestrator.workflow.stages.validating import (
    models as _models,
    requested_changes as _requested_changes,
    review_claims as _claims,
    review_coverage as _review_coverage,
    review_launch_hold as _launch_hold,
    review_verdicts as _verdicts,
    review_writes as _review_writes,
)
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")

_ANCHOR = _verdicts._FEEDBACK_ANCHOR

# The run ledger a handed request's launch is read off (`HandedLaunch.owed`):
# its counts, the charge standing and what it was taken for, and the start of
# the launch owed once.
RUN_LEDGER = frozenset((
    _run_ledger_values.AGENT_RUNS_USED,
    _run_ledger_values._LEGACY_RUNS_USED,
    _run_ledger_values.AGENT_RUN_RESERVATION,
    _run_ledger_values.AGENT_RUN_FINGERPRINT,
    _run_ledger_values.AGENT_RUN_OWED_STARTED,
))

# The verdict, and the feedback anchor written beside it as handed.
_ANCHORED = frozenset((_verdicts.RETURNED_VERDICT, _ANCHOR))

# The handoff: the verdict written as handed at the run count it found, beside
# the anchor of its post. Decided on what the request stands on, the anchor,
# the run ledger that count is read off, and the park's flags, each exactly as
# the reading spells it -- a run charged meanwhile is a count the record would
# misstate, an anchor another road wrote is not this post's to replace, and a
# park another road recorded is a human's to answer, not a launch's to run
# under. Its preparation and its commit each admit it only with room for the
# request at its widest handoff beside its launch's charge (`_hands_off`).
_HANDOFF = _commits.ReportWrite(
    owned=_ANCHORED,
    decided_on=_review_writes.VERDICT_STANDS_ON | _ANCHORED | RUN_LEDGER | _review_writes._PARK_FLAGS,
)

# A request dropped as its subject or its evidence moved before its developer
# was launched, with the anchor where it names this road's post: decided on
# what it stands on, the anchor, and the start of the launch it owes, which
# recorded meanwhile is that developer launched and keeps the anchor its
# replay needs.
_DROP = _commits.ReportWrite(
    owned=_ANCHORED,
    decided_on=_review_writes.VERDICT_STANDS_ON | _ANCHORED | {_run_ledger_values.AGENT_RUN_OWED_STARTED},
)

# A request retired as its developer was launched, found started by a later
# entry: decided on the verdict handed and the start that says so, and on
# nothing its subject moves.
_RETIRE = _commits.ReportWrite(
    owned=frozenset((_verdicts.RETURNED_VERDICT,)),
    decided_on=frozenset((_verdicts.RETURNED_VERDICT, _run_ledger_values.AGENT_RUN_OWED_STARTED)),
)

# What the handoff's preparation answers where the comment has no room for
# the request at its handoff and its launch's charge beside it.
_NO_ROOM = "no room for the change request at its handoff"


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
    resumes in: a verdict whose feedback post failed is posted again -- or
    the post an earlier tick made in the same words is found and taken, its
    response lost or its handoff refused behind it -- and one already handed
    resumes where that handoff stopped, without posting again.
    What is posted and handed on is the record's findings as shown
    (`HandedLaunch.of`), so one persisted with its declaration raw reaches
    the pull request and its developer concise, its recorded feedback left as
    it reads.
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
    (`_hands_off`), in one guarded commit that records the post as its anchor
    at the run count it found. One already handed has its feedback posted and
    anchored, so it is not posted again: the relabel or the launch behind that
    commit is what a tick that died on it left owed, where it is still owed at
    all. Either way the relabel is made only where the launch it announces
    would be made now (`HandedLaunch.stands`): that commit, or the tick that
    read the comment, is a request long enough for another road to clear the
    anchor or launch the developer, and a relabel over either would leave the
    issue on `workflow:fixing` with nobody launched. An issue already on that
    label -- the fixing stage's recovery of an owed launch -- is not relabelled
    at all: the write would announce a stage entry nothing made. `restores` is
    a later tick's handoff, holding no decision: `context` names the issue's
    checkout where it stands, restored only behind that relabel
    (`_launches_the_developer`), so a request whose subject moved is dropped
    first, over GitHub's readings alone, and its feedback post is looked for
    on the pull request before it is made (`requested_changes.
    _post_reviewer_feedback`), since an earlier tick may have made it and
    never learned its id.

    Nothing at all is done under a park `context.state` shows standing --
    another road's, which a reading the caller took to prove the request
    ready carried onto it: a human answers that park, and feedback posted
    under it, or a developer launched, would answer nobody's ask. The request
    waits as it is for the reply that clears it.
    """
    gh, issue = context.gh, context.issue
    if context.state.get(_review_writes._AWAITING_HUMAN):
        log.warning(
            "issue=#%d a park stands on its pinned comment; posting, relabelling, "
            "and launching nothing for its reviewer's change request under it", issue.number,
        )
        return
    handed = owned
    if owned.handed is None:
        handed = _hands_off(context, owned, finds=restores)
        if handed is None:
            return
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


def _hands_off(
    context: _models._RequestedChanges, owned: _verdicts.ReturnedVerdict, *, finds: bool,
) -> _verdicts.ReturnedVerdict | None:
    """Post the reviewer's feedback, hold the request to what stands behind it, and commit it handed; or None to stop.

    The handoff is prepared before anything is posted: the comment read
    afresh, what the tick staged laid over it, has to be one its commit would
    land on -- readable, the very one the tick read, the records the request
    stands on, its anchor, the run ledger, and the park's flags as the tick
    read them -- with room for the request at its widest handoff, its post's
    ledger entry reserved, and the launch's charge beside it
    (`ReturnedVerdict.fits_beside`). A comment another road filled, moved,
    parked, or replaced since posts nothing, and the request waits unhanded
    for a later tick.

    Only a post identified by the id it landed as goes on: that id is the
    anchor the handoff is written beside, so a post that failed, and one that
    left no id, hold the verdict unhanded with nothing written. Where `finds`,
    a post an earlier tick made for this very request is found on the pull
    request by its words and its receipt (`feedback_posts.finds`) and taken as
    this one instead of posting again. The
    post is a request of its own, long enough for a push, a later report, a
    repoint of the issue's pull request, or a later evidence revision to
    land, so the comment is read against the one the post was made over --
    the ledger entry it staged is this road's own, not another road's -- and
    the request is dropped where anything it stands on moved, and held where
    another road parked the issue meanwhile (`_still_stands`). The post stages
    no anchor: that goes down only with the handoff behind this reading
    (`review_verdicts.hands_off`), so a drop here keeps whatever anchor the
    comment carries -- one another road wrote meanwhile included -- rather
    than writing this road's over it.

    The handoff itself is a guarded commit captured over that reading
    (`_HANDOFF`), and held to the room its preparation was, over the very
    candidate it sends: the request as handed, its post's ledger entry
    counted once, and the launch's charge beside it. A record it was decided
    on that another road moves after it -- a later report, a repoint, a
    verdict put in place of this one, evidence recorded or settled, the anchor
    written, a run charged, a park recorded -- refuses it with nothing
    written, relabelled, or launched, and so does a comment another road
    filled behind the post past that room, which would leave the developer's
    charge nowhere to land; so does an edit GitHub never confirmed, which a
    later tick finds handed or not and finishes either way: resumed without a
    second post where it landed, and handed again behind the post it finds
    where it did not, once the comment has room for it.
    """
    commit = _commits.ReportCommit(context.gh, context.issue, context.state)
    posted_over = commit.staging()
    handoff = _HANDOFF.admitting(
        lambda candidate: None if owned.fits_beside(candidate, None) else _NO_ROOM,
    )
    if commit.prepares(posted_over, handoff).status is not _commit_models.CommitStatus.PREPARED:
        log.warning(
            "issue=#%d its pinned comment would not take its reviewer's change "
            "request as handed; posting nothing on PR #%s", context.issue.number, context.pr_number,
        )
        return None
    posted = _requested_changes._post_reviewer_feedback(context, owned, finds=finds)
    if posted is None:
        log.warning(
            "issue=#%d holding its reviewer's change request until its feedback "
            "is posted on PR #%s under an id the handoff can anchor",
            context.issue.number, context.pr_number,
        )
        return None
    if not _still_stands(context, owned, posted_over.data, None):
        return None
    _verdicts.hands_off(context.state, _run_ledger_values._runs_used(context.state), posted)
    handed = _verdicts.read_returned_verdict(context.state)
    handoff = _HANDOFF.admitting(
        lambda candidate: None if handed.fits_beside(candidate, None) else _NO_ROOM,
    )
    if not _review_writes.lands(context.gh, context.issue, context.state, handoff):
        return None
    return _verdicts.read_returned_verdict(context.state)


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
    readings where anything it stands on moved since. The run's result
    retires the request in a guarded commit decided on it -- its report's
    record, the park it lands on, or the hand-back behind the relabel
    (`requested_changes._finish_requested_fix`) -- prepared over the comment
    read afresh right behind the run (`HandedLaunch.retires`), so nothing of
    that result is written, posted, or pushed where another road moved what
    the retirement is decided on. Where
    `restores`, the checkout the developer resumes in is restored first -- a
    request of its own, which that last check reads behind.
    """
    if restores:
        restored = _dev_worktree._ensure_resume_worktree(context.spec, context.issue, context.state)
        context = context.in_checkout(restored)
    launch = HandedLaunch(context, handed)
    if not launch.stands():
        return
    owed = _launch_hold.owed_launch(context, handed, launch.owed)
    attempt = _requested_changes._run_requested_fix(context, owed=owed)
    if launch.retires(attempt):
        _requested_changes._finish_requested_fix(context, attempt, handed)

class HandedLaunch:
    """The developer launch one handed change request owes: whether it stands, and whether it is owed.

    `context` is what the request hands its developer, which `of` builds over
    the issue's checkout where it stands, nothing restored or created: for a
    recovery that only reads the launch -- and parks it where it may have run
    (`review_launch_park`) -- and for a later tick's handoff, which restores
    that checkout only once the request is held to what stands
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
        """The launch `handed` owes, on the pull request its subject names, handing on its findings as shown.

        The feedback posted and the words its developer is resumed on are the
        record's feedback as a human is shown it (`review_findings`): a record
        persisted before its findings were formatted still carries the raw
        slice, verification declaration and all, while formatting findings
        already concise changes nothing. `handed` itself is kept exactly as
        read -- the handoff, the launch hold, and every drop compare the
        pinned record against it -- so its feedback is never rewritten on the
        comment, and the claim, its receipt, and the anchor stay the ones that
        record was persisted and handed with, never read again off the
        formatted words.
        """
        return cls(_models._RequestedChanges(
            gh, spec, issue, state,
            wt=_worktree_paths._worktree_path(spec, issue.number),
            round_n=handed.round_n,
            pr_number=_review_subjects.ReviewSubject.identity_recorded_in(handed.subject)[0],
            feedback=_findings._concise_findings(handed.feedback),
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
        a guarded commit (`_RETIRE`) decided on that verdict and that start as
        the comment spells them, so a later report or anything else another
        road wrote is kept, not written back over, and a verdict another road
        put in its place, or a start that moved, refuses it with nothing
        written -- as does a comment that will not read; one GitHub never
        confirmed is retired, or found still waiting and retired, by a later
        tick reading the same start. Any other run charged since the handoff -- a reviewer's, or
        another road's of another launch -- recorded no such start, and
        neither did a charge still standing as the run circuit's unstarted
        reservation, which reached no process: the launch is still owed, and
        the circuit honors that reservation for the launch it was taken for
        rather than charging a second run. Between the two, the subject and
        the evidence the request claims are held to what stands, the comment
        read behind them, and a moved one drops the request with its anchor,
        while a park standing there holds it for the reply it waits on
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
            if _verdicts.drops_the_verdict(state, only=handed):
                _review_writes.lands(context.gh, context.issue, state, _RETIRE)
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
        anchor = _record_values.as_recorded_number(state.get(_ANCHOR))
        if not stood or (handed.anchor is not None and anchor == handed.anchor):
            return stood
        log.warning(
            "issue=#%d its reviewer's change request was handed beside feedback "
            "comment %s and the pinned anchor names %r; holding the handoff rather "
            "than launching a developer no failed run could replay that feedback to",
            context.issue.number, handed.anchor, state.get(_ANCHOR),
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

    def retires(self, attempt: _models._AwaitingDevAttempt) -> bool:
        """Prepare this request's retirement behind its launch's run, writing nothing; whether its result is written.

        The developer launched is the request answered, so the verdict is
        dropped -- but only in a write that records what the run left and is
        decided on the request, the pull request the issue points at, its
        start, the feedback anchor, and the park's flags
        (`review_writes.ANSWERED`): the commit recording the run's report,
        which writes the drop itself (`report_records.HandedRun.retires`), the
        park the round lands, or the hand-back behind the relabel
        (`requested_changes._finish_requested_fix`); every write recording or
        holding the run's report is decided on the same records.
        The request is the one durable obligation the run leaves until then,
        so a write GitHub never confirmed leaves either both or neither on the
        comment, never a request retired with nothing to answer it -- which the
        next tick would hand back for a review nobody asked for. Prepared here
        first, over the comment read afresh: a verdict another road put in this
        one's place, a repoint, a start written away, the anchor repointed --
        which a continue would replay -- a park recorded, or a comment that
        will not read refuses it, nothing is written or posted of the run's
        result, and the tick's state is withheld; a later tick answers the run
        as the comment stands. A run that wrote nothing to answer -- paused
        live, killed by the shutdown sweep, or refused at the run circuit,
        which leaves the launch owed -- retires nothing, and its result is left
        to write nothing as well.
        """
        if attempt.paused or is_shutdown_sweep_interrupted(attempt.run.agent_result):
            return True
        context = self.context
        commit = _commits.ReportCommit(context.gh, context.issue, context.state)
        staged = commit.staging()
        _verdicts.drops_the_verdict(staged, only=self.handed)
        prepared = commit.prepares(staged, _review_writes.ANSWERED)
        return prepared.status is _commit_models.CommitStatus.PREPARED


def _still_stands(
    context: _models._RequestedChanges,
    held: _verdicts.ReturnedVerdict,
    measured_over: dict,
    anchored: int | None,
) -> bool:
    """Whether the subject and the evidence `held` stands on still stand, and no park stands over them; or not.

    The comment is read again against `measured_over`, the comment the state
    in hand was last read or written as, behind the subject resolved again
    (`review_coverage._verdict_still_stands`), and the claim is judged over
    that reading: anything short of the very evidence it claims, settled, is
    a later revision superseding it. A proved move drops the request in a
    guarded commit captured over that reading (`_DROP`), so the newer records
    are kept rather than the ones the request read, and a record the drop was
    decided on that another road moves after it -- a verdict put in this
    one's place, the anchor, the start of the launch it owes -- refuses it
    with nothing written; and only the verdict this road holds
    (`review_verdicts.drops_the_verdict`), since one another road put in its
    place is that road's to finish. The feedback's anchor goes with it where
    it still names `anchored`, the post this road's handoff wrote it for: it
    names words about a subject nobody is handing on, and a later park's
    retry replaying them would hand a developer a review of work the pull
    request no longer carries -- only where this road's verdict was the one
    dropped: a verdict another road put in its place may record that very
    post as its own anchor, which is that road's to keep. An anchor another
    road wrote since is carried onto the state by that reading, and stays. So is the start of the
    developer a handed `held` owes, recorded at the count it was handed at,
    and that start comes first: that developer's own push moves the head
    during these requests, and its run is the one that anchor's replay
    answers, so nothing is dropped and the caller retires the verdict as
    launched (`HandedLaunch.stands`). A comment or a
    subject nobody could read proves nothing and writes nothing, and the
    request waits as it was. So does one whose reading shows a park standing
    -- another road's, recorded during these requests, which that reading
    carried onto the state: a human answers it, and a request handed over or
    launched under it would run a developer nobody asked for, so nothing is
    written over it and the request waits for the reply that clears it.
    """
    state = context.state
    stood = _review_coverage._verdict_still_stands(context.gh, context.issue, state, held.subject, measured_over)
    if stood and held.evidence is not None:
        stood = _claims.claim_standing(state, held.evidence) is _claims.ClaimStanding.SETTLED
    launched = held.handed is not None and _run_ledger_values._owed_started(state) == held.handed
    if stood is False and not launched:
        log.info(
            "issue=#%d the subject, or the evidence, its reviewer's change request "
            "stands on moved before its developer was launched; dropping the verdict",
            context.issue.number,
        )
        dropped = _verdicts.drops_the_verdict(state, only=held)
        if dropped and anchored is not None and state.get(_ANCHOR) == anchored:
            state.set(_ANCHOR, None)
        _review_writes.lands(context.gh, context.issue, state, _DROP)
    if stood and state.get(_review_writes._AWAITING_HUMAN):
        log.warning(
            "issue=#%d a park stands on its pinned comment behind its reviewer's "
            "change request; holding the request for the reply that park waits on",
            context.issue.number,
        )
        return False
    return bool(stood)
