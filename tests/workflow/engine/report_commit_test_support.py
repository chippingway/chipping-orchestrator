# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The comment a report's guarded commits land over, and the roads that move it meanwhile.

A report's record, its binding, and the park a refusal of either takes are each
committed over the comment a tick read, so a case's state is pinned on the issue
first and remembered as read. Another road is a whole-state write through the
legacy writer, over a reading of its own, which is what every unmigrated road is.
"""
from __future__ import annotations

import copy
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_delivery as _delivery
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import report_delivery_test_support as delivery_support


def pinned(seeded: tuple, state: PinnedState) -> tuple:
    """`seeded`, with `state` pinned on its issue as the tick that read it holds it.

    Whatever the case stages on `state` after this is the tick's own.
    """
    github, issue = seeded
    github.seed_state(issue, **copy.deepcopy(state.data))
    reading = github.read_pinned_state(issue)
    state.comment_id = reading.comment_id
    state.synced = reading.synced
    return seeded


def records(
    state: PinnedState, agent_result, route=WorkflowLabel.IMPLEMENTING,
) -> tuple:
    """Pin `state` on a fresh issue and record the run `agent_result` was over it.

    Answers whether the tick ended, then the client and the issue it ran on.
    """
    github, issue = pinned(delivery_support.seeded_issue(), state)
    stopped = _delivery.recording_stops_the_tick(
        github, issue, state, agent_result, route,
    )
    return stopped, github, issue


def another_road(github, issue, **fields) -> dict:
    """Another road's whole-state write of `fields` over the comment as it stands now.

    What a tick that read the comment earlier never sees. A field given None is
    written as `null`. Answers what the comment carries afterwards.
    """
    reading = github.read_pinned_state(issue)
    reading.data.update(copy.deepcopy(fields))
    github.write_pinned_state(issue, reading)
    return github.pinned_data(issue.number)


def under_the_edit(github, issue, **fields):
    """A patch that has another road write `fields` once a guarded commit has read the comment.

    Taken on the strict edit's walk to its comment, which is the last reading
    before the edit lands: what another road writes there moves the comment
    out from under the reading the candidate was derived and checked over.
    """
    return patch.object(github, _WALK, _UnderTheEdit(github, issue, fields))


# The request a strict edit walks to its comment with.
_WALK = "_pinned_comment"


class _UnderTheEdit:
    """The strict edit's walk, taken once another road has written over the comment."""

    def __init__(self, github, issue, fields: dict) -> None:
        self._github = github
        self._issue = issue
        self._fields = fields
        self._walks = github._pinned_comment

    def __call__(self, issue, comment_id):
        """Write the other road's fields, then walk to the comment."""
        another_road(self._github, self._issue, **self._fields)
        return self._walks(issue, comment_id)


def behind(github, issue, request: str, **fields):
    """A patch that has another road write `fields` once, right behind `request`.

    `EDIT` is the strict edit a guarded commit lands through: whatever it came
    to -- landed and answered, or landed with its answer lost -- the comment
    then carries a field the tick holding the commit's state never read.
    `NOTICE` is the post a park's notice goes out as, between preparing its
    record and landing it: the comment then carries a field the preparation
    never read.
    """
    sends = getattr(github, request)
    return patch.object(github, request, _Behind(sends, github, issue, fields))


EDIT = "edit_pinned_state"

NOTICE = "comment"


class _Behind:
    """One request, with another road writing over the comment once it is sent."""

    def __init__(self, sends, github, issue, fields: dict) -> None:
        self._sends = sends
        self._github = github
        self._issue = issue
        self._fields = fields
        self._pending = True

    def __call__(self, *request, **options):
        """Send the request, then write the other road's fields over the comment, once."""
        answered = self._sends(*request, **options)
        if self._pending:
            self._pending = False
            another_road(self._github, self._issue, **self._fields)
        return answered
