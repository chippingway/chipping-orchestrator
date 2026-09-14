# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Resolve canonical and legacy workflow labels and enforce strict label inputs.

Canonical labels take precedence when both spellings appear. A relabel
removes only this workflow's current state. The ``label_name`` and ``value``
keywords share a strict parser; missing, duplicate, or unknown arguments
raise ``TypeError`` before label validation.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any

from orchestrator.workflow.state import WorkflowLabel, legacy_label_name

_MISSING_LABEL = object()


def _canonical_label_names() -> Mapping[str, WorkflowLabel]:
    """Map each label the orchestrator writes to its member."""
    return MappingProxyType({str(member): member for member in WorkflowLabel})


def _legacy_label_names() -> Mapping[str, WorkflowLabel]:
    """Map each pre-namespace spelling to the member that replaced it."""
    return MappingProxyType({
        legacy_name: member
        for member in WorkflowLabel
        for legacy_name in (legacy_label_name(member),)
        if legacy_name is not None
    })


CANONICAL_LABELS = _canonical_label_names()
LEGACY_LABELS = _legacy_label_names()


def label_for_name(label_name: str | WorkflowLabel) -> WorkflowLabel | None:
    """Return the workflow member a GitHub label denotes, or None if it is not one.

    Both spellings resolve, so an issue still carrying the pre-namespace label
    keeps routing. Which of the two an issue is actually IN, when it carries
    one of each, is `issue_workflow_label`'s question -- not this one's.
    """
    wanted_name = str(label_name)
    return CANONICAL_LABELS.get(wanted_name) or LEGACY_LABELS.get(wanted_name)


def issue_workflow_label(
    label_names: Iterable[str],
) -> WorkflowLabel | None:
    """Return the workflow state one issue's labels put it in.

    A namespaced label outranks a pre-namespace one no matter which order
    GitHub lists them in. The orchestrator only ever writes the namespaced
    spelling and strips the rest as it goes, so a bare tag sitting beside one
    is never the current state: it is a leftover the migration has not reached,
    or a name the repository uses for something of its own. Reading it as the
    state would route the issue to the wrong handler.
    """
    names = list(label_names)
    for lookup in (CANONICAL_LABELS, LEGACY_LABELS):
        for name in names:
            resolved_label = lookup.get(name)
            if resolved_label is not None:
                return resolved_label
    return None


def replaced_label_names(label_names: Iterable[str]) -> frozenset[str]:
    """Return the labels a workflow-label write on this issue replaces.

    Always the namespaced ones -- those are the orchestrator's own. A bare tag
    joins them when it names a state being replaced anyway: either because the
    namespaced spelling of that same state is on the issue beside it (one
    state, two spellings, and the migration exists to end that), or because
    the issue carries no namespaced label at all and the bare one is therefore
    its pre-migration state.

    What survives is a bare tag naming some OTHER state than the one being
    replaced, on an issue that already has its state namespaced. Nothing the
    orchestrator wrote could have left that behind, so it belongs to the
    repository and is not this write's to delete.
    """
    names = list(label_names)
    canonical = {name for name in names if name in CANONICAL_LABELS}
    if not canonical:
        return frozenset(name for name in names if name in LEGACY_LABELS)
    replaced_states = {CANONICAL_LABELS[name] for name in canonical}
    return frozenset(canonical | {
        name for name in names
        if LEGACY_LABELS.get(name) in replaced_states
    })


def coerce_label_name(label_name: str | WorkflowLabel) -> WorkflowLabel:
    """Return the workflow member for a wire label or raise ``ValueError``."""
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


def coerce_workflow_label(
    label_name: str | WorkflowLabel | object = _MISSING_LABEL,
    **legacy_fields: Any,
) -> WorkflowLabel:
    """Coerce a workflow label supplied as ``label_name`` or ``value=``.

    Exactly one label argument is required. Missing, duplicate, or unknown
    arguments raise ``TypeError`` before the typed label parser checks the
    supplied value.
    """
    legacy_label = legacy_fields.pop("value", _MISSING_LABEL)
    if legacy_fields:
        unexpected_name = next(iter(legacy_fields))
        raise TypeError(
            "coerce_workflow_label() got an unexpected keyword argument "
            f"{unexpected_name!r}",
        )
    if label_name is not _MISSING_LABEL and legacy_label is not _MISSING_LABEL:
        raise TypeError(
            "coerce_workflow_label() got multiple values for the label",
        )
    selected_label = legacy_label if label_name is _MISSING_LABEL else label_name
    if selected_label is _MISSING_LABEL:
        raise TypeError(
            "coerce_workflow_label() missing required argument: 'label_name'",
        )
    return coerce_label_name(selected_label)
