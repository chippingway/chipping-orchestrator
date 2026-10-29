# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The commit a finished squash still owes its relabel over.

One boundary is left when a rewrite is finished, and this is the record that
covers it. The write that ends the claim and the relabel behind it are two
calls, and an issue left on `validating` between them is one the next tick
runs a second reviewer on, over a branch already approved, squashed, and
published. So the claim is not dropped there but SETTLED -- replaced by the
commit the handoff was made over, which is what the route ahead of that
reviewer reads to move the label instead.

The successor of a pending collapse rather than a member of one, and the
difference is the whole of what this owner is for. Nothing about the rewrite
is outstanding by the time it is written -- the push landed, the notice its
count was worded from went out, and the watermarks behind it are seeded -- so
nothing here may freeze the branch, refuse a resume over it, or hold an agent
off it. What is outstanding is a label, and the record is the only thing that
says it is owed.

Read for a usable value rather than for presence, which is the opposite of
what the group it succeeds is read for and for the opposite reason. An
unreadable claim there describes a branch mid-rewrite, so it has to reach a
refusal; here it describes a rewrite already measured, published, and
announced, where the most an unreadable value can cost is the reviewer round
this route would have saved -- so it is dropped and the round runs.

The key lives outside `LATE_STATE_KEYS` for the reason the collapse's own do:
it describes a rewrite that outlives the generation it was made under -- the
gate retires one the moment it approves the squashed commit -- so the write
that clears a generation may take none of it.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

# What is left of a collapse once the rewrite itself is over: the commit the
# push put on the pull request, kept until the label behind it has moved.
LATE_COLLAPSE_HANDOFF = "late_collapse_handoff_sha"


def read_settled_handoff(state: PinnedState) -> str:
    """The commit a finished squash still owes its relabel over, or "".

    Held to the same shape every other end in this domain is: a whole object
    id, at its exact length. What the value is spent on is a comparison
    against the commit the pull request is standing on, and what a value that
    cannot name a commit buys is a comparison nobody can make -- which, on the
    road where there is no pull request to compare against at all, is a label
    moved past the reviewer on the strength of a string somebody typed.
    """
    return _payloads.as_hex(
        state.get(LATE_COLLAPSE_HANDOFF), _formats.COMMIT_LENGTHS,
    ) or ""


def record_settled_handoff(state: PinnedState, published: str) -> None:
    """Stage the commit the relabel behind a finished collapse is owed over.

    Written where a publication really landed, and a publication whose commit
    is not one this domain froze records nothing. A value that cannot name a
    commit is not one a later tick could check the publication against, and a
    record nothing can check is exactly what this one may not become: what it
    buys is a relabel taken without a reviewer.

    Such a value is dropped rather than refused, which is the opposite of what
    the claim this record succeeds does with one. That claim is written before
    the reset, where a refusal costs a rewrite nobody has made yet; this one is
    written past the push and past the notice, where there is nothing left to
    call off -- so the only thing an unusable value may cost is the reviewer
    round the record would have saved.
    """
    if _formats.is_hex_of(published, _formats.COMMIT_LENGTHS):
        state.set(LATE_COLLAPSE_HANDOFF, published)


def clear_settled_handoff(state: PinnedState) -> None:
    """Drop the handoff record, leaving every other field alone."""
    state.state_data.pop(LATE_COLLAPSE_HANDOFF, None)
