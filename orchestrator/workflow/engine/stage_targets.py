# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Declare label-to-handler targets and resolve stage owners only when called.

The engine names each defining module without binding the stage tree at
import time. Cleanup has its own target, and the unlabeled entry goes to
pickup through the same call-time resolution.
"""
from __future__ import annotations

import importlib
from collections.abc import Mapping
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.state import WorkflowLabel

_CONFLICTS_PACKAGE = "orchestrator.workflow.stages.conflicts"
_DECOMPOSITION_PACKAGE = "orchestrator.workflow.stages.decomposition"
_LATE_CANCELLATION_OWNER = f"{_DECOMPOSITION_PACKAGE}.late_cancellation"

_LATE_CLOSE_OBSERVATION_OWNER = f"{_DECOMPOSITION_PACKAGE}.late_close_observation"

_LATE_CLOSE_READING_OWNER = f"{_DECOMPOSITION_PACKAGE}.late_close_reading"
_LATE_RELABEL_OWNER = f"{_DECOMPOSITION_PACKAGE}.late_relabel"
_LATE_RESTART_OWNER = f"{_DECOMPOSITION_PACKAGE}.late_restart"
_LATE_REUSE_OWNER = f"{_DECOMPOSITION_PACKAGE}.late_reuse"
_DISCUSSION_PACKAGE = "orchestrator.workflow.stages.discussion"
_DOCUMENTING_PACKAGE = "orchestrator.workflow.stages.documenting"
_FIXING_PACKAGE = "orchestrator.workflow.stages.fixing"
_IMPLEMENTING_PACKAGE = "orchestrator.workflow.stages.implementing"
_LATE_RECONCILE_OWNER = f"{_IMPLEMENTING_PACKAGE}.late_reconcile"

# The owner that tells the `discussion` stage's plan from a delivery, read
# through rather than re-derived so what counts as a plan is decided once.
_IMPLEMENTING_HANDLER_OWNER = f"{_IMPLEMENTING_PACKAGE}.handler"
_IN_REVIEW_PACKAGE = "orchestrator.workflow.stages.in_review"
_QUESTION_PACKAGE = "orchestrator.workflow.stages.question"
_VALIDATING_PACKAGE = "orchestrator.workflow.stages.validating"

# The one handler a label does not choose. It is reached by being closed on a
# cleanup-swept label instead, and it is deliberately not in the table below:
# an entry there would make it the handler for those labels open or closed.
_CLEANUP_SWEEP_TARGET = (
    f"{_DECOMPOSITION_PACKAGE}.late_sweep", "_handle_closed_owner_cleanup",
)

# Keyed by the member rather than the label string so the table cannot drift
# from the vocabulary it routes: a relabeled state is a lookup miss here, and a
# lookup miss is an issue nobody handles.
_STAGE_HANDLER_TARGETS: Mapping[str | None, tuple[str, str]] = MappingProxyType({
    None: ("orchestrator.workflow.engine.pickup", "_handle_pickup"),
    WorkflowLabel.DECOMPOSING: (f"{_DECOMPOSITION_PACKAGE}.run", "_handle_decomposing"),
    WorkflowLabel.READY: (f"{_DECOMPOSITION_PACKAGE}.blocked", "_handle_ready"),
    WorkflowLabel.BLOCKED: (f"{_DECOMPOSITION_PACKAGE}.blocked", "_handle_blocked"),
    WorkflowLabel.UMBRELLA: (f"{_DECOMPOSITION_PACKAGE}.umbrella", "_handle_umbrella"),
    WorkflowLabel.IMPLEMENTING: (f"{_IMPLEMENTING_PACKAGE}.handler", "_handle_implementing"),
    WorkflowLabel.DOCUMENTING: (f"{_DOCUMENTING_PACKAGE}.handler", "_handle_documenting"),
    WorkflowLabel.VALIDATING: (f"{_VALIDATING_PACKAGE}.handler", "_handle_validating"),
    WorkflowLabel.IN_REVIEW: (f"{_IN_REVIEW_PACKAGE}.handler", "_handle_in_review"),
    WorkflowLabel.FIXING: (f"{_FIXING_PACKAGE}.handler", "_handle_fixing"),
    WorkflowLabel.RESOLVING_CONFLICT: (
        f"{_CONFLICTS_PACKAGE}.handler", "_handle_resolving_conflict",
    ),
    WorkflowLabel.QUESTION: (f"{_QUESTION_PACKAGE}.handler", "_handle_question"),
    WorkflowLabel.DISCUSSION: (f"{_DISCUSSION_PACKAGE}.handler", "_handle_discussion"),
})


def _call_handler(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    target: tuple[str, str],
) -> None:
    """Import the module a target names and run the handler off it."""
    module_name, handler_name = target
    issue_handler = getattr(importlib.import_module(module_name), handler_name)
    issue_handler(gh, spec, issue)
