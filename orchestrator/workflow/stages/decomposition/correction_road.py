# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one correction a rejected initial decomposer answer earns: asked for at its rejection, and launched once.

Only the answer `correction_source.earned` names asks for it (`requests`): a
completed, accounted, read-only run's manifest the parser refused with a
concrete error, over a conversation the pinned command can resume. Every
other answer keeps the disposition it always had.

Before anything is armed, the run's own disposition so far -- the session pin,
the settlement of a frozen read, the stamp -- is written whole, since the
arming is decided on the comment carrying that very session and baseline
(`correction_checkpoint.arm`), and a write that does not land holds the tick.
An arming that lands grants the launch only while the comment reads it
ELIGIBLE; one that lands crowded is given up behind the ordinary park, and a
refused one parks as before. One sent and never confirmed holds the tick with
the caller's state withheld, for the next tick to read back
(`correction_reconcile`).

The launch (`launch`) is a retry the issue's daily budget pays for like any
fresh spawn, so a spent budget takes its retry-cap park instead, and a
`/orchestrator continue` buys the fresh decomposition that park always bought:
the session it retires is the one the attempt was saved under, so the attempt
is retired with it. Then the tracked spawn charges the lifetime ledger and
accounts the usage once, as for every run, under the attempt's one owed launch
(`correction_standing.owed_launch`): the circuit refuses it on any reading that
no longer grants it, and asks the issue afresh right behind the charge
(`correction_live.resolves`), so a hold, a close, a relabel, or an edit
invokes nothing. It resumes the saved session under the pinned command --
backend and arguments alike -- handing it the exact error and the whole output
contract (`engine/decomposition_prompts._build_correction_prompt`), never a
replacement conversation.

Every park the launch and its answer take on the rejected run's own tick is
bounded where the tick's scope bounds them or the reply boundary is the one
the source's requirements were settled through (`bounds`), as a later tick's
launch is by the read it froze: a reply written while either run was out stays
past the boundary for the saved session's resume, never marked read and taken
for an edit.
"""
from __future__ import annotations

import dataclasses
import logging
from functools import partial

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    park_watermarks as _park_watermarks,
    record_admission as _record_admission,
    retry_budget as _retry_budget,
    run_charge_state as _run_charge_state,
    usage as _usage,
)
from orchestrator.workflow.stages.decomposition import (
    correction_checkpoint as _checkpoint,
    correction_live as _live,
    correction_records as _records,
    correction_source as _source,
    correction_standing as _standing,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.models import _DecomposerRunPlan

log = logging.getLogger("orchestrator.workflow")


@dataclasses.dataclass(frozen=True)
class CorrectionAsk:
    """What asking for a rejected answer's one correction came to.

    `launched` is the run of `attempt`'s correction, where its launch was
    asked -- a launch the circuit turned away included -- and `held` a tick
    that ends with nothing more, a retry-cap park the launch took among them.
    Neither is the ordinary park, which is taken behind an `attempt` armed
    with no launch granted, so the park lands before the attempt is given up.
    `bounded` is whether every park the launch and its answer take is
    bounded (`bounds`).
    """

    attempt: _records.CorrectionAttempt | None = None
    launched: AgentResult | None = None
    held: bool = False
    bounded: bool = False


def requests(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState, run_plan: _DecomposerRunPlan,
) -> CorrectionAsk:
    """Arm and launch the one correction `run_plan`'s rejected answer earns, where it earns one.

    `run_plan.agent_result` is the run whose manifest the parser refused, and
    the error the parser refuses it with is the one its correction is handed.
    The comment is read back before the run's disposition is written whole
    over it (`correction_checkpoint.read_back`): one another road or a human
    wrote while the run was out -- a session pinned in place of the run's, a
    cycle moved -- withholds the caller's state and holds the tick, so that
    write never puts back what it replaced and no correction is armed for a
    conversation the record no longer names. A write over the attempt that
    left the caller's state withheld -- sent and never confirmed, or landing
    over a comment moved since -- holds the tick too, since no whole-state
    write may follow it. The launch's parks are bounded as `bounds` answers,
    and the answer says so for its own disposition's.
    """
    source = _source.earned(issue, state, run_plan)
    if source is None:
        return CorrectionAsk()
    _checkpoint.read_back(gh, issue, state)
    if state.withheld or not _record_admission.written(gh, issue, state):
        log.warning(
            "issue=#%d the disposition its manifest correction is armed over did not land; holding the tick",
            issue.number,
        )
        return CorrectionAsk(held=True)
    armed = _checkpoint.arm(gh, issue, state, source)
    if state.withheld or not armed.settled:
        return CorrectionAsk(held=state.withheld)
    attempt = armed.reading.attempt
    if not armed.reading.grants:
        return CorrectionAsk(attempt)
    bounded = bounds(gh, issue, state, attempt.source)
    with _park_watermarks.bounded_parks(bounded):
        launched = launch(gh, spec, issue, state, attempt)
    return CorrectionAsk(attempt, launched, held=launched is None, bounded=bounded)


def bounds(gh: GitHubClient, issue: Issue, state: PinnedState, source: _records.CorrectionSource) -> bool:
    """Whether every park a correction launched on its rejected run's tick takes is bounded.

    Where the tick's own scope bounds its parks -- a resume handed a frozen
    read -- and where the reply boundary `state` carries is the one `source`'s
    requirements were settled through: the thread through it reads as that
    revision, so a park walking from it over our own comments stops short of
    no comment the rejected run read, and of every reply written while the
    correction was out, which stays past it for the saved session's resume
    rather than being marked read and taken for an edit. A thread with no
    boundary, or one nobody could read, bounds nothing: the park stands on its
    notice, as the rejected run's own would have.
    """
    if _park_watermarks._parks_bounded():
        return True
    floor = state.get(_state._LAST_ACTION_COMMENT_ID)
    if not isinstance(floor, int):
        return False
    try:
        thread = gh.comments_after(issue, None, state_comment_id=state.comment_id)
    except Exception:
        log.exception("issue=#%d could not be read for its manifest correction's reply boundary", issue.number)
        return False
    read = [seen for seen in thread if seen.id <= floor]
    ours = _comments._orchestrator_ids(state)
    return _content_hash._compute_user_content_hash(issue, ours, comments=read) == source.requirements


def launch(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    attempt: _records.CorrectionAttempt,
) -> AgentResult | None:
    """Spend a retry and launch `attempt`'s one correction; None where it is held, or the retry budget parked it.

    The pinned comment and the issue are read afresh first (`_still_owed`),
    so a spent budget's park is never written or announced over a hold, a
    moved owner or requirements, a moved saved context, or a comment another
    road wrote since the tick read it: each holds the tick with nothing said.
    """
    if not _still_owed(gh, issue, state, attempt):
        return None
    if not _retry_budget._charge_or_park(gh, issue, state, stage=_source.STAGE):
        gh.write_pinned_state(issue, state)
        return None
    resolves = partial(_live.resolves, gh, issue, state, attempt.source)
    owed = _standing.owed_launch(issue.number, attempt, resolves)
    stands = partial(_live.uncontrolled, owed.stands, resolves)
    owed = dataclasses.replace(owed, stands=stands)
    budget = _run_charge_state.AgentRunBudget(issue=issue, state=state, owed=owed)
    return _usage._run_agent_tracked(gh, budget, _source.resumed(spec, issue, attempt.source))


def _still_owed(gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt) -> bool:
    """Whether the comment, read back unmoved, and then the issue still stand as `attempt` was armed over."""
    _checkpoint.read_back(gh, issue, state)
    live = _live.answers(gh, issue, state, attempt.source)
    if live is not _live.Live.STANDS or state.withheld:
        log.info("issue=#%d reads %s ahead of its manifest correction's launch; holding it", issue.number, live.value)
        return False
    return True
