# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The workflow relabel that names only the labels it moves.

`issues.set_workflow_label` sends the whole label set it read off the issue,
so a label applied after that reading -- an operator's `paused` or `backlog`
above all -- is written away by it, however few requests stand between the
reading and the write. A relabel made over requests it cannot drop -- the
dependency release, whose last request in front of the write is the
publication its children are licensed on -- moves the issue here instead: the
new workflow label is added, and each workflow label it replaces is taken off
by name, so nothing else the issue carries by then is ever named, and a hold
applied in the meantime stays.

The label is added before any is taken off. An interrupted move leaves the
issue carrying both, which every reader tolerates as it does a human's second
workflow label and the issue's next relabel takes off, rather than carrying
none, which every reader takes for an issue nobody picked up. A label already
gone when the move takes it off is gone. The move is guarded, announced, and
left readable on the object it went through exactly as a whole-set write is.
"""
from __future__ import annotations

import logging
from typing import Any

from github import GithubException
from github.Issue import Issue

from orchestrator import config
from orchestrator.github import issues as _issues
from orchestrator.workflow import (
    label_reading as _label_reading,
    state as _workflow_state,
    transition_guard as _transition_guard,
)

log = logging.getLogger("orchestrator.github")

# How GitHub answers the removal of a label the issue no longer carries.
_NOT_FOUND = 404


def move_workflow_label(client: Any, issue: Issue, new_label: str) -> None:
    """Put `issue` on `new_label`, adding it and then taking off the workflow labels it replaces, one by one.

    The labels taken off are the current workflow labels the reading `issue`
    carries; every other label stays, applied before that reading or after
    it. The new label is coerced and the edge guarded first, so a label that
    is not canonical, or an edge the graph refuses under `enforce`, raises
    before a request leaves.
    """
    new_workflow_label = _label_reading.coerce_workflow_label(new_label)
    _transition_guard.guard_transition(
        client.workflow_label(issue), new_workflow_label, config.WORKFLOW_TRANSITION_GUARD,
    )
    label_names = [issue_label.name for issue_label in issue.labels]
    replaced = _label_reading.replaced_label_names(label_names) - {new_workflow_label}
    issue.add_to_labels(str(new_workflow_label))
    for name in sorted(replaced):
        _taken_off(issue, name)
    kept = [carried for carried in label_names if carried not in replaced and carried != new_workflow_label]
    _issues._cache_written_labels(issue, [*kept, new_workflow_label])
    client._emit_stage_enter(issue, _workflow_state.stage_name(new_workflow_label))


def _taken_off(issue: Issue, name: str) -> None:
    """Take one label off the issue, a label somebody took off first answering as gone.

    GitHub answers that removal 404 with a message of its own ("Label does
    not exist") rather than the one PyGithub types as an unknown object, so
    the status is what is read. Any other refusal raises.
    """
    try:
        issue.remove_from_labels(name)
    except GithubException as refused:
        if refused.status != _NOT_FOUND:
            raise
        log.info("issue=#%s no longer carried %r when its relabel took it off", issue.number, name)


class GitHubLabelMoveMixin(_issues.GitHubIssueMixin):
    """The relabel that keeps every label it does not move, a link in the issue chain beside the whole-set write."""

    move_workflow_label = move_workflow_label
