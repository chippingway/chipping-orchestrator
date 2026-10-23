# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Stateless helpers shared by the in-memory GitHub models."""
from __future__ import annotations

from typing import Any

from orchestrator.github.issue_polling import SWEEP_LABELS

_SWEPT_LABEL_NAMES = frozenset(str(sweep_label) for sweep_label in SWEEP_LABELS)


def _copy_issue_comments(issue: Any) -> list[Any]:
    return list(issue.comments)


def _has_closed_sweep_label(issue: Any) -> bool:
    """Whether a closed issue is one the real sweep would still surface.

    Matched on the exact canonical names the real sweep queries, a subset of
    the workflow labels routing resolves: a closed issue on any other label,
    an obsolete bare name included, is not swept. Both label groups the real
    sweep walks are here, since it walks them as one pass on one cadence.
    """
    return any(label.name in _SWEPT_LABEL_NAMES for label in issue.labels)


def _review_has_feedback(review: Any) -> bool:
    return (
        (review.state or "").upper() in {"CHANGES_REQUESTED", "COMMENTED"}
        and bool((review.body or "").strip())
    )
