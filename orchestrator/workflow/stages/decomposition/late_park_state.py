# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The durable claim a late park and its generation make together.

Park reasons and pinned keys belong beside the predicates that read them.
Every late writer commits its generation through this owner, so a park and
whatever the step staged reach GitHub in one write. Notice delivery may only
follow that write; its own recovery owner reads the same state predicates.

The consumed-comment watermark is shared with later workflow stages. A reply
spent here must never become fresh feedback when the issue advances, and a
malformed or older reading must never lower the watermark.
"""
from __future__ import annotations

from orchestrator.workflow.engine import retry_budget as _retry_budget
from orchestrator.workflow.late_split import formats as _formats, state as _late_state
from orchestrator.workflow.stages.decomposition import late_notice as _late_notice
from orchestrator.workflow.stages.decomposition.late_models import _LateContext

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

# The issue-wide record of what the workflow has already acted on. Shared with
# every other stage, which is why this mode has to keep it moving: a reply this
# mode read and acted on is one the later validating -> in_review handoff must
# not find again as fresh PR feedback.
_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# Every way this mode hands an issue back, spelled once because each is a
# durable pinned value and because the set below is read against them.
PARK_HOLD_FAILED = "late_plan_pr_hold_failed"
PARK_INCOMPLETE = "late_generation_incomplete"
PARK_WORKTREE_MISSING = "late_worktree_missing"
# The recorded commits are HERE-or-not, which is a different answer
# from a checkout that is gone: the worktree can be present and still
# not hold the pair, on a host the branch never reached.
PARK_EVIDENCE_MISSING = "late_evidence_missing"
PARK_WORKTREE_MUTATED = "late_worktree_mutated"
PARK_TIMEOUT = "late_adjudicator_timeout"
PARK_UNPARSED = "late_manifest_invalid"
PARK_UNRECORDABLE = "late_result_unrecordable"
PARK_OWNER_UNREADABLE = "late_owner_unreadable"
PARK_SNAPSHOT_FAILED = "late_snapshot_failed"
PARK_CHILDREN_FAILED = "late_children_failed"
PARK_SUPERSESSION_FAILED = "late_supersession_failed"
PARK_PR_UNRECONCILED = "late_pr_unreconciled"
PARK_QUESTION = "late_question"
PARK_CONTENT_DRIFT = "late_content_drift"
PARK_REVISION_DIRTY = "late_revision_dirty"
PARK_REVISION_UNMEASURED = "late_revision_unmeasured"
PARK_REVISION_UNANSWERED = "late_revision_unanswered"
# What an adjudication that could not split the candidate hands back under.
# The agent has answered the question it was asked and the answer is that this
# oversized change stays one change, which is a thing only a human may
# license: the park is the workflow saying so and waiting.
PARK_SINGLE_DECISION = "late_single_decision"

# The shared spawn budget's own park, spelled by the engine that decides it
# rather than again here. A late adjudication is charged to the same per-issue
# day of tokens every other agent run is, so what stops it when that day is
# spent is the same durable reason every other stage's gate takes -- and it has
# to READ as that reason, because the tick that meets it next may be an initial
# decomposition rather than an adjudication.
PARK_RETRY_CAP = _retry_budget.PARK_RETRY_CAP

# The parks a fresh attempt answers, and therefore retires before it runs. A
# hold that failed has now been reconciled, a worktree that was gone is back, a
# run that timed out or answered unusably is about to be re-run, and a pull
# request lookup nobody could take is about to be taken again, and each of the
# three transaction steps -- the snapshot, the children, the supersession -- is
# about to be reconciled again from the same recorded verdict, at no agent's
# cost. The eight left out are the ones no retry answers. `PARK_QUESTION` is the announcement
# itself, and the four content
# parks are the workflow waiting to be told what an edited scope, a worktree
# the developer left changed, a candidate nobody could measure, or a developer
# that changed nothing and vouched for nothing now means. Retiring one of those
# would drop the very state the next tick reads to tell a human's answer from
# the silence before it.
#
# `PARK_SINGLE_DECISION` is left out because the attempt that would supersede
# it does not exist: the verdict is recorded, so every later tick reuses the
# same answer and reaches the same park at no agent's cost. Retiring it would
# clear the flag and re-take it one step later, saying the same sentence to
# the same thread once a poll while the human it is addressed to reads it.
#
# `PARK_RETRY_CAP` is left out for the plainest reason of the eight: a retry is
# exactly what it refuses. The attempt that would supersede it is the one the
# budget has no room for, so retiring it here would clear the flag and then
# meet the same spent budget one step later -- announcing the same sentence
# once a poll, and taking the park a human has to answer down in between.
#
# `PARK_OWNER_UNREADABLE` is left out for a different reason: it IS answered by
# a retry, but by one that runs before any of this -- the pending owner check
# the generation records, which is what brings a tick back to the read at all.
# That reconciliation reads the standing reason to decide whether it owes the
# thread a follow-up, so retiring the park here would erase the only durable
# evidence that this mode had said anything to retire.
_SUPERSEDED_PARKS = frozenset((
    PARK_HOLD_FAILED,
    PARK_EVIDENCE_MISSING,
    PARK_INCOMPLETE,
    PARK_WORKTREE_MISSING,
    PARK_WORKTREE_MUTATED,
    PARK_TIMEOUT,
    PARK_UNPARSED,
    PARK_UNRECORDABLE,
    PARK_PR_UNRECONCILED,
    PARK_SNAPSHOT_FAILED,
    PARK_CHILDREN_FAILED,
    PARK_SUPERSESSION_FAILED,
))


def _stands_already(context: _LateContext, reason: str) -> bool:
    """Whether this issue is already parked for exactly this reason.

    Asked of what the tick FOUND, not only of what it has staged. A park this
    tick retired into memory and is now re-taking for the same reason is the
    same park -- the step it named failed again, nothing about the issue moved
    between them, and the human it mentioned has already been told.

    "Nothing moved between them" is what the memory really claims, which is why
    the run that could move something clears it. Past a spawn the reason is no
    longer enough to call two parks the same: an agent answered, and a second
    categorized question or a second unusable reply says something the first
    notice did not. Suppressing those would leave an outcome recorded, durable,
    and never announced -- so only the reconciliation retries that spawn
    nothing keep the memory that quiets them.

    A park somebody cleared is not standing, whatever reason it carried, so an
    issue a human un-parked is announced to again rather than silently
    re-parked.

    And a park whose sentence was never said is not one the human has been
    told about, whatever its flag claims. The flag goes down before the
    comment goes out, so a refused post leaves one standing over a thread that
    was told nothing -- and answering from the flag alone would call that a
    repeat and suppress every later attempt to say it. What makes a park a
    repeat is the sentence, so that is what is asked.
    """
    if context.retired_park == reason:
        return True
    if not _stands_for(context, reason):
        return False
    return _late_notice._owed_notice(context) is None


def _stands_for(context: _LateContext, reason: str) -> bool:
    """Whether this issue is parked, right now, for exactly this reason.

    The flag alone, with nothing said about whether anybody was told. Asked by
    the steps that RETIRE a park -- which is owed to a park either way -- as
    against the ones that decide whether to repeat its notice.
    """
    if not context.state.get(_AWAITING_HUMAN):
        return False
    return context.state.get(_PARK_REASON) == reason


def _stands_parked(context: _LateContext) -> bool:
    """Whether this issue is already stopped waiting on a human.

    The flag alone, asked by the two steps that must not talk over a reason
    somebody else's park already took. The owner guard is one: an issue that a
    timeout, an unusable reply, or a stalled revision has already handed back
    is one nobody is going to publish anyway, and replacing that reason with
    "the owner could not be read" would swap the thing the human is being
    asked about for one they cannot answer -- what brings the next tick back
    to the read in that case is the generation's own pending marker, not the
    park. The announcement a recorded question earns is the other: a question
    the issue is already waiting on a human for is not asked twice.
    """
    return bool(context.state.get(_AWAITING_HUMAN))


def _mark_replies_read(context: _LateContext, through) -> None:
    """Record the trusted conversation this tick acted on as read, issue-wide.

    The late fingerprints are this mode's own bookkeeping; the watermark moved
    here is everybody's. A reply that resolved a park, certified a candidate,
    or reopened a question has been ACTED on, and leaving the shared watermark
    behind would let the validating -> in_review handoff read the same comment
    as fresh PR feedback -- routing the pull request to `fixing` over an answer
    this mode already spent, or resuming the developer on input it handled.

    `through` is the highest TRUSTED comment folded in, so an untrusted comment
    sitting above it stays unconsumed exactly as it does on every other resume:
    nothing an outsider posts is marked read on their behalf. A one-way ratchet,
    because a park notice or another stage may already have moved it further.
    """
    if not _formats.whole_number(through):
        return
    prior = context.state.get(_LAST_ACTION_COMMENT_ID)
    if not _formats.whole_number(prior) or through > prior:
        context.state.set(_LAST_ACTION_COMMENT_ID, through)


def _persist(context: _LateContext) -> None:
    """Write the generation this tick reached, and the state around it."""
    _late_state.write_late_generation(context.state, context.generation)
    context.gh.write_pinned_state(context.issue, context.state)
