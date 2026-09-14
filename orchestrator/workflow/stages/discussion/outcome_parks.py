# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The endings that report what the agent run itself produced.

Nothing here reads the tree or the branch: a round that wrote is settled by the
checkout and publication owners beside this one, and what is left over is what
the backend handed back -- a run that ran out of time, one that returned with
nothing to say, and the analysis a finished round posts for the humans to
answer by number. The last of those is the stage's ordinary ending rather than
a failure, and it parks for the same reason all of them do: the next move is a
human's, and the reason prefix is what tells the next tick so.
"""
from __future__ import annotations

import logging

from orchestrator.agents.models import AgentResult
from orchestrator.config import settings as config
from orchestrator.workflow.engine import agent_diagnostics as _agent_diagnostics, messages as _messages
from orchestrator.workflow.stages.discussion import (
    models as _models,
    parks as _parks,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _park_timed_out_discussion(run: _models._DiscussionRun) -> None:
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} discussion agent timed out "
        f"after {config.AGENT_TIMEOUT}s; manual intervention "
        "needed. The per-issue worktree is left intact for inspection.",
        reason=_state._DISCUSSION_TIMEOUT,
    )


def _park_silent_discussion(
    run: _models._DiscussionRun, discussion_result: AgentResult,
) -> None:
    # A round of this stage is either a first spawn or a resume of the pinned
    # session, and the stderr tail is what tells an operator which one went
    # quiet -- so the message names neither rather than sending them looking
    # for a session that may never have been asked for.
    diagnostics = _agent_diagnostics._format_stderr_diagnostics(
        discussion_result, "Discussion agent",
    )
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} discussion agent produced no output (the "
        "backend exited without writing a response); manual intervention "
        f"needed.{diagnostics}",
        reason=_state._DISCUSSION_SILENT,
    )
    log.warning(
        "issue=#%s discussion agent produced no output; "
        "exit_code=%d timed_out=%s stderr_tail=%r",
        run.issue.number,
        discussion_result.exit_code,
        discussion_result.timed_out,
        _agent_diagnostics._stderr_log_tail(discussion_result),
    )


def _park_discussion_response(
    run: _models._DiscussionRun, response: str,
) -> None:
    _parks._park_discussion(
        run,
        f"{config.HITL_MENTIONS} discussion agent opened the design "
        f"discussion:\n\n{_messages._as_blockquote(response)}",
        reason=_state._DISCUSSION_RESPONSE,
    )
