# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Classify how far a rebase's exemption transfer reached.

The bounded handoff vocabulary distinguishes missing, outstanding,
settled, and unprovable claims. Reading a workflow authorization phase
waits for the call that needs that higher-layer record.
"""
from __future__ import annotations

from enum import StrEnum


class _Handoff(StrEnum):
    """How far the exemption an interrupted rebase was carrying got."""

    NOTHING = "nothing"
    UNRECORDED = "unrecorded"
    OUTSTANDING = "outstanding"
    SETTLED = "settled"
    UNVOUCHED = "unvouched"


def _is_settled(authorization) -> bool:
    """Whether this record says the receipt behind its push has landed."""
    from orchestrator.workflow.late_split import (
        rewrite_values as _rewrite_values,
    )
    return authorization.phase == _rewrite_values.LateRewritePhase.PUBLISHED
