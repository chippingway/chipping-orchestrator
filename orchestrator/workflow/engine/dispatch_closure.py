# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Keep poll and refetch close readings durable across processing and refused submissions.

The shared observation registry retains a close until its cycle is settled.
Receipt recording is resolved on its stage owner, and a refused worker
submission preserves the cleanup obligation for the next poll -- written down
under the issue's writer claim, or left as the enumeration latched it where
that claim is refused.
"""
from __future__ import annotations

import contextlib
import importlib
import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import (
    issue_is_closed,
)
from orchestrator.scheduler import claim_notes as _claim_notes
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    observations,
    poll_models as _poll_models,
    stage_targets as _stage_targets,
)

log = logging.getLogger("orchestrator.workflow")


# The three ways a cleanup observation goes unspent, said in the one line that
# holds it, so an operator watching a closed owner sit still for a tick can
# tell a worker holding the issue from a pass that reached it and broke, and
# either from a pass that ran the whole ending, left it owed, and could not
# get the issue back under a label a later tick would find it by.
_HELD_BY_A_WORKER = "a worker is already running it"


def _recorded_at_poll(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    read_at: int | None,
) -> bool:
    """Latch this closed reading and get its durable half written.

    Latched FIRST, because the reading is the one thing this exists to keep
    and everything after it is a request that can fail. Dropped again only
    where the record positively says there is nothing to end -- a closed issue
    with no late cycle is owed a turn, not an observation, and carrying one
    would send it through a cleanup pass it never earned. `read_at` is a
    moment no later than the read `issue` is, which the latch keeps.

    Answers whether the reading was kept, so a caller that has to hold one
    across the pass it is handing it to knows whether it is holding anything.
    """
    issue_number = int(issue.number)
    observations.observe_close(spec.slug, issue_number, read_at)
    late_close_observation = importlib.import_module(_stage_targets._LATE_CLOSE_OBSERVATION_OWNER)
    if late_close_observation._record_observed_close(
        gh, spec, issue_number, polled=issue,
    ):
        return True
    observations.settle_close(spec.slug, issue_number)
    return False


@contextlib.contextmanager
def _refetched_close(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    reading: _poll_models._PollReading,
):
    """Hold a close the REFETCH established and the enumeration could not.

    An issue open when it was listed and closed by the time its pass refetches
    it carries a reading nothing else in this process holds: no latch was
    taken, because there was nothing to latch, and nothing was written down.
    Every step behind the refetch can fail -- the pinned read the guard is
    built on, the write that marks the cancellation -- and a human who reopens
    the issue before the next poll takes the reading off the remote for good,
    leaving the stage handler its label names to resume a cycle a close ended.

    So it is taken here, where it first exists and before anything acts on it,
    exactly as the enumeration takes its own: latched, written down from the
    same object, and dropped again where the record says there is nothing to
    end. What the pass then does with it is the ordinary thing -- the guard
    reads the same close off the same object -- and what a pass that could not
    finish leaves behind is the reading, held for the next tick.

    A pass already carrying a closed reading holds nothing here: the poll's
    own is the older of the two and is already latched and already written.

    The moment it is latched at is read after the refetch, which is sound
    only because the refetch was taken under this pass's claim: every other
    poller's hold this process can find had ended before the claim was
    granted, so none falls between the read and the moment.
    """
    if reading.closed or not issue_is_closed(issue):
        yield
        return
    read_at = _claim_notes.moment()
    if not _recorded_at_poll(gh, spec, issue, read_at):
        yield
        return
    with _closed_reading(gh, spec, int(issue.number), read_at):
        yield


def _refused_submit(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    reading: _poll_models._PollReading,
) -> None:
    """Hold whatever observation a refused fan-out submit was carrying.

    A cleanup route already says a late owner was observed closed, so the
    reading is latched on the strength of the route alone. A closed issue on
    any OTHER label may be carrying the same reading and no label says so: an
    authorized settlement hands its issue to `implementing` a moment before it
    retires the cycle, and a close landing in that window wears a label whose
    handler is an ordinary terminal.

    That one was latched by the enumeration that read it closed, and is
    dropped here only where the record positively says there is nothing to
    end. The order is the whole of it: the probe is a request, and a request
    can fail or can land after the very retirement it was asking about -- so
    a reading conditioned on it would be lost to either, and the reading is
    the one thing this path exists to keep. A latch held over an issue with
    no cycle costs the next tick one cleanup pass that settles it; a reading
    dropped costs the close itself.

    Both read the record and post on the thread, so both are taken under the
    issue's writer claim -- `alongside` the worker of this process a duplicate
    refusal names, since the receipt is a comment built to be written beside
    it. A claim another poller holds, or one that could not be worked, leaves
    the latch as the partition left it: the enumeration took this tick's
    closed reading under the same claim, or kept it as a contender where that
    claim was refused, so there is nothing newer here to keep. The moment the
    reading was taken at goes into the latch with it.
    """
    if not (reading.cleanup_only or reading.closed):
        return
    with _issue_processing._writer_claim(
        gh, spec, issue_number, alongside=True,
    ) as held:
        if not held:
            return
        if reading.cleanup_only:
            _deferred_cleanup(gh, spec, issue_number, _HELD_BY_A_WORKER)
            return
        _kept_closed_reading(gh, spec, issue_number, reading.read_at)


@contextlib.contextmanager
def _closed_reading(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    read_at: int | None = None,
):
    """Hold one closed issue's reading across the pass that would spend it.

    Asked on the way out however the pass ends, because a pass can fail to
    spend the reading without failing at all: the pinned read the guard is
    built on answers a refusal of its own, so a tick that could not read the
    record refuses the issue and marks nothing. What a pass that DID mark it
    leaves behind is a record positively saying there is nothing to end,
    which is exactly what drops the reading again. `read_at` is the moment
    the reading was taken at, where its taker knew one.
    """
    try:
        yield
    finally:
        _kept_closed_reading(gh, spec, issue_number, read_at)


def _kept_closed_reading(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    read_at: int | None = None,
) -> None:
    """Hold a closed reading no pass acted on, unless the record says not to.

    Latched FIRST and dropped again only where the record positively says
    there is nothing to end. The order is the whole of it: the probe is a
    request, and a request can fail -- so a reading conditioned on it would be
    lost to that, and the reading is the one thing this path exists to keep. A
    latch held over an issue with no cycle costs the next tick one cleanup
    pass that settles it; a reading dropped costs the close itself.

    The probe and the durable receipt are ONE read for the same reason. They
    ask the same record about the same reading, and two reads of a record the
    worker is writing can disagree: one saw a cycle and kept the observation
    while the other saw the retirement behind it and left the thread saying
    nothing, which leaves the reading in memory alone for a restart to take.
    So the owner writes the receipt from the read that decides this, and
    answers with what that read established.
    """
    observations.observe_close(spec.slug, issue_number, read_at)
    late_close_observation = importlib.import_module(_stage_targets._LATE_CLOSE_OBSERVATION_OWNER)
    if not late_close_observation._record_observed_close(gh, spec, issue_number):
        observations.settle_close(spec.slug, issue_number)
        return
    _said_deferred(spec, issue_number, _HELD_BY_A_WORKER)


def _deferred_cleanup(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    reason: str,
) -> None:
    """Latch a close no pass took, say why, and write it down once.

    A cleanup submission is the only kind whose loss costs an OBSERVATION
    rather than a turn: this poll saw the issue closed, and a human who
    reopens it before the next pass takes that reading away. Two things can
    cost one. The scheduler admits no second worker for an issue one is
    already running, so a submit can be refused outright; and a pass that was
    admitted can fail before it has marked anything.

    Either way the reading is latched rather than discarded, and it is read
    by both of the parties that could not otherwise have it. The next tick
    routes the issue to the sweep on the strength of it -- whatever the issue
    reads as by then -- and the run already holding the issue asks the same
    latch before every step the remote keeps, so a close it could never see
    for itself still ends its cycle where it stands.

    The durable half is attempted by every pass that latches one and settled
    by the first that lands it. A comment rather than a pinned write for the
    reason the latch exists at all -- the pinned comment is written whole, so
    writing it from here would drop whatever the worker holding the issue
    recorded in between -- and retried rather than tried once, because a post
    GitHub refuses leaves an observation with no durable half at all, which a
    restart before the run reaches a barrier takes away for good. The owner
    itself is what bounds the repeats: it writes nothing where the thread
    already says this, and remembers the attempt that landed.
    """
    observations.observe_close(spec.slug, issue_number)
    _said_deferred(spec, issue_number, reason)
    late_close_observation = importlib.import_module(_stage_targets._LATE_CLOSE_OBSERVATION_OWNER)
    late_close_observation._record_observed_close(gh, spec, issue_number)


def _said_deferred(
    spec: _config_models.RepoSpec, issue_number: int, reason: str,
) -> None:
    """Say what was held, so an operator can tell one hold from the other."""
    log.info(
        "repo=%s issue=#%d observed closed with a late cycle to settle, but "
        "%s; holding the observation and sweeping it on the next polling "
        "pass",
        spec.slug, issue_number, reason,
    )
