# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The wire key the in_review owners scan and ratchet on.

`pr_last_comment_id` bounds both IssueComment surfaces -- the issue thread and
the PR conversation share that id namespace -- but it does not answer for
either alone. The pull request answers to it and to nothing else, since no
other cursor has read that surface; the issue thread answers to it AND to
`last_action_comment_id`, the delivery cursor an implementing or validating
resume settles for exactly the replies it quoted. `surfaces` is where those
two questions are asked apart. It is written into the pinned JSON comment live
issues already carry -- the validating handoff seeds it, the legacy migration
backfills it, the fixing handler reads it back -- so renaming it is a
migration of every open PR rather than a refactor.

It sits here rather than on the owner that carries it because the owner that
writes it is rarely the one that reads it: the handoff and the migration seed,
`watermarks` carries it over what a tick wrote, `surfaces` reads it, and
`feedback` scans what those reads answer.

`in_review_handoff_pending` is the other, and it answers a different kind of
question: whether this issue owes `workflow:validating` a label move it has
not made yet. A requirements edit leaves the approval this label stands on
stale, so the round is reset and the label moved -- two operations a process
can die between. The marker goes down with the reset and comes off once the
label has moved, so a relabel nobody made is found and remade rather than
leaving an issue here to be pinged as ready on an approval that is over. It
is additive: an issue without it owes no move, which is every issue that
predates it.

`owes_validating_a_move` reads it back beside the other things that say the
same: a developer report still owed, and an approval recorded against a report
other than the one the issue now records as current, or against requirements
other than the ones its drift baseline holds. It is asked here
because the marker is what it chiefly reads, and every road that stages the
move is answered by it.

`stages_the_handoff` is the one write spelled here rather than at the owner
that makes it. Every field the hand-back puts down goes down together -- the
marker above, the fresh review round, and the record that the publication this
move is for already has its budget -- and a report recorded on the drift road
has to be measured against the comment they leave. `report_record_state`
reserves that write by calling this, so a field added here moves the
reservation with it instead of quietly eating a margin nobody rechecks.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    review_subjects as _review_subjects,
)

_PR_LAST_COMMENT_ID = "pr_last_comment_id"

_HANDOFF_PENDING = "in_review_handoff_pending"

_REVIEW_ROUND = "review_round"

# The requirements baseline the drift check holds an issue to.
_USER_CONTENT_HASH = "user_content_hash"


def owes_validating_a_move(state: PinnedState) -> bool:
    """Whether the approval this label stands on no longer covers the work.

    A report still owed, a move staged and not made, or an approval of some
    other report than the current one, or of other requirements than the
    drift baseline holds the issue to -- each answered by the same move.
    """
    return (
        _report_delivery.owes_a_report(state)
        or bool(state.get(_HANDOFF_PENDING))
        or not _review_subjects.approval_covers_current(state)
        or not approval_covers_requirements(state)
    )


def approval_covers_requirements(state: PinnedState) -> bool:
    """Whether the recorded approval was given the requirements the baseline holds.

    The approval was given the thread at one revision, and a drift baseline
    moved past it is requirements somebody was handed since -- a developer
    resumed on an edit, a reply spent on a park -- that no reviewer was.
    Asked here, where the approval is about to be advertised as ready to
    merge; the roads that finish a squash already under way do not ask it. An
    approval nothing recorded names no requirements, and is held to its
    report alone. An edit landing after the baseline was measured is
    `review_coverage`'s to find, over the issue read afresh at the ping.
    """
    approved = state.get(_review_subjects.APPROVED_SUBJECT)
    if not isinstance(approved, dict):
        return True
    return (
        _review_subjects.ReviewSubject.requirements_recorded_in(approved)
        == state.get(_USER_CONTENT_HASH)
    )


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
