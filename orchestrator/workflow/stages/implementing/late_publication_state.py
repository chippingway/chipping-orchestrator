# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read and write the exact commit, lease, and pull-request publication receipt.

The issue pointer and published PR remain distinct. A receipt answers a
recovery only when its lease and publication match the attempt, and its
three recorded fields are written together.
"""
from __future__ import annotations

from orchestrator.github import (
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
)
from orchestrator.workflow.stages.implementing import (
    state as _state,
)


def _published_commit(state: _pinned_state.PinnedState) -> str:
    """The commit this stage last pushed, or "" where none was.

    Published beside the approval for the owner that has to tell a candidate
    nobody has ruled on from one this stage already put on a pull request. The
    two are the same window read from its two ends: the approval says a push
    is owed, and this says one was made, so between the push and the relabel
    the second is what says the size question has been answered AND acted on.
    Read fail-closed like every other late commit field, so a hand-edited
    value is no publication rather than an unmeasured one.
    """
    return _payloads.as_hex(
        state.get(_state._PUBLISHED_SHA), _formats.COMMIT_LENGTHS,
    ) or ""


def _published_lease(state: _pinned_state.PinnedState) -> str:
    """The head the recorded publication replaced, or "" where none is named.

    What scopes the receipt beside it to one publication attempt. A receipt is
    never cleared, so on its own it goes on naming a commit this stage pushed
    rounds ago and answers "this tick's push landed" for any pull request
    somebody rewound onto it. The head it REPLACED is the fact that dates it,
    and a caller that froze its own head is what compares the two.

    Read fail-closed like every other late commit field, and empty is a
    receipt that vouches for no moved head at all -- an initial publication,
    which froze no head, or one written before this pair was recorded.
    """
    return _payloads.as_hex(
        state.get(_state._PUBLISHED_LEASE), _formats.COMMIT_LENGTHS,
    ) or ""


def _recorded_pull_request(state: _pinned_state.PinnedState) -> int:
    """The pull request this ISSUE records, or 0 where none is readable.

    The publication a stage is working on, as against the one a receipt is
    about: the two agree on every ordinary tick and the receipt's own is what
    a landed push is proved by. This is for the caller that has to say which
    pull request it is PROVING against and holds no frozen entry to read one
    off -- the squash resume, and the accepted settlement whose reconciliation
    proved this very number on its way in.

    Read fail-closed like every other late identity.
    """
    return _payloads.as_identity(state.get(_state._PR_NUMBER)) or 0


def _published_pull_request(state: _pinned_state.PinnedState) -> int:
    """The pull request the recorded publication went onto, or 0 for none.

    The third member of the receipt group, and the one the bookkeeping behind
    a landed push is bound by: the commit says what reached a remote, the head
    it replaced dates that to one attempt, and this says which pull request
    now carries it.

    Read fail-closed like every other late identity, so a hand-edited or
    truncated value is no pull request rather than one nothing checked. What a
    reader does with 0 is refuse -- there is no second place to look that is
    not a search, and a search by branch answers with whatever is open on the
    ref rather than with the publication this receipt is about.
    """
    return _payloads.as_identity(state.get(_state._PUBLISHED_PR)) or 0


def _claims_a_value(state: _pinned_state.PinnedState, key: str) -> bool:
    """Whether the record CARRIES something at `key` rather than an absence.

    `None` and `""` are the only two values read as an absence, and they are
    named rather than tested for falsehood. The payload is JSON, so a field
    can hold anything a hand edit or a half-written crash leaves -- `false`,
    `0`, `[]`, `{}` -- and every one of those is falsy in Python while being
    exactly the damage the reader below exists to catch. Written as "empty
    means absent" that refusal is bypassed by the shapes nobody wrote on
    purpose, which is the one set it most has to answer for.
    """
    if not state.carries(key):
        return False
    written = state.get(key)
    return written is not None and written != ""


def _publication_from(
    state: _pinned_state.PinnedState, head: str, pull_request: int,
) -> str:
    """The commit recorded as pushed FROM this head onto this pull request.

    The whole receipt group asked as the one question every caller of it
    actually has: is the publication this record names the one I am about to
    act on? No member answers it alone. A receipt is never cleared, so by
    itself it goes on naming a commit this stage pushed rounds ago and vouches
    for any pull request somebody rewound onto it; a head with no receipt
    beside it names no push at all; and the two together still say nothing
    about WHICH publication received the commit -- so a branch that has been
    pushed from this head before, onto a pull request since closed and
    replaced, answers yes to both.

    All three date one push to one attempt, and the caller supplies both of
    the facts it is proving against: the head it froze, and the pull request
    it froze that head on. A receipt naming another number is an earlier
    publication of this issue's, and one naming none is a record this build
    cannot tie to any publication at all -- both answer "" rather than being
    taken at their word, since what the answer licenses is a carve-out from
    the refusal that catches somebody else's branch move.

    A caller with no head of its own is claiming nothing here, and gets "".
    """
    if not head or _published_lease(state) != head:
        return ""
    if not pull_request or _published_pull_request(state) != pull_request:
        return ""
    return _published_commit(state)


def _record_publication(
    state: _pinned_state.PinnedState,
    published: str,
    superseded: str,
    pull_request: int = 0,
) -> None:
    """Record the commit a push put on the remote, and the head it replaced.

    The pair is written together for the reason the approval's is, and the
    danger is the mirror image: a receipt whose head was dropped is the one
    that vouches for a publication somebody else moved, so the second half is
    written on EVERY receipt -- cleared where there is no head to name rather
    than left for the next receipt to inherit from the last.

    The pull request travels with them for the same reason and answers the
    question neither of them does: which publication now carries the commit.
    Left to the relabel that records `pr_number`, it is missing for exactly
    the window the receipt exists for -- a push that landed and a process that
    died before that write -- and a reader with no identity there falls back
    to a lookup by branch, which a replacement somebody opened over the same
    ref satisfies. Cleared with the rest where a caller names none, never
    inherited from the receipt before.
    """
    state.set(_state._PUBLISHED_SHA, published)
    state.set(_state._PUBLISHED_PR, pull_request or None)
    state.set(_state._PUBLISHED_LEASE, superseded or None)
