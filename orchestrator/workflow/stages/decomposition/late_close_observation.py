# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist and adopt closes observed while late-cycle work or retirement is in flight.

Receipt claims serialize posts and scans. A later reopen cannot erase a
close already observed, and a receipt over a retired cycle reconstructs its
cancellation before any new work can start.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github import (
    client as _client,
    issues as _issues,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import (
    observation_receipts as _observation_receipts,
    observations as _observations,
)
from orchestrator.workflow.late_split import (
    endings as _endings,
    models as _late_models,
    state as _late_state,
)
from orchestrator.workflow.stages.decomposition import (
    late_cancellation_state as _late_cancellation_state,
    late_close_reading as _late_close_reading,
)

log = logging.getLogger("orchestrator.workflow")


_OBSERVED_CLOSE_NOTICE = (
    ":no_entry: **Cancelled.** This issue was observed closed while its "
    "oversized committed candidate was still being worked, so late-split "
    "cycle {cycle} is cancelled: nothing further is adjudicated, created, or "
    "activated for it.\n\nReopening the issue does not resume that cycle. "
    "What it already put on this repository is settled by a later pass and "
    "the issue ends on `rejected`, which an operator removes to authorize a "
    "fresh attempt.\n\n{marker}"
)


def _record_observed_close(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    *,
    polled: Issue | None = None,
) -> bool:
    """Write down, on the thread, a close no pass could be handed.

    The durable half of an observation the polling thread is holding, and a
    COMMENT rather than a pinned write for the reason the observation had to
    be held in the first place: the pinned comment is written whole, and a
    second writer racing the worker that owns the issue would drop whatever
    that worker recorded in between. A comment is added, so it races nothing.

    What reads it back is the process AFTER this one. The latch covers every
    observation this process makes -- the run holding the issue asks it before
    every step the remote keeps -- and what no latch survives is a restart, so
    the receipt is here for the tick that comes up against a cycle a dead
    process was already ending.

    Skipped where there is nothing to end: an owner with no cycle, and one
    whose record already carries the mark. Skipped too where the thread
    already says it, since a receipt is one sentence rather than one per poll
    that observes the same close.

    Retried, though, for as long as the thread does not have one. Raising
    here would cost the tick that was posting it, so a refusal is logged and
    the latch carries the observation meanwhile -- but a latch is memory, and
    an observation whose receipt never landed is one a restart takes away
    entirely. So the memo that suppresses the second attempt is written by
    the attempt that SUCCEEDED, and every later poll tries again until one
    does.

    Under a claim, because asking and posting cannot be made one operation.
    The claim is what stops two polls in that gap -- a worker's failed pass
    and the next tick's enumeration meet there -- from walking the same
    receipt-less thread and posting one apiece, and it carries the GENERATION
    of the reading it was taken for: a cleanup settling the observation
    mid-post has already dropped the memo on purpose, and re-creating it
    would suppress the next close's receipt for a reading nobody holds. Handed
    back either way, since a claim over an attempt that ended would suppress
    every later poll's receipt for good.

    Answers whether the reading is one a later pass still has to be handed,
    off the SAME record read the receipt was written from. The two questions
    were once asked of two reads, and two reads of a record a worker is
    writing can disagree: one saw a cycle and kept the observation while the
    other saw the retirement behind it and left the thread saying nothing, so
    the reading survived in memory alone and a restart took it. One read
    answers both, and a read that established nothing keeps the reading --
    which is the answer a request that failed is entitled to give.

    `polled` is the object the caller already has, where it has one. The
    enumeration writes the receipt from the issue it just listed rather than
    fetching the same one again, which is the whole of what asking at poll
    time costs over asking at the end of a pass: one pinned read.
    """
    claim = _observation_receipts.claim_receipt_post(spec.slug, issue_number)
    if claim is None:
        return _late_close_reading._owns_a_live_cycle(gh, spec, issue_number) is not False
    try:
        cycle = _observed_close_posted(gh, spec, issue_number, polled=polled)
    except Exception:
        log.exception(
            "repo=%s issue=#%d observed closed, but the receipt saying so "
            "could not be posted; the observation is held in memory only "
            "until a later poll gets one onto the thread, and a restart "
            "before then would lose it",
            spec.slug, issue_number,
        )
        _observation_receipts.release_receipt_post(claim)
        return True
    _observation_receipts.receipt_written(claim)
    return cycle is not None


def _observed_close_posted(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    *,
    polled: Issue | None = None,
) -> int | None:
    """Post this cycle's close receipt, unless something already says it.

    Answers which cycle this observation belongs to, having discharged the
    receipt in three ways rather than one: the post landed, the thread
    already carries it, or there is nothing for it to say -- an owner with no
    cycle a close would end, which is a state no later reader needs a receipt
    for and the caller drops the reading on.
    """
    issue = gh.get_issue(issue_number) if polled is None else polled
    state = gh.read_pinned_state(issue)
    cycle = _late_close_reading._ending_cycle(
        spec, issue_number, _late_state.read_late_generation(state),
    )
    if cycle is None:
        return None
    marker = _late_close_reading._observed_close_marker(issue_number, cycle)
    if _late_close_reading._carries_observed_close(gh, issue, marker):
        return cycle
    gh.comment(issue, _OBSERVED_CLOSE_NOTICE.format(
        cycle=cycle, marker=marker,
    ))
    log.warning(
        "repo=%s issue=#%d observed closed while a worker held it; its late "
        "cycle %d is cancelled and the thread now says so",
        spec.slug, issue_number, cycle,
    )
    return cycle


def _mark_observed_close(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState,
) -> None:
    """Mark a live cycle on an issue the POLL read closed.

    The dispatcher's own reading, applied where it can still change
    something. It is BOUND to the task rather than re-derived because the
    worker refetches the issue after the poll classified it: a human who
    reopens in that window would have the fresh object say open, and the
    close the poll saw would be gone with nothing left to end the cycle.

    Nothing to do where the record carries no cycle or already carries the
    mark, which is every closed issue but the narrow window this exists for.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.is_present or generation.cancelled:
        return
    log.warning(
        "issue=#%s was read closed by the poll that classified it and wears "
        "a LIVE late cycle; ending cycle %d rather than dispatching it on a "
        "reading a reopen has since taken away",
        issue.number, generation.cycle_id,
    )
    _late_cancellation_state._marked(gh, issue, state, generation)


def _closed_under_a_label(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Mark a live cycle whose owner this dispatch can see is already closed.

    The cleanup route takes a closed owner on either label an adjudication
    runs under, so what reaches HERE closed is one whose label names an
    ordinary terminal instead: the `implementing` an authorized settlement
    hands the issue to a moment before it retires the cycle. A close landing in
    that window is one nothing else would ever end -- the terminal arc that
    label names drains a merged pull request or a human close and writes the
    late record off nowhere, and the relabel guard beside it merely puts
    `decomposing` back, which a reopen before the next tick takes away again.

    An observed close ends the cycle, so it is marked here and the ending
    below runs from the mark like any other. Costs no request: the reading is
    the issue this guard was handed, and the record is the one it already
    read.

    This is the FRESH reading, taken of the issue the worker refetched. The
    poll's own is bound to the task and applied by `_mark_observed_close`
    ahead of this guard, because a human who reopens between the two would
    otherwise take it away -- so the two together cover a close whichever
    side of the refetch it landed on.
    """
    if generation.cancelled or not _issues.issue_is_closed(issue):
        return generation
    log.warning(
        "issue=#%s is closed and wears %r over a LIVE late cycle; ending "
        "cycle %d rather than leaving it for a label that would not",
        issue.number, gh.workflow_label(issue), generation.cycle_id,
    )
    return _late_cancellation_state._marked(gh, issue, state, generation)


def _inherited_close(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Adopt a close a process that is gone observed and never settled.

    An in-memory latch dies with the process holding it, and a close observed
    against a worker is exactly the reading no tick after that process has any
    other way to take: the issue may well be open again, and its record still
    says the cycle is live. So the thread is asked, and a receipt there is as
    good as the reading that produced it -- the cycle is marked cancelled
    here, and the ending below runs from the mark like any other.

    Asked ONCE per owner per process, which is what keeps it off the wire in
    the steady state. What it recovers is an observation a DEAD process was
    holding; every observation this one makes is in the latch already, and the
    latch costs no request at all. So a thread that carries no receipt is
    walked on the first tick that sees this owner and never again.

    Once it has actually ANSWERED, that is. A claim standing over a walk that
    raised would send every later tick straight past the receipt and on to
    the live stage handler, which is the one thing this exists to prevent --
    so the claim is held for the length of the walk and handed back by an
    exception leaving it, and the tick fails where it stands, exactly as the
    pinned read above it does.
    """
    if generation.cancelled:
        return generation
    with _observation_receipts.scanning_receipt(spec.slug, issue.number) as claimed:
        if not claimed:
            return generation
        marker = _late_close_reading._observed_close_marker(issue.number, generation.cycle_id)
        if not _late_close_reading._carries_observed_close(gh, issue, marker):
            return generation
    log.warning(
        "repo=%s issue=#%s carries a receipt for a close its own record "
        "never recorded; adopting that observation and ending cycle %d",
        spec.slug, issue.number, generation.cycle_id,
    )
    return _late_cancellation_state._marked(gh, issue, state, generation)


def _latched_close_ends(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> bool:
    """Mark a latched close on this owner, and say whether the walk stops.

    The barrier a handler already inside its own walk takes. The dispatcher's
    guard asked the same question before the label became this call, but a
    dependency-graph scan is a request per child and the poll runs beside it:
    a close latched in the middle of one reaches no other pass, and what the
    walk would otherwise do next is reclaim a remote, hand the issue its
    terminal, or start an agent on a child.

    Marking is the whole of what happens here, which is the same bargain the
    post-agent guard makes: the mark says the cycle is over, every gate below
    reads it, and what the remote is still owed is settled by the ending --
    from the closed-owner sweep if the issue is closed by then, and from the
    dispatcher's own guard if a human has reopened it. Doing that work HERE
    would be doing it on a reading this walk cannot trust.

    True only where there is a cycle to end. An umbrella the initial
    decomposer made carries no generation, and a latched close against one is
    a closed issue the ordinary terminals own.
    """
    if not _observations.close_observed(spec.slug, issue.number):
        return False
    generation = _late_state.read_late_generation(state)
    if not generation.is_present:
        return False
    log.warning(
        "repo=%s issue=#%s was observed closed while its children were being "
        "walked; ending cycle %d rather than acting on that walk",
        spec.slug, issue.number, generation.cycle_id,
    )
    _late_cancellation_state._marked(gh, issue, state, generation)
    return True


def _retired_close_adopted(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
) -> _late_models.LateGeneration | None:
    """Put back a cycle a retirement dropped, if a close was seen inside it.

    The one window the reinstatement behind the retirement write cannot cover
    for itself: that barrier is this process's memory, and a process that dies
    between the write and it leaves a record with no cycle identity and a
    receipt on the thread naming one. Nothing else would ever look at that
    receipt -- the guard above returns on a record with no cycle, and the
    closed-owner sweep reads the same field to decide anything is owed.

    So the retirement records which cycle it dropped, and this is what reads
    it back. The thread is asked exactly once per owner per process, under the
    same claim the inherited-close scan takes and for the same reason: what it
    recovers is an observation a DEAD process was holding, and one this
    process makes is in the latch already.

    The cycle goes back with the ledgers the retirement carried across and an
    identity rebuilt beside them -- see `_reconstructed`, which is what makes
    the ending REPORTABLE as well as runnable.

    Marked here rather than left for the inherited-close scan behind it,
    because the two share one claim: this walk is the one that answered, so
    it is the one that records what it found. What comes back is a record
    that already says the cycle is over, and the ending below runs from it
    like any other.

    None wherever there is nothing to adopt: a record no retirement wrote, a
    thread that carries no receipt for the cycle it names, and a walk that
    could not answer -- which hands its claim back and leaves the tick to the
    dispatcher's own per-issue isolation.
    """
    retired = _endings.read_retired_cycle(state)
    if retired is None:
        return None
    with _observation_receipts.scanning_receipt(spec.slug, issue.number) as claimed:
        if not claimed:
            return None
        marker = _late_close_reading._observed_close_marker(issue.number, retired)
        if not _late_close_reading._carries_observed_close(gh, issue, marker):
            return None
    log.warning(
        "repo=%s issue=#%s carries a receipt for a close observed inside the "
        "write that retired cycle %d; putting that cycle back so the ending "
        "has something to run from",
        spec.slug, issue.number, retired,
    )
    return _late_cancellation_state._marked(
        gh, issue, state,
        _late_cancellation_state._reconstructed(issue, state, retired),
    )
