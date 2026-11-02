# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one correction a rejected initial decomposer answer earns: asked for at its rejection, and launched once.

A dormant road: these helpers are callable and tested, but no production road
asks them yet, so production decomposition keeps its own outcomes and a
manifest that fails validation still parks awaiting a human
(`outcomes._park_unparsed_manifest`). Nothing here publishes a correction's
answer or recovers an attempt on a later tick.

Only the answer `correction_source.earned` names asks for it (`requests`): a
completed, accounted, read-only run's manifest the parser refused with a
concrete error, over a conversation the pinned command can resume. Every
other answer keeps the disposition it always had.

Before anything is armed, the run's own disposition so far -- the session pin,
the settlement of a frozen read, the stamp -- is written whole, since the
arming is decided on the comment carrying that very session and baseline
(`correction_checkpoint.arm`), and a write that does not land holds the tick.
An arming that lands grants the launch only while the comment reads it
ELIGIBLE; one that lands crowded hands back the attempt with no launch, for
the caller's ordinary park, and a refused one hands back nothing. One sent and
never confirmed holds the tick with the caller's state withheld, until a
read-back (`correction_checkpoint.read_back`) says what landed.

The launch (`launch`) is asked only of an attempt the comment, read back
unmoved, still reads ELIGIBLE. It is a retry the issue's daily budget pays for
like any fresh spawn, so a spent budget takes its retry-cap park instead, and the
`/orchestrator continue` that park waits on buys the fresh decomposition it
always bought: the session it retires is the one the attempt was saved under,
so the attempt grants no launch behind it. The daily slot it pays lands in
the write reserving its lifetime charge (`correction_budget`), so a correction
whose disposition is never written still counts it, and a reservation standing
unstarted has paid it already. Then the tracked spawn charges the lifetime
ledger and accounts the usage once, as for every run, under the attempt's one
owed launch (`correction_standing.owed_launch`): the circuit refuses it on any
reading that no longer grants it, and asks the issue afresh right behind the
charge (`correction_live.resolves`), so a hold, a close, a relabel, or an edit
invokes nothing, and lands the charge and the start only over the readings
they were decided on, each asking the issue and the comment once more right
before it leaves, so a session pinned meanwhile is never written back over and
resumed, and a hold landing during the editor's walk invokes nothing. It
resumes the saved session under the pinned command -- backend and arguments
alike -- handing it the exact error and the whole output contract
(`engine/decomposition_prompts._build_correction_prompt`), never a replacement
conversation.

Every park the launch takes on the rejected run's own tick is bounded where
the tick's scope bounds it or the reply boundary is the one the source's
requirements were settled through (`bounds`), and the answer says so for the
parks its run's disposition takes: a reply written while either run was out
stays past the boundary for the saved session's resume, never marked read and
taken for an edit.
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
    run_charge_state as _run_charge_state,
    usage as _usage,
)
from orchestrator.workflow.stages.decomposition import (
    correction_budget as _budget,
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
    Neither is the ordinary park, which stays the caller's to take, behind
    an `attempt` armed with no launch granted as behind no attempt at all.
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
    over it (`correction_checkpoint.read_back`), and the write lands only
    while the comment still reads as the tick last synced with it
    (`record_admission.strictly_written`): one another road or a human
    wrote while the run was out, or between that read and the write -- a
    session pinned in place of the run's, a cycle moved -- withholds the
    caller's state and holds the tick, so that write never puts back what it
    replaced and no correction is armed for a conversation the record no
    longer names. A write over the attempt that left the caller's state
    withheld -- sent and never confirmed, or landing over a comment moved
    since -- holds the tick too, since no whole-state write may follow it.
    The launch's parks are bounded as `bounds` answers, and the answer says
    so for its own disposition's.
    """
    source = _source.earned(issue, state, run_plan)
    if source is None:
        return CorrectionAsk()
    _checkpoint.read_back(gh, issue, state)
    if state.withheld or not _record_admission.strictly_written(gh, issue, state):
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

    A recorded attempt whose saved command or session no resume may take
    (`correction_source.launchable`) -- a record edited by hand since its
    arming -- is never launched. The pinned comment and the issue are read
    afresh next (`_still_owed`),
    so a spent budget's park is never written or announced over an attempt
    the comment no longer grants its launch, a hold, a moved owner or
    requirements, a moved saved context, or a comment another road wrote
    since the tick read it: each holds the tick with nothing said. The daily
    retry is staged in the write reserving the lifetime charge
    (`correction_budget.pays`), a reservation of this launch already standing
    has paid it, and a spent budget's park lands, and is announced, only over
    the comment the tick read and an issue that still stands
    (`correction_budget.admits`). The charge and the start land only
    over the readings they were decided on (`OwedLaunch.strict`), since the
    circuit's judge asks the issue behind each of those readings
    (`correction_live.uncontrolled`): a session a human pins while those
    requests are out is never written back over and resumed. Each of those
    edits asks `resolves` and the comment once more right before it leaves,
    so a hold landing during the editor's walk invokes nothing either.
    """
    if not _source.launchable(attempt.source.command, attempt.source.session):
        log.warning("issue=#%d its manifest correction saved no session it may resume; launching nothing", issue.number)
        return None
    if not _still_owed(gh, issue, state, attempt):
        return None
    request = _source.resumed(spec, issue, attempt.source)
    resolves = partial(_live.resolves, gh, issue, state, attempt.source)
    if not _budget.admits(gh, issue, state, request, resolves):
        return None
    owed = _standing.owed_launch(issue.number, attempt, resolves)
    owed = dataclasses.replace(
        owed,
        stands=partial(_live.uncontrolled, owed.stands, resolves),
        pays=partial(_budget.pays, issue.number),
        strict=True,
    )
    budget = _run_charge_state.AgentRunBudget(issue=issue, state=state, owed=owed)
    return _usage._run_agent_tracked(gh, budget, request)


def _still_owed(gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt) -> bool:
    """Whether the comment, read back unmoved, still grants `attempt` its launch, and the issue still stands.

    Only an ELIGIBLE attempt is owed one: an attempt started, crowded,
    unproved, resolved, or no longer the comment's buys no retry, so no
    retry-cap park is written or announced for a launch the circuit would
    refuse anyway.
    """
    held = _checkpoint.read_back(gh, issue, state)
    if not held.settled or not held.reading.grants or held.reading.attempt != attempt:
        log.info("issue=#%d its manifest correction is not owed a launch on its comment; holding it", issue.number)
        return False
    live = _live.answers(gh, issue, state, attempt.source)
    if live is not _live.Live.STANDS or state.withheld:
        log.info("issue=#%d reads %s ahead of its manifest correction's launch; holding it", issue.number, live.value)
        return False
    return True
