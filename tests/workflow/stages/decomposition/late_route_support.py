# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One late owner, routed the way a tick routes it.

The subject of every case that reaches here is a guard that runs BEFORE a
label becomes a handler call, so the route has to be the real one: the
dispatcher's own, with the stage handler the label names held so that reaching
it is a visible failure rather than a live decomposer run.
"""
from __future__ import annotations

import functools
import importlib
from unittest.mock import Mock, patch

from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    stage_targets as _stage_targets,
)
from tests.workflow.stages.decomposition.late_cleanup_support import (
    RecordedDelete,
    SeededUmbrella,
    SnapshotOutcome,
    walk_owner,
)


def routed_owner(
    case,
    seeded: SeededUmbrella,
    label,
    remote: RecordedDelete = None,
) -> Mock:
    """Route this issue the way a tick does, holding its stage handler.

    Hands back the handler that was held, so a case says what it is about by
    asserting the handler was or was not reached.
    """
    module_name, handler_name = _stage_targets._STAGE_HANDLER_TARGETS[label]
    owner = importlib.import_module(module_name)
    dispatched = Mock()
    answers = remote or RecordedDelete(SnapshotOutcome.DELETED)
    with answers.answering(), patch.object(owner, handler_name, dispatched):
        walk_owner(case, seeded, functools.partial(
            _issue_processing._route_issue_to_handler, label=label,
        ))
    return dispatched
