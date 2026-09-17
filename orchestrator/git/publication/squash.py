# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The composed squash-and-publish entry point stage handlers call.

Sequencing the steps is the whole job: `planning` runs every probe while the
branch is still intact, `resume` answers a squash an earlier tick did not
finish, the size gate is entered on the publication the squash is about to
force-push onto, the terms of the rewrite go onto the pinned comment, and only
a plan that survived all of it and has a rewrite to make reaches the destructive
`rewrite`. Keeping that order here means no owner has to know when the next one
is safe to run.

Whether there is a rewrite to make is the plan's answer rather than this
owner's. Several commits are collapsed into one; a single commit is rewritten
where the shared normalization would write its subject differently -- a line
missing the pull request's reference, and one still carrying the tracked
issue's beside it; and a branch with neither is handed back untouched.

The gate sits BEFORE the rewrite deliberately. A squash is one of the pushes
onto a pull request the remote already carries, and the refusals it owes --
a pull request nothing could read, one a human closed mid-review, a tree that
is not provably clean, a head that moved out from under the reading -- are all
answerable while the branch is intact. Asked after the reset instead, every
one of them would cost a rewrite and a rollback to learn.

The recovery sits BEFORE what is on the branch is read as a verdict, for the
same kind of reason. A branch a squash already rewrote carries one commit
under the subject that rewrite committed, which is exactly what a branch the
squash has nothing left to do to carries, so reading the branch first would
report an unpushed rewrite as a success that measured and published nothing.
The record the rewrite wrote before it ran is what tells the two apart, and it
is read before anything is concluded from what is on the branch.

The record itself goes down between the entry and the reset, and both ends of
that window are deliberate. Ahead of the entry it would cost a write for every
publication the pull request refuses; behind the reset there would be nothing
left to write it FROM. A write GitHub refuses stops the squash rather than
letting it run unrecorded: the approved commits stay on the branch, and the
next tick squashes them afresh.

Where a refusal LEFT the branch is not a step in that sequence, and `standing`
owns it: it is a reading over the pinned record and the checkout, taken once
on the way out of here over an outcome this module has already decided. The
same owner answers whether a collapse is claimed at all, which is what decides
whether an install with the switch off still owes the entry a rewrite would
have taken.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.git.measurement import commits as measurement_commits
from orchestrator.git.publication import models, planning, resume, rewrite, standing
from orchestrator.git.verification import status as _worktree_status

# The revision a checkout's own head is named by.
_HEAD = "HEAD"

# Why the worktree is not the one this squash was planned over any more. Each
# is spelled as the park comment reads it, because what an operator has to
# reconcile differs by which of the two moved.
_DIRTIED_UNDER_THE_RECORD = "the tree stopped being provably clean"

_MOVED_UNDER_THE_RECORD = (
    "the plan was taken over `{planned}` and the checkout stands on `{head}`"
)

_RACED_THE_RECORD = (
    "the worktree stopped being the one this squash was planned over while its "
    "terms were being recorded ({refusal})"
)

_MOVED_UNDER_THE_READING = (
    "the worktree stopped being the one this squash was planned over while its "
    "pull request was being read ({refusal})"
)

# What a squash that could not say in advance what it was about to do is
# reported as. The rewrite destroys the evidence of itself, so a record it
# could not write is one no later tick could recover from.
_UNRECORDED_COLLAPSE = "{refusal}; the approved commits are still on the branch"


def _squash_and_force_push(
    gate, branch: str, pr_number: int | None,
) -> models._SquashOutcome:
    """Squash all commits since `origin/<base>` into one, force-push with lease.

    `gate` is the subject the size gate decides about -- the issue, its pinned
    state, and the checkout -- built by the caller, which is in the layer this
    module would otherwise have to reach up into for it. `pr_number` is handed
    in on the same terms: the pull request the squash subject references --
    the reviewer run's on an approval, the pinned one on a recovery -- or None
    where there is no number to reference.

    Returns one `_SquashOutcome`, in the four shapes a squash can end in:
      * `success` with `sha` and `count=0` — nothing for this call to rewrite:
        no commit on top of base, or the one commit there already carries the
        subject a publication would give it. Caller should leave state alone.
      * `success` with `sha` and `count=N>=1` — N commits were replaced by one.
        `sha` is the new local HEAD; the remote was force-pushed to match.
        `count=1` is the branch whose single commit was rewritten for its
        subject alone, so nothing was collapsed and no notice is owed; only
        `count>1` says history was replaced by less of it.
      * `error` — squash refused, or squash / push failed. Caller parks
        awaiting_human and the remote was not updated. `standing` says where
        that leaves the branch, in one of three: INTACT is the ordinary
        failure, which aborted before anything destructive or restored what it
        rewound, so the original commits are on the branch; COLLAPSED is a
        failure taken over a collapse an earlier tick left, which stays where
        it is because nothing here can prove what putting it back would
        restore; BURIED is a record the branch grew PAST, with the approved
        commits in its own history under whatever was committed on top of
        them; UNKNOWN is a failure this build cannot place at all -- a record
        it cannot read whole, a recorded head no object here answers to, or a
        checkout that would not report its own head.
      * `held` — the size gate took the issue out of this caller's hands.
        Where something durable names the squashed commit -- an oversized
        generation, or a frozen pair whose count never came back -- it stays
        on the branch for the verdict or the reconciliation that answers it;
        on a reading the gate could not take at all it froze nothing, parked
        with its own notice, and the branch was put back where the squash
        found it, so the retry has commits to squash and measure again rather
        than one nobody counted. Either way the caller stops without parking
        and without a handoff.

    A collapse an earlier tick did not finish is answered first, and it is
    answered before the commits on the branch are read as a verdict: the
    record that squash wrote before it ran is the only thing that tells one
    collapsed commit from a branch with nothing to collapse. Nothing is
    resumed on that record's shape alone -- both ends are peeled as objects,
    the history between them is walked against the count, and the commit on
    the branch has to carry the tree the recorded head left. What a proved
    record earns is the publication the interrupted tick owed: resumed under
    the lease it names, finished as a leased no-op where the push already
    landed, and reported with the count only the record still holds -- or the
    branch put back onto the head it names, where nothing durable claims what
    is on it.

    A record that goes down and is never spent is the caller's to drop, not
    this one's: the count on it is what the handoff behind a landed push still
    has to announce, so the write that finishes that handoff is what ends it.

    The publication is entered before anything destructive runs, so a pull
    request nothing could read, one a human closed mid-review, a dirty tree,
    or a head that moved off what this stage read all refuse with the branch
    exactly as the reviewer approved it. The squashed commit is then measured
    like every other candidate for a pull request the remote already carries:
    the tree is the one that was just approved, but the BASE moves, so what
    the branch adds to it is a question only this reading answers -- and this
    is the last push before a human is asked to merge.

    `SQUASH_ON_APPROVAL=off` decides only whether a NEW collapse is made. A
    collapse an earlier tick already made is finished either way -- it is on
    the branch and the remote either has it or does not -- so an install that
    flips the switch between the rewrite and the push does not abandon
    reviewer-approved work off the pull request. An issue with nothing
    recorded costs such an install nothing at all: no probe is run and no
    reading is taken.

    All of it behind the other switch. `DECOMPOSE=off` keeps a squash out of
    the gate entirely: no pull request is read, none of those refusals can be
    taken, and no reading is taken over the commit the squash makes. What such
    an install does is squash and force-push, under the lease this stage read
    for itself and under no other claim about the remote.

    The squash commit subject reuses the first commit's subject when it
    already carries a reusable `<prefix>:` form (Conventional or repo-local,
    so an `event:` / `career:` subject survives); otherwise it builds one
    from the issue title with `_infer_subject_prefix` -- a repo-local prefix
    when recent base history uses one, else `fix`/`feat`. With
    `PR_REF_IN_SUBJECT` on, either one is then normalized through
    `pr_references`, the owner every publisher shares, against this pull
    request and the tracked issue together: the line ends in exactly one
    ` (#<pr_number>)`, so a reused subject an earlier approval round already
    squashed to is not given a second reference, and the issue's own number
    goes -- the one a developer copied out of recent history, and the
    `subject (#issue) (#pr)` a developer commit and an earlier publication
    each wrote half of. Off, or with no number, the selected subject is
    committed exactly as it was picked: nothing appended, and nothing
    stripped on the way to a reference that is never written.

    That switch also decides the one-commit branch. On, such a branch is put
    through this same reset, commit, gate, and leased push for its subject
    alone whenever the normalization would write that subject differently --
    a line missing the reference, and one carrying the tracked issue's beside
    it -- with the tree untouched, the count 1, and nothing collapsed. Off, or
    with no number, a one-commit branch is not rewritten here at all. A
    rewrite the recovery finishes keeps the subject it was committed under
    either way.

    The message is subject-only -- no body, no trailers -- so the
    orchestrator-authored squash matches the repo's subject-only commit rule.
    The commit is authored under the AGENT_GIT_* identity (via env vars) so
    attribution matches the per-step commits this squash replaces.
    """
    return standing._tells_the_caller_where_the_branch_is(
        gate, _squashed_or_resumed(gate, branch, pr_number),
    )


def _squashed_or_resumed(
    gate, branch: str, pr_number: int | None,
) -> models._SquashOutcome:
    """Finish a collapse this issue began, or make one out of what is here.

    `SQUASH_ON_APPROVAL` decides only the second. A collapse an earlier tick
    already made is not a squash this switch can decline: it is on the branch
    and the remote either has it or does not, so an install that turns the
    switch off between the rewrite and the push would otherwise abandon
    reviewer-approved work off the pull request -- or, past the push, drop the
    only record the notice could be worded from. So the record is asked first
    and the switch second, and an issue with nothing recorded costs an install
    with it off exactly what it always did: no probe, no reading, no write.

    Whether one was CLAIMED when the tick began is remembered, because the
    recovery may drop it on the way past and the road behind that drop is not
    the same on both settings. With the switch on, a dropped record hands the
    branch to a rewrite that enters the publication and refuses a remote that
    moved; with it off there is no rewrite to do the asking, and the tick
    would hand a divergent branch on having read nothing. So the branch that
    is NOT going to be rewritten is answered by its own owner below.

    `PR_REF_IN_SUBJECT` is asked here as well, and what it decides is the
    plan's message: off, the plan is built with no number at all. On a branch
    of several commits that changes the subject alone. On a branch of one it
    decides whether there is a rewrite at all, since a subject the
    normalization hands back as written -- and every subject on an install
    that references nothing, where nothing is normalized -- leaves the plan
    with no message and this call with the no-op it has always been.
    """
    claimed = standing._claims_a_collapse(gate)
    if not config.SQUASH_ON_APPROVAL and not claimed:
        return models._SquashOutcome(success=True)
    try:
        plan = planning._prepare_squash(
            gate.spec, gate.worktree, gate.issue,
            pr_number if config.PR_REF_IN_SUBJECT else None,
        )
    except planning._SquashPreparationError as error:
        return rewrite._squash_failure(str(error))
    resumed = resume._resumed_squash(gate, branch, plan)
    if resumed is not None:
        return resumed
    if plan.rewrites and config.SQUASH_ON_APPROVAL:
        return _rewrites_the_branch(gate, branch, plan)
    return _handed_back(gate, plan, claimed)


def _handed_back(
    gate, plan: planning._SquashPlan, claimed: bool,
) -> models._SquashOutcome:
    """The branch this call will not rewrite, once a record is off it.

    Nothing here rewrites anything: either the plan found nothing to do -- no
    commits over the base, or the one commit there already committed under the
    subject a publication gives it -- or the switch says a new rewrite is not
    this install's mechanism. What the road still owes is the reading the
    rewrite would have taken.

    A branch that never CLAIMED a collapse owes none, and that is the whole of
    what an install with `SQUASH_ON_APPROVAL=off` has always cost: no probe,
    no pull-request read, no write.

    A branch that claimed one owes the entry, because the recovery has just
    dropped that record and only a rewrite would otherwise have asked. The
    record is the claim that a squash was begun here, so a tick that engages
    the recovery, concludes the reset never ran, throws the only evidence
    away, and reports success without ever reading the publication is one that
    hands `documenting` a branch whose remote may have moved out from under
    it. Asked, a pull request somebody closed, merged, or force-pushed refuses
    with the reviewer-approved commits exactly where they are.

    The drop itself stands whichever way that reading goes: the branch still
    carries every commit the record counted, so nothing was collapsed and the
    record is stale however the remote has moved. What the refusal buys is a
    human being told, rather than the divergence being carried into the next
    stage.

    That reading is taken whatever `DECOMPOSE` is set to, which is the one
    place in this owner the switch does not reach. Everywhere else a push
    follows and the lease is the second answer to a remote somebody moved;
    here there is no push at all, so a reading skipped is the last thing
    between a publication that has left and `documenting` having the issue.

    And the checkout is proved AGAIN once that reading comes back, for the
    reason the record write is: the read is a REQUEST, so the worktree is
    writable for the whole of it. A commit landing in that window is work no
    reviewer saw, and reported as the approved head it would be handed to
    `documenting` as though it were.
    """
    handed = models._SquashOutcome(success=True, sha=plan.original_head)
    if not claimed:
        return handed
    entry = rewrite._gated_rewrite()._proved_publication(
        gate, plan.original_head,
    )
    if not entry.is_frozen:
        return rewrite._squash_failure(entry.refusal)
    return _moved_under_the_reading(gate, plan) or handed


def _moved_under_the_reading(
    gate, plan: planning._SquashPlan,
) -> models._SquashOutcome | None:
    """Refuse a checkout that moved while the publication was being read.

    The same window the record write opens, one road over: the pull-request
    read is a request too, and nothing holds the worktree for its duration. A
    commit made there is a commit no reviewer approved and nothing measured,
    and this road reports the head it planned over -- so handed on, that
    commit reaches `documenting`, the docs pass, and the merge button as work
    somebody signed off.

    `standing` answers the two halves differently for the reason it always
    does: a tree that went dirty leaves the approved commits at the head this
    plan was taken over, and a head that moved has not been shown to leave
    them anywhere this call can name.
    """
    unmoved, refusal = _still_the_planned_checkout(gate, plan.original_head)
    if not refusal:
        return None
    return models._SquashOutcome(
        error=_MOVED_UNDER_THE_READING.format(refusal=refusal),
        standing=(
            models.BRANCH_INTACT if unmoved else models.BRANCH_UNKNOWN
        ),
    )


def _still_the_planned_checkout(gate, planned: str) -> tuple[bool, str]:
    """Whether the worktree is still the one a plan was taken over.

    Both halves are read, because a plan is about a head AND a tree: the reset
    behind a squash is `--soft` and the commit behind that takes the INDEX, so
    a change staged in any window here is collapsed in and force-pushed as
    work a reviewer approved, while a head that moved is a commit nobody here
    can account for being published under a plan taken over something else.

    The answer says WHICH of the two moved as well as that one did, since the
    two leave the approved commits in different places and every caller here
    words a human's notice from that.
    """
    proved = measurement_commits._prove_candidate_commit(gate.worktree, _HEAD)
    unmoved = proved.is_frozen and proved.sha == planned
    if unmoved and _worktree_status._worktree_status(
        gate.worktree,
    ).is_clean:
        return True, ""
    if unmoved:
        return True, _DIRTIED_UNDER_THE_RECORD
    return False, _MOVED_UNDER_THE_RECORD.format(
        planned=planned, head=proved.sha or "an unreadable head",
    )


def _rewrites_the_branch(
    gate, branch: str, plan: planning._SquashPlan,
) -> models._SquashOutcome:
    """Enter the publication, say what the rewrite is, and then make it.

    The three steps a squash with a rewrite to make still owes, in the one
    order that is safe, and the same three whether the rewrite replaces a
    history or only the subject over it. The entry refuses every publication
    this rewrite could not be pushed onto while the branch is still intact.
    The record goes down behind it, because the rewrite destroys the only
    evidence of what it was about and a write spent ahead of the entry would
    be spent on publications the entry refuses. And the rewrite runs last,
    when both have answered.

    A record GitHub would not take stops the squash rather than being skipped.
    What it buys is the whole of the recovery: without it a process that dies
    mid-rewrite comes back to a one-commit branch nothing on the comment
    accounts for, and the retry reports success having measured and published
    nothing. So the approved commits are left where they are and the next tick
    tries again.

    And the checkout is proved AGAIN once that write comes back, because the
    write is a request: the worktree is writable for the whole of it, and the
    reset that follows commits the index rather than the plan. A change staged
    in that window is collapsed into the squash and force-pushed as work a
    reviewer approved, with nothing between it and the pull request.
    """
    from orchestrator.workflow.stages.implementing import late_collapse_state

    gated = rewrite._gated_rewrite()
    entry = gated._entered_rewrite(gate, plan.original_head)
    if not entry.is_frozen:
        return rewrite._squash_failure(entry.refusal)
    unrecorded = late_collapse_state._records_the_collapse(
        gate,
        head=plan.original_head,
        base_sha=plan.base_sha,
        count=plan.count,
    )
    if unrecorded:
        return rewrite._squash_failure(
            _UNRECORDED_COLLAPSE.format(refusal=unrecorded),
        )
    raced = _raced_the_record(gate, plan)
    if raced is not None:
        return raced
    return rewrite._rewrite_squash(gate, branch, plan, entry)


def _raced_the_record(
    gate, plan: planning._SquashPlan,
) -> models._SquashOutcome | None:
    """Refuse a checkout that moved while its terms were being recorded.

    The window every other reading in this owner is taken outside of. The
    entry proved the tree and the head before the record went down, and the
    record is a REQUEST -- so between the two the worktree is writable by
    whatever else has it: an agent still winding down, an operator, a cleanup
    racing a timeout.

    Both halves are proved, because the reset behind this is `--soft` and the
    commit behind that takes the INDEX. A change staged in the window is
    collapsed into the squash and force-pushed onto the pull request as work a
    reviewer approved; a head that moved is a commit nobody here can account
    for being published under a plan taken over something else.

    The record goes with the refusal: nothing was rewritten, so what it
    describes did not happen, and left standing it would send the next tick's
    recovery at a branch still carrying every commit it names. The caller's
    own park write is what makes the drop durable.

    `standing` says where that leaves the branch, and the two halves answer
    differently. A tree that went dirty leaves the approved commits exactly
    where a human will look for them, on the head this plan was taken over. A
    head that MOVED is not a collapse -- nothing was rewritten here, and the
    record saying otherwise has just been dropped -- so a notice claiming
    either place would be inventing one: it is unknown, and the reading that
    found it is what the error already says.
    """
    from orchestrator.workflow.stages.implementing import late_collapse_state

    unmoved, refusal = _still_the_planned_checkout(gate, plan.original_head)
    if not refusal:
        return None
    late_collapse_state._forgets_the_collapse(gate.state)
    return models._SquashOutcome(
        error=_RACED_THE_RECORD.format(refusal=refusal),
        standing=(
            models.BRANCH_INTACT if unmoved else models.BRANCH_UNKNOWN
        ),
    )
