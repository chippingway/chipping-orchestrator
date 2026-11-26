# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an implementing developer's conversation was grounded on, carried to the task snapshots of its continuations.

A task snapshot names the requirements the conversation that wrote it was
handed. A fresh conversation is handed its prompt's: the road's own, or, on an
`/orchestrator continue` retry that re-grounds a replacement session, the read
of the issue its preamble quoted -- an edit beside the command included -- while
the baseline the issue records (`user_content_hash`), which stamps the retry's
report, stays where it was, the edit owed to the drift road. A resumed
conversation is handed nothing new, so it still holds what it was grounded on,
which nothing on the issue says once that differs from the baseline.

So where an attempt's conversation was handed something other than the
baseline, the pinned state keeps that beside it (`task_snapshot_grounding`):
the conversation, the requirements it was handed, and the baseline the issue
recorded then. A later attempt resuming that same conversation is bound to the
same requirements while the record still speaks for it; another conversation,
or a baseline a road has since settled -- handing the developer the
requirements it settles -- leaves it saying nothing, and the attempt is bound
to what its road hands it. A record lost with a held tick, or one no reading
can parse, is the same nothing.

Only a task snapshot reads it. It decides nothing, and it is written with the
tick's own state, never by a write of its own.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import prompt_delivery as _prompt_delivery

GROUNDING = "task_snapshot_grounding"

_SESSION = "session_id"

_REQUIREMENTS = "requirements"

_BASELINE = "baseline"


def handed(
    state: PinnedState, resumed: str | None, fresh_requirements: str | None, road_requirements: str,
) -> str:
    """The requirements an attempt's conversation was handed.

    A fresh conversation (`resumed` None) is handed its prompt's:
    `fresh_requirements` where the road re-grounds one apart from its
    handoff, the road's own otherwise. A resumed one holds what it was
    grounded on where the record still speaks for it, and the road's own
    otherwise.
    """
    if resumed is None:
        return road_requirements if fresh_requirements is None else fresh_requirements
    return _grounded(state, resumed) or road_requirements


def remember(state: PinnedState, session_id: str | None, requirements: str) -> None:
    """Stage what `session_id` was handed where it is not the baseline the issue records; clear a record otherwise."""
    baseline = state.get(_prompt_delivery.PINNED_USER_CONTENT_HASH)
    if session_id and requirements and requirements != baseline:
        state.set(GROUNDING, {_SESSION: session_id, _REQUIREMENTS: requirements, _BASELINE: baseline})
    elif state.get(GROUNDING) is not None:
        state.set(GROUNDING, None)


def _grounded(state: PinnedState, resumed: str) -> str | None:
    """What the record says `resumed` was grounded on, where it still speaks for that conversation."""
    record = state.get(GROUNDING)
    if not isinstance(record, dict) or record.get(_SESSION) != resumed:
        return None
    if record.get(_BASELINE) != state.get(_prompt_delivery.PINNED_USER_CONTENT_HASH):
        return None
    requirements = record.get(_REQUIREMENTS)
    return requirements if isinstance(requirements, str) and requirements else None
