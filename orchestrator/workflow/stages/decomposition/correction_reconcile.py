# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a `decomposing` tick owes a manifest correction an earlier tick left pending.

Asked once the drift reset, the split recovery, and the kill switch have had
their say and before the tick resumes or spawns a decomposer
(`session._run_for_the_tick`), since every run charged behind a pending attempt
would be one its resolution covers: an attempt resolved only after a new
decomposer is charged would cover that decomposer's own rejected answer too.
So the attempt is answered first, from what the tick's reading says of it
(`correction_standing.read`):

- ELIGIBLE on an issue no park stands on is the launch an earlier tick owed and
  never made -- a restart behind the arming, an arming read back, a start the
  circuit refused, a lifetime grant answering the run-limit park its charge
  took -- and it is launched now, with the error the record keeps
  (`correction_road.launch`).
- STALE is an attempt whose requirements or saved conversation moved: an
  edit's reset retiring the session, or the continuation a retry-cap park its
  launch took was answered with. It is retired over a reading that proves the
  move, the tick's own reset written first where the move is that reset's
  (`correction_settlement.retires`), and the tick goes on to the fresh
  decomposition the move buys.
- STARTED (a launch whose answer nothing acted on: a hold, an unresolved
  accounting, an interruption, a lost write), CROWDED, UNPROVED, an
  unresumable command, or ELIGIBLE under a park a human owns is never launched:
  it is exhausted, and an issue no park stands on parks for a human first, so
  the session stays theirs to resume with a reply. A park already standing is
  that answer -- the one a correction's park left with its exhaustion lost --
  and its tick goes on to the reply it waits on.
- EXHAUSTED with nothing charged since it resolved, its context standing, and
  no park standing is a correction's answer, or an attempt given up, that
  nothing was made of -- an exhaustion that landed ahead of a park write that
  did not, or ahead of a decision that never reached its label -- so the issue
  parks for a human rather than spawning a replacement decomposition.

Each park here is said once (`correction_notices.parks_once`): a notice of
ours carrying the attempt's receipt is recorded as the park rather than
posted again. ABSENT, RETIRED, DAMAGED, DISPLACED, and an exhausted attempt
anything was charged behind, whose context moved, or that a park stands over
owe nothing here: a resolved attempt
has spent its one launch, and a claim nobody can read or that names another
record is never acted on. A write over the attempt left unconfirmed, landing
over a comment moved since the tick read it, or a thread a park could not
read holds the tick, so no decomposer is charged behind an attempt nobody can
say is resolved.
"""
from __future__ import annotations

from types import MappingProxyType

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import run_ledger_values as _run_ledger_values
from orchestrator.workflow.stages.decomposition import (
    correction_notices as _notices,
    correction_records as _records,
    correction_road as _road,
    correction_settlement as _settlement,
    correction_source as _source,
    correction_standing as _standing,
    replies as _replies,
)
from orchestrator.workflow.stages.decomposition.models import _DecomposerRunPlan

_STANDING = _standing.Standing

# What owes the tick nothing: no attempt, a retired one, or a claim never acted on.
_PASSIVE = frozenset((_STANDING.ABSENT, _STANDING.RETIRED, _STANDING.DAMAGED, _STANDING.DISPLACED))

# Why an attempt was never answered, by what its reading says of it -- an
# exhausted one by whether a correction of it returned.
_UNANSWERED = MappingProxyType({
    _STANDING.STARTED: "was started, but nothing could act on its answer",
    _STANDING.CROWDED: "could not be launched: the pinned comment has no room to record it",
    _STANDING.UNPROVED: "could not be launched: the conversation it would resume could not be read",
    _STANDING.ELIGIBLE: "could not be launched: the pinned decomposer command does not parse",
    True: "returned, but nothing was made of its answer",
    False: "was given up before it was launched",
})


def reconciles(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> _DecomposerRunPlan | None:
    """The plan this tick's correction owes, or None where the tick goes on to its ordinary decomposer road."""
    reading = _standing.read(state, issue.number)
    attempt = reading.attempt
    if reading.standing in _PASSIVE:
        return None
    if reading.standing is _STANDING.EXHAUSTED:
        return _unacted(gh, issue, state, attempt)
    if reading.standing is _STANDING.STALE:
        return None if _settlement.retires(gh, issue, state, attempt) else _held(state)
    launchable = _source.resumable(attempt.source.command) is not None
    if reading.grants and launchable and not _replies.parked(state):
        launched = _road.launch(gh, spec, issue, state, attempt)
        return _DecomposerRunPlan(agent_result=launched, correction=attempt)
    return _given_up(gh, issue, state, reading)


def _given_up(
    gh: GitHubClient, issue: Issue, state: PinnedState, reading: _standing.CorrectionReading,
) -> _DecomposerRunPlan | None:
    """Exhaust an attempt no launch may be made for, parking a human first where no park stands.

    None lets a parked tick go on to the reply it waits on.
    """
    parked = _replies.parked(state)
    attempt = reading.attempt
    notice = _notice(attempt, reading.standing)
    if not parked and not _notices.parks_once(gh, issue, state, attempt, notice):
        return _held(state)
    _settlement.spends(gh, issue, state, attempt)
    return None if parked and not state.withheld else _held(state)


def _unacted(
    gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt,
) -> _DecomposerRunPlan | None:
    """Park an exhausted attempt nothing was made of, where nothing since stands behind it; None otherwise."""
    charged_since = _run_ledger_values._runs_used_strictly(state) != attempt.floor
    moved = _standing.moved(state, attempt.source)
    if charged_since or moved is not None or _replies.parked(state):
        return None
    returned = attempt.correction is not None
    _notices.parks_once(gh, issue, state, attempt, _notice(attempt, returned))
    return _held(state)


def _notice(attempt: _records.CorrectionAttempt, unanswered: object) -> str:
    """What a park over `attempt` tells the human, `unanswered` naming why its correction answered nothing."""
    diagnostic = attempt.source.diagnostic
    why = _UNANSWERED[unanswered]
    return (
        f"{config.HITL_MENTIONS} decomposer manifest invalid ({diagnostic}); its one automatic correction {why}. "
        "Manual adjudication needed: reply to resume the decomposer session, or edit the issue to decompose it "
        "afresh."
    )


def _held(state: PinnedState) -> _DecomposerRunPlan:
    """A tick that ends here, launching nothing, keeping a checkout a standing park may be keeping for inspection."""
    return _DecomposerRunPlan(agent_result=None, keep_worktree=_replies.parked(state))
