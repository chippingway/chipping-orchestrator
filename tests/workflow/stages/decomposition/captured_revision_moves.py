# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What lands on an issue while a captured late revision's recovery works, each at the moment it lands.

A recovery takes requests between the admission and every write it makes --
the checkout measured, the comment walked to, the owner read again behind its
handoff -- and an operator, another road, or a poll can land a move inside any
of them. Each move here is held in place of one of those requests for a
dispatch (`CapturedRevisionCase._dispatched`), so a case can say what the
recovery left once that move landed exactly there.
"""
from __future__ import annotations

import contextlib
import copy
from collections.abc import Callable, Iterator
from functools import partial
from unittest.mock import MagicMock, patch

from tests.support.fakes import FakeLabel
from tests.workflow import git_owners as _git_owners
from tests.workflow.stages.decomposition import (
    captured_revision_support as _captured,
    late_content_support as _content_support,
    late_revision_support as _revision_support,
    late_run_support as _run_support,
)

# The seams a checkout's tree and its head are read through.
_TREE_READ = "_worktree_status"
_HEAD_READ = "_head_sha"

# The owner read a recovery's handoff claims, which its settlement clears.
_OWNER_CHECK_PENDING = "late_owner_check_pending"


class AppliedInTheWalk:
    """A strict edit's walk to the pinned comment with an operator's control applied to the issue as it walks.

    The walk is the comment lookup the strict edit asks a caller's question
    behind (`github/edit_questions`), so a control applied in it is one no
    reading taken ahead of the edit could have seen.
    """

    def __init__(self, case: _captured.CapturedRevisionCase, control: str) -> None:
        self._case = case
        self._control = FakeLabel(control)
        self._walks = case.github._pinned_comment

    def __call__(self, issue, comment_id, *, authoritative: bool = False):
        """Apply the control on an edit's own walk, then answer the lookup as the double does."""
        if authoritative:
            self._case.issue.labels.append(self._control)
        return self._walks(issue, comment_id, authoritative=authoritative)

    def patched(self) -> contextlib.AbstractContextManager:
        """The lookup, held in place of the double's for the block."""
        return patch.object(self._case.github, "_pinned_comment", self)


class BehindTheHandoff:
    """`aside(*args, **fields)` done to the issue once, behind the commit that hands a recovery's capture on.

    Either on the first fetch of the issue once the capture reads handed off
    (`fetched`) -- the owner read's own, or the question a write behind it asks
    first -- or right behind that commit's own edit, ahead of anything after it
    (`landed`), or right behind the edit that settles the owner read behind
    it, ahead of the notice that settlement says (`landed`, `settled`) -- or,
    for a capture withdrawn behind its park rather than handed on, behind the
    edit that retires it (`landed`, `stage`). The
    record and the number of comments said as the aside is done are kept
    (`record`, `said`), for a case to hold what the recovery left after it to
    them.
    """

    def __init__(self, case: _captured.CapturedRevisionCase, aside: Callable[..., object], *args, **fields) -> None:
        self._case = case
        self._aside = partial(aside, *args, **fields)
        self._fetches = case.github.get_issue
        self._edits = case.github.edit_pinned_state
        self._settled = False
        self._stage = _captured.HANDED_OFF
        self.record: dict | None = None
        self.said = 0

    def fetched(self) -> contextlib.AbstractContextManager:
        """The fetch, held in place of the double's for the block."""
        return patch.object(self._case.github, "get_issue", self._fetch)

    def landed(self, *, settled: bool = False, stage=_captured.HANDED_OFF) -> contextlib.AbstractContextManager:
        """The strict edit, held in place of the double's for the block; behind the settlement if `settled`."""
        self._settled = settled
        self._stage = stage
        return patch.object(self._case.github, "edit_pinned_state", self._edit)

    def _fetch(self, number: int):
        fetched = self._fetches(number)
        self._behind()
        return fetched

    def _edit(self, issue, state, **options):
        sent = self._edits(issue, state, **options)
        self._behind()
        return sent

    def _behind(self) -> None:
        """Do the aside the first time the capture reads handed off, keeping the record and comments as they stood."""
        pinned = self._case._pinned()
        handed = getattr(_captured.capture_of(pinned), "stage", None) is self._stage
        owed = self._settled and pinned.get(_OWNER_CHECK_PENDING)
        if self.record is None and handed and not owed:
            self.record = copy.deepcopy(self._case._pinned())
            self.said = len(self._case._bodies())
            self._aside()


def applying(case: _captured.CapturedRevisionCase, control: str) -> Callable[[], None]:
    """An operator applying `control` to `case`'s issue."""
    return partial(case.issue.labels.append, FakeLabel(control))


class MovedAfterTheReturn:
    """A developer run finishing on its report, its checkout's head moved to `moved` once the return was read.

    The head is read through the seam the harness holds for the run, told to
    answer the revised commit once -- the return's own reading -- and `moved`
    after it, so nothing outlives the harness that holds it.
    """

    def __init__(self, moved: str) -> None:
        self._moved = moved

    def __call__(self, *_asked, **_answering):
        """Answer the run on its report, the read of the head after its own answering `moved`."""
        heads = _git_owners.GIT_SEAM_OWNERS[_HEAD_READ]._head_sha
        heads.side_effect = [_content_support.REVISED_SHA, self._moved]
        return _run_support.agent_reply(_captured.DEV_REPORT)


class InTheLastRead:
    """`aside(*args, **fields)` done to the issue once, right behind a recovery's question reads the comment again.

    The question a strict edit asks behind its walk to the comment reads the
    pinned comment once more after the admission's own requests
    (`implementing/captured_rereads`) -- the first reading of the comment
    behind a walk -- and the aside lands right behind it: after the comment
    that read returns, ahead of everything the question asks after it.
    """

    def __init__(self, case: _captured.CapturedRevisionCase, aside: Callable[..., object], *args, **fields) -> None:
        self._case = case
        self._aside = partial(aside, *args, **fields)
        self._walks = case.github._pinned_comment
        self._reads = case.github.read_pinned_state
        self._walked = False
        self.done = False

    def patched(self) -> contextlib.AbstractContextManager:
        """The walk and the read, held in place of the double's for the block."""
        held = contextlib.ExitStack()
        held.enter_context(patch.object(self._case.github, "_pinned_comment", self._walk))
        held.enter_context(patch.object(self._case.github, "read_pinned_state", self._read))
        return held

    def _walk(self, issue, comment_id, *, authoritative: bool = False):
        self._walked = self._walked or authoritative
        return self._walks(issue, comment_id, authoritative=authoritative)

    def _read(self, issue):
        reading = self._reads(issue)
        if self._walked and not self.done:
            self.done = True
            self._aside()
        return reading


class TreeReadWhile:
    """A checkout's tree read as the harness holds it, with `aside(*args, **fields)` done to the issue as it is read."""

    def __init__(self, aside: Callable[..., object], *args, **fields) -> None:
        self._aside = partial(aside, *args, **fields)
        self._reads: Callable | None = None

    def __call__(self, worktree):
        """Do the aside, then answer the read the harness holds."""
        self._aside()
        return self._reads(worktree)

    @contextlib.contextmanager
    def patched(self) -> Iterator[None]:
        """The read, held in place of the harness's for the block -- the one the harness holds as the block opens."""
        self._reads = _git_owners.GIT_SEAM_OWNERS[_TREE_READ]._worktree_status
        with _git_owners.seam_patch(_TREE_READ, MagicMock(side_effect=self)):
            yield


class MeasuredWhile:
    """A candidate measured oversized, with `aside(*args, **fields)` done to the issue while it is measured."""

    def __init__(self, aside: Callable[..., object], *args, **fields) -> None:
        self._aside = partial(aside, *args, **fields)

    def __call__(self, *_measured, **_asked):
        """Do the aside, then answer the measurement."""
        self._aside()
        return _revision_support.REMEASURED_OVERSIZED

    def patched(self) -> contextlib.AbstractContextManager:
        """The measurement, held in place of the harness's for the block."""
        return _git_owners.seam_patch("_measure_candidate", MagicMock(side_effect=self))
