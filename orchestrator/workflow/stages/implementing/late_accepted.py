# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The push a human's adjudication already accepted, made from the settlement.

No measurement, because there is nothing left to measure: a verdict read this
exact diff and said it ships as one change. What the push still owes is the
two things every gated one owes -- it publishes the commit that was DECIDED
rather than whatever the checkout became, and it is pinned to the head the
reading was taken over -- plus the proof the settlement cannot skip, which is
that the checkout is still the one the verdict was reached about, and the
barrier every publication owes whatever else it skips: nothing is pushed onto
work that ENDED while this settlement was being written down.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.verification import status as _worktree_status
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_parks as _parks,
    late_publication as _publication_gate,
    late_push as _push,
)

log = logging.getLogger("orchestrator.workflow")


# The revision a checkout's own head is named by.
_HEAD = "HEAD"


def _publishes_approved(gate: _late_gate_models._Gate, branch: str) -> bool:
    """Push a commit an authorized settlement accepted onto the publication it names.

    No measurement, because there is nothing left to measure: a human read
    this exact diff and said it ships as one change, and the record that said
    so is what the approval beside it came from. What the push still owes is
    the two things every gated one owes -- it publishes the commit that was
    decided rather than whatever the checkout became, and it is pinned to the
    head the reading was taken over, so a pull request somebody moved while
    the adjudication was open rejects it instead of being overwritten.

    What it does NOT skip is the checkout. An adjudication is a human reading
    a diff over hours or days, and the worktree is writable the whole time: an
    operator can commit in it, an agent from another stage can be resumed over
    it, a rebase can move it. So the same two proofs every publication takes
    are taken here -- the tree is provably clean, and `HEAD` is still the
    commit that was accepted -- because what a verdict licenses is one commit
    and only it. A push named against the approved id would put the right
    commit on the remote either way, and that is precisely the danger: every
    stage past this one works from the CHECKOUT, so one left on an unmeasured
    descendant reaches review, a squash, and a merge with nobody having read
    it.

    The window this proof cannot cover is the push itself, and the settlement
    takes `_standing_on` again on the far side of it for that reason -- there
    rather than here, because the same reading is owed by the retry that
    finds the push already landed and makes none of its own.

    Work that ENDED is refused immediately before the push, on the same terms
    and through the same owner every gated publication refuses one. This road
    reaches the transport directly rather than through the gated call, so the
    barrier that call makes has to be made here too -- and the window it
    covers is the widest on any road: the pull request was last read by the
    reconciliation several steps back, and between that reading and this push
    lie the exemption, the identity, the debt, the park persist and both
    checkout probes. A pull request somebody merged or closed in it still has
    its branch where the adjudication left it, so the lease SUCCEEDS and the
    force-push moves terminal work; a close a poll latched is the same answer
    one field over. Neither is anything a verdict licensed.

    The lease is required rather than defaulted, for the same reason: nothing
    measures this candidate again, so the head the record names is the whole
    of what stops the push landing on a pull request somebody moved while the
    adjudication was open.

    False is a refusal or a push that did not land, and the caller parks for
    all of them: the approval and its lease are still on the record, so the
    retry asks for the same commit against the same head once the checkout is
    back where the verdict left it -- or, where what ended was the publication
    itself, once a human has said what an accepted commit with no pull request
    to join should do.

    The settlement rides the same call the gated tail makes, so a permission
    a rewrite left standing is answered here too -- and it is answered with no
    permit behind it, deliberately: nothing on this road asks `late_transfer`
    anything, so what it may do is drop a permission this publication has gone
    PAST and never carry a verdict over. A permit granted for some other
    object is one the remote will never stand where it accounts for again;
    one granted for the commit in hand is left where it stands for the tick
    that re-asks it.
    """
    approved = _parks._approved_commit(gate.state)
    lease = _parks._approved_lease(gate.state)
    if not approved or not lease or not _standing_on(gate.worktree, approved):
        return False
    published = _publication_gate._PublishedCandidate(
        held=False, revision=approved, lease=lease,
        # The publication this road's own reconciliation proved on the way in
        # -- the number it recorded once it had held that pull request to its
        # state, its repository, its branch and the frozen head. Carried so
        # the receipt the push behind this writes names the publication it went
        # onto: this road freezes no entry, so there is nothing else for the
        # write to read one off, and a receipt without it leaves the next
        # recovery with a branch to search rather than a number to prove.
        pull_request=_parks._recorded_pull_request(gate.state),
    )
    if _publication_gate._publication_ended(gate):
        return False
    if not _push._pushed(gate, branch, published):
        return False
    # No post-push proof is owed HERE: the settlement takes `_standing_on`
    # again on the far side of this push, and the retry that finds the
    # push already landed takes the same reading with no push of its own.
    _push._publication_paid(gate, published, False)
    return True


def _standing_on(worktree: Path, approved: str) -> bool:
    """Whether this checkout is still the accepted commit, cleanly.

    Both halves, and both PROVED: a `git status` that established nothing
    names no paths, which is what a clean tree names too, and a revision this
    host cannot peel is not a head that matches anything. Either failure is a
    checkout the verdict was not taken over.

    Asked on both sides of the push, and by the settlement's own retry, so the
    one reading that decides whether an accepted commit may be handed on is
    spelled once.
    """
    if not _worktree_status._worktree_status(worktree).is_clean:
        log.error(
            "the checkout at %s is not provably clean; refusing to publish "
            "the accepted commit %s from it", worktree, approved,
        )
        return False
    proved = _measurement_commits._prove_candidate_commit(worktree, _HEAD)
    if proved.is_frozen and proved.sha == approved:
        return True
    log.error(
        "the checkout at %s stands on %s rather than the accepted commit %s; "
        "refusing to hand an unmeasured checkout to the stage behind this",
        worktree, proved.sha or "an unreadable head", approved,
    )
    return False
