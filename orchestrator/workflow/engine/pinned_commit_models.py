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
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from orchestrator.github.pinned_state import PinnedState

# What a field the comment does not carry reads as, apart from one it carries
# as `null`. A transformation is handed it for an absent value, and returns it
# to have the field dropped.
ABSENT = object()

# A domain's own rule for one owned field, applied over the fresh reading:
# called with the field's fresh value, its value as the commit was captured,
# and its value as the caller staged it -- each ABSENT where missing, and each
# a copy nothing else holds -- and returning what the field is committed as.
Transform = Callable[[Any, Any, Any], Any]


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
    never touches that state itself. `fields` names what earned a refusal, and
    `length` is the rendered body an OVERFLOW measured.
    """

    status: CommitStatus
    reading: PinnedState | None = None
    refusal: CommitRefusal | None = None
    fields: tuple[str, ...] = ()
    length: int | None = None


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

    @classmethod
    def capture(
        cls,
        state: PinnedState,
        *,
        prerequisites: Iterable[str] = (),
        owned: Iterable[str] = (),
    ) -> PinnedCommit:
        """The commit guarded by `state` as it was read.

        Taken before anything is staged on `state`, since what the caller
        changes is told by its difference from this. A field may be both a
        prerequisite and owned: a record the decision rests on and the commit
        replaces.
        """
        return cls(
            comment_id=state.comment_id,
            parsed=state.parsed,
            read=MappingProxyType({field: spelled(state.data, field) for field in state.data}),
            prerequisites=frozenset(prerequisites),
            owned=frozenset(owned),
        )

    def moved(self, fresh: Mapping[str, Any]) -> tuple[str, ...]:
        """The prerequisites `fresh` spells otherwise than this capture read them, sorted; empty where none moved."""
        return tuple(sorted(
            field for field in self.prerequisites
            if spelled(fresh, field) != self.read.get(field)
        ))


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
