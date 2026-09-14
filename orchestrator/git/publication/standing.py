# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a squash that failed left the branch, and whether one was claimed.

A refusal is what an operator acts on, and the notice behind one sends them
somewhere: to the commits still at HEAD, off the tip to the head a record
names, into the branch's own history under whatever was committed on top of
that head, or -- honestly -- nowhere this build can name. Which of the four is
a READING taken over the pinned record, the checkout's own head, and the
objects and ancestry between them, not a step in the collapse, so it answers
here rather than inside the sequencer that composes the collapse.

Nothing in this owner resets, writes, or pushes. Every road through `squash`
arrives with its outcome already decided and asks only for the field the park
notice is worded from, which is why the classification can be a pure reading
and why adding a probe to it costs no publication anything.

The claim itself -- whether the pinned comment records a squash somebody may
not have finished -- answers here too. It is the same question the stamp is
gated on, and the sequencer asks it once more to decide whether an install
with `SQUASH_ON_APPROVAL=off` owes the entry a rewrite would have taken. Both
readings go through the gate's own owner in `rewrite`, so the hop out of this
layer stays spelled in one place.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.git.measurement import commits as measurement_commits
from orchestrator.git.publication import models, resume
from orchestrator.git.verification import probes as verification_probes


def _claims_a_collapse(gate) -> bool:
    """Whether this issue records a squash somebody may not have finished."""
    from orchestrator.workflow.stages.implementing import late_collapse_state

    return late_collapse_state._claims_a_collapse(gate.state)


def _tells_the_caller_where_the_branch_is(
    gate, outcome: models._SquashOutcome,
) -> models._SquashOutcome:
    """Stamp a failure with which of the three places it left the branch.

    The caller words a human's notice from this, and the three are different
    errands. The ordinary failure aborts before anything destructive or
    restores what it rewound, so the commits a reviewer approved are at HEAD
    and squashing by hand starts from them. A failure over a collapse this
    call could not finish leaves the branch standing on the squash, with the
    approved history reachable from the head the record names. And a failure
    this build cannot account for is neither: said to be either one, it sends
    an operator looking for commits that are not where the notice says.

    An issue with no claim on its comment is left alone. Every road that puts
    the branch back drops the record in the same breath, so a failure with
    nothing recorded is the ordinary one by construction -- and that is the
    default the outcome already carries.
    """
    if not outcome.error:
        return outcome
    if not _claims_a_collapse(gate):
        return outcome
    return replace(outcome, standing=_where_the_branch_stands(gate))


def _where_the_branch_stands(gate) -> str:
    """Which of the three places a claimed collapse leaves the branch in.

    Three readings, and no two of them answer for each other. The RECORD says
    what the rewrite was about, but a record this build cannot read whole says
    nothing at all -- and the branch behind such a claim may be untouched,
    collapsed, or anywhere else. The CHECKOUT's own head says where the branch
    is now, and one git would not report is the same silence. The recorded
    HEAD is the third: it is the place the notice sends an operator to, so an
    object this host does not hold is an errand nobody can run, whatever the
    branch is standing on.

    Only one shape is the rewrite that did not happen: a record read whole
    whose head is the head the checkout is on, with the approved commits
    exactly where a human squashing by hand will look.

    A branch that moved off a recorded head this host really holds is two
    shapes rather than one, and the ANCESTRY tells them apart. A recorded head
    still reachable from HEAD is buried: nothing was rewritten, the approved
    commits are in the branch's own history under whatever was committed on
    top of them, and a notice sending an operator to the reflog would be
    sending them past the commits they are looking for. One the branch
    REPLACED is not reachable, which is what a finished collapse leaves, and
    the reflog entry a collapse notice names is the one that resolves.
    Everything else is unknown, and saying so is the whole of what this
    reading owes.
    """
    from orchestrator.workflow.stages.implementing import late_collapse_state

    recorded = late_collapse_state._recorded_collapse(gate.state)
    head = verification_probes._head_sha(gate.worktree)
    if recorded is None or not head:
        return models.BRANCH_UNKNOWN
    if head == recorded.head:
        return models.BRANCH_INTACT
    named = measurement_commits._prove_candidate_commit(
        gate.worktree, recorded.head,
    )
    if not named.is_frozen:
        return models.BRANCH_UNKNOWN
    if resume._is_ancestor(gate.worktree, recorded.head, head):
        return models.BRANCH_BURIED
    return models.BRANCH_COLLAPSED
