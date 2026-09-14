# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read frozen late-run records and recover their adjudication and resume identity.

Stored children pass manifest validation, stored agent specs stay locked,
and a session resumes only against the same candidate generation.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator import config
from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.late_split import (
    events as _events,
    formats as _formats,
    models as _late_models,
    payloads as _payloads,
)
from orchestrator.workflow.stages.decomposition import (
    validation as _split_validation,
)
from orchestrator.workflow.stages.decomposition.late_result_models import _DECOMPOSER_ROLE, _LateAdjudication, _LateRun

_LATE_AGENT_ROLE = "late_agent_role"
_LATE_AGENT = "late_agent"
_LATE_SESSION_ID = "late_session_id"
_LATE_RUN_CYCLE_ID = "late_run_cycle_id"
_LATE_SOURCE_SHA = "late_source_sha"
_LATE_RUN_GENERATION = "late_run_generation"
_LATE_RESULT_VERDICT = "late_result_verdict"
_LATE_RESULT_CATEGORY = "late_result_category"
_LATE_RESULT_QUESTION = "late_result_question"
_LATE_RESULT_SPLIT_BLOCKER = "late_result_split_blocker"
_LATE_RESULT_CHILDREN = "late_result_children"


def _read_late_run(state: _pinned_state.PinnedState) -> _LateRun:
    """Return the late run this issue is locked to, defaults where unset.

    Every field is read through the late domain's own defensive readers: a
    hand-edited or older value that cannot be typed reads back absent, so a
    damaged `late_result_verdict` leaves the run looking unanswered -- which
    costs one more adjudication -- rather than publishing on a verdict nobody
    recorded.
    """
    spec, backend, extra_args = _locked_spec(state)
    return _LateRun(
        role=_payloads.as_text(
            state.get(_LATE_AGENT_ROLE),
        ) or _DECOMPOSER_ROLE,
        session_id=_payloads.as_text(state.get(_LATE_SESSION_ID)),
        cycle_id=_payloads.as_identity(state.get(_LATE_RUN_CYCLE_ID)) or 0,
        source_sha=_payloads.as_hex(
            state.get(_LATE_SOURCE_SHA), _formats.COMMIT_LENGTHS,
        ) or "",
        generation=_payloads.as_count(state.get(_LATE_RUN_GENERATION)) or 0,
        verdict=_payloads.as_member(
            _late_models.LateVerdict, state.get(_LATE_RESULT_VERDICT),
        ),
        category=_payloads.as_member(
            _events.LateVerdictCategory, state.get(_LATE_RESULT_CATEGORY),
        ),
        question=_payloads.as_text(state.get(_LATE_RESULT_QUESTION)) or "",
        split_blocker=_payloads.as_text(
            state.get(_LATE_RESULT_SPLIT_BLOCKER),
        ) or "",
        children=_recorded_children(state),
        spec=spec,
        backend=backend,
        extra_args=extra_args,
    )


def _recorded_children(state: _pinned_state.PinnedState) -> tuple[dict, ...]:
    """Return the recorded child manifest, or nothing if it is not one.

    Held to the same rules the reply was: the child cap, the shape of each
    child, and the acyclicity of the graph they declare. A manifest a hand
    edit or an older binary left in a shape this validator refuses is not one
    children may be created from, and reading it back as empty is what sends
    the adjudicator round again instead of creating half of a split.
    """
    recorded = state.get(_LATE_RESULT_CHILDREN)
    if not isinstance(recorded, list) or not recorded:
        return ()
    if _split_validation._split_manifest_error({"children": recorded}):
        return ()
    return tuple(recorded)


def _locked_spec(
    state: _pinned_state.PinnedState,
) -> tuple[str, str, tuple[str, ...]]:
    """Return the agent spec a late run is locked to, or the configured one.

    A legacy bare-backend value (`"codex"` / `"claude"`) re-parses to
    `(backend, ())` and round-trips cleanly, the way every other role's pin
    does.
    """
    stored = _payloads.as_text(state.get(_LATE_AGENT))
    if stored:
        backend, extra_args = config._parse_agent_spec(_LATE_AGENT, stored)
        return stored, backend, extra_args
    return (
        config.DECOMPOSE_AGENT_SPEC,
        config.DECOMPOSE_AGENT,
        config.DECOMPOSE_AGENT_ARGS,
    )


def _recovered_adjudication(run: _LateRun) -> _LateAdjudication:
    """Rebuild the adjudication a recorded outcome stands for.

    Everything a caller acts on comes back: the verdict, the category, the
    question to announce, the explanation a `single` gave for not splitting,
    and the manifest to create children from. Only the agent's rationale for
    accepting the change does not, because that prose is the part of a reply
    the pinned comment deliberately never kept.

    A record with no explanation is rebuilt with none, and the carrier answers
    for the absence: what the record holds is what an agent wrote, and a
    rebuilt outcome that manufactured a sentence would be indistinguishable
    from one that had it all along.
    """
    return _LateAdjudication(
        verdict=run.verdict,
        category=run.category,
        question=run.question,
        split_blocker=run.split_blocker,
        children=run.children,
    )


def _spawn_record_for(
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
    *,
    resuming: bool = False,
) -> _LateRun:
    """The record a run over this generation would be started under.

    One definition, because two callers have to agree on it exactly: the hold
    measures whether the comment could still hold this beside a preserved
    pull-request body, and the spawn writes it. A locked spec is an operator's
    command line and is not bounded by anything here, so measuring anything
    other than the real one would be measuring the wrong write.

    `resuming` is the caller saying this run carries a human's answer to the
    question the pinned session asked. It is not enough on its own: the record
    also has to say that session really ran against THIS cycle, generation,
    and commit, because a session pinned before a revision replaced the
    candidate holds a conversation about work nobody is adjudicating. A run
    that fails either test opens a fresh conversation, and the session id goes
    with the record it belonged to.
    """
    recorded = _read_late_run(state)
    continues = resuming and recorded.ran_against(generation)
    return replace(
        recorded,
        cycle_id=generation.cycle_id,
        source_sha=generation.candidate_sha,
        generation=generation.generation,
        session_id=recorded.session_id if continues else None,
    )
