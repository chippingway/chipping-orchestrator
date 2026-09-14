# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Typed recording requests and the keyword signatures callers bind through.

One owner for what a recorder is asked to write and what it carries while
writing it: the signature each of the three argument-bound event families is
reached through, the request the two renaming ones bind into, the inputs one
completed tracked agent run is summarized from, and the two optional groups an
`agent_exit` folds in when the run offered them.

The signatures are declared rather than written as parameter lists because the
recorders they belong to are what a caller reaches, and the caller's spelling
is the contract: `result=` is the keyword every producer passes, while the
field it lands in is named for what it holds. Binding through
`inspect.Signature` keeps both -- the arity, the keyword-only rule, and the
`TypeError` a missing argument raises stay exactly what a plain `def` would
give, and the rename happens once, here, instead of at every call site.

A catalog record renames nothing, so it declares a signature and no request:
what a caller's keywords bind to is already the extras the record carries, and
the field list stays free to grow without a producer's keywords moving.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from orchestrator.agents.models import AgentResult


ISSUE_FIELD = "issue"
RESULT_FIELD = "result"


@dataclass(frozen=True)
class StageEvaluationRequest:
    repo: str
    issue: int
    stage: str | None
    duration_s: float
    evaluation_result: str


@dataclass(frozen=True)
class AgentExitContext:
    """Inputs that describe one completed tracked agent run."""

    repo: str
    issue: int
    stage: str
    agent_role: str
    backend: str
    agent_spec: str | None
    resume_session_id: str | None
    agent_result: AgentResult
    duration_s: float
    review_round: int | None
    retry_count: int | None
    fallback_model: str | None
    prompt: str | None
    cwd: Path | None


@dataclass
class CodexCatalog:
    """Out-of-band capabilities missing from Codex's JSON stream.

    `available_skills` and `skill_levels` are two projections of one scan, so
    they are filled together or not at all -- a level is only ever reported
    for a name the same enumeration produced.
    """

    available_skills: list[str] | None = None
    skill_levels: dict[str, str] | None = None
    tools: list[str] | None = None


@dataclass(frozen=True)
class AgentExitSkillFields:
    """Normalized optional skill fields for an `agent_exit` event.

    `skills_evidence` maps each triggered name to why it counts as a load
    (`confirmed` / `inferred`); `skills_incidental` / `skills_incidental_count`
    carry the path-only references the run made without loading a skill.
    `skill_levels` maps each offered name to the source level that defined it
    (`project` / `user` / `harness`), and rides beside `skills_available`
    rather than reshaping it, so a reader that knows only the names array is
    unaffected. All are dropped (their key absent) when empty, so a run with
    nothing to report keeps today's record shape.
    """

    skills_triggered: list[str] | None = None
    skills_triggered_count: int | None = None
    skills_available: list[str] | None = None
    skill_levels: dict[str, str] | None = None
    skills_evidence: dict[str, str] | None = None
    skills_incidental: list[str] | None = None
    skills_incidental_count: int | None = None


def _parameter(
    name: str,
    default: Any = inspect.Parameter.empty,
) -> inspect.Parameter:
    return inspect.Parameter(
        name,
        inspect.Parameter.KEYWORD_ONLY,
        default=default,
    )


STAGE_EVALUATION_SIGNATURE = inspect.Signature(
    (
        _parameter("repo"),
        _parameter(ISSUE_FIELD),
        _parameter("stage"),
        _parameter("duration_s"),
        _parameter(RESULT_FIELD),
    )
)
REPO_SKILL_CATALOG_SIGNATURE = inspect.Signature(
    (
        _parameter("repo"),
        _parameter("base_branch"),
        _parameter("remote_name"),
        _parameter("skills_available"),
        _parameter("skill_paths", None),
        _parameter("skill_levels", None),
    )
)
AGENT_EXIT_SIGNATURE = inspect.Signature(
    (
        _parameter("repo"),
        _parameter(ISSUE_FIELD),
        _parameter("stage"),
        _parameter("agent_role"),
        _parameter("backend"),
        _parameter("agent_spec"),
        _parameter("resume_session_id"),
        _parameter(RESULT_FIELD),
        _parameter("duration_s"),
        _parameter("review_round"),
        _parameter("retry_count"),
        _parameter("fallback_model", None),
        _parameter("prompt", None),
        _parameter("cwd", None),
    )
)


def bind_stage_evaluation(
    positional_fields: tuple[Any, ...],
    keyword_fields: dict[str, Any],
) -> StageEvaluationRequest:
    bound_fields = STAGE_EVALUATION_SIGNATURE.bind(
        *positional_fields,
        **keyword_fields,
    )
    bound_values = dict(bound_fields.arguments)
    bound_values["evaluation_result"] = bound_values.pop(RESULT_FIELD)
    bound_values[ISSUE_FIELD] = int(bound_values[ISSUE_FIELD])
    return StageEvaluationRequest(**bound_values)


def bind_agent_exit(
    positional_fields: tuple[Any, ...],
    keyword_fields: dict[str, Any],
) -> AgentExitContext:
    bound_fields = AGENT_EXIT_SIGNATURE.bind(
        *positional_fields,
        **keyword_fields,
    )
    bound_fields.apply_defaults()
    bound_values = dict(bound_fields.arguments)
    bound_values["agent_result"] = bound_values.pop(RESULT_FIELD)
    bound_values[ISSUE_FIELD] = int(bound_values[ISSUE_FIELD])
    return AgentExitContext(**bound_values)
