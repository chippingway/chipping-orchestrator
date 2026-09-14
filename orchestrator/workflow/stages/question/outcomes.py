# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finished question run left behind, in the order that matters.

The live pause comes first and writes nothing, because every mutation below it
-- the timestamp, the usage fold, the session id already retained -- has to
replay identically on the next active tick. Then the timeout, which keeps its
worktree: a killed run may have been mid-edit.

Everything after that is the read-only contract. New commits and a dirty tree
are inspected BEFORE interruption and before the answer, so a run that wrote
despite the prompt parks on what it wrote rather than on what it said -- an
operator needs the tree to look at, and the implementing stage's relabel guard
needs the `question_*` reason to refuse shipping those changes as dev work. Only
a clean tree gets to be an answer, and an empty message on a clean tree is a
backend failure wearing an answer's clothes, which is why that park is the one
carrying stderr diagnostics.

A launch that never became a process is the exception to that ordering, and it
comes before even the pause. There is no tree reading it can be blamed for: a
checkout dirty from some earlier run is not its doing, and a `question_dirty`
park in its name would overwrite the durable park the refusal itself took.

Assessment and routing are split because the park has to be selected before any
of it is published: the cleanup policy the outcome carries is applied by the
caller first, so an exception while posting the park comment still leaves the
right tree on disk.
"""
from __future__ import annotations

import logging

from orchestrator.agents.models import AgentResult
from orchestrator.config import settings as config
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import creation as _worktree_creation, paths as _worktree_paths
from orchestrator.workflow.engine import (
    agent_diagnostics as _agent_diagnostics,
    guards as _guards,
    issue_usage as _issue_usage,
    usage as _usage,
)
from orchestrator.workflow.stages.question import models as _models, run as _run, state as _state

log = logging.getLogger("orchestrator.workflow")


def _assess_question_outcome(
    run: _models._QuestionRun, question_result: AgentResult,
) -> _models._QuestionOutcome:
    """Inspect a completed agent run in the stage's required order."""
    # A launch that never reached a process is declined ahead of everything,
    # because everything below reads a worktree or a message for what THIS run
    # left -- and it left nothing. The refusal has already been recorded
    # wherever it was decided.
    if _guards._ignore_if_never_invoked(run.issue, question_result):
        return _models._QuestionOutcome(None, run.keep_worktree)

    # A live pause must leave every in-memory session and watermark mutation
    # unpersisted so the next active tick can replay the same durable state.
    if _guards._paused_during_agent_run(run.gh, run.issue):
        return _models._QuestionOutcome(None, run.keep_worktree)

    run.state.set("last_question_at", _usage._now_iso())
    if not question_result.interrupted:
        _issue_usage._accumulate_issue_usage(run.state, question_result.usage)

    if question_result.timed_out:
        return _models._QuestionOutcome(_state._QUESTION_TIMEOUT, True)

    return _assess_question_worktree(run, question_result)


def _assess_question_worktree(
    run: _models._QuestionRun, question_result: AgentResult,
) -> _models._QuestionOutcome:
    """Classify a completed, non-timeout run from its worktree and answer.

    Read-only violations (new commits / dirty tree) take precedence over
    interruption so a killed run that changed the tree still leaves an
    inspection target for the operator.
    """
    worktree = _worktree_paths._worktree_path(run.spec, run.issue.number)
    if _worktree_creation._has_new_commits(run.spec, worktree):
        return _models._QuestionOutcome(_state._QUESTION_COMMITS, True)

    dirty_files = tuple(
        _worktree_status._worktree_dirty_files(worktree),
    )
    if dirty_files:
        return _models._QuestionOutcome(
            _state._QUESTION_DIRTY, True, dirty_files=dirty_files,
        )

    if _guards._ignore_if_interrupted(run.issue, question_result):
        return _models._QuestionOutcome(None, run.keep_worktree)

    answer = (question_result.last_message or "").strip()
    if answer:
        return _models._QuestionOutcome(
            _state._QUESTION_ANSWER, False, answer=answer,
        )
    return _models._QuestionOutcome(_state._QUESTION_SILENT, False)


def _park_dirty_question(
    run: _models._QuestionRun, dirty_files: tuple[str, ...],
) -> None:
    shown_files = dirty_files[:10]
    display_lines = [f"- `{file_path}`" for file_path in shown_files]
    hidden_count = len(dirty_files) - len(shown_files)
    if hidden_count:
        display_lines.append(f"- ... ({hidden_count} more)")
    files_markdown = "\n".join(display_lines)
    _run._park_question(
        run,
        f"{config.HITL_MENTIONS} question agent left "
        f"{len(dirty_files)} uncommitted change(s) but this stage "
        "is read-only; refusing to push. Reset the worktree "
        f"before resuming.\n\n{files_markdown}",
        reason=_state._QUESTION_DIRTY,
    )


def _park_silent_question(
    run: _models._QuestionRun, question_result: AgentResult,
) -> None:
    diagnostics = _agent_diagnostics._format_stderr_diagnostics(
        question_result, "Question agent",
    )
    _run._park_question(
        run,
        f"{config.HITL_MENTIONS} question agent produced no "
        "output (likely a session-resume failure); manual "
        f"intervention needed.{diagnostics}",
        reason=_state._QUESTION_SILENT,
    )
    log.warning(
        "issue=#%s question agent produced no output; "
        "exit_code=%d timed_out=%s stderr_tail=%r",
        run.issue.number,
        question_result.exit_code,
        question_result.timed_out,
        _agent_diagnostics._stderr_log_tail(question_result),
    )


def _park_answered_question(run: _models._QuestionRun, answer: str) -> None:
    quoted_lines = answer.replace("\n", "\n> ")
    quoted_answer = f"> {quoted_lines}"
    _run._park_question(
        run,
        f"{config.HITL_MENTIONS} question agent responded:\n\n"
        f"{quoted_answer}",
        reason=_state._QUESTION_ANSWER,
    )


def _route_question_outcome(
    run: _models._QuestionRun,
    question_result: AgentResult,
    outcome: _models._QuestionOutcome,
) -> None:
    """Persist the park selected by `_assess_question_outcome`."""
    if outcome.park_reason == _state._QUESTION_TIMEOUT:
        _run._park_question(
            run,
            f"{config.HITL_MENTIONS} question agent timed out "
            f"after {config.AGENT_TIMEOUT}s; manual intervention "
            "needed. The per-issue worktree is left intact for inspection.",
            reason=_state._QUESTION_TIMEOUT,
        )
        return
    if outcome.park_reason == _state._QUESTION_COMMITS:
        _run._park_question(
            run,
            f"{config.HITL_MENTIONS} question agent committed in "
            "the worktree but this stage is read-only; refusing "
            "to push. Reset the worktree before resuming.",
            reason=_state._QUESTION_COMMITS,
        )
        return
    if outcome.park_reason == _state._QUESTION_DIRTY:
        _park_dirty_question(run, outcome.dirty_files)
        return
    if outcome.park_reason == _state._QUESTION_SILENT:
        _park_silent_question(run, question_result)
        return
    _park_answered_question(run, outcome.answer)
