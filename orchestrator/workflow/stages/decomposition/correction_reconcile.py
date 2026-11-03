# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a `decomposing` tick owes a manifest correction an earlier tick left pending, and the run it then makes.

Two questions, asked at two points of the tick.

Ahead of the frozen read and the drift check (`recovers_park`, asked by
`run._prepare_decomposer_run`), the record is asked whether the attempt is owed
a park that does not stand: a claim nobody can read holds the tick with nothing
written, since whatever it still owes cannot be said; an attempt STARTED (a
launch whose answer nothing acted on: a hold, an unresolved accounting, an
interruption, a lost write), CROWDED, UNPROVED, or whose saved command or
session no resume may take is never launched; and an EXHAUSTED one with nothing
charged since it resolved and its context standing is a correction's answer, or
an attempt given up, that nothing was made of -- an exhaustion that landed
ahead of a park write, or of a decision, that did not. Each parks for a human
before anything reads a reply as an edit, so a reply written while the
correction was out is the park's to deliver rather than drift that would retire
the saved session: the park is said once (`correction_notices.parks_once`),
recorded over a notice of ours carrying the attempt's receipt where one stands,
and bounded, the reply boundary walking our own comments and no further; a
pending attempt is exhausted behind it, and an exhaustion that does not land --
over a charge count nobody can read, say -- holds the tick, so no resume or
fresh decomposer is charged beside an attempt still pending. The tick then goes
on as a parked one. A notice the record still holds for an attempt whose park a
move or a close took away is dropped as that attempt is spent
(`correction_settlement.discards`), since nothing will ever post it.

Once the drift reset, the split recovery, and the kill switch have had their
say, and before any decomposer is charged behind it (`run_for_the_tick`) --
since an attempt resolved only after a new decomposer is charged would cover
that decomposer's own rejected answer too -- the attempt is answered from the
tick's reading of it (`reconciles`):

- ELIGIBLE on an issue no park stands on is the launch an earlier tick owed and
  never made -- a restart behind the arming, an arming read back, a start the
  circuit refused, a lifetime grant answering the run-limit park its charge
  took -- and it is launched now, with the error the record keeps
  (`correction_road.launch`), on a tick that froze its thread for it
  (`replies.reads_the_thread`), so a reply written since the rejected run is
  no edit, and every park the launch's disposition takes is bounded by that
  read wherever its boundary is the settled one.
- STALE is an attempt whose requirements or saved conversation moved: an
  edit's reset retiring the session, or the continuation a retry-cap park its
  launch took was answered with. It is retired over a reading that proves the
  move, the tick's own reset written first where the move is that reset's,
  only over the comment the retirement read (`correction_settlement.retires`),
  and the tick goes on to the fresh decomposition the move buys only once the
  retirement has landed: a reset refused over a comment moved since, or a
  retirement refused -- over a charge count nobody can read, say -- holds it.
- Any other pending attempt is exhausted, behind a park where none stands; a
  park already standing -- the one a correction's park left with its
  exhaustion lost -- is its answer, and its tick goes on to the reply it waits
  on.

Then the run the tick makes is the resume of a park still standing, or the
fresh spawn. ABSENT, RETIRED, DISPLACED, and EXHAUSTED owe nothing there but
the drop of a park notice the record still holds for them, one an earlier
tick's drop did not land (`correction_settlement.discards`), which the tick
takes before its run and holds on where it does not land; a claim nobody can
read holds the tick there too. A write over the attempt left
unconfirmed, landing over a comment moved since the tick read it, or a thread a
park could not read holds the tick, so no decomposer is charged behind an
attempt nobody can say is resolved.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import park_watermarks as _park_watermarks, run_ledger_values as _run_ledger_values
from orchestrator.workflow.stages.decomposition import (
    correction_live as _live,
    correction_notices as _notices,
    correction_road as _road,
    correction_settlement as _settlement,
    correction_source as _source,
    correction_standing as _standing,
    replies as _replies,
    session as _session,
)
from orchestrator.workflow.stages.decomposition.models import _DecomposerRunPlan

log = logging.getLogger("orchestrator.workflow")

_STANDING = _standing.Standing

# What owes a tick's run nothing: no attempt, a resolved one, or one naming another record.
_PASSIVE = frozenset((_STANDING.ABSENT, _STANDING.RETIRED, _STANDING.DISPLACED, _STANDING.EXHAUSTED))

# What the tick settles before its ordinary run: a passive attempt, any notice
# still held for it dropped, and a stale one, retired.
_SETTLING = _PASSIVE | {_STANDING.STALE}

# A pending attempt that may never be launched, whatever stands beside it, save
# an eligible one whose saved command and session a resume may take.
_UNLAUNCHABLE = frozenset((_STANDING.STARTED, _STANDING.CROWDED, _STANDING.UNPROVED, _STANDING.ELIGIBLE))

# What a park's live reading answers that holds the tick: a hold, or a reading
# GitHub would not answer. A move of the requirements or the saved context is
# the drift road's, so the attempt is spent and the tick goes on to it; a close
# or a relabel spends it too, and ends the tick on an issue this label no
# longer owns.
_HOLDING = frozenset((_live.Live.HELD, _live.Live.UNREAD))

# The parent's markers of a split transaction begun: the count written before
# its first child, and the children recorded as each lands
# (`recovery._recover_stale_manifest`).
_SPLIT_MARKERS = ("expected_children_count", "children")

# Why an attempt was never answered, by what its reading says of it -- an
# exhausted one by whether a correction of it returned.
_UNANSWERED = MappingProxyType({
    _STANDING.STARTED: "was started, but nothing could act on its answer",
    _STANDING.CROWDED: "could not be launched: the pinned comment has no room to record it",
    _STANDING.UNPROVED: "could not be launched: the conversation it would resume could not be read",
    _STANDING.ELIGIBLE: "could not be launched: its saved decomposer command or session cannot be resumed",
    True: "returned, but nothing was made of its answer",
    False: "was given up before it was launched",
})


def recovers_park(gh: GitHubClient, issue: Issue, state: PinnedState) -> Issue | None:
    """Take the park an attempt is owed where none stands; the issue the tick goes on with, None ending it.

    A park the issue no longer stands for takes nothing: a hold or an unread
    reading ends the tick with the attempt as it stands; a close or a relabel
    spends it and ends the tick, so no decomposer is charged on an issue
    another label owns; and a move of the requirements or the saved context
    spends it and goes on to the drift road -- on the issue fetched afresh
    behind that reading (`correction_live.controls`), so the drift check and
    any fresh decomposition it buys read the requirements the move was read
    off, never the snapshot the tick began with. Either move drops a notice
    the record held for that park (`correction_settlement.discards`). An
    exhaustion, or that drop, that does not land ends the tick too, the
    attempt left as it stands. Anything else goes on with the caller's issue.
    """
    reading = _standing.read(state, issue.number)
    if reading.standing is _STANDING.DAMAGED:
        log.warning(
            "issue=#%d its manifest correction record cannot be read; holding the tick with nothing written "
            "until it is repaired", issue.number,
        )
        return None
    unanswered = _owed_park(state, reading)
    if unanswered is None or _replies.parked(state):
        return issue
    notice = _notice(state, reading, unanswered)
    parked = _notices.parks_once(gh, issue, state, reading.attempt, notice)
    if not _settlement.settles_park(gh, issue, state, reading, parked):
        return None
    if parked is _live.Live.STANDS:
        return issue
    return _live.controls(gh, issue)[1]


def run_for_the_tick(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
    replies: _replies.DecomposerReplies | None,
) -> _DecomposerRunPlan:
    """The decomposer run this tick makes once drift, recovery, and the kill switch have had their say.

    The correction an earlier tick left pending first (`reconciles`); then a
    park still standing is resumed on the replies the tick froze -- a drift
    reset took the park down, and with it the session the replies would have
    answered -- and anything else spawns the fresh decomposition, handed that
    same read where the tick froze one.
    """
    reconciled = reconciles(gh, spec, issue, state, replies)
    if reconciled is not None:
        return reconciled
    if replies is not None and _replies.parked(state):
        return _session._resume_decomposer_on_human_reply(gh, spec, issue, state, replies)
    return _session._spawn_fresh_decomposer(gh, spec, issue, state, replies)


def reconciles(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    replies: _replies.DecomposerReplies | None,
) -> _DecomposerRunPlan | None:
    """The plan this tick's correction owes, or None where the tick goes on to its ordinary decomposer road.

    An owed launch is made on a tick that froze its thread for it
    (`replies.reads_the_thread`), and every park its disposition takes is
    bounded by that read wherever its boundary is the one the rejected run
    settled through (`DecomposerReplies.bounds`), so a reply written while the
    correction was out stays past it; the read is never settled, since the
    correction is handed the error alone.
    """
    reading = _standing.read(state, issue.number)
    attempt = reading.attempt
    if reading.standing is _STANDING.DAMAGED:
        return _held(state)
    if reading.standing in _SETTLING:
        settle = _settlement.retires if reading.standing is _STANDING.STALE else _settlement.discards
        return None if settle(gh, issue, state, attempt) else _held(state)
    if _owed_park(state, reading) is None and not _replies.parked(state):
        bounding = replies if replies is not None and replies.bounds(issue, state) else None
        with _park_watermarks.bounded_parks(bounding is not None):
            launched = _road.launch(gh, spec, issue, state, attempt)
        return _DecomposerRunPlan(agent_result=launched, replies=bounding, correction=attempt)
    return _given_up(gh, issue, state, reading)


def _owed_park(state: PinnedState, reading: _standing.CorrectionReading) -> object:
    """Why the attempt `reading` carries is owed a park where none stands, or None where it owes none.

    A pending attempt that may never be launched owes one; an eligible one
    whose saved command and session a resume may take
    (`correction_source.launchable`) owes none, being still to launch. An
    exhausted one owes one only where nothing has been charged since it
    resolved, its context stands, and no split transaction stands on the
    parent, so the answer nothing was made of is the last thing the issue did:
    a split's markers say its answer was acted on, and the split recovery
    finishes it (`recovery._recover_stale_manifest`), seeding and handing off
    the children it recorded, rather than a park taking its place.
    """
    attempt = reading.attempt
    if reading.standing is _STANDING.EXHAUSTED:
        charged_since = _run_ledger_values._runs_used_strictly(state) != attempt.floor
        split = any(state.get(marker) for marker in _SPLIT_MARKERS)
        if charged_since or split or _standing.moved(state, attempt.source) is not None:
            return None
        return attempt.correction is not None
    if reading.standing not in _UNLAUNCHABLE:
        return None
    launchable = _source.launchable(attempt.source.command, attempt.source.session)
    return None if reading.grants and launchable else reading.standing


def _given_up(
    gh: GitHubClient, issue: Issue, state: PinnedState, reading: _standing.CorrectionReading,
) -> _DecomposerRunPlan | None:
    """Exhaust an attempt no launch may be made for, parking a human first where no park stands.

    None lets a parked tick go on to the reply it waits on, and only once the
    attempt reads spent: an exhaustion that does not land holds the tick, so
    no resume is charged beside an attempt still pending.
    """
    parked = _replies.parked(state)
    attempt = reading.attempt
    notice = _notice(state, reading, reading.standing)
    if not parked and _notices.parks_once(gh, issue, state, attempt, notice) in _HOLDING:
        return _held(state)
    spent = _settlement.spends(gh, issue, state, attempt)
    return None if parked and spent and not state.withheld else _held(state)


def _notice(state: PinnedState, reading: _standing.CorrectionReading, unanswered: object) -> str:
    """What a park over `reading`'s attempt tells the human, `unanswered` naming why its correction answered nothing.

    The notice a park was about to post when its tick ended, where the record
    holds one (`correction_notices.owed`), is said in its own words instead.
    """
    held = _notices.owed(state, reading.attempt)
    if held is not None:
        return held
    diagnostic = reading.attempt.source.diagnostic
    why = _UNANSWERED[unanswered]
    return (
        f"{config.HITL_MENTIONS} decomposer manifest invalid ({diagnostic}); its one automatic correction {why}. "
        "Manual adjudication needed: reply to resume the decomposer session, or edit the issue to decompose it "
        "afresh."
    )


def _held(state: PinnedState) -> _DecomposerRunPlan:
    """A tick that ends here, launching nothing, keeping a checkout a standing park may be keeping for inspection."""
    return _DecomposerRunPlan(agent_result=None, keep_worktree=_replies.parked(state))
