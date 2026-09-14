# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Record unmeasured publication debt and discard approvals for superseded candidates.

The candidate, frozen lease, permission basis, and route spends stay
together. Staging lets a transfer write that debt with its own permission;
the ordinary verdict persists it before the push that owes its receipt.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split import (
    state as _late_state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_parks as _parks,
)

log = logging.getLogger("orchestrator.workflow")



def _frozen_lease(gate: _late_gate_models._Gate) -> str:
    """The head an approval on the published side is pinned to.

    The retirement below takes the generation -- and the head it froze -- off
    the record, and the push it licenses has not run yet. If that push fails,
    the retry has an approved commit and no reason to measure again, so
    without this the only head left to pin to is whatever the pull request has
    become since: a head somebody moved in between would be adopted as the
    lease and force-overwritten. Carried past the retirement, the retry pins
    to what was frozen and git refuses instead.

    Empty for a call taken before anything was published, which is what makes
    the implementing seam's push take its own reading of the remote exactly as
    it always did.
    """
    if gate.entry is None:
        return ""
    return gate.entry.published_sha


def _supersedes_approval(gate: _late_gate_models._Gate, candidate_sha: str) -> None:
    """Drop an approval this publication is going past.

    An approval names one commit and says that commit is owed a push. A tick
    publishing a DIFFERENT one has moved past the debt rather than paid it: a
    developer resumed on a human's guidance committed again, or an exemption
    one step over named some other commit, and the branch will not carry the
    approved commit as its tip. Left standing it would freeze this branch out
    of the ordinary base refresh for as long as the issue lives and park every
    later tick asking for a checkout back for work nobody is going to push.

    An approval naming the commit in hand is left exactly where it is: it is
    still owed, and the handoff that carries it is what spends it -- so a
    publication that parks instead comes back to a record that still says
    which commit the issue is waiting on.
    """
    approved = _parks._approved_commit(gate.state)
    if not approved or approved == candidate_sha:
        return
    log.info(
        "issue=#%d is publishing %s and no longer owes a push for approved "
        "commit %s; dropping it rather than holding the branch for work "
        "nothing is going to publish",
        gate.issue.number, candidate_sha or "a candidate it did not name",
        approved,
    )
    _parks._forget_approval(gate.state)


def _owed_by_an_unmeasured_push(
    gate: _late_gate_models._Gate, candidate_sha: str, lease: str, basis: str = "",
) -> None:
    """Name the commit an unmeasured publication owes a push for, durably.

    The measured road records this beside its retirement, and a candidate that
    skipped the reading owes it just as much: nothing was frozen for it, so
    past this call the only account of the work is the commit on the branch.
    A tick that died between here and the push comes back to an issue with no
    generation, no debt, and a pull request that may or may not have received
    it -- and the stage below runs from there, spawning an agent over work
    nobody can say is unpublished.

    Recorded, the reconciliation ahead of every handler finds the debt first,
    republishes the same commit against the same head, and closes what the
    route owed in the receipt's own write -- so the stage behind it runs over
    the world the dead tick would have handed it.

    What the route still owes rides the same write, because the recovery has
    no run behind it to re-derive a reviewer round, a consumed fix batch, or a
    docs receipt from. The debt and the obligations are spent together by the
    push that pays them.

    A debt this issue ALREADY carries for the commit is left exactly as it
    is. It was granted by an earlier tick against a head that tick froze, and
    the head read now is precisely the move its lease exists to refuse -- so
    re-leasing it here would repair a half-written approval by pinning it to
    the present, which is the one substitution the refusal behind it forbids.
    An approval naming some other commit is gone by this point, dropped by the
    supersession a line above.

    Written only where the push will MOVE the publication. A pull request
    already standing on the commit has nothing to receive, so there is no
    window to survive -- and a debt written there would be paid by a
    republication that closes a round the tick which really published it
    already closed. A call taken before anything was published names no head
    at all, and the initial publication owns that window itself.

    The lease is handed IN rather than read off the entry, because the entry
    is not the only road to one. Where the switch keeps a candidate out of the
    gate nothing freezes a publication, and the head the push is pinned to is
    the CALLER's own reading of the remote -- so the debt is recorded against
    that instead. What the switch decides is the measurement; the account of
    what a push is putting where is not its to turn off.
    """
    if _stages_unmeasured_debt(gate, candidate_sha, lease, basis):
        gate.gh.write_pinned_state(gate.issue, gate.state)


def _stages_unmeasured_debt(
    gate: _late_gate_models._Gate, candidate_sha: str, lease: str, basis: str = "",
) -> bool:
    """Put the debt an unmeasured push owes in memory, and say whether it did.

    The rule above without the write, so an owner that has its OWN write to
    make can carry the debt out on it rather than one behind it. The two are
    not interchangeable orderings of the same thing: a record that LICENSES a
    rewritten commit to publish is the account of what the branch carries, and
    the debt is the account of where it has still to go -- split
    across two writes, a process dying between them comes back to a branch the
    record explains and no debt naming the push it is still owed, and the
    reconciliation that would have finished it never runs.

    Answering rather than writing is also what keeps the caller's write
    honest: an owner that staged nothing has nothing of this to make durable
    and says so, instead of spending a request on a comment it did not change.

    What the debt RESTS on is handed DOWN from the answer that admitted the
    candidate rather than re-derived here, and that difference is the whole of
    it. A commit an exemption and an authorization both vouch for leaves a
    debt that may be spent only while that authorization can still be read --
    but proving one is a git reading, and a second reading is a second chance
    to fail. Re-asked here, a store that stopped answering between the gate's
    proof and this write would record an operator's bypass as ordinary
    unmeasured debt, and the tick after a crash would spend it without asking
    anyone. Handed down, the record says what the gate actually decided on.

    A road that carried nothing records the ordinary unmeasured basis, and so
    does a value from outside this build's own vocabulary: what a caller
    cannot name is not a claim the record may carry. That is every other road
    here -- a rewrite permit, a supersession the switch let past, a receipt
    the remote already carries -- each a record this workflow made for itself
    and re-derives on the next tick.
    """
    if _parks._approved_commit(gate.state) == candidate_sha:
        return False
    if not lease or lease == candidate_sha:
        return False
    log.info(
        "issue=#%d is publishing unmeasured candidate %s onto a pull request "
        "standing at %s; recording the debt before the push that pays it",
        gate.issue.number, candidate_sha, lease,
    )
    admitted = _parks.LateApprovalBasis.UNMEASURED
    if basis in tuple(_parks.LateApprovalBasis):
        admitted = _parks.LateApprovalBasis(basis)
    _parks._approve(gate.state, candidate_sha, lease, admitted)
    _late_state.write_late_spends(gate.state, gate.spends.fields)
    return True
