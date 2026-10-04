# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A poll latching a close from inside one of the run's own requests.

The latch is what the run in flight asks before every step the remote keeps,
and every case that needs one asks it against a window that is REMOTE work:
the pinned write that forces an issue to be an umbrella, the repository walk
that looks a half-created child up, the child-label scan an umbrella opens
with, the request that opens a child issue, the branch delete a terminal
settles with, the relabel that releases the first child. A human closes the
issue inside one of those, a poll sees it, and no second worker may be handed
the reading -- which is exactly the shape these seams plant. Each latch carries
the moment the poll read it at, as a poll's does, which is what ties it to the
cycle the run holds: no other poller has held the issue since.
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator.workflow.engine import observations as _observations
from tests.workflow.observation_support import read_now

# The client calls each once-only window is, named so a case says which
# request it is closing the issue inside of rather than spelling a method.
CREATE_CHILD = "create_child_issue"
ISSUE_COMMENT = "comment"
ORPHAN_WALK = "find_issue_carrying"
PR_SEARCH = "find_pr_for_commit"
CHILD_RELABEL = "set_workflow_label"
BRANCH_DELETE = "delete_remote_branch"

# The pinned field a live cycle is named by, and the one a retirement drops.
_CYCLE_ID = "late_cycle_id"


def latches_on_call(github, repo_slug: str, issue_number: int, seam: str):
    """Latch a close from inside one client call the run makes exactly once.

    Reaching the seam IS the trigger, which is what every window but two is
    shaped like: the orphan walk, the pull-request search, the create, the
    child relabel, and the branch delete a terminal settles with are each
    asked once on the path a case is about.
    """
    return _LatchingSeam(
        github, seam, repo_slug, issue_number, _always,
    ).answering()


def latches_on_write(github, repo_slug: str, issue_number: int, key: str):
    """Latch a close from inside the pinned write that carries `key`.

    Keyed off what the write says rather than off reaching it, because pinned
    state is written on nearly every step and only one of those writes is the
    window a case is about.
    """
    return _LatchingSeam(
        github,
        "write_pinned_state",
        repo_slug,
        issue_number,
        lambda asked: asked[1].data.get(key) is not None,
    ).answering()


def latches_on_retirement(
    github, repo_slug: str, issue_number: int, *, after: bool = False,
):
    """Latch a close around the write that drops an issue's late cycle.

    Keyed off what the write no longer says: every pinned write a late tick
    makes names the cycle, and the retirement a published `single` ends on is
    the one that does not.

    `after` moves the latch to the far side of that write, which is the last
    instant inside the retirement window: the write has landed, the worker is
    about to ask what the window observed, and a barrier taken any earlier
    would step straight over it.
    """
    seam = _LatchingSeam(
        github, "write_pinned_state", repo_slug, issue_number,
        lambda asked: asked[1].data.get(_CYCLE_ID) is None,
    )
    seam.after_the_call = after
    return seam.answering()


def latches_on_child_read(github, repo_slug: str, issue_number: int):
    """Latch a close from inside the pinned read taken of a CHILD.

    Keyed off whose comment is being read, because the owner's own record is
    read through the same seam and reaching it is not this window.
    """
    return _LatchingSeam(
        github, "read_pinned_state", repo_slug, issue_number,
        lambda asked: int(asked[0].number) != issue_number,
    ).answering()


def latches_on_child_scan(github, repo_slug: str, issue_number: int):
    """Latch a close from inside the read that lists a child's labels.

    Keyed off the number asked for, because the owner is read through the
    same seam and reaching it is not what this window is about.
    """
    return _LatchingSeam(
        github, "get_issue", repo_slug, issue_number,
        lambda asked: int(asked[0]) != issue_number,
    ).answering()


def _always(asked) -> bool:
    """A seam the run reaches exactly once, so reaching it is the trigger."""
    return True


class _LatchingSeam:
    """Latch a close from inside one call the run makes, then answer it.

    The seam still does what it was asked. What each case is about is the
    state the run leaves once that step HAS happened and the reading arrived
    a moment too late for any request of its own to show it.

    `after_the_call` moves the latch to the far side of the call, which is
    the one window a step cannot see for itself: the request has landed, and
    whatever the run asks next is the only thing that could still notice.
    """

    after_the_call = False

    def __init__(
        self,
        github,
        seam: str,
        repo_slug: str,
        issue_number: int,
        when,
    ) -> None:
        self._github = github
        self._seam = seam
        self._slug = repo_slug
        self._number = issue_number
        self._when = when
        self._answering = getattr(github, seam)

    def __call__(self, *asked, **answering):
        """Latch the close around this call, if this call is the one."""
        latching = self._when(asked)
        if latching and not self.after_the_call:
            _observations.observe_close(self._slug, self._number, read_now())
        answered = self._answering(*asked, **answering)
        if latching and self.after_the_call:
            _observations.observe_close(self._slug, self._number, read_now())
        return answered

    def answering(self):
        """Put this in front of every call the run makes to that seam."""
        return patch.object(self._github, self._seam, side_effect=self)
