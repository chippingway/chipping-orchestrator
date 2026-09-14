# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The workflow package API: one polling tick, the labels, and the guard.

What a caller outside the tree needs to drive the state machine or reason about
it is named here explicitly and nowhere else: the per-repo tick, the two label
vocabularies a GitHub issue carries, and the transition guard together with the
predicate under it and the exception an illegal write raises. The five past the
tick are the `state` owner's own objects, re-exported rather than rebuilt, so
the graph an out-of-tree caller reads cannot fork from the one every in-tree
caller names on that owner. Everything past this surface belongs to the owner
that defines it -- `workflow/engine/` for the tick's collaborators,
`workflow/stages/` for the per-label handlers -- and is reached by importing
that owner, so a patch aimed at one lands where the call site reads it.

`tick` resolves the engine inside the call. The GitHub and git layers below the
engine import `workflow/state.py` for the label vocabulary they are typed by,
and a submodule import runs this initializer first, so an engine import at
module scope would route those layers straight back into the GitHub and git
modules they are still initializing.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.workflow.state import (
    ControlLabel,
    IllegalTransition,
    WorkflowLabel,
    guard_transition,
    is_allowed_transition,
)

if TYPE_CHECKING:
    import threading

    from orchestrator import config
    from orchestrator.github.client import GitHubClient
    from orchestrator.scheduler.service import IssueScheduler

__all__ = (
    "ControlLabel",
    "IllegalTransition",
    "WorkflowLabel",
    "guard_transition",
    "is_allowed_transition",
    "tick",
)


def tick(
    gh: GitHubClient,
    spec: config.RepoSpec,
    *,
    global_semaphore: threading.BoundedSemaphore | None = None,
    scheduler: IssueScheduler | None = None,
) -> None:
    """Drive a single polling tick for one repo.

    The pass order, the scheduler / in-tick split, and the sequential width
    behind it -- per-issue isolation included -- are
    `workflow/engine/tick.py`; the bounded pool the other width runs on, and
    the isolation inside that one, are `workflow/engine/parallel.py` beside
    it. A test that has to intercept any of them patches the owner it is
    defined on.
    """
    from orchestrator.workflow.engine import tick as _engine_tick

    _engine_tick.tick(
        gh, spec, global_semaphore=global_semaphore, scheduler=scheduler,
    )
