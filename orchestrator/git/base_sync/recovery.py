# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The single route from an interrupted auto-rebase to one terminal answer.

The verified facts arrive from ``snapshot`` and the answers live in
``outcomes``; what this owner adds is the order they are asked in, and that
order is the safety property. An ineligible label is answered before anything
is fetched, an unmoved HEAD is answered before any comparison is trusted, and
equality with the remote is checked before the
ahead/behind counts are -- so the reissued force-push is only ever reached by
a head proven to be ahead of a remote the tick actually read. Anything else
parks. The legacy keyword signature is bound here too, because the flat
callers still pass the pre-context argument list this route derives its
context from.

What the remote says is only half of what an interrupted rebase has to be
classified by, because the rebase may have been carrying a human's verdict
onto the commit it produced. ``transfers`` answers the other half off the
pinned comment -- how far the transfer's own writes got -- and the road that
still has something to publish is handed it. A rewrite the grant never reached
is given re-derived evidence, so the replay is decided on the transfer the
dead tick would have asked for rather than measured past the same ceiling and
adjudicated a second time with a pull request open over the work.

Every road out of here ends in a notice, an audit event, and the anchor
dropped, so the publication the attempt recorded making its rewrite for is
reconciled against the one this issue holds now before any of them is taken.
An issue moved off the refresh-driven set is answered the same way -- by what
the attempt left rather than by the label alone: an anchor over a checkout
still standing on it is dropped, and a recorded replay, an unspent permission,
or a branch git has already moved parks with every record intact, since no
road runs here and a clear would leave them asymmetrically stranded.

The counts are a fallback for one state alone -- a comment carrying no record
of a replay at all -- and the window between git returning and the write that
names one has a road of its own, where the head is proved by what it
contributes rather than by an id nobody wrote down. Every state neither of
those covers -- a record this build cannot read, one naming another commit, a
tree carrying uncommitted changes, a remote somebody rolled back -- is
fail-closed: the branch goes back onto the anchor and a human is asked.

The count of questions this carries is what the subject costs rather than a
module that outgrew itself. One interrupted attempt is classified on two
readings taken together -- where the remote stands, and how far the transfer's
own writes got -- and the ORDER those questions are asked in is the safety
property. Split across owners, the order would live nowhere and each half
would be free to reach the push on a question the other had already refused.
"""
from __future__ import annotations

import inspect
from typing import Any

from orchestrator.git.base_sync import (
    attempts,
    outcomes,
    persistence,
    publication,
    snapshot,
    transfers,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
    _PendingRewrite,
)
from orchestrator.git.base_sync.state import _PR_REFRESH_DETOUR_LABELS
from orchestrator.git.verification import probes as verification_probes
from orchestrator.workflow.state import WorkflowLabel

# Why a push that landed could not be finished, in the operator's own terms.
# Spelled at the seam that answers for it rather than beside the park, which
# takes whatever reason its caller established.
_UNROTATED = (
    "the push went out and the verdict did not move with it, so the "
    "permission granted for `{published}` is still outstanding"
)

# The two handoffs that say a grant is still standing over a commit the branch
# does not have: one this build reads as owed a push, and one it cannot read
# at all. A settled transfer is neither -- it is never cleared, so an issue
# that earned one would never look unstarted again.
_UNSPENT_TRANSFERS = frozenset((
    transfers._Handoff.OUTSTANDING, transfers._Handoff.UNVOUCHED,
))

# The two handoffs a checkout whose attempt record has no head may still be
# published on. Neither is an id the ATTEMPT wrote: one is the verdict the
# permit re-proves the contribution against, and the other is the permission
# this route's own grant persisted before its push -- cross-bound to the
# lease, the terms, and the accepted pair before it is called outstanding.
_VOUCHED_IN_FLIGHT = frozenset((
    transfers._Handoff.UNRECORDED, transfers._Handoff.OUTSTANDING,
))

_RECOVERY_SIGNATURE = inspect.Signature((
    inspect.Parameter("gh", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("spec", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("issue", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("state", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("worktree", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("pr_number", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter("label", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter(
        "pending_pre_rebase_sha",
        inspect.Parameter.KEYWORD_ONLY,
    ),
    inspect.Parameter(
        "pending_rewrite",
        inspect.Parameter.KEYWORD_ONLY,
        default=_PendingRewrite(),
    ),
    inspect.Parameter("behind", inspect.Parameter.KEYWORD_ONLY, default=0),
    inspect.Parameter(
        "unparking_consumed_max",
        inspect.Parameter.KEYWORD_ONLY,
        default=None,
    ),
))


def _retry_recovery_push(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    carried: transfers._Handoff = transfers._Handoff.NOTHING,
    *,
    permit_alone: bool = False,
) -> bool:
    """Publish a verified ahead-only recovery head and finalize its state.

    Measured before it is published, like every other push onto a pull request
    the remote already carries: the head this recovery found is one an earlier
    tick rebased and never pushed, so nothing on this branch has been read
    against the base it now sits on.

    Unless the branch is standing on a rewrite of a commit an adjudication
    accepted, which is the one candidate that may be published without a
    reading. `carried` says how far the interrupted tick got with that
    transfer, and what this call owes it is the evidence: a permission the
    grant already recorded is what `late_transfer` re-asks the permit over,
    and a rewrite that never reached one is re-derived here so the replay is
    not measured past the same ceiling and adjudicated a second time with a
    pull request open over the work.

    Where there IS such a transfer, the permit is the whole of what may let
    this push out. It is asked before the gate and the gate is told the same,
    so a refusal is a refusal on both sides of that seam rather than a
    fall-through to the cumulative reading -- which on this road would
    force-push a replay nothing vouched for and clear the recovery with the
    verdict still on the commit a human ruled on. The rotation is read back
    afterwards for the same reason, since a permit that stopped holding
    between the two asks leaves the push landed and the verdict where it was.

    `permit_alone` says the ATTEMPT record names no head -- the process died
    inside the window between `git rebase` and the write after it -- so the
    transfer is the only thing that can vouch for this checkout. Evidence that
    will not assemble parks there rather than falling through, because the
    fall-through is the ordinary cumulative reading and measuring a commit is
    not a way of establishing whose it is. A permission this route's own grant
    already persisted is that evidence rather than the absence of it, so it
    licenses the road exactly as the re-derived rewrite does.
    """
    dirty_files = verification_probes._worktree_dirty_files(context.worktree)
    if dirty_files:
        return outcomes._park_dirty_recovery(
            context, recovery_snapshot, dirty_files,
        )
    rewrite = transfers._reconstructed(
        context, recovery_snapshot.head, carried,
    )
    licensed = rewrite is not None or carried == transfers._Handoff.OUTSTANDING
    if permit_alone and not licensed:
        return outcomes._park_unproven_replay_recovery(
            context, recovery_snapshot,
        )
    if licensed and not transfers._permits_the_publication(
        context, recovery_snapshot.head, rewrite,
    ):
        return outcomes._park_refused_permit_recovery(
            context, recovery_snapshot,
        )
    return _pushes_the_recovered_head(
        context, recovery_snapshot, rewrite, licensed,
    )


def _pushes_the_recovered_head(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    rewrite,
    licensed: bool,
) -> bool:
    """Reissue the interrupted push and finalize what it earns.

    `licensed` says a transfer this recovery already knows about is the whole
    of what may let the push out, and it is passed to the gate as well as
    asked ahead of it: a permit that stops holding between the two asks is
    refused there rather than measured, and one that stops holding after the
    push leaves the verdict where it was, which the rotation read below
    catches.
    """
    landed = recovery_snapshot.head
    records = publication._gate_records()
    published = publication._gated_publication()._publishes(
        records._gate(
            context.gh, context.spec, context.issue, context.state,
            context.worktree,
        ),
        recovery_snapshot.branch,
        records._Entered(
            head=context.pending_pre_rebase_sha or "", reconciling=True,
            # The head this recovery verified against the remote and the one
            # the finalize below records as published. The gate proves the
            # checkout again, and a commit that landed between the two
            # readings would be the one pushed while the notice and the event
            # named this one -- so the candidate is bound and a moved checkout
            # refuses instead.
            candidate=landed,
            rewrite=rewrite,
            permit_only=licensed,
        ),
    )
    unfinished = _unfinished_recovery_push(
        context, recovery_snapshot, published, licensed,
    )
    if unfinished is not None:
        return unfinished
    return persistence._finalize_recovered_rebase(
        context,
        local_head=landed,
        method="crash_recovery_pushed",
        notice=outcomes._pushed_recovery_notice(context, landed),
    )


def _unfinished_recovery_push(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    published,
    licensed: bool,
) -> bool | None:
    """What a reissued push that did not finish owes, or None where it did.

    Four answers before the finalize, and each is a different tick. A permit
    the gate refused publishes nothing and parks here, since measuring is the
    one thing this road may not fall back on. A hold is a tick the gate
    finished for itself -- parked, or handed to the adjudication -- and only
    the flags it left in memory are owed a write. A push that went out and
    failed is the caller's own park. And a push that landed without the
    verdict moving with it is a permit that stopped holding inside the gate.
    """
    if published.refused:
        return outcomes._park_refused_permit_recovery(
            context, recovery_snapshot,
        )
    if published.held:
        # The gate took the candidate this recovery was finishing, so the
        # finalize behind this -- the notice, the event, the `validating`
        # route -- is not this tick's. The park it left is written here, since
        # nothing else would.
        context.gh.write_pinned_state(context.issue, context.state)
        return True
    if not published.landed:
        return outcomes._park_failed_recovery_push(context, recovery_snapshot)
    landed = recovery_snapshot.head
    if licensed and not transfers._rotated_onto(context.state, landed):
        return outcomes._park_unfinished_recovery(
            context, recovery_snapshot, _UNROTATED.format(published=landed),
        )
    return None


def _recover_pending_auto_base_rebase_context(
    context: _AutoRebaseRecoveryContext,
) -> bool:
    """Route an interrupted auto-rebase from verified local/remote state."""
    if context.label not in _PR_REFRESH_DETOUR_LABELS:
        return _answers_an_ineligible_label(context)

    recovery_snapshot = snapshot._fetch_recovery_snapshot(context)
    if recovery_snapshot is None:
        return True
    if (
        recovery_snapshot.local_head
        and recovery_snapshot.local_head == context.pending_pre_rebase_sha
    ):
        return _finish_an_unmoved_head(context, recovery_snapshot)

    return _route_recovery_snapshot(context, recovery_snapshot)


def _answers_an_ineligible_label(
    context: _AutoRebaseRecoveryContext,
) -> bool:
    """Answer an anchor found under a label the base refresh does not drive.

    Nothing is fetched and nothing is compared, because nothing under this
    label is coming back to do either. So the road is a clear or a park, and
    what decides between them is whether the attempt left anything a clear
    would strand.

    An anchor over a checkout still standing ON it strands nothing. Git never
    moved the branch, no replay exists, and no permission was granted, so the
    anchor is a promise to come back that nobody is coming back for: dropping
    it costs the issue nothing, and leaving it pinned would strand a flag no
    later tick under this label ever reads.

    Everything else parks with every record intact. A rebase the tick
    RECORDED, or a permission granted for a push that never landed, is state
    the clear cannot honour: it would drop the one field naming what the
    branch would go back to while leaving the verdict, the debt, and the
    replay standing without it. A checkout that has MOVED off the anchor under
    the terms alone is the same refusal one reading over: that is the window
    between `git rebase` returning and the write that names what it produced,
    and the terms on their own cannot tell it from an attempt that never
    started. Cleared there, the replay stays on the branch with nothing on the
    comment naming it, and the issue this route hands on is one no reader can
    tell from an issue with nothing in flight -- so another handler or a
    decomposition tick is free to start over on a change a human already ruled
    on.

    The head is read locally, which costs no fetch and no request. A reading
    that could not be taken is no evidence the branch is where the attempt
    left it, so it parks with everything else this route cannot prove.
    """
    if context.pending_rewrite.left_a_replay:
        return outcomes._park_stranded_recovery(context)
    if transfers._left_mid_transfer(context.state):
        return outcomes._park_stranded_recovery(context)
    if verification_probes._head_sha(
        context.worktree,
    ) != context.pending_pre_rebase_sha:
        return outcomes._park_stranded_recovery(context)
    return snapshot._clear_ineligible_recovery(context)


def _finish_an_unmoved_head(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Answer a checkout standing exactly where the attempt anchored it.

    Two states look identical from HEAD alone, and only one of them is the
    shortcut. An attempt that pinned its anchor and got no further left
    nothing else behind: no record of a replay, no permission it never spent,
    and a tree git has not touched. Dropping the anchor there costs nothing --
    the normal rebase flow picks the branch up on this same tick and does the
    work again.

    The other is an attempt that got a long way and was UNDONE. A reset that
    landed and whose park write did not, or somebody's own `git reset`, puts
    the branch back on the anchor with the record of the replay, the
    permission granted for it, and the debt beside it all still standing.
    Dropping the anchor there throws away the only thing that brings a
    recovery back, leaves the transfer state for the next grant to trip over,
    and hands the branch straight to a fresh rebase -- which force-pushes a
    commit no adjudication has seen over the one the pull request carries.

    So the shortcut is for the unstarted attempt only, and everything else is
    finished as the rollback it is: the reset is re-run onto the head the
    branch is already on, which is what lets the abandoned debt and the
    permission the replay will never spend go with it, and the issue parks for
    a human to say what undid it.
    """
    if _unstarted_attempt(context, recovery_snapshot):
        return snapshot._clear_unchanged_recovery(context)
    return outcomes._park_undone_recovery(context, recovery_snapshot)


def _unstarted_attempt(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Whether this attempt left nothing behind but the anchor it pinned.

    Three things say it did leave something. A record of the replay it
    produced, whether whole or in pieces, is an attempt that reached the write
    after `git rebase` -- and a reset that put the branch back before its own
    park write leaves exactly that. A mark that a finish announced ANYTHING
    says the same from the far end of the route, and it is asked by presence
    rather than against the head in hand: no finish ever announces the anchor,
    so a mark naming it is a checkpoint something took apart rather than an
    absence, and read as one it would hand the branch to a fresh rebase over a
    publication that has already gone out. A permission this build reads as
    outstanding, or one it cannot vouch for at all, is a grant that was never
    spent on a commit the branch no longer has.

    A SETTLED permission is not one of them: a transfer that finished is never
    cleared, so every issue that ever earned one would fail this test for the
    rest of its life.

    The TREE is nobody's question here, and deliberately. A checkout carrying
    uncommitted work is one the clean-tree gate ahead of every rebase already
    refuses, so a shortcut taken over one hands the branch to a flow that
    stands down on the same tick -- and where the dirt came from a reset this
    attempt took, the record it left is the first test above.

    Costs no git and no request, which is what lets the ordinary unstarted
    attempt -- the whole reason this shortcut exists -- pay nothing for it.
    """
    if context.pending_rewrite.left_a_replay:
        return False
    if attempts._carries_an_announcement(context.state):
        return False
    carried = transfers._carried_by(context, recovery_snapshot.head)
    return carried not in _UNSPENT_TRANSFERS


def _route_recovery_snapshot(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Route a changed-head recovery from its completed local/remote compare.

    Two classifications rather than one, taken together because the answer is
    the pair. Where the REMOTE stands says which effect the dead tick got as
    far as -- still on the anchor and the push never went out, on the rewrite
    and it did, anywhere else and somebody moved the branch out of band. What
    the pinned comment CARRIES says which of the transfer's own writes it got
    as far as, and that is what the road with something left to publish is
    handed: the evidence a permit is decided on. It costs no git and no
    request, so the road that has nothing left to publish pays nothing for a
    question it does not ask.

    The unpublished road is answered by exact SHAs rather than by the
    ahead/behind counts, and for the interrupted rebase that is the whole
    difference between finishing and parking. A rebase REPLAYS the branch: the
    commit the pull request still carries is on no local history afterwards,
    so git counts the branch as behind its own publication -- ahead by the
    replay and the base it moved onto, behind by the object it replaced. Read
    off those counts, the canonical pre-push recovery is indistinguishable
    from a remote somebody else pushed to, and the tick that only ever needed
    to reissue its push parks instead. What tells them apart is the pair of
    heads the attempt itself recorded: the anchor the remote must still be
    standing on, and the replay the checkout must still be.
    """
    completed = snapshot._complete_recovery_snapshot(
        context, recovery_snapshot,
    )
    if completed is None:
        return True
    if completed.local_head and completed.local_head == completed.remote_head:
        return outcomes._finalize_already_published_recovery(
            context, completed,
        )
    return _route_an_unpublished_head(
        context, completed, transfers._carried_by(context, completed.head),
    )


def _route_an_unpublished_head(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: transfers._Handoff,
) -> bool:
    """Route a checkout the pull request is not standing on.

    What survives every refusal beside this is the retry the anchor exists
    for -- reached on the pair of heads the attempt recorded, or, for a remote
    neither of them accounts for, on the counts over an attempt that recorded
    nothing at all.
    """
    refused = _refused_before_the_retry(context, completed, carried)
    if refused is not None:
        return refused
    in_flight = _is_an_attempt_in_flight(context, completed, carried)
    if in_flight or _is_this_attempts_rewrite(context, completed):
        return _retry_recovery_push(
            context, completed, carried, permit_alone=in_flight,
        )
    return _route_a_moved_remote(context, completed, carried)


def _refused_before_the_retry(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: transfers._Handoff,
) -> bool | None:
    """The park this checkout owes before any push, or None where it owes one.

    Five refusals, in the order the evidence for them costs nothing to read.

    The first is not about the commit at all: whether the attempt was made for
    the publication this tick holds. It is asked of the RECORD rather than of
    the permit, because the permit is not on every road -- an issue carrying
    no verdict never had one, and it still reaches a finalize that posts a
    notice to this tick's pull request, files an audit event under this tick's
    stage, and drops the anchor.

    The second is the announcement mark, asked by PRESENCE and asked of every
    road here. It is written between a finish's notice and its relabel, so it
    stands only where a push had already landed and the pull request had
    already been told -- and this whole road is reached over a remote that is
    not standing on the checkout. Whichever head the mark names, then, the
    publication it describes is one the remote has lost: a rollback, or a
    checkpoint something took apart. A retry would overwrite the rollback
    under a lease the anchor satisfies and announce the same rebase a second
    time, which is the one outcome the mark exists to prevent.

    Then the three about the commit. A remote the record says already carried
    this replay has been rolled back by somebody, and the anchor a retry would
    lease against is the head they rolled it back to. A transfer record nobody
    can vouch for would reach the ordinary cumulative gate and send an
    adjudicated change into a second adjudication. And an attempt record that
    does not vouch for the checkout -- damaged, or whole and naming some other
    commit -- is the same refusal one field over: read as the window it
    resembles, it would fall through to the counts, and a strictly-ahead
    checkout would be measured and force-pushed on the strength of a claim
    nothing could check.
    """
    if _made_for_another_publication(context):
        return outcomes._park_foreign_publication_recovery(context, completed)
    if attempts._carries_an_announcement(context.state):
        return outcomes._park_announced_recovery(context, completed)
    return _refused_by_the_records(context, completed, carried)


def _refused_by_the_records(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: transfers._Handoff,
) -> bool | None:
    """The three refusals about the commit itself, or None where none holds.

    Split from the two above them only so each function answers a countable
    number of ways; the order across both is one order and is the property
    that matters.
    """
    if transfers._rolled_back_publication(context, completed.head, carried):
        return outcomes._park_rolled_back_recovery(context, completed)
    if carried == transfers._Handoff.UNVOUCHED:
        return outcomes._park_unvouched_recovery(context, completed)
    if _unclaimed_checkout(context, completed):
        return outcomes._park_unrecorded_recovery(context, completed)
    return None


def _made_for_another_publication(
    context: _AutoRebaseRecoveryContext,
) -> bool:
    """Whether the attempt was made for a publication this tick is not on.

    A pull request repointed or an issue relabelled while the process was down
    leaves a record naming terms the issue no longer has, and every road
    behind this one is loud: the notice goes to the pull request this tick
    holds, the audit event is filed under the stage this tick reads, and the
    anchor that is the only thing bringing the tick back is dropped. Where the
    checkout carries a verdict the permit refuses the same disagreement, but
    an ordinary interrupted rebase has no permit to refuse it -- the replay
    would be measured, force-pushed, and finalized under terms nothing
    checked.

    Silent where the attempt recorded no TERMS, which is the window between
    the anchor going down and git being allowed to run, and a comment from
    before this record existed. There is no claim to disagree with there, and
    the roads behind this one already refuse to publish anything they cannot
    show the terms of.

    Asked of the terms alone rather than through `answers_for`, which requires
    the replay beside them. The terms go down before git runs and the head
    only once it returns, so a comment carrying the first and not the second
    is an attempt still in flight -- one this route has a road for -- and it
    can say which publication it was made for just as exactly as a finished
    record can.

    The stage is compared against the label this tick read rather than against
    the transition graph, since what the record names is the stage the rewrite
    was entered from and nothing on this road relabels before it publishes.
    """
    recorded = context.pending_rewrite
    if not recorded.is_declared:
        return False
    claimed = (recorded.pr_number, recorded.stage)
    return claimed != (context.pr_number, _recovered_stage(context.label))


def _recovered_stage(label: str) -> WorkflowLabel | None:
    """The label this tick read, as the vocabulary a record is written in.

    A label the pinned record could never name is None rather than a raised
    lookup, and it answers the comparison above as the disagreement it is:
    nothing this route writes puts a stage there that is not one of these.
    """
    try:
        return WorkflowLabel(label)
    except ValueError:
        return None


def _is_an_attempt_in_flight(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: transfers._Handoff,
) -> bool:
    """Whether the attempt is still inside the window its record has no head.

    The narrowest window the attempt has and the only one no ATTEMPT record
    can close: the rebase produced a commit, the write naming it never
    happened, and what the comment still carries is the terms the attempt was
    entered under and the anchor the remote is standing on. Every road that
    reads the head off that record refuses this checkout, rightly -- nothing
    wrote it down, so nothing there can say it is this attempt's work.

    Something else can, and which something depends on how far the tick that
    died had got.

    A comment carrying no permission is answered by the verdict alone. An
    issue whose exemption names the commit the pull request carries has a pair
    a human ruled on recorded on it, and the permit re-fingerprints the
    checkout's contribution against that pair before it licenses anything: a
    replay of the accepted change proves out, and a commit somebody else left
    does not. So the road opens only where there IS such a verdict to prove
    against, and the push behind it is permitted or it does not happen.

    A comment carrying an OUTSTANDING one is answered by the permission
    itself, and it is this route's own grant looking back at it. The road
    above persists that permission before it pushes, so a process lost between
    the two comes back to exactly this shape -- terms with no head, and a
    permission naming one. It is not the window it resembles: the grant is
    cross-bound to this attempt before it is called outstanding, by the lease
    the anchor names, the publication and stage the terms name, and the
    accepted pair the identity names, and it was written only once the permit
    had proved the contribution equal to the one a human ruled on. Refused
    here, this route would park every crash its own durable write caused --
    the counts over a replayed branch read as divergence -- and the
    authorization it left would stand for ever with nothing able to spend it.

    Every other handoff is somebody else's claim or none: a settled transfer
    is over, one nobody can vouch for is refused above, and an issue carrying
    no verdict at all reaches neither road.

    Both other halves are still required, and for the reasons they always
    were. The remote has to be standing exactly on the anchor, which is what
    says no push of this attempt's ever landed and what the force-with-lease
    is pinned to. And the terms have to read back whole, since the permit's
    publication checks are asked against them.
    """
    if carried not in _VOUCHED_IN_FLIGHT:
        return False
    if completed.remote_head != context.pending_pre_rebase_sha:
        return False
    recorded = context.pending_rewrite
    return recorded.is_declared and not recorded.sha


def _unclaimed_checkout(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Whether a record was written and does not vouch for this checkout.

    The counts behind this refusal are a fallback for one state and one only:
    an attempt that reached no record of a REPLAY, which is either a comment
    from before this record existed or the window between git returning and
    the write that names what it produced. There they are all a recovery has
    on its own, and a strictly-ahead branch is a fast-forward the anchor lease
    loses nothing to.

    Every other absence is a claim. A group something took a member out of,
    and a whole group naming some OTHER commit, both leave a checkout the
    attempt does not vouch for -- and read as the window they resemble, the
    counts would measure it and force-push it under a lease a rebuilt
    worktree, an operator's reset, and a branch pointed at other work all
    satisfy. So a record of the replay having been written at all is what
    decides which road is available, and a comment carrying none is the only
    one that reaches the counts.

    The TERMS on their own are not that claim. They go down with the anchor,
    before git can move the branch, so a comment carrying them and no head
    says an attempt was in flight rather than anything about the checkout --
    and the road that answers for that window vouches for the head by what it
    contributes instead.
    """
    recorded = context.pending_rewrite
    return recorded.left_a_replay and not recorded.names(completed.head)


def _is_this_attempts_rewrite(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Whether the checkout is the replay this attempt made, over its anchor.

    Both halves, and neither is enough alone. The REMOTE has to be standing
    exactly on the anchor the rebase pinned before git ran, which is what says
    no push of this attempt's landed and what the force-with-lease behind the
    retry is pinned to. And the CHECKOUT has to be the head that attempt
    recorded as its own replay, which is the only thing that says the
    divergence in front of this tick is the rebase's work rather than a
    worktree somebody rebuilt, an operator's reset, or a branch pointed
    somewhere else -- every one of which satisfies the same lease and would
    take the candidate off the pull request.

    Empty provenance answers no, and what happens then depends on which
    emptiness it is. A comment carrying the attempt's terms and no head is the
    window between git returning and the write that records the replay, and
    the road beside this one answers for it on the evidence rather than on an
    id. A comment carrying nothing at all is an attempt from before this
    record existed, and there the recovery falls back to the counts it always
    used: a strictly-ahead branch is a fast-forward the anchor lease loses
    nothing to, and a divergent one parks.
    """
    if completed.remote_head != context.pending_pre_rebase_sha:
        return False
    return context.pending_rewrite.names(completed.head)


def _route_a_moved_remote(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: transfers._Handoff,
) -> bool:
    """Route a remote neither SHA this recovery holds accounts for.

    Reached once the pull request is proved to be standing on neither the
    rewrite this branch carries nor the anchor the rebase pinned before git
    ran, so whatever is on it arrived from somewhere else. The counts are what
    is left to tell those apart, and they answer the question they were always
    about: a pair of zeros over two heads that disagree is a reading that did
    not happen, a remote with commits of its own is one a force-push would
    drop, and a strictly-ahead branch is a lease this recovery may still try
    -- the push is pinned to the anchor, so a remote that is not on it refuses
    the request rather than being overwritten.
    """
    if completed.ahead == 0 and completed.behind == 0:
        return outcomes._reject_unknown_recovery_comparison(context, completed)
    if completed.behind > 0:
        return outcomes._park_diverged_recovery(context, completed)
    return _retry_recovery_push(context, completed, carried)


def _recover_pending_auto_base_rebase(
    *args: Any,
    **kwargs: Any,
) -> bool:
    """Finalize a clean auto-base-rebase interrupted by a prior crash.

    The pinned pre-rebase SHA distinguishes an unchanged worktree, an
    already-published rewrite, an ahead-only rewrite that still needs a
    push, and a branch that diverged through an out-of-band update. Returns
    False only when HEAD still equals the anchor and the normal rebase flow
    should continue on the same tick.
    """
    bound_fields = _RECOVERY_SIGNATURE.bind(*args, **kwargs)
    bound_fields.apply_defaults()
    context = _AutoRebaseRecoveryContext(**bound_fields.arguments)
    return _recover_pending_auto_base_rebase_context(context)


_recover_pending_auto_base_rebase.__signature__ = _RECOVERY_SIGNATURE
