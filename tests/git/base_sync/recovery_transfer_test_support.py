# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Comparisons, terminal mocks, and common values for replay recovery tests.
"""
from __future__ import annotations

import contextlib
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    outcomes,
    recovery_push as _recovery_push,
    replay_checkout_parks as _replay_checkout_parks,
    replay_publication_parks as _replay_publication_parks,
    replay_recovery as _replay_recovery,
    replay_transfer_parks as _replay_transfer_parks,
    transfers,
)
from orchestrator.git.measurement.models import FrozenCommit, MeasurementFailure
from orchestrator.git.verification import status as _worktree_status
from orchestrator.workflow.stages.implementing import (
    late_push as _push,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    transfers_test_support as seed,
)

RETRY_PUSH = "_retry_recovery_push"

UNVOUCHED = "_park_unvouched_recovery"

ANCHOR_KEY = "pending_auto_base_rebase_push_sha"

FOREIGN_PUBLICATION = "_park_foreign_publication_recovery"

ANNOUNCED = "_park_announced_recovery"

UNFINISHED = "_park_unfinished_recovery"

# Every terminal an unpublished checkout can select, on the owner it lives on.
_ANSWERS = MappingProxyType({
    FOREIGN_PUBLICATION: _replay_publication_parks,
    ANNOUNCED: _replay_checkout_parks,
    "_park_rolled_back_recovery": _replay_checkout_parks,
    UNVOUCHED: _replay_transfer_parks,
    "_park_unrecorded_recovery": _replay_checkout_parks,
    "_park_diverged_recovery": outcomes,
    "_reject_unknown_recovery_comparison": outcomes,
    RETRY_PUSH: _recovery_push,
})

# The one label this route's own finish writes, and one the base refresh does
# not drive that an operator can relabel onto.
_VALIDATING = WorkflowLabel.VALIDATING
_RESOLVING = WorkflowLabel.RESOLVING_CONFLICT

# A remote standing where the attempt's anchor says it left it, and one
# somebody else moved.
_ON_ANCHOR = seed.ACCEPTED_SHA
_MOVED = seed.FOREIGN_SHA

# A base the remote would not name, which is the half of the re-derived
# evidence no local reading can stand in for.
_NO_BASE = FrozenCommit(
    failure=MeasurementFailure.BASE_UNREADABLE, detail="no token",
)

_UNREADABLE_TREE = _worktree_status._WorktreeStatus(readable=False)


def _snapshot(
    remote_head: str = _ON_ANCHOR,
    local_head: str = seed.REPLAYED_SHA,
    **counts,
):
    """The comparison one recovery road is handed."""
    return fixtures._snapshot(
        local_head=local_head, remote_head=remote_head, **counts,
    )


def _pushed(**answer) -> _push._PushedCandidate:
    """What one gated publication answered, in the shape the retry reads."""
    return _push._PushedCandidate(**answer)


def _handled() -> MagicMock:
    """A collaborator stub that reports the tick as handled."""
    return MagicMock(return_value=True)


@contextlib.contextmanager
def _every_answer(selected: dict):
    """Patch every terminal the road can select, recording them by name."""
    with contextlib.ExitStack() as stack:
        for name, owner in _ANSWERS.items():
            selected[name] = _handled()
            stack.enter_context(patch.object(owner, name, selected[name]))
        yield


def _assert_selects(case, answer: str, completed=None) -> MagicMock:
    """Route one completed comparison and pin the single road it takes."""
    selected = {}
    completed = completed or _snapshot()
    with _every_answer(selected):
        case.assertTrue(_replay_recovery._route_an_unpublished_head(
            case.context, completed,
            transfers._carried_by(case.context, completed.head),
        ))
    taken = selected.pop(answer)
    taken.assert_called_once()
    for unselected in selected.values():
        unselected.assert_not_called()
    return taken
