# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What happens to issue #7 while its rewritten head's commands run, and the room made behind it.

Each is handed the case as the verify runner's double runs (`during`), between
the evidence decision's binding being proved and its being proved again: a
review recorded over the comment as it stands, a pinned comment that would not
read or whose edit's answer is lost, and a comment filled to its limit by
records the finish never decided on. `makes_room` is a human clearing that
filler once the finish has held for it. `FailingPosts` is GitHub refusing the
notice of a failed run, or landing it and losing the answer.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from tests.workflow.engine import verification_evidence_test_support as support

# A key nothing reads, standing in for whatever else fills the comment.
_FILLER = "room_filler"

# How the notice of a failed run opens, which tells it from the announcement.
_FAILURE_NOTICE = ":x:"


def unmoved(_case) -> None:
    """Nothing another road does while the commands run."""


def later_review(case) -> None:
    """Settle report 3 of the rebased head and hand a reviewer it, written over the comment as it stands."""
    case.rereads()
    case.rewrites(support.REBASED_SHA, revision=3)


def unreadable(case) -> None:
    """Have the pinned comment refuse every read until a case says otherwise."""
    case.gh.pinned_failures.unreadable.add(case.issue.number)


def loses_answers(case) -> None:
    """Have every pinned edit land and its answer be lost until a case says otherwise."""
    case.gh.pinned_failures.lost.add(case.issue.number)


def fills_the_comment(case) -> None:
    """Fill the pinned comment to its limit, as another road's records would."""
    filled = case.gh.read_pinned_state(case.issue)
    filled.set(_FILLER, "")
    room = MAX_PINNED_BODY - len(pinned_state_body(filled.data))
    filled.set(_FILLER, "x" * room)
    case.gh.write_pinned_state(case.issue, filled)


def makes_room(case) -> None:
    """Take the filler back off the pinned comment, as a human making room does."""
    emptied = case.gh.read_pinned_state(case.issue)
    emptied.data.pop(_FILLER)
    case.gh.write_pinned_state(case.issue, emptied)


class FailingPosts:
    """The client's pull-request comment, with the notice of a failed run refused or its answer lost while `failing`.

    A lost answer lands the comment first and raises after, which is the post
    a retry has to find on the thread rather than make again. Every other
    comment -- the announcement among them -- is posted as the client posts it.
    """

    def __init__(self, case, *, lands: bool) -> None:
        self._post = case.gh.pr_comment
        self._lands = lands
        self.failing = True
        case.gh.pr_comment = self

    def __call__(self, pr_number: int, body: str):
        """Post `body` onto `pr_number`, unless it is a failure notice GitHub is failing."""
        if not (self.failing and body.startswith(_FAILURE_NOTICE)):
            return self._post(pr_number, body)
        if self._lands:
            self._post(pr_number, body)
        raise RuntimeError("GitHub did not answer the comment")
