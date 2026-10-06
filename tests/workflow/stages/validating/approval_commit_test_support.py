# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which guarded commit an approval tail's case is about, and GitHub losing the response of just that one.

A whole tick makes several guarded commits -- a reviewer round's, the
evidence's, the tail's own -- so a case about one of them names it by what it
stages (`staging`): the first commit carrying a field, or carrying it spelled
one way. `LosesOneResponse` has GitHub take that commit and lose its response,
every other commit of the tick answered as ever, which losing every edit's
response for the tick (`review_write_test_support.loses_the_responses`) cannot
say. `FillsAhead` has another road fill the comment right ahead of that
commit, to just short of what its own candidate needs, so whatever the commit
has to fit beyond that candidate is visibly what refuses it, and
`refusing_the_record` has it leave a note ahead of a squash's record of its
collapse that refuses that record, by an edit left unanswered or by leaving it
no room.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
from functools import partial
from typing import Any
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedEdit, pinned_state_body
from orchestrator.workflow.engine import pinned_commit as _pinned_commit

# A staged field asked about whatever it spells.
_ANY = object()

# The note another road leaves on the comment, which nothing reads.
NOTE = "operator_notes"

# How far short of its ceiling a filled comment leaves the candidate: enough
# for the candidate, and short of anything it has to leave room for beyond it.
# A negative spare leaves the candidate itself past the ceiling.
FITS = 64

OVERFLOWS = -1


def staging(field: str, spelled: Any = _ANY) -> Callable[[Mapping], bool]:
    """Whether a guarded commit's staged record carries `field` -- as `spelled`, where given."""
    return partial(_stages, field, spelled)


def refusing_the_record(github, issue, *, unreadable: bool) -> Callable[[], AbstractContextManager]:
    """Another road's note ahead of a squash's record of its collapse, and what that record is written under.

    Answered when called, right ahead of the record: the note left on the
    comment, and a context in which the record's edit goes unanswered -- where
    `unreadable` -- or, the note filling the comment to a character short of
    its ceiling, in which nothing but that lack of room refuses it.
    """
    return partial(_refuses_the_record, github, issue, unreadable)


def _refuses_the_record(github, issue, unreadable: bool) -> AbstractContextManager:
    """Leave the note `refusing_the_record` describes; the context the record is written in."""
    noted = github.read_pinned_state(issue)
    noted.set(NOTE, "")
    room = MAX_PINNED_BODY - len(pinned_state_body(noted.data)) - 1
    noted.set(NOTE, "kept" if unreadable else "x" * room)
    github.write_pinned_state(issue, noted)
    if unreadable:
        return patch.object(github, "edit_pinned_state", return_value=PinnedEdit.UNREAD)
    return nullcontext()


def _stages(field: str, spelled: Any, staged: Mapping) -> bool:
    """Whether `staged` carries `field`, as `spelled` unless that is `_ANY`."""
    return field in staged and (spelled is _ANY or staged[field] == spelled)


class LosesOneResponse:
    """GitHub taking the first guarded commit `when` names and losing its response; every other one answered.

    `when` is asked of the commit's staged record, as the comment would carry
    it.
    """

    def __init__(self, case, when: Callable[[Mapping], bool]) -> None:
        self._case = case
        self._when = when
        self._commits = _pinned_commit.commit
        self._pending = True

    def __call__(self, gh, issue, guard, staged, *derived):
        if not (self._pending and self._when(staged)):
            return self._commits(gh, issue, guard, staged, *derived)
        self._pending = False
        lost = self._case.github.pinned_failures.lost
        lost.add(issue.number)
        landed = self._commits(gh, issue, guard, staged, *derived)
        lost.discard(issue.number)
        return landed

    def patched(self):
        """A patch of the guarded commit losing that one response."""
        return patch.object(_pinned_commit, "commit", self)


class FillsAhead:
    """Another road filling the comment right ahead of the first guarded commit `when` names.

    Filled with a note of its own, sized so the comment and what the commit
    stages over it come to `spare` characters short of the comment's ceiling:
    at `FITS`, the commit's own candidate fits and anything it has to leave
    room for beyond that candidate does not; at `OVERFLOWS`, the candidate
    itself is past the ceiling.
    """

    def __init__(self, case, when: Callable[[Mapping], bool], spare: int = FITS) -> None:
        self._case = case
        self._when = when
        self._spare = spare
        self._commits = _pinned_commit.commit
        self._pending = True

    def __call__(self, gh, issue, guard, staged, *derived):
        if self._pending and self._when(staged):
            self._pending = False
            self._fills(staged)
        return self._commits(gh, issue, guard, staged, *derived)

    def patched(self):
        """A patch of the guarded commit with the comment filled ahead of it."""
        return patch.object(_pinned_commit, "commit", self)

    def _fills(self, staged: Mapping) -> None:
        state = self._case.github.read_pinned_state(self._case.issue)
        widened = len(pinned_state_body(dict(staged)))
        growth = widened - len(pinned_state_body(state.data))
        state.set(NOTE, "")
        room = MAX_PINNED_BODY - len(pinned_state_body(state.data))
        state.set(NOTE, "x" * (room - growth - self._spare))
        self._case.github.write_pinned_state(self._case.issue, state)
