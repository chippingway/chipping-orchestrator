# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The hermetic patch set one stage handler runs inside, and where it lands."""
from __future__ import annotations

import contextlib
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.agents import runner as _agent_runner
from orchestrator.git.worktrees import evidence as _worktree_evidence
from orchestrator.observability.analytics import settings as analytics_settings
from tests.workflow.git_owners import GIT_SEAM_OWNERS
from tests.workflow.patch_builders import _build_workflow_mocks
from tests.workflow.patch_models import _WorkflowRunContext

_RUN_AGENT = "run_agent"

_CHECKOUT_IDENTITY = "_checkout_identity"

# The module every mocked name is defined on: the git seams, plus the spawn,
# whose owner is the one non-git module in the set, and the checkout's
# ownership read, which every road that works in a checkout already standing
# at the issue's path asks first and which no case here can answer from a
# real worktree. A stage imports the owner it borrows from, so a mock anywhere
# else would let the real command run -- which is why a name missing here
# raises rather than falling back to a second module.
_SEAM_OWNERS = MappingProxyType({
    **GIT_SEAM_OWNERS,
    _RUN_AGENT: _agent_runner,
    _CHECKOUT_IDENTITY: _worktree_evidence,
})


def _enter_mock(stack, attribute: str, attribute_mock) -> None:
    """Install one mock on the module its callers resolve it off."""
    stack.enter_context(
        patch.object(_SEAM_OWNERS[attribute], attribute, attribute_mock),
    )


def _patch_and_run(callable_, context: _WorkflowRunContext):
    workflow_mocks = _build_workflow_mocks(context)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(
            analytics_settings,
            "ANALYTICS_LOG_PATH",
            context.analytics_log_path,
        ))
        stack.enter_context(patch.object(
            analytics_settings,
            "TRAJECTORY_LOG_PATH",
            context.trajectory_log_path,
        ))
        for attribute, attribute_mock in workflow_mocks.items():
            _enter_mock(stack, attribute, attribute_mock)
        callable_()
    return workflow_mocks
