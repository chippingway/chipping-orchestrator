# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a guarded split does, in the one order every crash in it is safe in.

`late_split_preparation` owns the admissibility checks, immutable snapshot,
and durable children. This owner orders their announcement and supersession
with fresh owner and publication guards; `late_retirement` performs the
retirement, activation, and reclamation licensed by those checks.

Snapshot, children, links, supersession, activation, cleanup -- and the order
is the contract, because each step is an effect on GitHub or on a remote that
the process can die immediately after. Every one of them is preceded by the
durable fact that lets the next tick tell "already done" from "never started",
and every one of them is idempotent when that fact turns out to be ambiguous.

**Snapshot first, before any child.** A split ends with the parent's branch
superseded and its pull request closed, so the committed work survives only as
the ref `late_snapshot` creates and proves. A child created ahead of that ref
would be pointed at a branch that is about to stop existing.

**Then the children, each recorded before anything is done with it.** The
umbrella flag and the expected count go down before the first one, and every
child lands in the children list, the direct-consumer ledger, and the
obligation ledger in a single write. That write is what makes the snapshot's
reclamation wait for it, which is why it has to be durable before the child can
run.

**Then the links, and only then the supersession.** The parent says what it
became and where its children are; the pull request its work is on says it is
superseded, names the umbrella, the children, the snapshot ref, and the exact
commit, and is closed. Neither can be undone, and both are idempotent -- the
parent's announcement is gated on the durable stamp beside it, and the pull
request's is gated on its own hidden marker on the thread, so a crash between a
post and the write recording it costs at most a repeat that never happens
twice.

**And the owner between every one of them.** A close is not something this run
is told about: a poll that observes one while this worker holds the issue can
hand it to nobody, so the issue is re-read before each step the remote keeps --
before each child, before the announcement, before the supersession, and before
the retirement that hands the parent to `umbrella` and lets its children run.
What a close ends is the CYCLE rather than the tick, and where it lands is what
the cancellation reads back: an ending entered at the supersession still owns
the held pull request, and one entered just past it takes on the superseded
branch the retirement never got to write down.

**And the publication between every one of them too, on the road that has
one.** The owner is not the only thing a human moves mid-pass: the pull
request the close is made on can be merged, reopened, or pushed to, and every
step of the tail is licensed by that close being on it. So it is asked on the
same rule and at the same barriers -- in front of the close, in front of the
retirement, in front of EVERY child released, and immediately in front of the
branch delete. No step is ever run on evidence a step before it took, and
"before it" includes the reading a step of its own spent: the child scan a
release is decided on is a request per child, and the probe the reclamation
may spend on an ordered ref is another, so the last two barriers live inside
the walk and inside the reclamation rather than in front of either.

The one in front of the close is why the close is made against a second
reading rather than the first: the receipt the first carries costs a comment
listing, which is a round-trip standing between the state and head read beside
it and the write those two license. Asked again with no listing behind them,
they are the last thing to reach GitHub before the write -- so a change a
human settled or somebody pushed to inside that window is left untouched,
rather than marked and closed and only then refused.

What a refusal costs depends on which side of the retirement it lands. Before
it the pass parks: the record is live, so the issue stays on `decomposing`
with the children blocked and the branch intact, and the next tick supersedes
the same pull request again. Past it there is no live adjudication left to
park, so the last two barriers decline the step in front of them and leave it
to the retry that owns it: the umbrella's own walk for the children, its
terminal for the branch. Which is why the pre-retirement barrier is placed as
the very last thing before that write, with the branch resolved ahead of it
rather than between.

Those two retries ask the same question themselves, and that is what makes
declining a step safe rather than a one-tick delay. The retirement keeps the
publication group on purpose -- it is the only thing left on the issue naming
which pull request this split closed -- so the shared activation walk re-asks
it in front of every relabel it makes and `late_cleanup` re-asks it in front
of every branch it deletes, on this pass and on every umbrella tick after it.
Dropped there, a change reopened afterwards would have its work handed to
children on the very next poll and the ref it points at reaped by the
terminal.

**Then the label, the retirement, and the activation, in that order.** The
generation is retired -- identity, commits, both ledgers, and the publication
group kept, the measurement dropped -- in the same write that hands the issue
to `umbrella`,
because a live generation pins `workflow:decomposing` and the relabel guard
would put an early flip straight back. Activation runs after that write for the
reason the initial split's does: a crash between them must not leave a runnable
child under a parent still labelled `decomposing`. And the owner is read once
more between the two, since the write itself is a request a close can land
inside -- that last read is taken without a claim, because the retirement has
already moved the record to `cleaning_up` and a claim would name `owner_check`
over the boundary the whole-ledger rule reads.

**Cleanup last, and never in the way.** The superseded branch is an obligation
recorded on the ledger and reconciled after the children are running: a delete
that fails leaves a `failed` entry to retry and does not hold a single child
back, while the umbrella's own terminal completion is what it does block. That
asymmetry is the point -- children waiting on a branch deletion would be work
stalled on tidiness, whereas an umbrella closing over an unreclaimed remote
would be an obligation nobody ever settles.

Every failure is a park with the recorded verdict left standing, so the retry
costs a GitHub read rather than an agent: the next eligible tick reuses the
same recorded split, re-enters here, adopts everything already durable, and
carries on from the first step that did not land.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github import comments as _github_comments
from orchestrator.workflow.engine import comments as _comments, usage as _usage
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
)
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateGeneration,
    LatePhase,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from orchestrator.workflow.stages.decomposition import (
    late_hold as _late_hold,
    late_outcome as _late_outcome,
    late_owner as _late_owner,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_publication as _late_publication,
    late_retirement as _late_retirement,
    late_split_preparation as _late_split_preparation,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateAdjudicationRun,
    _LateContext,
    _LateDisposition,
)
from orchestrator.workflow.stages.decomposition.models import _SplitPlan

log = logging.getLogger("orchestrator.workflow")


_DECOMPOSED_AT = "decomposed_at"


# Stamped on the two comments this transaction owes, so a retry recognizes one
# it posted even when the write that was supposed to record it never landed.
# Both are scoped to the exact adjudication: a pull request outlives a cycle
# and an issue thread outlives everything, so an unscoped marker would
# read an earlier episode's receipt as this one's. HTML comments, so neither is
# visible in the rendered thread.
_SUPERSESSION_MARKER = (
    "<!--orchestrator-late-supersession:issue={issue}"
    ":cycle={cycle}:generation={generation}-->"
)


_FORWARD_LINK_MARKER = (
    "<!--orchestrator-late-split:cycle={cycle}:generation={generation}-->"
)


_FORWARD_LINKS = (
    ":scissors: the late decomposer read the committed candidate `{sha}` as "
    "{count} separable changes, so this issue becomes an umbrella and the "
    "work is handed to its children:\n\n{children}\n\nThe committed work is "
    "preserved on the immutable ref `{ref}` at `{sha}`; each child reuses the "
    "part of it their own scope covers. This issue has no implementation of "
    "its own and closes once every child resolves.\n\n{marker}"
)


_SUPERSESSION_NOTICE = (
    ":scissors: **Superseded.** The committed implementation for issue "
    "#{parent} was adjudicated as {count} separable changes, so this pull "
    "request is closed without merging and issue #{parent} is now an "
    "umbrella.\n\nThe work it carried is preserved on the immutable ref "
    "`{ref}` at `{sha}` -- nothing is lost, and each child reuses the part of "
    "it their scope covers:\n\n{children}\n\n{marker}"
)


# How the pull request a published split was measured on can fail to be the
# one the verdict was taken over. Each is spelled as the log line reads it,
# because what an operator has to reconcile differs by which of them moved.
_SETTLED_PUBLICATION = "PR #{number} is {state} rather than open"


# What is logged where the barrier past the retirement declines the delete in
# front of it. Not a park: the issue is an umbrella by then and its own
# terminal is what comes back for this, so what the sentence owes an operator
# is the reason and the retry that will take it.
_HELD_BACK_RECLAMATION = (
    "issue=#%d is an umbrella and %s, so branch %s was left on the ledger "
    "rather than deleted behind a change that still points at it; the "
    "umbrella's terminal reclaims it once every child resolves"
)


_SUPERSESSION_FAILED_PARK = (
    "the committed candidate for this issue was split and its snapshot and "
    "children are safe, but pull request #{number} -- the one carrying the "
    "superseded work, whether this cycle held it or the candidate was "
    "measured on it -- could not be superseded. So no child was activated "
    "while it is still open. The next tick retries the same supersession, "
    "which posts nothing twice."
)


_DISAGREEING_PUBLICATION_PARK = (
    "the committed candidate for this issue was split and its snapshot and "
    "children are safe, but {disagreement}. So no child was activated and "
    "the branch was not reclaimed: what the recorded verdict was taken over "
    "is not what that pull request carries now, and finishing the split "
    "behind it would hand the work to children -- and delete the branch it "
    "points at -- over a change nobody adjudicated. Reconcile the pull "
    "request by hand, and the next tick settles the same recorded verdict."
)


_UNDONE_SUPERSESSION_PARK = (
    "the committed candidate for this issue was split, its snapshot and "
    "children are safe, and the supersession was made -- but {disagreement}. "
    "So no child was activated and the branch was not reclaimed: the "
    "supersession is what licenses both, and neither may run beside a pull "
    "request that no longer carries it. Reconcile the pull request by hand, "
    "and the next tick supersedes it again and settles the same recorded "
    "verdict."
)


def _published_split(
    context: _LateContext,
    finished: _LateAdjudicationRun,
    plan: _SplitPlan,
    snapshot_ref: str,
) -> _LateAdjudicationRun:
    """Finish a transaction whose children exist: announce, supersede, hand.

    Every step here is one the remote keeps: a comment saying what the parent
    became, the pull request its work is on closed over a supersession notice,
    the umbrella label, and the children this walk lets start. A cycle a close
    ended takes none of them -- what it has already put on the remote is on
    the ledger, and the cleanup path is what settles it, closing that same
    pull request over a cancellation instead.

    So the owner is read BETWEEN them and not once for all of them, on the
    same rule the child loop above runs on: publication is three separate
    moments, each of which is a GitHub round-trip a human can close the issue
    inside. Reading once would let a close observed during the announcement
    or the supersession still hand the parent to `umbrella` and let its
    children loose -- which is the one effect of the whole transaction that
    puts an agent on somebody's repository.

    Each of the three checks leaves the record where the interruption
    actually happened, and the cancellation reads it from there: an ending
    entered at the supersession closes that pull request over a cancellation
    notice, and one entered between the supersession and the
    retirement takes the superseded branch on as owed rather than retiring
    over a branch nothing names.
    """
    stopped = _stopped_publishing(context)
    if stopped is not None:
        return stopped
    _announced(context, plan, snapshot_ref)
    stopped = _stopped_publishing(context)
    if stopped is not None:
        return stopped
    if not _superseded(context, plan, snapshot_ref):
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    return _retired_split(context, finished, plan)


def _retired_split(
    context: _LateContext,
    finished: _LateAdjudicationRun,
    plan: _SplitPlan,
) -> _LateAdjudicationRun:
    """Hand the parent on, let its children run, and take its branch back.

    Entered with the pull request settled and the children still `blocked`,
    which is the state the third and last owner read is asked from: past it
    an agent runs on somebody's repository, so a close observed anywhere
    between the supersession and here ends the cycle instead.

    The publication is asked again on the same rule and at the same barriers,
    because the supersession is one round-trip and each step below is another:
    a human can reopen, merge, or push to the change between any two of them.
    Every effect here is one nothing takes back -- the children run, the
    pointer is cleared, and the branch behind the pull request is deleted --
    and the supersession is what licenses all three, so each is asked for
    afresh rather than once for the lot.

    What a refusal costs differs by which barrier takes it, and that is the
    retirement's doing. Before it, the answer is a park: the record is still
    live, so the issue stays on `decomposing` with the children blocked and
    the branch intact, and the next tick supersedes the pull request again.
    Past it there is no record left to park -- the write drops the generation
    and hands the issue to `umbrella` -- so what the later barriers do is
    decline the step in front of them and leave it to the retry that owns it:
    the umbrella's own walk for the children, its terminal for the branch.
    Narrower than a park and the strongest thing still available, which is why
    the pre-retirement barrier is placed as the very last thing before that
    write, with the branch resolved ahead of it rather than between.
    """
    stopped = _stopped_publishing(context)
    if stopped is not None:
        return stopped
    # Resolved ahead of the barrier, and ahead of the write that clears
    # `pr_number`: the resolver falls back to the legacy ref while a pull
    # request is recorded, so a second reading after that write could name a
    # different branch from the one this transaction just recorded as owed.
    branch = _worktree_paths._resolve_branch_name(
        context.state, context.spec, context.issue.number,
    )
    undone = _publication_holds(context)
    if undone:
        return _late_outcome._finished(
            context, _parked_undone(context, undone),
        )
    ended = _late_retirement._handed_to_children(context, plan, branch)
    if ended is not None:
        return _late_outcome._finished(context, ended)
    _reclaimed_or_held(context, branch)
    return replace(
        finished,
        disposition=_LateDisposition.SETTLED,
        generation=context.generation,
    )


def _parked_undone(
    context: _LateContext, undone: str,
) -> _LateDisposition:
    """Park the pass whose supersession came undone before the retirement."""
    _parked_publication(
        context,
        context.generation.published_pr_number,
        undone,
        _UNDONE_SUPERSESSION_PARK,
    )
    return _LateDisposition.PARKED


def _reclaimed_or_held(context: _LateContext, branch: str) -> None:
    """Take the branch back, unless the change pointing at it came back.

    The last irreversible act of the whole road, and the furthest from the
    proof that licensed it: a pinned write, a label write, an owner read, a
    child scan, and one relabel per child all stand in between. So the
    publication is asked once more here, and a pull request that is open again
    keeps its branch -- deleting the ref behind a change somebody reopened is
    the one part of this tail a later pass could never undo.

    Held rather than failed. The obligation went onto the ledger as `pending`
    in the retirement write and stays exactly there, so the umbrella's own
    terminal reclaims it once every child resolves -- which is the retry that
    already owns this, and the reason no typed failure is emitted for a delete
    this pass deliberately never attempted.
    """
    held = _publication_holds(context)
    if not held:
        _late_retirement._reclaimed_branch(context, branch)
        return
    log.error(_HELD_BACK_RECLAMATION, context.issue.number, held, branch)


def _stopped_publishing(
    context: _LateContext,
) -> _LateAdjudicationRun | None:
    """Ask the owner whether the next publication step may happen at all.

    None is the only answer that lets one run, and it is the same guard the
    child loop takes between two creates -- a closed owner ends the cycle
    where it stands, an unreadable one parks with the read owed on the
    record, and neither is a state anything below may publish over.
    """
    still_wanted = _late_owner._still_wanted(context)
    if still_wanted is None:
        return None
    return _late_outcome._finished(context, still_wanted)


def _announced(
    context: _LateContext, plan: _SplitPlan, snapshot_ref: str,
) -> None:
    """Say on the parent what it became, exactly once.

    Two gates, because neither answers the whole question on its own. The
    generation's own `links_announced` flag is the cheap one and the one that
    holds on the ordinary retry -- it is scoped to this adjudication, unlike
    `decomposed_at`, which an EARLIER decomposition of the same issue already
    wrote and which would therefore suppress this announcement entirely. The
    thread is the expensive one and the one that covers the window the flag
    cannot: a comment that landed and a process that died before the write is
    indistinguishable from the outside, so the marker this generation stamps
    into its own sentence is looked for among the comments before another is
    posted. It is asked only when the flag is unset, so a resume past the
    announcement costs nothing.

    `decomposed_at` is written all the same, because it is what the stage's
    own readers date a decomposition by; it is simply not this step's receipt.
    """
    if context.generation.links_announced:
        return
    if not _links_on_thread(context):
        _comments._post_issue_comment(
            context.gh,
            context.issue,
            context.state,
            _FORWARD_LINKS.format(
                sha=context.generation.candidate_sha,
                count=len(plan.created),
                children=_child_lines(plan),
                ref=snapshot_ref,
                marker=_forward_marker(context.generation),
            ),
        )
    context.state.set(_DECOMPOSED_AT, _usage._now_iso())
    context.generation = replace(
        context.generation,
        phase=LatePhase.SUPERSEDING,
        links_announced=True,
    )
    _late_park_state._persist(context)


def _links_on_thread(context: _LateContext) -> bool:
    """Whether this generation's own forward links are already said.

    Walked whole rather than from a watermark: the post moves every watermark
    this mode keeps past itself, so a scan bounded by one would start above
    the very comment it is looking for.
    """
    return _github_comments.carries_own_marker(
        context.gh.comments_after(context.issue, None),
        _forward_marker(context.generation),
        bot_login=getattr(context.gh, "_bot_login", None),
    )


def _forward_marker(generation: LateGeneration) -> str:
    """The receipt this generation's forward-link comment carries."""
    return _FORWARD_LINK_MARKER.format(
        cycle=generation.cycle_id, generation=generation.generation,
    )


def _supersession_marker(context: _LateContext) -> str:
    """The receipt this generation's supersession notice carries."""
    return _SUPERSESSION_MARKER.format(
        issue=context.issue.number,
        cycle=context.generation.cycle_id,
        generation=context.generation.generation,
    )


def _supersession_notice(
    context: _LateContext, plan: _SplitPlan, snapshot_ref: str,
) -> str:
    """What either road tells the pull request it is closing.

    One sentence for both, because what it says is a fact about the SPLIT
    rather than about which pull request carried the work: the umbrella it
    became, the children it went to, the ref it is preserved on, and the exact
    commit. Which pull request hears it is the caller's question.
    """
    return _SUPERSESSION_NOTICE.format(
        parent=context.issue.number,
        count=len(plan.created),
        ref=snapshot_ref,
        sha=context.generation.candidate_sha,
        children=_child_lines(plan),
        marker=_supersession_marker(context),
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
    if context.generation.has_publication_context:
        return _superseded_publication(context, plan, snapshot_ref)
    number = context.generation.plan_pr_number
    if number is None:
        return True
    settled = _released_hold(context) and _closed_over_notice(
        context, number, _supersession_notice(context, plan, snapshot_ref),
    )
    if not settled:
        return _unsuperseded(context, number)
    _recorded_resource(
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
    release = _late_hold._release_hold(
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
    number = context.generation.published_pr_number
    if number is None:
        return True
    if not _released_hold(context):
        return _unsuperseded(context, number)
    return _proved_and_closed(
        context, number, _supersession_notice(context, plan, snapshot_ref),
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
        context.gh, context.issue, number, _supersession_marker(context),
    )
    if reading.refused:
        return _unsuperseded(context, number)
    unsettled = _publication_is_still_the_one(context, reading, number)
    if unsettled:
        return _parked_publication(
            context, number, unsettled, _DISAGREEING_PUBLICATION_PARK,
        )
    if reading.state == _late_publication.CLOSED:
        return _recorded_supersession(context, number)
    return _closed_publication(context, number, notice, reading.superseded)


def _publication_is_still_the_one(
    context: _LateContext,
    reading: _late_publication._PublicationReading,
    number: int,
) -> str:
    """Why this pull request is not the one the verdict was taken over, or "".

    Named rather than counted, because what an operator has to reconcile
    differs by which of the two moved: a change they settled themselves, and a
    change somebody pushed to while the adjudication was open.

    A pull request closed over THIS adjudication's own receipt is neither, as
    far as the STATE goes. It is the supersession this transaction already
    made, on a tick that died before the retirement behind it -- so the close
    is no disagreement and the step below finishes as a read. A MERGED one is
    not that, whatever the thread says: a human who reopened and landed the
    work decided the opposite of what the supersession claims, and handing it
    to children afterwards is the one outcome nothing takes back. A reopened
    one is not that either -- it reads `open`, so the close is made again,
    with the receipt already on the thread keeping the notice from repeating.

    The head is proved on that path too, and on every other. A close does not
    freeze a branch: somebody can push to it after this transaction closed the
    pull request and before the retry arrives, and the receipt says only that
    the close was made, never that what it closed is still what the verdict
    was taken over. Waved through, the retry would settle the split, activate
    the children, and RECLAIM that branch -- deleting a commit no snapshot
    holds, because the snapshot was taken of the frozen head.
    """
    if reading.state == _late_publication.CLOSED and reading.superseded:
        return _own_supersession_holds(context, reading, number)
    if reading.state != _late_publication.OPEN:
        return _SETTLED_PUBLICATION.format(
            number=number, state=reading.state,
        )
    return _publication_moved(context, reading, number)


def _own_supersession_holds(
    context: _LateContext,
    reading: _late_publication._PublicationReading,
    number: int,
) -> str:
    """Why the close this split already made cannot be finished, or "".

    The receipt answers the state and nothing else, so the head is asked
    exactly as it is on the open path: a branch pushed to behind the close is
    a disagreement whoever made it, and it fails closed here rather than being
    discovered by the reclamation that deletes it.
    """
    moved = _publication_moved(context, reading, number)
    if moved:
        return moved
    log.info(
        "issue=#%d finds PR #%d already closed over this adjudication's "
        "own supersession; finishing the split its retirement interrupted",
        context.issue.number, number,
    )
    return ""


def _publication_moved(
    context: _LateContext,
    reading: _late_publication._PublicationReading,
    number: int,
) -> str:
    """Why this pull request no longer stands where it was frozen, or "".

    A head that will not read as a whole object id is movement too: what the
    verdict was taken over is a named commit, and text that is not one cannot
    be shown to be it.
    """
    head = _payloads.as_hex(reading.head, _formats.COMMIT_LENGTHS)
    frozen = context.generation.published_sha
    if head == frozen:
        return ""
    return _late_publication._MOVED_PUBLICATION.format(
        number=number, frozen=frozen, moved=head or "an unreadable head",
    )


def _parked_publication(
    context: _LateContext, number: int, disagreement: str, park: str,
) -> bool:
    """Park with the children durable and the pull request left alone.

    Nothing is activated and nothing is reclaimed, so the retry finds the same
    world: the snapshot and the children are on the remote, the pull request
    is where its human left it, and the same recorded verdict is settled again
    once the disagreement is reconciled.

    Parked with the disagreement in the notice rather than with the write
    failure's sentence, because this is not a supersession that failed. It is
    one this transaction refuses to finish -- and past the close it is one it
    already MADE -- so telling the human it "could not be superseded" would
    send them looking for a write that never went wrong. Which of the two the
    human is reading is `park`: a pull request that may not be superseded and
    one whose supersession came undone are different things to reconcile, and
    only the caller knows which side of the close it is on.
    """
    log.error(
        "issue=#%d was adjudicated as a split against PR #%d and %s; "
        "refusing to finish that split behind it",
        context.issue.number, number, disagreement,
    )
    return _unsuperseded(
        context, number, park.format(disagreement=disagreement),
    )


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
        return _unsuperseded(context, number)
    overtaken = _publication_is_still_the_one(context, confirmed, number)
    if overtaken:
        return _parked_publication(
            context, number, overtaken, _DISAGREEING_PUBLICATION_PARK,
        )
    if not _superseded_pull_request(context, confirmed, notice, said):
        return _unsuperseded(context, number)
    return _recorded_supersession(context, number)


def _recorded_supersession(context: _LateContext, number: int) -> bool:
    """Write the supersession this pass either made or found already made."""
    _recorded_resource(
        context,
        LateResourceKind.PLAN_PR,
        str(number),
        LateResourceState.RECONCILED,
    )
    return True


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
            marker=_supersession_marker(context),
            carries_marker=said,
        )
    except Exception:
        log.exception(
            "issue=#%d could not supersede the publication it had confirmed",
            context.issue.number,
        )
        return False


def _publication_holds(context: _LateContext) -> str:
    """Why the close this pass made no longer holds, or "".

    The shared reading one owner down, taken off the record this pass is
    carrying -- which still names the publication past the retirement, since
    that write keeps the group.
    """
    return _late_publication._publication_undone(
        context.gh, context.issue, context.generation,
    )


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
        held, notice=notice, marker=_supersession_marker(context),
    )


def _recorded_resource(
    context: _LateContext,
    kind: LateResourceKind,
    target: str,
    resource_state: LateResourceState,
) -> None:
    """Move one obligation to the state this step left it in, durably.

    A ledger update this binary cannot apply is logged and stepped over rather
    than raised: by the time most of these run the children are already live,
    and taking the tick out over a bookkeeping entry would strand them behind
    an exception instead of behind a retry.
    """
    try:
        context.generation = context.generation.with_resource(LateResource(
            kind=kind, target=target, resource_state=resource_state,
        ))
    except _formats.InvalidLateValue:
        log.exception(
            "issue=#%d could not record the %s obligation %r",
            context.issue.number, kind, target,
        )
        return
    _late_park_state._persist(context)


def _unsuperseded(
    context: _LateContext, number: int, message: str = "",
) -> bool:
    """Park with the children durable and none of them activated.

    One reason key for every way the supersession does not land, because what
    the issue is waiting on is the same in all of them: a pull request this
    workflow may not act on behind. `message` is the sentence the human reads
    when a caller has a sharper one than "the write failed".
    """
    _recorded_resource(
        context,
        LateResourceKind.PLAN_PR,
        str(number),
        LateResourceState.FAILED,
    )
    _parked(
        context,
        message or _SUPERSESSION_FAILED_PARK.format(number=number),
        LateFailure.SUPERSESSION_FAILED,
        _late_park_state.PARK_SUPERSESSION_FAILED,
    )
    return False


def _child_lines(plan: _SplitPlan) -> str:
    """The forward links one split owes every reader of it."""
    return "\n".join(
        f"- #{number}: {child['title']}" for number, child in plan.created
    )


def _parked(
    context: _LateContext, message: str, failure: LateFailure, reason: str,
) -> None:
    """Hand the issue back with the recorded verdict and ledgers standing."""
    _late_outcome._emit_failure(context, failure)
    _late_parks._park(context, message, reason=reason)


def _run_late_split(
    context: _LateContext, finished: _LateAdjudicationRun,
) -> _LateAdjudicationRun:
    """Prepare the durable split, then publish and retire it in guarded order."""
    prepared = _late_split_preparation._prepare_split(context, finished)
    if isinstance(prepared, _LateAdjudicationRun):
        return prepared
    return _published_split(
        context, finished, prepared.plan, prepared.snapshot_ref,
    )
