# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Validate workflow-label writes against the declared transition graph.

A repeated label is allowed. Off, warning, and enforcement modes preserve
their existing behavior and messages, and warnings use the literal
orchestrator.state_machine channel selected by operator filters.
"""
from __future__ import annotations

import logging

from orchestrator.workflow import transitions as _transitions
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.state_machine")



class IllegalTransition(Exception):
    """A workflow-label write is absent from ``ALLOWED_TRANSITIONS``."""


def is_allowed_transition(
    current: WorkflowLabel | None,
    new: WorkflowLabel,
) -> bool:
    """Return whether relabeling ``current`` to ``new`` is legal."""
    if current == new:
        return True
    return new in _transitions.ALLOWED_TRANSITIONS.get(current, frozenset())


def guard_transition(
    current: WorkflowLabel | None,
    new: WorkflowLabel,
    mode: str,
) -> None:
    """Warn or raise when a workflow-label write is illegal."""
    if mode == "off" or is_allowed_transition(current, new):
        return
    allowed = ", ".join(
        sorted(
            str(state)
            for state in _transitions.ALLOWED_TRANSITIONS.get(current, frozenset())
        ),
    )
    current_label = None if current is None else str(current)
    allowed_text = allowed or "(none -- terminal state)"
    detail = (
        "illegal workflow transition "
        f"{current_label!r} -> {str(new)!r}; "
        f"allowed from there: {allowed_text}"
    )
    if mode == "enforce":
        raise IllegalTransition(detail)
    log.warning("%s", detail)
