# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read whether the interrupted replay belongs to this checkout and publication.

These predicates have no effects. The dormant replay coordinator applies them
in order before any retry, distinguishing a recorded replay, a grant-vouched
in-flight window, and a publication changed outside the attempt.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    attempts,
    transfer_values as _transfer_values,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.workflow.state import WorkflowLabel

# The two handoffs a checkout whose attempt record has no head may still be
# published on. Neither is an id the ATTEMPT wrote: one is the verdict the
# permit re-proves the contribution against, and the other is the permission
# this route's own grant persisted before its push -- cross-bound to the
# lease, the terms, and the accepted pair before it is called outstanding.
_VOUCHED_IN_FLIGHT = frozenset((
    _transfer_values._Handoff.UNRECORDED, _transfer_values._Handoff.OUTSTANDING,
))


def _made_for_another_publication(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
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

    One stage disagreement is this route's OWN and is forgiven: a finish
    relabels the issue to `validating` right after it records that it has
    announced itself, and before the write that clears the attempt -- so a
    tick that finds that mark beside a record made from another stage is
    looking at its own last step, and a remote since rolled back is the
    announced publication the next question refuses. Read as foreign instead,
    it parks without resetting over a branch the pull request no longer has.

    The forgiveness is as narrow as the step it recognizes. Only `validating`,
    because that is the one label this route ever writes; an issue somebody
    moved to `fixing` or `documenting` while the process was down is a
    publication this attempt was not made for, whatever mark stands beside it.
    Only the pull request the record names, because no step of this route
    repoints one. And only a mark naming the head in hand, because the finish
    writes the commit it published and nothing else -- a mark naming any other
    head is not evidence the relabel was this route's.
    """
    recorded = context.pending_rewrite
    if not recorded.is_declared:
        return False
    if recorded.pr_number != context.pr_number:
        return True
    stage = _recovered_stage(context.label)
    if recorded.stage == stage:
        return False
    return not _relabelled_by_its_own_finish(context, completed, stage)


def _relabelled_by_its_own_finish(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    stage: WorkflowLabel | None,
) -> bool:
    """Whether a `validating` label is the relabel this attempt's finish made.

    Read off the announcement the same finish wrote one step earlier, held to
    the commit the checkout is standing on: that pair -- the label and a mark
    naming this head -- is the one shape only this route's last step leaves.
    """
    if stage != WorkflowLabel.VALIDATING:
        return False
    return attempts._already_announced(context.state, completed.head)


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
    carried: _transfer_values._Handoff,
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
