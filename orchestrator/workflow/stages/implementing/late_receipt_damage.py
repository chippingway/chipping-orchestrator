# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Identify missing or unusable members of the publication receipt as one group.

A wholly absent or wholly empty receipt differs from a partial claim.
Claimed commits and publication numbers must parse, and a nonempty receipt
must include both its published commit and pull request.
"""
from __future__ import annotations

from orchestrator.github import (
    pinned_state as _pinned_state,
)
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _late_publication_state,
    state as _state,
)

# The publication receipt group, in the order a refusal names its members:
# the commit that reached a remote, the head that push replaced, and the pull
# request it went onto. Each is read fail-closed by the owner beside it, so a
# member that CARRIES a value and reads back empty is one this build cannot
# use -- which is the gap `_damaged_receipt` is the whole of.
_RECEIPT_GROUP = (
    (_state._PUBLISHED_SHA, _late_publication_state._published_commit),
    (_state._PUBLISHED_LEASE, _late_publication_state._published_lease),
    (_state._PUBLISHED_PR, _late_publication_state._published_pull_request),
)


def _damaged_receipt(state: _pinned_state.PinnedState) -> str:
    """Which member of the receipt group claims a publication it cannot name.

    Asked of all three at once, because the three are ONE record: `_record_
    publication` writes every member on every receipt and clears every member
    on none, so a group that reads back partial is not a record with a gap in
    it but one nothing here produced. Every other reader in this domain is
    fail-CLOSED and so reads a partial group as an absence -- right for one
    deciding "may this commit publish", and exactly wrong for one deciding
    whether the record is SOUND. Told "no receipt", that second reader
    measures the candidate and publishes: the branch is force-pushed, a second
    pull request is opened over whatever the first may already carry, and the
    write behind that push puts a fresh group down over the damaged one, which
    destroys the evidence an operator would have repaired it from.

    Three shapes are damage, and `_missing_member` and `_unusable_member`
    below own them in that order. A KEY that is not there while its siblings
    are is the first, and telling it from the `null` an initial publication
    writes is the whole reason presence is asked of every member rather than
    of the commit alone: the write puts all three keys down, so one that has
    gone is a hand edit or a half-written record and the group can no longer
    say what it is about. A member that carries a VALUE this build cannot read
    is the second, and it is named so the park can tell a human which field to
    repair. An ORPHAN is the third -- a lease or a pull request with no
    readable commit beside it, which claims this stage published and cannot
    say what.

    An empty MEMBER is not damage where its key is there: `null` is what an
    initial publication records for the head it froze none of, and what an
    install writing no identity records for the number. The delivery proof
    refuses the second on its own terms, with a remedy of its own.

    Answers with the member to repair, and "" for a group that is whole and
    for an issue that never published at all.
    """
    return _missing_member(state) or _unusable_member(state)


def _missing_member(state: _pinned_state.PinnedState) -> str:
    """The member whose KEY is gone while the rest of the group is there.

    Presence alone, which is the one question the value readers cannot ask:
    a member holding `null` and a member that is not on the comment read back
    identically to every one of them, and only the first is something a write
    of this build's ever produced.

    "" for a record carrying no member at all, which is an issue that never
    published and has nothing to be partial about.
    """
    present = [member for member, _ in _RECEIPT_GROUP if state.carries(member)]
    if not present:
        return ""
    absent = [
        member for member, _ in _RECEIPT_GROUP if member not in present
    ]
    return absent[0] if absent else ""


# The two members a group that claims anything has to fill. A publication is
# a commit that reached a remote and the pull request that now carries it, and
# neither is derivable from the other: a receipt with no commit cannot say
# what was published, and one with no number leaves the recovery behind it a
# branch to search rather than an identity to prove. The LEASE is not among
# them -- an initial publication froze no head, records `null`, and is the
# commonest sound group there is.
_REQUIRED_MEMBERS = (_state._PUBLISHED_SHA, _state._PUBLISHED_PR)


def _unusable_member(state: _pinned_state.PinnedState) -> str:
    """The member of a whole group that cannot say what it claims to.

    Two shapes over the same gap between "carries a value" and "carries one
    this build can use". A member holding something no reader here will type
    answers for itself. And a group that claims ANYTHING while one of the two
    members a publication is named by stands empty answers with the member it
    is missing: a lease or a number with no commit beside it claims this stage
    published and cannot say what, and a commit with no number cannot say
    where it went -- which leaves every reader behind it a lookup by branch,
    and that answers with whatever is open on the ref.

    An empty LEASE is sound, and is why the two are named rather than the
    whole group being required: the initial publication froze no head to be
    pinned to and records none.
    """
    unreadable = [
        member for member, read_member in _RECEIPT_GROUP
        if _late_publication_state._claims_a_value(state, member) and not read_member(state)
    ]
    if unreadable:
        return unreadable[0]
    claimed = [
        member for member, _ in _RECEIPT_GROUP
        if _late_publication_state._claims_a_value(state, member)
    ]
    if not claimed:
        return ""
    missing = [
        member for member in _REQUIRED_MEMBERS if member not in claimed
    ]
    return missing[0] if missing else ""
