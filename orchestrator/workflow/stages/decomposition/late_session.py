# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist late-run spawn, session, and result records, and invoke the adjudicator.

A new spawn clears the previous result, its rationale included, and the
publication override. Results are written only after the whole pinned
payload -- the rationale already cut to its bound, every other field whole --
fits the comment ceiling, and the preflight reserves room for the longest
supported session id.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    prompt_context as _prompt_context,
    run_charge_state as _run_charge_state,
    usage as _usage,
)
from orchestrator.workflow.late_split import (
    models as _late_models,
    overrides as _overrides,
)
from orchestrator.workflow.stages.decomposition import (
    late_prompt as _prompt,
    late_result_payloads as _late_result_payloads,
    late_run_reading as _late_run_reading,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.late_result_models import _LateAdjudication, _LateRun

log = logging.getLogger("orchestrator.workflow")

# The stage a late run is attributed to on both observability surfaces. Late
# adjudication is an additive mode under the existing label, not a stage of
# its own, so an analytics row reads `decomposing` exactly as the initial
# decomposer's does.
_DECOMPOSING_STAGE = "decomposing"

_RETRY_COUNT = "retry_count"

# What a completed run recorded, and therefore what a fresh one has to drop.
_RESULT_KEYS = (
    _late_run_reading._LATE_RESULT_VERDICT,
    _late_run_reading._LATE_RESULT_CATEGORY,
    _late_run_reading._LATE_RESULT_QUESTION,
    _late_run_reading._LATE_RESULT_SPLIT_BLOCKER,
    _late_run_reading._LATE_RESULT_CHILDREN,
    _late_run_reading._LATE_RESULT_RATIONALE,
)

# What a recorded outcome is measured against: not its own size, but what the
# WHOLE pinned comment would become with it in -- the preserved held-PR body
# and every other stage's keys included. A result small enough on its own can
# still be the one that pushes the comment past what GitHub accepts, and
# finding that out from the failed write means the agent has already been paid
# for and the next tick pays again.
#
# The headroom below GitHub's limit is for the keys other stages still write
# into the same comment after an outcome is recorded -- watermarks, counters,
# a PR number. Leaving an outcome sitting exactly at the ceiling would move
# the failure onto whichever of them wrote next.
_COMMENT_HEADROOM = 4096

MAX_RECORDED_BODY = _pinned_state.MAX_PINNED_BODY - _COMMENT_HEADROOM

# What a park's own sentence is measured at, once it has earned one. The
# obligation NAMES the recorded explanation rather than copying it
# (`late_notice`), so what has to fit is this mode's own wording rather than
# anything an agent wrote -- which is what makes a fixed figure enough.
#
# It is NOT taken out of what an outcome may record. Every verdict is held to
# the one outcome budget, and the headroom that budget leaves under GitHub's
# limit is where a park's sentence is written afterwards. Charging a `single`
# for the sentence it earns would refuse a verdict this comment can hold --
# and that refusal is one the next attempt supersedes, so it would buy another
# decomposer run against a candidate already adjudicated and leave the
# `single` short of the durable park a human's decision is owed on.
MAX_NOTICE_BODY = 1024

# What the sentence around a quote, the mention the shared park prefixes, and
# the marker it appends need of the comment they all go in, and so what the
# quote itself may take of a delivered notice.
_DELIVERY_HEADROOM = 2048

MAX_QUOTED_BLOCK = _pinned_state.MAX_PINNED_BODY - _DELIVERY_HEADROOM

# What a notice itself is measured against, which is the reserve ON TOP of the
# outcome budget rather than inside it. The headroom under GitHub's limit is
# for the keys other stages write into the comment AFTER an outcome is
# recorded, and a park's own sentence is one of them -- so measuring it inside
# the outcome's budget charges it twice.
#
# What that buys is the record an older binary left. Such a record was written
# against the whole outcome budget and never reserved anything, so a park it
# earns today would find no room and drop the retry its sentence depends on --
# and this park is one nothing supersedes, so the human would never be told.
# The reserve cannot be taken out of a record already on the issue; it can be
# left beside it.
#
# It is the standing answer rather than the only one, because a record can sit
# outside it without ever having broken it. `late_notice` owns that reading:
# the reserve is granted on top of whatever the comment actually costs today,
# and this is the floor it never drops below.
MAX_NOTICE_COMMENT = MAX_RECORDED_BODY + MAX_NOTICE_BODY

# How long a session id this record will pin. Every backend issues a bounded
# token, so an id past this is not one -- and pinning it would put the comment
# past the room a hold measured for it. The resume such an id would have
# served does not exist yet; a write that cannot land does.
MAX_SESSION_ID = 256


def _record_late_spawn(
    state: _pinned_state.PinnedState, run: _LateRun,
) -> None:
    """Record what a late run IS, before that run can fail.

    Written ahead of the spawn for the reason the initial decomposer's spec
    is: a backend that produces an answer without surfacing a session id would
    otherwise leave the issue unattributed, and a later config flip could
    retarget its resume at a CLI that never ran here. The identity of the
    attempt goes with it, so the result recorded when the run returns cannot
    be read as an answer to a different generation or a different commit.

    The session goes only when the run is not continuing it. A resume keeps
    the pinned id so a tick that crashes mid-run resumes the same conversation
    rather than opening a second one; a fresh run drops it so a backend that
    surfaces none of its own cannot leave the next tick resuming the run this
    one replaced. The result is dropped either way -- what a new run decides
    replaces what the last one did, and a half-read record is not an answer.

    The drop is the same one a human's answer takes, reached through the same
    owner, and that is what makes it the statement of the rule no road gets
    around: whatever made the last answer stop being the answer, the run
    recorded here is the one replacing it, so the operator's authorization to
    publish that answer goes with it.
    """
    state.set(_late_run_reading._LATE_AGENT_ROLE, run.role)
    state.set(_late_run_reading._LATE_AGENT, run.spec)
    state.set(_late_run_reading._LATE_RUN_CYCLE_ID, run.cycle_id)
    state.set(_late_run_reading._LATE_SOURCE_SHA, run.source_sha)
    state.set(_late_run_reading._LATE_RUN_GENERATION, run.generation)
    if run.session_id:
        state.set(_late_run_reading._LATE_SESSION_ID, run.session_id)
    else:
        state.data.pop(_late_run_reading._LATE_SESSION_ID, None)
    _drop_late_result(state)


def _drop_late_result(state: _pinned_state.PinnedState) -> None:
    """Forget the outcome a completed run recorded, keeping its identity.

    What a human's answer to a categorized question earns, what a certificate
    over edited requirements earns, and what the run replacing an outcome
    records on its way past. The record is what suppresses the next spawn, so
    an answer nothing holds any more has to stop being an answer before the
    adjudicator will run again -- and only the result goes, because the spec
    this issue is locked to and the session it opened are not what the human
    replied to.

    An operator's authorization to publish goes with it, and that is not a
    courtesy: what they authorized was ONE answer, taken against the
    requirements as they then read. The terms that record carries -- the
    frozen pair, the measurement, the digest -- all survive an answer being
    thrown away and re-earned, so a record left standing here would let the
    NEXT adjudication's `single` publish on a permission nobody granted it.
    The two are one fact, so every road that ends an answer reaches this one
    owner rather than remembering to drop the permission beside it.
    """
    for recorded in _RESULT_KEYS:
        state.data.pop(recorded, None)
    _overrides.clear_publication_override(state)


def _record_late_session(
    state: _pinned_state.PinnedState, agent_result: AgentResult,
) -> None:
    """Pin the session a finished run opened, when it surfaced one.

    Bounded, because the room for it was reserved before any pull request was
    ever held. A token longer than any backend issues is not one this may pin:
    it would push the comment past what the hold proved would fit, and the
    write that follows -- a park, or the outcome itself -- has nowhere else to
    go.
    """
    session_id = agent_result.session_id
    if not session_id:
        return
    if len(session_id) > MAX_SESSION_ID:
        log.error(
            "a %d-character session id is longer than any backend issues; "
            "not pinning it", len(session_id),
        )
        return
    state.set(_late_run_reading._LATE_SESSION_ID, session_id)


def _record_late_result(
    state: _pinned_state.PinnedState, adjudication: _LateAdjudication,
) -> bool:
    """Record the whole of a completed adjudication, or record none of it.

    What each verdict decided is what gets written: a `single` the explanation
    of what stopped a split, a `question` its category and the sentence it
    asked, and a `split` the ordered child manifest that IS its decision --
    and beside a `single` or a `split`, the rationale it argued with.
    Recording all of it is what lets a crashed tick recover the answer instead
    of paying for a second agent run that may not even decide the same way.

    Returns whether it fit -- measured on the whole comment this write would
    produce, not on the outcome alone, because the comment is shared and what
    is already in it counts. An outcome past the budget is refused whole
    rather than shortened: a truncated question asks something nobody said, a
    truncated explanation gives a reason nobody wrote, and a truncated
    manifest names children nobody proposed. A caller told False has an
    outcome it cannot make durable, which is a human's problem and not a thing
    to half-record.

    The rationale is settled before any of that is asked. It is prose nothing
    acts on, cut to its fixed bound with a marker saying so, so what is
    measured is the record exactly as it would be written -- escapes and all
    -- and a long argument is never on its own what refuses the verdict it
    came with.

    One budget, and every verdict is held to it. What a verdict goes on to
    owe the thread is not taken out of what it may record: the park a `single`
    earns is one nothing supersedes, while the refusal a smaller budget would
    produce IS superseded -- so charging it for its own sentence would buy
    another decomposer run against a candidate already adjudicated and leave
    that `single` short of the park a human's decision is owed on. The
    sentence is written into the headroom this budget leaves under GitHub's
    limit, afterwards.
    """
    recorded = _late_result_payloads._result_payload(adjudication)
    if not _late_result_payloads._fits_the_comment({**state.data, **recorded}, MAX_RECORDED_BODY):
        return False
    for key, written in recorded.items():
        state.set(key, written)
    return True


def _holdable(
    state_data: dict, generation: _late_models.LateGeneration,
) -> bool:
    """Whether a comment holding this could still record the run beside it.

    Asked before a held PR's description is replaced, because the write that
    starts the run has no safe failure of its own: parking is another write of
    the same oversized comment, so a refusal there would strand the pull
    request held with nothing recorded and every retry raising again.

    What it measures is the real thing -- the locked spec, this generation's
    identities, and the bounded session id a finished run pins -- rather than
    a reserve standing in for them. The phase is the hold's own, which is the
    longer of the two spellings a late write puts there, so the measurement
    errs toward refusing.
    """
    written = _pinned_state.PinnedState(data=dict(state_data))
    _record_late_spawn(written, _late_run_reading._spawn_record_for(written, generation))
    written.set(_late_run_reading._LATE_SESSION_ID, "s" * MAX_SESSION_ID)
    return _late_result_payloads._fits_the_comment(written.data, MAX_RECORDED_BODY)


def _spawn_late_adjudicator(
    context: _LateContext, run: _LateRun, worktree: Path,
) -> AgentResult:
    """Run the late adjudicator in the worktree holding the candidate.

    The candidate's own checkout, because the diff being adjudicated is
    between two commits this host holds and nothing has been pushed: a
    scratch checkout of the base branch could not show the agent the work it
    is being asked about.

    A session id on the record is one this run continues -- the record decided
    that, not this call -- so an answer to a categorized question reaches the
    agent that asked it. `None` opens a fresh conversation, which is what
    every run that is not answering one gets.
    """
    return _usage._run_agent_tracked(
        context.gh,
        _run_charge_state.AgentRunBudget(
            issue=context.issue, state=context.state,
        ),
        agent_role=run.role,
        stage=_DECOMPOSING_STAGE,
        backend=run.backend,
        prompt=_prompt._build_late_decompose_prompt(
            context.spec,
            context.issue,
            _prompt_context._recent_comments_text(context.issue),
            context.generation,
            config.default_repo_specs(),
        ),
        cwd=worktree,
        agent_spec=run.spec,
        resume_session_id=run.session_id,
        extra_args=run.extra_args,
        retry_count=context.state.get(_RETRY_COUNT),
    )
