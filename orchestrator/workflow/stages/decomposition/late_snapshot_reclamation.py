# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Order and prove snapshot reclamation before deleting its exact remote ref.

The reclaiming state is durable before a fresh consumer proof and deletion.
A missing ref can finish interrupted receipt delivery, while cancellation
between effects leaves the generation marked and suppresses child notices.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.workflow.late_split import (
    formats as _formats,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.obligations import LateResource, LateResourceState
from orchestrator.workflow.stages.decomposition import (
    late_cleanup_proof as _late_cleanup_proof,
    late_cleanup_reading as _late_cleanup_reading,
    late_cleanup_state as _late_cleanup_state,
    late_consumer_release as _late_consumer_release,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan

log = logging.getLogger("orchestrator.workflow")


# The two states an entry reaches once the decision to reclaim it is durable.
# Both are retryable past the consumer proof, but only for a ref the remote no
# longer has: a decision already carried out has to be finished, while one
# that never reached the remote is still a decision about a ref a consumer may
# have come back for.
_ORDERED = frozenset((
    LateResourceState.RECLAIMING, LateResourceState.FAILED,
))

# The two transport answers that mean the ref is gone: one this call deleted,
# and one an earlier call already had.
_RECLAIMED = frozenset((
    _snapshot_refs.SnapshotOutcome.DELETED,
    _snapshot_refs.SnapshotOutcome.ABSENT,
))


def _reclaim_snapshot(
    walk: _late_cleanup_state._Pass, generation: LateGeneration, ref: str,
) -> LateGeneration:
    """Order, carry out, and announce the reclamation of one snapshot ref.

    Four steps, and the order is the whole crash-safety argument.

    **The decision goes down first.** Reaching here means every recorded
    consumer was just proved ended, and that proof is not repeatable: a human
    can reopen one at any moment. So the entry is written `reclaiming` BEFORE
    the delete, which is what stops a tick that died after the push from
    leaving a ref the ledger says is retained and the remote does not have.
    What the entry does not buy is a later visit acting on this visit's proof:
    the consumers are read again ahead of every delete, and only a ref the
    remote no longer has finishes without one -- there the delete has already
    happened, and a consumer that came back to it is answered by the receipt
    and the child's own guard.

    **The delete is named against the commit this generation preserved**, so a
    ref somebody re-pointed is refused rather than reclaimed, and an absent
    one is a success -- which is what makes the retry cost one read.

    **The children are told before the entry is closed.** A child that reads
    its ancestry after this owner has gone quiet would otherwise follow a
    pointer to nothing, so each is sent one comment saying the ref is gone and
    what continuing takes. It runs behind a delete the remote accepted and
    ahead of the record of it, so a tick that dies in between re-enters
    through `reclaiming` and repeats it; a child already holding this
    reclamation's receipt is skipped, which is what keeps the sentence to one.
    Nothing here touches a consumer's pinned state -- what acts on the receipt
    is the child's own guard, on the child's own dispatch.

    Refused outright unless the target IS this generation's ref. The transport
    proves the namespace and the commit, and neither is identity: every
    generation of every issue in a lineage cut from the same candidate names
    the same SHA, so a hand-edited entry naming a sibling's ref would pass
    both tests and destroy the only copy of what that sibling was told to
    reuse. The name is re-derived here from the issue being walked and the
    record's own counters, and nothing else is deleted.
    """
    issue_number = walk.issue.number
    if not _late_cleanup_reading._our_snapshot(issue_number, generation, ref):
        log.error(
            "issue=#%d recorded snapshot %r is not the ref this generation "
            "preserved; refusing to delete it", issue_number, ref,
        )
        return _late_cleanup_state._recorded(
            generation, _late_cleanup_reading._SNAPSHOT, ref, LateResourceState.FAILED,
        )
    ordered = _ordered(walk, generation, ref)
    proven = _late_cleanup_reading._consumer_scan(walk.gh, walk.issue, generation)
    if not _may_take(walk, generation, ref, proven):
        log.info(
            "issue=#%d is not taking %s this visit: a consumer it records is "
            "live again", issue_number, ref,
        )
        return ordered
    # The scan above is a request per consumer and the probe behind it is
    # another, so the poll can observe the close anywhere in there -- and what
    # stands next is the delete itself. The mark goes down BEFORE it, because
    # a ref that is gone while the record still reads live is a reclamation
    # nothing afterwards can attribute to the cancellation that earned it.
    ordered = _late_cleanup_state._observed_close(walk, ordered)
    return _taken(walk, ordered, ref, proven)


def _may_take(
    walk: _late_cleanup_state._Pass, generation: LateGeneration, ref: str, proven: _ChildScan,
) -> bool:
    """The last reading before the delete, taken as late as one can be.

    The scan the pass qualified this ref on was taken before the branch half
    ran and before anything was written, and every one of those steps is a
    request a human can reopen a consumer during. So the consumers are read
    ONE more time, past the write that records the decision and immediately
    ahead of the delete it authorizes -- which leaves the delete request
    itself as the only window, and that one is irreducible.

    A ref the remote no longer has is the one case that needs no proof: what
    is left is finishing a delete that already happened, and a consumer that
    came back to it is answered by the receipt and the child's own guard
    rather than by keeping a ref nobody has.

    A refusal leaves the entry `reclaiming` rather than putting it back. The
    decision was taken and not carried out, which is exactly what that state
    means -- and it is read back by the rule that probes the ref before acting
    on it, so a ref still on the remote is kept until the consumers end again.
    """
    if _late_cleanup_proof._reclaimable(walk.state, generation, proven):
        return True
    return _already_gone(walk, generation, ref)


def _taken(
    walk: _late_cleanup_state._Pass, ordered: LateGeneration, ref: str, proven: _ChildScan,
) -> LateGeneration:
    """Carry out a delete this pass has just proved it may take."""
    if _deleted(walk, ordered, ref) not in _RECLAIMED:
        return _late_cleanup_state._recorded(ordered, _late_cleanup_reading._SNAPSHOT, ref, LateResourceState.FAILED)
    # The delete is a request, and what stands immediately behind it is the
    # one cleanup effect that WRITES to somebody else's issue. A close
    # observed inside the delete makes this a cancelled cycle, which owes its
    # children nothing at all -- so the reading is taken before the receipts
    # rather than after them.
    ordered = _late_cleanup_state._observed_close(walk, ordered)
    ordered, told = _late_consumer_release._release_consumers(walk, ordered, ref, proven)
    if not told:
        # The ref is gone and a child still records it. Leaving the entry
        # `reclaiming` is what keeps that obligation alive: it holds the
        # terminal and keeps the sweep visiting, and the next pass finds the
        # ref absent and delivers the receipt it could not.
        return ordered
    return _late_cleanup_state._recorded(ordered, _late_cleanup_reading._SNAPSHOT, ref, LateResourceState.RECONCILED)


def _deleted(
    walk: _late_cleanup_state._Pass, generation: LateGeneration, ref: str,
) -> _snapshot_refs.SnapshotOutcome:
    """Ask the remote to let go of one ref, reading a raise as a refusal.

    The transport answers every refusal it can name, but a caller that must
    RECORD the attempt cannot let one it could not name escape: an exception
    here would abandon the pass with the decision written and nothing said,
    which is the one outcome that produces no typed failure for an operator
    to see. A raise is therefore the same answer a refused push is, and takes
    the same `snapshot_delete_failed` with it.
    """
    try:
        return _snapshot_refs.delete_snapshot_ref(
            walk.spec, walk.spec.target_root,
            ref=ref, sha=generation.candidate_sha,
        )
    except Exception:
        log.exception("snapshot %r delete raised", ref)
        return _snapshot_refs.SnapshotOutcome.REFUSED


def _ordered(
    walk: _late_cleanup_state._Pass, generation: LateGeneration, ref: str,
) -> LateGeneration:
    """Record that this ref is going, before anything makes it so.

    The proof that let the decision be taken is a reading of live issues, and
    a reading is not a thing a retry can reproduce. What a retry CAN act on is
    a decision somebody durably took, so it is written down first and the
    delete underneath it is idempotent.

    Written once, though, and not on every retry of it. A record that already
    reads `reclaiming` or `failed` already carries the decision -- both are
    what the retry rule reads a decision back out of -- so putting
    `reclaiming` over a `failed` entry costs a write, loses the fact that the
    last attempt was refused, and leaves the pass's own outcome write with a
    state to move BACK to. A remote that goes on refusing would otherwise
    alternate the durable state between the two forever, reporting a
    transition on every other visit that nothing actually transitioned.

    The decision still travels forward in memory either way: the entry this
    pass hands on says `reclaiming`, so a delete that lands and a child this
    pass cannot reach still leave the ref recorded as being taken.
    """
    try:
        decided = replace(
            generation, obligations=generation.obligations.with_resource(LateResource(
                kind=_late_cleanup_reading._SNAPSHOT,
                target=ref,
                resource_state=LateResourceState.RECLAIMING,
            )),
        )
    except _formats.InvalidLateValue:
        log.exception("could not order the reclamation of %r", ref)
        return generation
    if not _already_ordered(generation, ref):
        walk.persist(decided)
    return decided


def _already_ordered(generation: LateGeneration, ref: str) -> bool:
    """Whether the record already holds a durable decision about this ref.

    Either of the two states a decision reaches counts, because the retry
    rule reads them alike: what both say is that a delete was authorized and
    the ledger has been standing behind it since.
    """
    return any(
        entry.resource_state in _ORDERED
        for entry in generation.obligations.resources
        if entry.kind == _late_cleanup_reading._SNAPSHOT and entry.target == ref
    )


def _already_gone(
    walk: _late_cleanup_state._Pass, generation: LateGeneration, ref: str,
) -> bool:
    """Whether an ordered ref the consumers no longer clear is gone anyway.

    One read, and it decides which of two wrongs to avoid. Assuming the ref
    is gone would delete one a reopened child came back for; assuming it is
    there would strand a ledger against a ref nothing can prove either way,
    holding a terminal open forever. Asking answers it, and only in the window
    where the two answers differ -- a decision recorded and the consumers no
    longer unanimous, which is a crash or a refusal followed by a reopen.

    Fails closed. Unreadable, mismatched, or raised all leave the ref held,
    which is the answer that destroys nothing.
    """
    try:
        observed = _snapshot_refs.observed_snapshot_ref(
            walk.spec, walk.spec.target_root,
            ref=ref, sha=generation.candidate_sha,
        )
    except Exception:
        log.exception("could not ask the remote about snapshot %r", ref)
        return False
    return observed == _snapshot_refs.SnapshotOutcome.ABSENT
