# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Resolve canonical workflow labels and enforce strict label inputs.

A workflow label is a current ``WorkflowLabel`` member or its exact wire
string, and nothing else names a state. A bare name such as ``ready`` or
``fixing`` is repository metadata like ``bug``: it routes nowhere, a relabel
leaves it on the issue, and coercion refuses it. A value that is not a string
names no state either, however it renders: every reading here goes through
`label_for_name`, which checks the value it is handed rather than its text. A
relabel removes only the current workflow labels. Coercion takes its label by
position or as ``label_name`` and by no other keyword.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from orchestrator.workflow.state import WorkflowLabel


def _canonical_label_names() -> Mapping[str, WorkflowLabel]:
    """Map each label the orchestrator writes to its member."""
    return MappingProxyType({str(member): member for member in WorkflowLabel})


CANONICAL_LABELS = _canonical_label_names()


def label_for_name(label_name: str | WorkflowLabel) -> WorkflowLabel | None:
    """Return the workflow member a GitHub label denotes, or None if it is not one.

    Only an exact canonical string resolves, a member being one. A value that
    is not a string is no label even when it renders as one: a path or any
    other object whose text reads `done` is not the terminal state. Which
    state an issue is actually IN, when it carries more than one, is
    `issue_workflow_label`'s question -- not this one's.
    """
    if not isinstance(label_name, str):
        return None
    return CANONICAL_LABELS.get(label_name)


def issue_workflow_label(
    label_names: Iterable[str],
) -> WorkflowLabel | None:
    """Return the workflow state one issue's labels put it in.

    The first canonical label in the order GitHub lists them: a write leaves
    at most one, so a second is a human edit, read past rather than refused.
    A bare name is no state however closely it matches one, so an issue
    carrying only `implementing` has no workflow label at all.
    """
    for name in label_names:
        resolved_label = label_for_name(name)
        if resolved_label is not None:
            return resolved_label
    return None


def replaced_label_names(label_names: Iterable[str]) -> frozenset[str]:
    """Return the labels a workflow-label write on this issue replaces.

    Every current workflow label on the issue, and nothing else. A control
    label, a name the repository picked for itself, and a bare name matching
    some state all stay -- the last even beside the canonical label of that
    same state -- because none of them is a workflow label this write owns.
    """
    return frozenset(
        name for name in label_names if label_for_name(name) is not None
    )


def coerce_workflow_label(label_name: str | WorkflowLabel) -> WorkflowLabel:
    """Return the workflow member for a canonical label or raise ``ValueError``."""
    resolved_label = label_for_name(label_name)
    if resolved_label is None:
        valid_labels = ", ".join(
            repr(str(member)) for member in WorkflowLabel
        )
        raise ValueError(
            f"{label_name!r} is not a valid workflow label; "
            f"expected one of: {valid_labels}",
        )
    return resolved_label
