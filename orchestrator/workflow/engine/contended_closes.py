# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Keep a close read while another poller holds the issue, tied to a cycle only by proof.

A contender writes nothing, so the latch is the whole of what it keeps. The
poll's closed reading is older than anything the contender reads after it, so
the latch is scoped to a cycle only where the record is read first and the
issue, read behind it, is still closed; a close that cannot be confirmed is
held unresolved and ends no cycle on its own. A retirement the holder noted on
the claim stands in for the cycle the record has stopped naming.
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
    after the record named its cycle is scoped to that cycle. Reading is not
    writing, so the two reads this costs are the contender's to take; they
    decide nothing about the issue, only what this process holds.

    A close the record says ends no cycle -- none on the record, or one already
    marked over -- adds nothing, and leaves any older latch on the issue as it
    was for the pass under the claim to answer. One that is open again by the
    read behind the record, and one whose reads failed, are held UNRESOLVED:
    still routed to a pass under the claim, so the reading survives the
    contention, but ending no cycle on its own, since the cycle that pass finds
    may be the fresh one. That pass ends a cycle with it only where the issue
    is closed again under the claim.

    The holder's retirement note is asked before either read, since a holder
    that lets go during them stamps its release over it, and again behind
    them, for one that entered its retirement window meanwhile.
    """
    issue_number = int(issue.number)
    noted = _claim_notes.noted_retirement(gh.repo_id, issue_number)
    try:
        state, standing = _read_behind_the_record(gh, issue)
    except Exception:
        log.exception(
            "repo=%s issue=#%d observed closed while its writer claim was "
            "refused, and it could not be read again; holding the observation "
            "unresolved for the next pass that holds the claim",
            spec.slug, issue_number,
        )
        _observations.observe_close(spec.slug, issue_number)
        return
    cycle = _ended_cycle(gh, spec, issue_number, state, noted)
    if cycle is None:
        return
    _observations.observe_close(spec.slug, issue_number)
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


def _read_behind_the_record(gh: GitHubClient, issue: Issue) -> tuple[PinnedState, bool]:
    """The issue's record, and whether the issue still reads closed after it.

    In that order and no other: a close read behind the record was standing
    while the record named whatever cycle it names.
    """
    state = gh.read_pinned_state(issue)
    return state, issue_is_closed(gh.get_issue(int(issue.number)))


def _ended_cycle(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    state: PinnedState,
    noted: int | None,
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
    `noted` is the note the refusal found before the record was read.
    """
    late_close_reading = importlib.import_module(_stage_targets._LATE_CLOSE_READING_OWNER)
    cycle = late_close_reading._ending_cycle(spec, issue_number, state)
    if cycle is not None or _late_state.read_late_generation(state).is_present:
        return cycle
    retired = _endings.read_retired_cycle(state)
    standing = _claim_notes.noted_retirement(gh.repo_id, issue_number)
    if retired is None or retired not in {noted, standing}:
        return None
    return retired
