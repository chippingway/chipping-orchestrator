# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What GitHub can do to a finished docs pass's completion write other than take it.

Each double here is armed off what the completion's strict edit carries -- a
stamped verdict -- rather than off how many writes came before it, and answers
every other request as always. The ways it is left unanswered are the in-memory
client's own (`pinned_failures`); the comment a human edits while the notice is
out, and the one a human has filled to its limit, are its pinned record edited
in place, as a maintainer's hand would.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from tests.workflow.stages.documenting import (
    documenting_gate_test_support as gate,
)

# How GitHub leaves the completion's edit unanswered, as the client's
# `pinned_failures` names it: a comment the edit could not read, refused before
# anything went out; an edit sent and refused, which never landed; and one that
# landed and whose answer was lost. The second and third come back alike --
# unconfirmed -- and only a later reading tells them apart.
UNREADABLE = "unreadable"
REFUSED = "refused"
LOST = "lost"

# The notice's own request, which a human's edit of the comment is timed by.
PR_COMMENT = "pr_comment"

# A field a human fills a pinned comment up to its limit with.
FILLER = "operator_note"


class _FailsTheCompletion:
    """The completion's edit, left unanswered the way `how` names; every other edit answered as always.

    The failure is set for that one edit alone, so it is gone again by the
    time the tick that follows reads the comment.
    """

    def __init__(self, github, how: str) -> None:
        self._edit = github.edit_pinned_state
        self._failures = getattr(github.pinned_failures, how)

    def __call__(self, issue, state, **options):
        if not gate._a_finished_pass(state):
            return self._edit(issue, state, **options)
        self._failures.add(issue.number)
        edited = self._edit(issue, state, **options)
        self._failures.discard(issue.number)
        return edited


class _StripsWhilePosting:
    """The notice's post, with one field stripped off the pinned comment by hand while it is out.

    A maintainer's edit: the comment the completion was prepared over is not
    the one its write then finds.
    """

    def __init__(self, github, issue_number: int, field: str) -> None:
        self._post = github.pr_comment
        self._pinned = github._pinned
        self._issue_number = issue_number
        self._field = field

    def __call__(self, *args, **options):
        posted = self._post(*args, **options)
        self._pinned[self._issue_number].data.pop(self._field, None)
        return posted


def _leaves_no_room(github, issue_number: int) -> None:
    """Fill the issue's pinned comment up to exactly its limit, as a human's notes on it might."""
    pinned = github._pinned[issue_number].data
    pinned[FILLER] = ""
    pinned[FILLER] = "x" * (MAX_PINNED_BODY - len(pinned_state_body(pinned)))


def _makes_room(github, issue_number: int) -> None:
    """Take the filler back off the issue's pinned comment, as a human making room does."""
    github._pinned[issue_number].data.pop(FILLER)
