# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Generation-scoped claims, durable receipt memos, and bounded thread scans.

Only one post claims an owner at a time. A receipt landing after settlement
cannot memoize the next generation, a memo names the cycle its receipt was
for, and a landed receipt reopens its thread scan. So does another poller on this host holding the issue since the scan,
and a scan answered for one cycle says nothing of another's receipt. A failed
scan releases only the scan claim this attempt acquired."""
from __future__ import annotations

import contextlib
from dataclasses import dataclass

from orchestrator.scheduler import claim_notes as _claim_notes
from orchestrator.workflow.engine import observation_state as _observation_state


@dataclass(frozen=True)
class ReceiptClaim:
    """One poll's right to post one observation's receipt.

    Handed out by `claim_receipt_post` and handed back by whichever half of
    the attempt finished it, so the owner it names and the reading it was
    taken for travel together: a claim settled against a different generation
    is one a cleanup ended while the post was still in flight, and the memo
    behind it belongs to nobody. `landed` is the cycle whose receipt this
    reading has already put on the thread, if any.
    """

    key: tuple[str, int]
    generation: int
    landed: int | None = None


def claim_receipt_post(
    repo_slug: str, issue_number: int,
) -> ReceiptClaim | None:
    """Take the one right to post this observation's receipt, or decline.

    The generation the claim was taken at travels back with it, and it is
    what `receipt_written` records the memo against: a settlement landing
    while the post is in flight moves that generation on, and a memo written
    from the stale one would say the NEXT observation's receipt is already
    durable when nothing on the thread says any such thing.

    None is a post another poll is making right now, which is what keeps the
    check and the post from being two separate decisions -- a worker's failed
    pass and the following tick's enumeration are in that gap together, and
    both would otherwise walk a thread that carries no receipt yet and post
    one apiece.

    A receipt already recorded for the reading in hand declines nothing by
    itself: the claim carries the cycle it named, and the poster owes nothing
    only where the record still names that cycle. Another poller on this host
    can settle the cycle a landed receipt was for and an operator restart it
    while the reading is still held, and a close of the fresh cycle is owed a
    receipt of its own -- one a memo remembering only the issue would
    suppress, so that a restart of this process lost the close outright.

    Handed back by `receipt_written` or `release_receipt_post`, never left
    standing: a claim over an attempt that ended would suppress every later
    poll's receipt for good.
    """
    key = _observation_state._owner_key(repo_slug, issue_number)
    with _observation_state._lock:
        if key in _observation_state._posting:
            return None
        _observation_state._posting.add(key)
        return ReceiptClaim(
            key=key,
            generation=_observation_state._settlements.get(key, 0),
            landed=_observation_state._receipted.get(key),
        )


def receipt_written(claim: ReceiptClaim, cycle_id: int) -> None:
    """Record that this reading's receipt for `cycle_id` is on the thread for good.

    Only where the reading is still the one the claim was taken for. A pass
    that settled the observation in the meantime has already dropped the memo
    on purpose, and re-creating it here would hand the next close a
    suppression it never earned -- an observation held in memory alone, which
    a restart before the run reaches a barrier takes away entirely.

    The one thread walk this process owes the owner is owed again with it.
    That claim is taken once because what it recovers is an observation a DEAD
    process was holding -- but a claim taken before this receipt existed is
    one that proved nothing about it, and every later pass would read past a
    receipt that is now there.
    """
    with _observation_state._lock:
        _observation_state._posting.discard(claim.key)
        if _observation_state._settlements.get(claim.key, 0) != claim.generation:
            return
        _observation_state._receipted[claim.key] = int(cycle_id)
        # A thread this process already walked has something on it now, so
        # the one look it owed is owed again: the claim was taken when there
        # was nothing to find, and a later pass reading past it would step
        # straight over the receipt this attempt just landed.
        _observation_state._scanned.pop(claim.key, None)


def release_receipt_post(claim: ReceiptClaim) -> None:
    """Hand back the right to post a receipt that never landed."""
    with _observation_state._lock:
        _observation_state._posting.discard(claim.key)


@contextlib.contextmanager
def scanning_receipt(
    repo_slug: str, issue_number: int, cycle_id: int, *, repo_id: int | None = None,
):
    """Whether this process still owes this owner's thread one look for this cycle.

    True once per owner and cycle while no other poller writes the issue, and
    the claim is taken as this is ENTERED rather than once the walk has
    answered, so a thread that carries no receipt is not walked again every
    dispatch. What the scan recovers is an observation a process that died was
    holding: anything this process observed since is in the latch, which costs
    nothing to ask. A walk for one cycle proved nothing about a receipt naming
    another, so a different cycle is owed a walk of its own.

    Owed again, too, once another poller on this host has held the issue since
    the walk. Every receipt is posted under the issue's writer claim, so a
    receipt that poller left -- and it may have died before marking what it
    observed -- landed inside a hold that ended after this walk began. Asked
    under this process's own claim, with the repository's id, the claim notes
    say whether any such hold has been found; one that ended before the walk
    was there to be read by it. Without the id, the walk is owed only by cycle.

    Handed back where the walk established nothing, which is what makes the
    claim honest. A listing that raises proved neither answer, and a claim
    standing over one would send every later tick straight past the receipt
    and on to the live stage handler -- so the claim survives a body that
    RETURNS and not one that raises, which is exactly the difference between
    a walk that answered and a walk that did not.
    """
    key = _observation_state._owner_key(repo_slug, issue_number)
    walk = (int(cycle_id), _claim_notes.moment())
    with _observation_state._lock:
        walked = _observation_state._scanned.get(key)
        claimed = walked is None or walked[0] != walk[0] or (
            repo_id is not None
            and not _claim_notes.undisturbed_since(repo_id, issue_number, walked[1])
        )
        if claimed:
            _observation_state._scanned[key] = walk
    try:
        yield claimed
    except Exception:
        if claimed:
            with _observation_state._lock:
                if _observation_state._scanned.get(key) == walk:
                    _observation_state._scanned.pop(key)
        raise
