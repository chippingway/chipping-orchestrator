# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a guarded pinned-state commit holds, and what it can come to.

A commit is captured from the reading a caller decided on, before anything is
staged over it (`PinnedCommit.capture`): the comment that reading came from, how
it spelled every field, which of those fields the decision depends on, and which
the caller owns. Everything is held as the comment's JSON spells it -- canonical,
keys sorted -- because that is the only comparison that tells apart what a
reader tells apart: a field written `null` from one never written, `true` from
`1`, `1.0` from `1`, at any depth. Python equality, and a `get` answering None
for both a `null` and a missing field, call each of those pairs equal, and a
write that took one for the other would put back a record a later reader
decides differently on.

The spellings are strings in a read-only mapping, so nothing the caller does to
its own state afterwards moves what the commit was captured over.

An outcome is one of four. PREPARED is a candidate measured and written
nowhere; REFUSED wrote nothing and names why; COMMITTED is a record GitHub
confirmed carrying the candidate, or one the fresh reading already showed
carrying it; UNCONFIRMED is a rewrite that went out and was never confirmed,
so the record may read either way. That last one is not a refusal and not a
success: whatever domain receipt the caller already keeps is what settles it
on a later reading.
"""
from __future__ import annotations

import enum
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

from orchestrator.github.pinned_state import PinnedState

# What a field the comment does not carry reads as, apart from one it carries
# as `null`. A transformation is handed it for an absent value, and returns it
# to have the field dropped.
ABSENT = object()

# What a transformation returns where it cannot keep both moves of its field --
# another road left it spelled as neither the capture nor the caller had it, and
# in no shape the domain's rule can join -- so the commit refuses it as an owned
# conflict, exactly as it refuses a field that has no transformation.
CONFLICT = object()

# A domain's own rule for one owned field, applied over the fresh reading:
# called with the field's fresh value, its value as the commit was captured,
# and its value as the caller staged it -- each ABSENT where missing, and each
# a copy nothing else holds -- and returning what the field is committed as.
Transform = Callable[[Any, Any, Any], Any]

# A domain's own check of the complete candidate, asked of exactly the one a
# commit would land: handed a copy of it as a state, and answering None to let
# it land, or that domain's refusal of it otherwise.
Admits = Callable[[PinnedState], Any]


class CommitRefusal(enum.Enum):
    """Why a commit wrote nothing."""

    # The pinned comment could not be read.
    UNREADABLE = "unreadable"
    # It reads, but not as a state: the captured reading or the fresh one.
    MALFORMED = "malformed"
    # It is not the comment captured: replaced, deleted, or never pinned.
    REPLACED = "replaced"
    # It moved between the fresh reading and the edit; nothing went out, and
    # a commit asked again derives over whatever it carries then.
    MOVED = "moved"
    # A record the decision depends on is no longer spelled as captured.
    PREREQUISITE_CHANGED = "prerequisite_changed"
    # Another writer moved an owned field the caller staged a value for.
    OWNED_CONFLICT = "owned_conflict"
    # The caller staged or transforms a field it did not declare.
    UNDECLARED_WRITE = "undeclared_write"
    # The complete candidate renders past what one comment holds.
    OVERFLOW = "overflow"
    # The caller's own domain refused the complete candidate.
    INADMISSIBLE = "inadmissible"


class CommitStatus(enum.Enum):
    """What a commit came to."""

    PREPARED = "prepared"
    COMMITTED = "committed"
    UNCONFIRMED = "unconfirmed"
    REFUSED = "refused"


@dataclass(frozen=True)
class CommitOutcome:
    """One commit's answer.

    `reading` is the record the candidate makes of the comment: measured for
    PREPARED, landed for COMMITTED, sent for UNCONFIRMED, and None for REFUSED.
    It is a copy the caller may keep or lay over its own state; the commit
    never touches that state itself. `fields` names what earned a refusal,
    `length` is the rendered body an OVERFLOW measured, and `inadmissible` is
    what the guard's own domain check answered where it refused the candidate.
    `seen`, for a guard that `reads_a_move` alone, is the comment a
    PREREQUISITE_CHANGED refusal read those fields moved on, or the one a
    MOVED edit found in place of the fresh reading
    (`PinnedCommit.keeps_the_move`), so the caller can say what moved and to
    what however soon it is put back.
    """

    status: CommitStatus
    reading: PinnedState | None = None
    refusal: CommitRefusal | None = None
    fields: tuple[str, ...] = ()
    length: int | None = None
    inadmissible: Any = None
    seen: PinnedState | None = None


# The refusals a guard that `reads_a_move` keeps the comment it read for.
_READ_MOVES = frozenset((CommitRefusal.PREREQUISITE_CHANGED, CommitRefusal.MOVED))


@dataclass(frozen=True)
class PinnedCommit:
    """The reading a commit is guarded by, and what it may write over a fresh one."""

    comment_id: int | None
    parsed: bool
    # Every field the captured reading carried, as the comment spelled it.
    read: Mapping[str, str]
    # The fields the decision depends on, absent ones included: a field the
    # captured reading lacked has to be lacking still.
    prerequisites: frozenset[str]
    # The fields the caller may write; every other field is the fresh
    # reading's, unknown ones included.
    owned: frozenset[str]
    # The caller's domain check of the complete candidate, where it has one.
    admits: Admits | None = None
    # Whether an edit that found the comment moved under it -- behind the
    # fresh reading -- is answered over the comment that edit read
    # (`under_the_edit`), and a refusal of moved prerequisites keeps the
    # comment it read them on (`keeps_the_move`); False keeps such an edit's
    # refusal naming no field, and every refusal carrying no comment.
    reads_a_move: bool = False

    @classmethod
    def capture(
        cls,
        state: PinnedState,
        *,
        prerequisites: Iterable[str] = (),
        owned: Iterable[str] = (),
        admits: Admits | None = None,
    ) -> PinnedCommit:
        """The commit guarded by `state` as it was read.

        Taken before anything is staged on `state`, since what the caller
        changes is told by its difference from this. A field may be both a
        prerequisite and owned: a record the decision rests on and the commit
        replaces. `admits` is asked of every candidate derived under this
        guard, the one a commit sends included.
        """
        return cls(
            comment_id=state.comment_id,
            parsed=state.parsed,
            read=MappingProxyType({field: spelled(state.data, field) for field in state.data}),
            prerequisites=frozenset(prerequisites),
            owned=frozenset(owned),
            admits=admits,
        )

    def moved(self, fresh: Mapping[str, Any]) -> tuple[str, ...]:
        """The prerequisites `fresh` spells otherwise than this capture read them, sorted; empty where none moved."""
        return tuple(sorted(
            field for field in self.prerequisites
            if spelled(fresh, field) != self.read.get(field)
        ))

    def held_to(self, prerequisites: Iterable[str]) -> PinnedCommit:
        """This guard, decided on `prerequisites` alone, everything else it read and owns kept."""
        return replace(self, prerequisites=frozenset(prerequisites))

    def reading_moves(self, reads: bool) -> PinnedCommit:
        """This guard, its edit's move read (`reads_a_move`) where `reads`."""
        return replace(self, reads_a_move=reads)

    def edit_options(self, over: dict, seen: list[PinnedState]) -> dict[str, Any]:
        """What the strict edit is asked with beside its candidate: `over`, and `seen` where `reads_a_move`."""
        return {"over": over, "seen": seen} if self.reads_a_move else {"over": over}

    def under_the_edit(
        self, refusal: CommitRefusal, seen: list[PinnedState],
    ) -> tuple[CommitRefusal, tuple[str, ...]]:
        """`refusal` an edit answered, and the prerequisites the comment it read spells otherwise.

        PREREQUISITE_CHANGED where any did, since that is what moved under the
        edit, the comment it read being kept in `seen` (`edit_options`); `refusal`
        with none named otherwise.
        """
        moved = self.moved(seen[0].data) if seen else ()
        return (CommitRefusal.PREREQUISITE_CHANGED if moved else refusal), moved

    def keeps_the_move(self, outcome: CommitOutcome, reading: PinnedState | None) -> CommitOutcome:
        """`outcome`, carrying `reading` as `seen` where this guard `reads_a_move` and it refuses a move.

        `reading` is the comment that refusal was read over: the fresh reading,
        or the one the strict edit read under it (`under_the_edit`) -- which,
        where it moved no prerequisite, is the comment a MOVED refusal found
        moved under the edit, a record the caller keeps as the fresh comment
        carries it among what may have moved.
        """
        if not self.reads_a_move or outcome.refusal not in _READ_MOVES:
            return outcome
        return replace(outcome, seen=reading)


def spelling(field_value: Any) -> str | None:
    """How the comment's JSON spells one value, or None for ABSENT.

    `null` is spelled, so a field holding it is told apart from one missing.
    """
    if field_value is ABSENT:
        return None
    return json.dumps(field_value, sort_keys=True)


def spelled(record: Mapping[str, Any], field: str) -> str | None:
    """How the comment's JSON spells one field of `record`, or None where it carries none."""
    return spelling(record.get(field, ABSENT))


def loaded(spelling: str | None) -> Any:
    """The value one spelling reads back as -- a fresh copy -- or ABSENT for none."""
    if spelling is None:
        return ABSENT
    return json.loads(spelling)
