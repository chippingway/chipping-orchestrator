# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Define the workflow and control label strings and their namespace boundary.

Live GitHub labels keep their exact wire values, and those values are the
whole vocabulary: a bare name that is not one of them is a repository label,
whatever state it resembles. Stage names strip the namespace for analytics,
audit events, and sessions.
"""
from __future__ import annotations

from enum import StrEnum

_LABEL_NAMESPACE = "workflow:"


class WorkflowLabel(StrEnum):
    """Workflow states whose values are the GitHub label strings."""

    DECOMPOSING = "workflow:decomposing"
    READY = "workflow:ready"
    BLOCKED = "workflow:blocked"
    UMBRELLA = "workflow:umbrella"
    IMPLEMENTING = "workflow:implementing"
    VALIDATING = "workflow:validating"
    DOCUMENTING = "workflow:documenting"
    IN_REVIEW = "in_review"
    FIXING = "workflow:fixing"
    RESOLVING_CONFLICT = "workflow:resolving_conflict"
    QUESTION = "question"
    DISCUSSION = "discussion"
    DONE = "done"
    REJECTED = "rejected"


class ControlLabel(StrEnum):
    """Modifiers that coexist with a workflow state.

    These values gate or redirect processing while leaving the underlying
    ``WorkflowLabel`` intact. They never enter the workflow transition table.

    ``BACKLOG`` and ``PAUSED`` are the operator's own controls and keep their
    bare spelling for a human to type; ``COMMUNITY_CONTRIBUTION`` is written by
    the orchestrator's open-PR sweep, so it is namespaced with everything else
    the orchestrator applies.
    """

    BACKLOG = "backlog"
    PAUSED = "paused"
    COMMUNITY_CONTRIBUTION = "workflow:community_contribution"


def stage_name(label: str | WorkflowLabel | None) -> str | None:
    """Return the bare tag a workflow label names its state by.

    Analytics rows, audit event payloads, and the stage an agent session is
    attributed to are their own compatibility contract, independent of how the
    label is spelled on GitHub, so each of those sinks is handed the tag rather
    than the label carrying it.
    """
    if label is None:
        return None
    return str(label).removeprefix(_LABEL_NAMESPACE)
