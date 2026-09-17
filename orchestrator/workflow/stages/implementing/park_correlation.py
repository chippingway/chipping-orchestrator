# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a park that emits for itself reports beside its reason.

The question park and the two checkout refusals emit `park_awaiting_human`
themselves: each owns a watermark read and durable state writes the shared
funnel in `workflow/engine/guards.py` does not, so neither can hand its notice
to that funnel and pick up a payload on the way through. What keeps their
records the same shape as a funnelled one is this owner instead, and the
allow-list it screens through is the funnel's own.

Every reported field is a structured identifier the caller already holds: the
route named on the `_ParkedRun` it was given, the session the backend handed
back, the exit status of the process, and the counters pinned state carries.
No part of what the agent wrote reaches one. The park's `reason` is decided
before this is called -- and the question park does read the final message to
decide it -- but the reason arrives here already reduced to a closed
vocabulary, while a payload assembled out of a completion message would carry
the transcript itself into the audit log and the analytics sink both.
"""
from __future__ import annotations

from typing import Any

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.implementing import state as _state

# Every road that reaches these parks runs or resumes the dev session -- the
# docs pass included, which is why it is not a role of its own here.
_DEVELOPER_ROLE = "developer"


def _correlated_fields(
    state: PinnedState, parked: _guards._ParkedRun, **extra: Any,
) -> dict[str, Any]:
    """The bounded payload one of these parks reports beside its reason.

    `exit_code` rides on every one of them because it is what separates a run
    that finished and asked something from one that died without saying
    anything -- the distinction the question park is built around, and the one
    an operator counting silent failures needs the record to carry.

    A `None` here is a field the issue has never held; both sinks drop it,
    which is why a park on an issue with no pull request yet reports no
    `pr_number` rather than a null one.
    """
    return _guards._screened_correlation({
        "route": parked.route,
        "agent_role": _DEVELOPER_ROLE,
        "session_id": parked.agent_result.session_id,
        "exit_code": parked.agent_result.exit_code,
        "conflict_round": parked.conflict_round,
        "retry_count": _guards._safe_int(state.get(_state._RETRY_COUNT)),
        "pr_number": _guards._safe_int(state.get(_state._PR_NUMBER)),
        **extra,
    })
