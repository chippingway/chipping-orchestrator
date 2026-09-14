# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Prove a squash's checkout, retained ownership, publication receipt, and retry lease.

A changed checkout is held without resetting work this squash did not make.
An approval, receipt, or live generation keeps its squash standing, and a
receipt for that exact rewrite lets recovery lease the already-published tip.
"""
from __future__ import annotations

import logging

from orchestrator import config
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.workflow.late_split import (
    collapses as _collapses,
    state as _late_state,
)
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_gate_models as _late_gate_models,
    late_park_notices as _late_park_notices,
    late_publication_state as _late_publication_state,
    late_records as _records,
)

log = logging.getLogger("orchestrator.workflow")



# The revision a checkout's own head is named by.
_HEAD = "HEAD"


# How a squash can fail to be the thing this owner publishes. Each is spelled
# as the park comment reads it, because what an operator has to reconcile
# differs by which side of the push it was noticed on.
_MOVED_CHECKOUT = (
    "the squash made `{squashed}` and the checkout stands on `{head}`"
)


_MOVED_SQUASH_PARK = (
    "{mentions} the reviewer approved this pull request and the orchestrator "
    "squashed its commits, but the checkout it squashed in is not the one the "
    "squash left behind: {refusal}. Something committed over the worktree "
    "while the publication was being made, so nothing has been handed on -- "
    "and the branch is left exactly as it was found rather than reset, since "
    "whatever moved it made a commit nobody here can account for. Reconcile "
    "the worktree with what landed and the next tick squashes afresh."
)


def _rewrite_stands(gate: _late_gate_models._Gate, squashed: str) -> bool:
    """Whether a HELD squash must be left on the branch it rewrote.

    A hold is not one state. Three of its shapes leave the squashed commit
    somebody's, and in each the reset the caller would otherwise take is the
    destructive step:

    * the push LANDED and only the handoff was held -- the receipt names the
      squash, so the remote carries it and a reset would take the branch off
      a commit the pull request has;
    * a DEBT names it -- the approval says this commit is owed a push and no
      other may be pushed in its place, so a reset would leave the
      reconciliation ahead of every later handler asking for a checkout back
      for work only the reflog still has;
    * the RECORD names it -- any live generation whose candidate is the
      squash, not merely an oversized one. Past the ceiling the adjudication
      owns it and an authorized settlement publishes it from this branch;
      short of a count the pair is one the reconciliation ahead of the next
      handler owes a reading, and that reading can only be taken in the
      checkout it was frozen on -- put back, the record names a commit the
      branch no longer has, and every later tick refuses it as a candidate
      that moved instead of measuring it again;
    * the checkout is not the squash at all -- something committed over it --
      and a reset would destroy work nobody here can account for.

    Everything else is a reading that refused before it froze anything: a pull
    request a human closed mid-rewrite, a head somebody moved under it, an
    approval nothing could pin. Those persist no record -- an entry that could
    not prove itself deliberately writes none -- so nothing names the squash,
    and leaving it on the branch is what makes the retry find ONE commit, take
    the nothing-to-squash road, and report success without measuring or
    pushing anything -- so the approved work reaches the merge button neither
    counted nor on the remote. Put back, the retry finds the commits it was
    approved with and squashes, measures, and publishes them afresh.

    The two questions are one rule read from its ends: the branch may go back
    only where nothing durable is left pointing at what is on it.

    The checkout is proved again here rather than taken from the reading
    before the push, and the two guard different steps: that one decides
    whether to PUBLISH, and a whole gated push stands between it and the
    reset this one decides.
    """
    if _named_by(gate.state, squashed):
        return True
    proved = _measurement_commits._prove_candidate_commit(gate.worktree, _HEAD)
    return not (proved.is_frozen and proved.sha == squashed)


def _named_by(state, squashed: str) -> bool:
    """Whether this record names the squash as work something still owns.

    Three fields, because three different things point at a commit and each
    outlives the step that wrote it: the receipt says the remote has it, the
    approval says a push is owed for it, and a live generation says a reading
    is about it. Any one of them left naming a commit the branch no longer has
    is a record every later tick trips over -- so the reset is the destructive
    step wherever one of them answers.

    Asked as a group rather than one at a time because they are written by
    different owners in different orders, and a road that lost a write can
    leave any subset of them down: a transfer whose grant landed and whose
    push was refused has the approval naming the squash while the receipt
    still names the head it replaced.
    """
    named = (
        _late_publication_state._published_commit(state),
        _late_approval_reading._approved_commit(state),
        _late_state.read_late_generation(state).candidate_sha,
    )
    return bool(squashed) and squashed in named


def _standing_on_the_squash(gate: _late_gate_models._Gate, squashed: str) -> bool:
    """Whether the checkout is still the commit the squash just made.

    Proved rather than read: a revision this host cannot peel is not a head
    that matches anything. A checkout standing somewhere else is not rolled
    back to the pre-squash head either -- whatever moved it committed
    something, and a reset would destroy work nobody here can account for. It
    parks with the branch exactly as it was found.
    """
    proved = _measurement_commits._prove_candidate_commit(gate.worktree, _HEAD)
    if proved.is_frozen and proved.sha == squashed:
        return True
    return _refuses_the_squash(
        gate,
        _MOVED_CHECKOUT.format(
            squashed=squashed, head=proved.sha or "an unreadable head",
        ),
    )


def _refuses_the_squash(gate: _late_gate_models._Gate, refusal: str) -> bool:
    """Park a squash whose checkout is not the commit it was handed, and stop.

    Reported and parked the way every other reading this gate could not take
    is, so an operator sees one shape for "the checkout is not what this was
    about" whichever side of the push it was noticed on. The flags are left in
    memory for the caller that ran this to persist, exactly as the gate's own
    parks are.
    """
    log.error(
        "issue=#%d cannot publish the squash it made (%s); refusing to hand a "
        "checkout nobody squashed to the pull request",
        gate.issue.number, refusal,
    )
    _late_park_notices._parked(
        gate, _records._reportable(gate, _late_state.read_late_generation(
            gate.state,
        )),
        refusal,
        _MOVED_SQUASH_PARK.format(
            mentions=config.HITL_MENTIONS, refusal=refusal,
        ),
    )
    return False


def _leased_head(
    gate: _late_gate_models._Gate,
    recorded: _collapses.LateCollapse,
    squashed: str,
) -> str:
    """The head a resumed collapse is entered on, of the two it may be.

    The recorded head is the ordinary one: the collapse was made over it, the
    pull request is still standing there, and the force-push that finishes the
    rotation is what moves it.

    The SQUASH itself is the other, and only where a durable receipt says this
    issue's own push put it there -- the commit recorded as published, dated
    to this attempt by the head it replaced. That is the window a tick that
    pushed and died before its handoff leaves: the remote already carries the
    rewrite, so entering on the head it moved off would refuse the very
    publication this recovery exists to finish, and the retry would remeasure
    a squash the pull request already has. Entered on the commit instead, the
    publication is the leased no-op it should be and the handoff behind it
    finishes with the count only the record still holds.

    The receipt alone would not say it. It is never cleared, so it goes on
    naming a commit this stage pushed rounds ago; what dates it to THIS
    collapse is the head it was pinned to, which is the head the record says
    was rewritten.
    """
    if _already_published(
        gate.state, recorded.head, squashed,
        _late_publication_state._recorded_pull_request(gate.state),
    ):
        return squashed
    return recorded.head


def _already_published(
    state, replaced: str, squashed: str, pull_request: int,
) -> bool:
    """Whether a durable receipt says this issue's push put the squash out.

    The receipt, the head it was pinned to, and the pull request it went onto,
    asked as one question, because none answers it alone: a receipt is never
    cleared, so on its own it goes on naming a commit this stage pushed rounds
    ago; a head with no receipt beside it names no push at all; and the two
    together still say nothing about WHICH publication received the commit, so
    a branch pushed from that head onto a pull request since closed and
    REPLACED by another on the same ref answers for both. All three date one
    push to one collapse -- the commit that went out, from the head this record
    says was rewritten, onto the publication the caller is proving against.

    Two owners ask it and they are the two ends of the same window. The entry
    a resume freezes is taken over the rewritten commit where this answers
    yes, since the pull request is already standing there. And a push that
    then does NOT go out may not put the branch back there: the remote carries
    the commit, so a reset would take the checkout off it and the count the
    handoff still owes a notice would go with the record.
    """
    return _late_publication_state._publication_from(
        state, replaced, pull_request,
    ) == squashed
