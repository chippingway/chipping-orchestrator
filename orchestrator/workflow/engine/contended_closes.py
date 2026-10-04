# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Keep a close read while another poller holds the issue, tied to a cycle only by proof.

A contender writes nothing, so the latch is the whole of what it keeps. The
poll's closed reading is older than anything the contender reads after it, so
the latch is scoped to a cycle only where the record is read first and the
issue, read behind it, is still closed -- with the record read again behind
that, naming the same cycle; a close that cannot be confirmed is held
unresolved and ends no cycle on its own. A retirement the holder noted on the
claim stands in for the cycle the record has stopped naming.

Dormant: a poll is refused an issue's writer claim only once the dispatch
takes one, and no dispatch path does yet, so nothing in production calls this
owner. It is complete for the activation that routes a refused issue here.
"""
from __future__ import annotations

import importlib
import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import issue_is_closed
from orchestrator.github.pinned_state import PinnedState
from orchestrator.scheduler import claim_notes as _claim_notes
from orchestrator.workflow.engine import observations as _observations, stage_targets as _stage_targets
from orchestrator.workflow.late_split import endings as _endings, state as _late_state

log = logging.getLogger("orchestrator.workflow")

# How many issue reads a contender takes behind its record, waiting for the
# record to name the same cycle either side of one.
_CONFIRMING_READS = 3


def _kept_contended_close(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue,
) -> None:
    """Keep a close this poll read on an issue whose writer claim it was refused.

    Latched in this process and nowhere else: the receipt that would make it
    durable is a post, and a post is the holder's to make. What a reading
    dropped here would cost is the close itself, once a human reopens the
    issue -- the stage handler its label names would resume a cycle the close
    ended.

    Scoped to a cycle, because the holder may settle the cycle the close ended
    before this process holds the issue again, and an operator may then
    authorize a fresh one: a latch that remembered only the issue would end
    that fresh cycle too, for a close that happened before it existed. But the
    holder can do that between the poll and any read this makes, so a record
    read after the closed reading says nothing about which cycle it ended. The
    record is read FIRST and the issue behind it: only a close still standing
    after the record named its cycle is scoped to that cycle. And the record is
    read again behind the issue: the holder may restart the cycle between the
    first record read and the issue read, and a close standing then may be the
    fresh cycle's, which the first read never named (`_read_behind_the_record`).
    Reading is not writing, so the reads this costs are the contender's to
    take; they decide nothing about the issue, only what this process holds.

    A close the record says ends no cycle at every read -- none on the record,
    or one already marked over -- adds nothing, and leaves any older latch on
    the issue as it was for the pass under the claim to answer. One that is
    open again by the read behind the record, and one whose reads failed,
    never found the record holding still, or found it naming a cycle and then
    none, are held UNRESOLVED: still routed to a pass under the claim, so the
    reading survives the contention, but ending no cycle on its own, since the
    cycle that pass finds may be the fresh one. That pass ends a cycle with it
    only where the issue is closed again under the claim. Every latch it keeps
    is a `fresh` reading, which withdraws a settlement this process's own
    publication hold is still postponing.

    The holder's retirement note is asked before the first read and again
    behind every read, record and issue alike and whatever the record says,
    for a holder that entered its retirement window meanwhile -- and every
    note found is kept for the rest of the reads, since a holder that lets go
    during them stamps its release over the note it left, and a confirmation
    that forgot it would read the retired cycle as ending nothing. A holder
    that notes and lets go between two asks leaves no note any of them sees,
    which is why a record that stops naming its cycle is held unresolved
    rather than read as ending nothing.
    """
    issue_number = int(issue.number)
    notes = {_claim_notes.noted_retirement(gh.repo_id, issue_number)}
    try:
        cycle, standing = _read_behind_the_record(gh, spec, issue, notes)
    except Exception:
        log.exception(
            "repo=%s issue=#%d observed closed while its writer claim was "
            "refused, and it could not be confirmed behind its record; holding "
            "the observation unresolved for the next pass that holds the claim",
            spec.slug, issue_number,
        )
        _observations.observe_close(spec.slug, issue_number, fresh=True)
        return
    if cycle is None:
        return
    _observations.observe_close(spec.slug, issue_number, fresh=True)
    if not standing:
        log.info(
            "repo=%s issue=#%d observed closed while its writer claim was "
            "refused, and open again behind its record; holding the "
            "observation unresolved, since cycle %d may have started after it",
            spec.slug, issue_number, cycle,
        )
        return
    _observations.scope_close(spec.slug, issue_number, cycle)
    log.info(
        "repo=%s issue=#%d observed closed, but its writer claim was refused; "
        "holding the observation of cycle %d and sweeping it on the next "
        "polling pass",
        spec.slug, issue_number, cycle,
    )


def _read_behind_the_record(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, notes: set[int | None],
) -> tuple[int | None, bool]:
    """The cycle a close on the issue's record ends, and whether the issue still reads closed behind it.

    The record first and the issue behind it: a close read there was standing
    while the record named whatever cycle it names. Then the record again,
    since the holder may have restarted the cycle between the two -- a close
    standing at the issue read may be the fresh cycle's, and the first record
    never named it. The answer stands only where the record read behind the
    issue ends the cycle the one before it did; otherwise the newer record is
    taken as the first and the issue read again behind it. A record that never
    holds still across `_CONFIRMING_READS` issue reads raises, holding the
    close unresolved rather than tying it to a cycle no read confirmed -- and
    so does one that named a cycle and names none behind the next issue read,
    since the close standing there may be that cycle's. `notes` gathers every
    retirement note found on the claim along the way.
    """
    issue_number = int(issue.number)
    cycle = _ended_cycle(gh, spec, issue_number, gh.read_pinned_state(issue), notes)
    for _ in range(_CONFIRMING_READS):
        standing = issue_is_closed(gh.get_issue(issue_number))
        notes.add(_claim_notes.noted_retirement(gh.repo_id, issue_number))
        confirmed = _ended_cycle(gh, spec, issue_number, gh.read_pinned_state(issue), notes)
        if confirmed == cycle:
            return cycle, standing
        if confirmed is None:
            raise RuntimeError(f"issue #{issue_number}'s record stopped naming cycle {cycle} behind an issue read")
        cycle = confirmed
    raise RuntimeError(f"issue #{issue_number}'s record moved behind every issue read")


def _ended_cycle(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    state: PinnedState,
    notes: set[int | None],
) -> int | None:
    """Which cycle a close on this record would end, as a contender can see it.

    The record's own answer, as an ordinary poll takes it. Where the record
    names no cycle at all, the holder may be the reason: a retirement takes
    the identity off the record a write before the barrier that answers a
    close, and that barrier is the holder's, reading only its own process's
    observations. The holder notes the cycle it is retiring on the claim it
    holds, and the record says which cycle a retirement last dropped; where
    the two agree, a close read now is one the holder's barrier never saw, and
    it is held against that cycle for the pass under the claim to adopt. The
    record's correlation alone is not that: it stands long after its window
    closed, so a close of an issue that has since gone back to its own work
    would otherwise be read as ending a split that already finished.
    `notes` is every note this refusal has found -- the one it found before
    the record was read, and one standing behind each read since -- and the
    note standing now, behind the read of `state`, joins it whatever the
    record says.
    """
    notes.add(_claim_notes.noted_retirement(gh.repo_id, issue_number))
    late_close_reading = importlib.import_module(_stage_targets._LATE_CLOSE_READING_OWNER)
    cycle = late_close_reading._ending_cycle(spec, issue_number, state)
    if cycle is not None or _late_state.read_late_generation(state).is_present:
        return cycle
    retired = _endings.read_retired_cycle(state)
    if retired is None or retired not in notes:
        return None
    return retired
