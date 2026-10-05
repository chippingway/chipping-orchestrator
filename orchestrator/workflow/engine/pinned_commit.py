# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The guarded commit of an issue's pinned state.

The pinned comment is an issue's whole durable record, and GitHub's edit of it
replaces the whole body with no condition on what it replaces. A writer that
rewrites the record from the state it read at the start of a tick puts back,
over every field another road wrote since, the value it read then -- a usage
total, a watermark, another domain's settled record -- and nothing on the
comment afterwards says that happened.

So a guarded commit is never written from the caller's state. The caller
captures the reading it decided on (`pinned_commit_models.PinnedCommit`),
stages its changes on its own state, and hands both here. The comment is read
afresh and has to be the comment captured, still parse, and still spell every
prerequisite exactly as captured. What the caller changed is told by the
difference between its staged state and the capture, and each changed field
has to be one it declared it owns. A changed field another writer moved
meanwhile is a conflict, not a field to take the older value back for -- save
where both writers left it spelled alike -- while an owned field the caller
left alone keeps whatever the fresh reading carries. A domain whose field has
to keep both moves -- a total, a ledger, a watermark -- supplies its own
transformation, which is applied over the fresh value instead. Every other
field, unknown ones included, is the fresh reading's.

The candidate that makes is measured as it would be written, through
`pinned_state_body` against `MAX_PINNED_BODY`, before anything goes out.
`prepare` stops there, for a caller that has an external effect to make only
if the record behind it will fit; `commit` asks everything again over a reading
taken behind whatever requests came between, and lands the candidate through
the strict edit (`GitHubStateMixin.edit_pinned_state`), which rewrites the
comment in place only while it still reads as the fresh reading did, and never
recreates one that is gone. `reread` is the same fresh reading taken alone, for
a caller that has requests of its own to make over the comment it captured
before it stages anything.

A refusal writes nothing and touches nothing the caller holds: the staged state
is only read, and a transformation is handed copies. An edit that went out and
was never confirmed is reported as UNCONFIRMED rather than as either answer --
whatever receipt the caller's own domain keeps is what a later reading settles
it by. The verification-evidence publication and settlement commit through this
(`verification_durable`, `verification_publishing`, `verification_settling`);
every other road still rewrites the whole record.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedEdit, PinnedState, pinned_state_body
from orchestrator.workflow.engine import pinned_commit_models as _models

log = logging.getLogger("orchestrator.workflow")

# What an edit GitHub answered is reported as.
_LANDED = MappingProxyType({
    PinnedEdit.EDITED: _models.CommitStatus.COMMITTED,
    PinnedEdit.UNCONFIRMED: _models.CommitStatus.UNCONFIRMED,
})

# What an edit refused before anything was sent is refused as.
_UNSENT = MappingProxyType({
    PinnedEdit.UNREAD: _models.CommitRefusal.UNREADABLE,
    PinnedEdit.MISSING: _models.CommitRefusal.REPLACED,
    PinnedEdit.MOVED: _models.CommitRefusal.MOVED,
})

_NO_TRANSFORMS: Mapping[str, _models.Transform] = MappingProxyType({})


def prepare(
    gh: GitHubClient,
    issue: Issue,
    guard: _models.PinnedCommit,
    staged: Mapping[str, Any],
    derived: Mapping[str, _models.Transform] = _NO_TRANSFORMS,
) -> _models.CommitOutcome:
    """The candidate a commit would land now, measured and written nowhere; or why it would be refused.

    Asked ahead of an external effect that depends on the record being
    written -- a comment posted, a label moved -- so the effect is never made
    for a record that could not follow it. A PREPARED answer licenses nothing
    past the requests that follow it: `commit` derives everything again.
    """
    change = _Change.of(guard, staged, derived)
    fresh = _fresh(gh, issue, change)
    if isinstance(fresh, _models.CommitOutcome):
        return fresh
    return change.over(issue, fresh)


def commit(
    gh: GitHubClient,
    issue: Issue,
    guard: _models.PinnedCommit,
    staged: Mapping[str, Any],
    derived: Mapping[str, _models.Transform] = _NO_TRANSFORMS,
) -> _models.CommitOutcome:
    """Derive the candidate over a fresh reading and rewrite the pinned comment with it in place.

    `staged` is the caller's state as it would have written it, and `derived`
    the transformations for the owned fields whose value is decided over the
    fresh one. A candidate the comment already reads as is COMMITTED with
    nothing sent. A comment that moved between the fresh reading and the edit
    is refused as MOVED with nothing sent, and a commit asked again derives
    over whatever it carries then.
    """
    change = _Change.of(guard, staged, derived)
    fresh = _fresh(gh, issue, change)
    if isinstance(fresh, _models.CommitOutcome):
        return fresh
    prepared = change.over(issue, fresh)
    if prepared.status is not _models.CommitStatus.PREPARED:
        return prepared
    if fresh.reads_as(prepared.reading.data):
        return replace(prepared, status=_models.CommitStatus.COMMITTED)
    edit = gh.edit_pinned_state(issue, prepared.reading, over=fresh.data)
    refusal = _UNSENT.get(edit)
    if refusal is not None:
        return _refused(issue, refusal)
    return replace(prepared, status=_LANDED[edit])


def reread(
    gh: GitHubClient, issue: Issue, guard: _models.PinnedCommit,
) -> PinnedState | _models.CommitOutcome:
    """The comment `guard` was captured from, read afresh, or why it cannot be; nothing staged or written.

    For a caller with requests of its own to make over the record before it
    stages anything -- a proof, a publication -- that has to stand on the
    comment it captured. Refused as `commit` refuses a reading: unreadable,
    not parsing, or not the comment captured. The prerequisites are left to
    the caller to hold the reading to (`PinnedCommit.moved`), since a domain
    may still have a write of its own to lay over a reading on which one
    moved; `commit` holds the comment to every one of them again whatever
    this answered.
    """
    return _fresh(gh, issue, _Change(guard, guard.read, _NO_TRANSFORMS))


@dataclass(frozen=True)
class _Change:
    """What one commit asks of the comment: its guard, the state staged, and the fields derived."""

    guard: _models.PinnedCommit
    # The staged state, as the comment's JSON would spell each field.
    staged: Mapping[str, str]
    derived: Mapping[str, _models.Transform]

    @classmethod
    def of(
        cls,
        guard: _models.PinnedCommit,
        staged: Mapping[str, Any],
        derived: Mapping[str, _models.Transform],
    ) -> _Change:
        """The change `staged` and `derived` make over `guard`."""
        return cls(
            guard=guard,
            staged=MappingProxyType({field: _models.spelled(staged, field) for field in staged}),
            derived=MappingProxyType(dict(derived)),
        )

    def assigned(self) -> list[str]:
        """The fields the caller staged a value for: spelled otherwise than captured, derived ones aside."""
        candidates = {*self.guard.read, *self.staged}.difference(self.derived)
        return sorted(
            field for field in candidates
            if self.guard.read.get(field) != self.staged.get(field)
        )

    def unread_refusal(self) -> tuple[_models.CommitRefusal, tuple[str, ...]] | None:
        """What refuses this change before the comment is read, and the fields it names.

        A write the caller did not declare is refused whatever the comment
        says, and so is a capture with nothing to commit over: a reading that
        would not parse, and an issue that pinned no comment, which the strict
        edit will not create.
        """
        writes = {*self.assigned(), *self.derived}
        undeclared = sorted(writes.difference(self.guard.owned))
        if undeclared:
            return _models.CommitRefusal.UNDECLARED_WRITE, tuple(undeclared)
        if not self.guard.parsed:
            return _models.CommitRefusal.MALFORMED, ()
        if self.guard.comment_id is None:
            return _models.CommitRefusal.REPLACED, ()
        return None

    def over(self, issue: Issue, fresh: PinnedState) -> _models.CommitOutcome:
        """This change laid over `fresh` and measured, or the refusal it earns there."""
        moved = self.guard.moved(fresh.data)
        if moved:
            return _refused(issue, _models.CommitRefusal.PREREQUISITE_CHANGED, moved)
        conflicts = [
            field for field in self.assigned()
            if _models.spelled(fresh.data, field) not in {
                self.guard.read.get(field),
                self.staged.get(field),
            }
        ]
        if conflicts:
            return _refused(issue, _models.CommitRefusal.OWNED_CONFLICT, tuple(conflicts))
        candidate = self._candidate(fresh.data)
        length = len(pinned_state_body(candidate))
        if length > MAX_PINNED_BODY:
            return _refused(issue, _models.CommitRefusal.OVERFLOW, length=length)
        return _models.CommitOutcome(
            _models.CommitStatus.PREPARED,
            reading=PinnedState(comment_id=fresh.comment_id, state_data=candidate),
        )

    def _candidate(self, fresh: dict) -> dict:
        """`fresh` with this change laid over it, as a reader would parse it back."""
        spellings = {field: _models.spelled(fresh, field) for field in fresh}
        spellings.update({
            field: self.staged.get(field) for field in self.assigned()
        })
        spellings.update({
            field: self._derived_spelling(fresh, field) for field in self.derived
        })
        return {
            field: json.loads(spelling)
            for field, spelling in spellings.items()
            if spelling is not None
        }

    def _derived_spelling(self, fresh: dict, field: str) -> str | None:
        """What the domain's transformation makes of one field, over its fresh value."""
        transform = self.derived[field]
        return _models.spelling(transform(
            _models.loaded(_models.spelled(fresh, field)),
            _models.loaded(self.guard.read.get(field)),
            _models.loaded(self.staged.get(field)),
        ))


def _fresh(
    gh: GitHubClient, issue: Issue, change: _Change,
) -> PinnedState | _models.CommitOutcome:
    """The pinned comment read afresh as the one `change` was captured from, or the refusal that ends it first."""
    unread = change.unread_refusal()
    if unread is not None:
        return _refused(issue, *unread)
    try:
        fresh = gh.read_pinned_state(issue)
    except Exception:
        log.exception(
            "issue=#%d could not read its pinned comment to commit over it", issue.number,
        )
        return _refused(issue, _models.CommitRefusal.UNREADABLE)
    if not fresh.parsed:
        return _refused(issue, _models.CommitRefusal.MALFORMED)
    if fresh.comment_id != change.guard.comment_id:
        return _refused(issue, _models.CommitRefusal.REPLACED)
    return fresh


def _refused(
    issue: Issue,
    refusal: _models.CommitRefusal,
    fields: tuple[str, ...] = (),
    length: int | None = None,
) -> _models.CommitOutcome:
    """One refusal, logged; nothing was written for it."""
    log.warning(
        "issue=#%d its pinned-state commit was refused as %s (fields %s, length %s); writing nothing",
        issue.number, refusal.value, list(fields), length,
    )
    return _models.CommitOutcome(
        _models.CommitStatus.REFUSED, refusal=refusal, fields=fields, length=length,
    )
