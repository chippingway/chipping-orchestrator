# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Stateless helpers shared by the in-memory GitHub models."""
from __future__ import annotations

from typing import Any

from orchestrator.github.issues import (
    CLEANUP_ROUTE_LABELS,
    CLOSED_SWEEP_LABELS,
)
from orchestrator.workflow.label_reading import label_for_name

_CLOSED_SWEEP_LABELS = frozenset(CLOSED_SWEEP_LABELS + CLEANUP_ROUTE_LABELS)


def _copy_issue_comments(issue: Any) -> list[Any]:
    return list(issue.comments)


def _has_closed_sweep_label(issue: Any) -> bool:
    """Whether a closed issue is one the real sweep would still surface.

    Matched by the member each label name resolves to, so a pre-namespace
    spelling counts -- the real sweep queries both spellings for exactly the
    issues no other pass would revisit. Both label groups the real sweep walks
    are here, since it walks them as one pass on one cadence.
    """
    return any(
        label_for_name(label.name) in _CLOSED_SWEEP_LABELS
        for label in issue.labels
    )


def _review_has_feedback(review: Any) -> bool:
    return (
        (review.state or "").upper() in {"CHANGES_REQUESTED", "COMMENTED"}
        and bool((review.body or "").strip())
    )
