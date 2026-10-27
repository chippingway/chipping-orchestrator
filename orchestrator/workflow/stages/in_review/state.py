# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The wire key the in_review owners scan and ratchet on.

`pr_last_comment_id` bounds both IssueComment surfaces -- the issue thread and
the PR conversation share that id namespace -- but it does not answer for
either alone. The pull request answers to it and to nothing else, since no
other cursor has read that surface; the issue thread answers to it AND to the
stretch of it developer prompts were handed (`engine/thread_delivery`), above
the newest comment the first prompt's bound left out and through the newest a
prompt quoted -- never the reply boundary a park waits above. `surfaces` is
where those two questions are asked apart. It is written into the pinned JSON
comment live issues already carry -- the validating handoff seeds it, this
stage initializes it where nothing did, the fixing handler reads it back --
so renaming it is a migration of every open PR rather than a refactor.

It sits here rather than on the owner that carries it because the owner that
writes it is rarely the one that reads it: the handoff seeds it and
`watermarks` initializes it and carries it over what a tick wrote,
`surfaces` reads it, and `feedback` scans what those reads answer.

`in_review_handoff_pending` is the other, and it answers a different kind of
question: whether this issue owes `workflow:validating` a label move it has
not made yet. A requirements edit leaves the approval this label stands on
stale, so the round is reset and the label moved -- two operations a process
can die between. The marker goes down with the reset and comes off once the
label has moved, so a relabel nobody made is found and remade rather than
leaving an issue here to be pinged as ready on an approval that is over. An
issue without it owes no move.

`owes_validating_a_move` reads it back beside the other things that say the
same: a developer report still owed, and an approval recorded against a report
other than the one the issue now records as current, against requirements
other than the ones its drift baseline holds, or beside no evidence claim
(`approval_claims_evidence`). It is asked here
because the marker is what it chiefly reads, and every road that stages the
move is answered by it.

`stages_the_handoff` is the one write spelled here rather than at the owner
that makes it. Every field the hand-back puts down goes down together -- the
marker above, the fresh review round, and the record that the publication this
move is for already has its budget -- and a report recorded on the drift road
has to be measured against the comment they leave. `report_record_room`
reserves that write by calling this, so a field added here moves the
reservation with it instead of quietly eating a margin nobody rechecks.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    review_subjects as _review_subjects,
)
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    review_verdicts as _verdicts,
)

_PR_LAST_COMMENT_ID = "pr_last_comment_id"

_HANDOFF_PENDING = "in_review_handoff_pending"

_REVIEW_ROUND = "review_round"

# The requirements baseline the drift check holds an issue to.
_USER_CONTENT_HASH = "user_content_hash"


def owes_validating_a_move(state: PinnedState) -> bool:
    """Whether the approval this label stands on no longer covers the work.

    A report still owed, a move staged and not made, or an approval of some
    other report than the current one, of other requirements than the drift
    baseline holds the issue to, or beside no evidence claim -- each answered
    by the same move.
    """
    approval_stands = (
        _review_subjects.approval_covers_current(state)
        and approval_covers_requirements(state)
        and approval_claims_evidence(state)
    )
    return (
        _report_delivery.owes_a_report(state)
        or bool(state.get(_HANDOFF_PENDING))
        or not approval_stands
    )


def approval_claims_evidence(state: PinnedState) -> bool:
    """Whether the recorded approval names, read whole, the evidence it was proved over.

    Every approval records that claim beside its subject, since none reaches
    the approval arc unproved (`stages/validating/unverified_approvals.py`),
    so one beside no claim -- absent, `null`, or in a shape its reader
    refuses -- rests on no evidence, and the issue owes `validating` a fresh
    review rather than standing here on an approval nothing proved. Whether
    the evidence a whole claim names still proves is the readiness proof's,
    which holds the ping rather than handing the issue back: a base refresh
    that re-verifies the head moves that evidence without making the review
    stale.
    """
    recorded = state.get(_approved_evidence.APPROVED_EVIDENCE)
    return _verdicts.EvidenceClaim.read(recorded) is not None


def approval_covers_requirements(state: PinnedState) -> bool:
    """Whether the recorded approval was given the requirements the baseline holds.

    The approval was given the thread at one revision, and a drift baseline
    moved past it is requirements somebody was handed since -- a developer
    resumed on an edit, a reply spent on a park -- that no reviewer was.
    Asked here, where the approval is about to be advertised as ready to
    merge; the roads that finish a squash already under way do not ask it. An
    approval with no record read whole names no requirements, and covers none.
    An edit landing after the baseline was measured is `review_coverage`'s to
    find, over the issue read afresh at the ping.
    """
    approved = _review_subjects.ReviewSubject.requirements_recorded_in(
        state.get(_review_subjects.APPROVED_SUBJECT),
    )
    return approved is not None and approved == state.get(_USER_CONTENT_HASH)


def stages_the_handoff(
    state: PinnedState, *, owed_publication: bool,
) -> None:
    """Stage every field the hand-back writes ahead of the label it moves.

    `owed_publication` is whether a publication this move is for is still to
    come -- a report not settled, or an edit its resume never answered at all
    -- which is what earns the record that its round is already reset. The
    reservation asks for it, since the hand-back that writes fewer fields
    cannot be the one a measurement has to survive.
    """
    if owed_publication:
        state.set(_report_delivery.OWED_ROUND_RESET, True)
    state.set(_HANDOFF_PENDING, True)
    state.set(_REVIEW_ROUND, 0)
