# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether an issue is live work that verification evidence may be settled for.

Asked twice about one transaction, of two readings of the issue. The
dispatcher's reconciliation asks it of the issue it routed, before anything is
read or posted; the settlement asks it again of the issue read afresh after
the artifact is posted, because a post is long enough for a human to close
the issue, pause it, relabel it `done` or `rejected`, or take its workflow
label off -- and evidence declared current on an issue somebody has just
ended or paused is a write the label exists to prevent.

Every one of those stands aside rather than retiring anything, so a reopen, an
unpause, or a relabel finds the transaction exactly as it was.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github.issues import issue_is_closed
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.workflow.state import WorkflowLabel

# The labels whose whole meaning is that the issue is over. A terminal label
# resolves to no handler, so the no-op behind the dispatch guard protects
# nothing.
_TERMINAL_LABELS = (WorkflowLabel.DONE, WorkflowLabel.REJECTED)


def stands_aside(issue: Issue, label: str | None) -> bool:
    """Whether `issue`, carrying `label`, is anything but live work.

    Closed, labelled `done` or `rejected`, held by a hard-skip control label,
    or carrying no workflow label at all. The labels and the state are lazy
    reads on an issue fetched afresh, so a caller asking of one holds this
    under its own boundary.
    """
    if label is None or label in _TERMINAL_LABELS:
        return True
    return hard_skip_control_label(issue) is not None or issue_is_closed(issue)
