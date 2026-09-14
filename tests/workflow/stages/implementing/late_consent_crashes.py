# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Crashes after pinned writes, relabels, park restoration, and consent notices."""
from __future__ import annotations

from orchestrator.workflow.stages.implementing import (
    state as _state,
)


class CrashedTick(RuntimeError):
    """The process dying between two writes one road makes."""


class DiesPastTheFirstWrite:
    """A client that makes its first durable write and then dies.

    For a road whose first write is not the one at risk: the sentence has been
    said AND recorded by then, and what the crash costs is whatever the write
    after that carried.
    """

    def __init__(self, github) -> None:
        self._wrapped = github.write_pinned_state
        self._writes = 0

    def __call__(self, *called, **options):
        self._writes += 1
        if self._writes > 1:
            raise CrashedTick
        return self._wrapped(*called, **options)


class DiesPastTheRelabel:
    """A client that dies on the first write once the label has moved.

    The window a successful publication opens: the handoff writes durably and
    then hands the issue to `validating`, and everything this stage still had
    in flight is past saving from that point on -- nothing under the new label
    spends it and this stage never sees the issue again. What it kills is the
    write AFTER the relabel, which is the last chance a road here would have
    had to tidy up in memory.
    """

    def __init__(self, github) -> None:
        self._github = github
        self._wrapped = github.write_pinned_state

    def __call__(self, *called, **options):
        if self._github.label_history:
            raise CrashedTick
        return self._wrapped(*called, **options)


class DiesRestoringTheHeldPark:
    """A client that dies on the write that would put a held park back.

    The window the durable rollback exists for, named by what makes it that
    window rather than by a count of writes: a handoff has recorded what the
    park was, the seam has written over it, and the write that would restore
    it is the one killed. Everything the seam itself persisted lands, which is
    the whole point -- a rollback kept in memory is gone by the next poll and
    the record still says whatever the seam left.
    """

    def __init__(self, github) -> None:
        self._wrapped = github.write_pinned_state
        self._recorded = False

    def __call__(self, issue, state, *called, **options):
        held = state.get(_state._HELD_PARK)
        if self._recorded and held is None:
            raise CrashedTick
        self._recorded = self._recorded or held is not None
        return self._wrapped(issue, state, *called, **options)


class DiesPastTheNotice:
    """A client whose write dies once the thread carries what a case is about.

    The window itself rather than a count of writes, so a case reproduces it
    whichever order the road makes its operations in: what it kills is always
    the write that would have recorded the sentences just posted.

    `said` is how many of them have to be on the thread first, for a road that
    says more than one thing before anything records any of it -- a pull
    request opened, then a refusal over a checkout that moved under the push.

    `spared` is how many writes past that go through anyway, for a road whose
    own next act is a write: the client this park hands the seam records each
    id the instant the post returns, so a case about the window PAST that one
    has to let it land.
    """

    def __init__(self, github, said: int = 1, spared: int = 0) -> None:
        self._github = github
        self._said = said
        self._spared = spared
        self._wrapped = github.write_pinned_state

    def __call__(self, *called, **options):
        if len(self._github.posted_comments) >= self._said:
            if not self._spared:
                raise CrashedTick
            self._spared -= 1
        return self._wrapped(*called, **options)
