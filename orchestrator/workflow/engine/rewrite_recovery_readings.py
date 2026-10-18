# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The client a base rewrite's recovery proof reads the pinned comment through, every reading asked first.

The proof before a park or hold that keeps the attempt
(`rewrite_landing_retirement.retires_unproved`) builds finishes of its own,
whose helpers -- the last word, an abandonment and its reconciliation, an
invalidation and its rechecks -- read the comment again of their own accord.
A successor read beside a blanked tip there, the tip put back behind it, is
movement no later proof would read. So those finishes, and a park's or hold's
record (`rewrite_recovery_parks`), read through `AsksEveryReading`
(`asks_every_reading`): every call passes through, and each parsed reading of
the issue's comment -- the comment a strict edit found moved, and the reread
behind a refusal for room, among them -- is handed to the proof's classifier
first.

`tip_moves` reads what a reading's base tip records moving for that
classifier (`rewrite_landing_retirement.moved_under`): blank or repointed
beside the attempt as the tick read it, every evidence; blank beside an
attempt still standing, evidence the tick never held. `owed_moves` reads
what it records moving under a transaction captured for the head, as a
finish held to the settled-evidence policy reads one still owed.
`stands_as_recovered` says whether the tick's state, once the proof's
rechecks laid what they read over it, still carries the attempt the
recovery recovers rather than one another road put in its place.
`LosesTheCheckout` lets the proof read a checkout gone from disk under one of
its own requests as that loss, rather than raise it past the record it owes,
and `RecordsALostCheckout` records that loss for a road that owes it.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import replace

from github.Issue import Issue

from orchestrator.git.base_sync import attempt_records as _attempt_records, state as _base_sync_state
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedEdit, PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_landing_records as _landing_records,
    verification_proof as _proof,
    verification_records as _records,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.rewrite_finish_outranking import outranks_the_owed

# The base tip the attempt recorded its replay as made onto, the one member of
# the attempt a comment may read moved -- blanked, as a reset is recorded, or
# repointed -- beside every other member as the tick read it, where any other
# member moved is another attempt (`tip_moves`).
_TIP_ALONE = (_base_sync_state._PENDING_REWRITE_BASE,)

# What that move is under the evidence the comment carries for the landed
# head: no base the tick read proves which one its head was replayed onto,
# however soon the tip is put back.
_TIP_MOVED_UNDER_THE_RECORD = ReportEvidence(
    ReportEvidenceVerdict.DEFER, "the base tip the attempt recorded its replay as made onto moved under a record",
)

# What evidence the tick never held is, read beside an attempt that still
# stands and records no base tip: nothing proves which base its head was
# replayed onto, however soon the tip is put back.
_SETTLED_UNBASED = ReportEvidence(
    ReportEvidenceVerdict.DEFER, "evidence was read beside an attempt that records no base tip its head was made onto",
)

# A readable revision read spent past a transaction captured for the head: it
# outranks that transaction for good, however soon the floor is put back.
_SPENT_PAST_THE_OWED = ReportEvidence(
    ReportEvidenceVerdict.DEFER, "a revision past the transaction captured for the head was read spent, outranking it",
)


class AsksEveryReading:
    """`gh` for one issue's recovery proof: every call passed through, each reading of its comment asked."""

    def __init__(self, gh: GitHubClient, issue_number: int, asks: Callable[[PinnedState], object]) -> None:
        self._gh = gh
        self._issue_number = issue_number
        self._asks = asks

    def __getattr__(self, name: str):
        return getattr(self._gh, name)

    def read_pinned_state(self, issue: Issue) -> PinnedState:
        """The comment `issue` pins, read through and asked."""
        read = self._gh.read_pinned_state(issue)
        self._hears(issue, (read,))
        return read

    def edit_pinned_state(self, issue: Issue, state: PinnedState, **options) -> PinnedEdit:
        """The strict edit, sent through, the comment it found moved asked.

        The edit keeps the comment its walk read where it answers MOVED only
        in a `seen` it is handed, so one is handed where the caller's guard
        asked for none.
        """
        if options.get("seen") is None:
            options["seen"] = []
        seen = options["seen"]
        before = len(seen)
        edit = self._gh.edit_pinned_state(issue, state, **options)
        self._hears(issue, seen[before:])
        return edit

    def _hears(self, issue: Issue, readings: Iterable[PinnedState]) -> None:
        """Hand each of `readings` that parsed to the classifier, where it is this proof's issue's comment."""
        if issue.number != self._issue_number:
            return
        for reading in readings:
            if reading.parsed:
                self._asks(reading)


class LosesTheCheckout:
    """A block a checkout gone from disk cuts short: a request of it there answered by that loss, not raised.

    For the recovery's proof (`rewrite_landing_retirement.retires_unproved`),
    which reads the checkout well after its caller found it on disk: a git
    request run in a checkout gone meanwhile fails with `FileNotFoundError`,
    swallowed here only where the checkout is gone by then, for the proof to
    read that loss and record it. Any other failure, or one over a checkout
    still on disk, goes on.
    """

    def __init__(self, context: _AutoRebaseRecoveryContext) -> None:
        self._context = context

    def __enter__(self) -> None:
        """Enter the block, handing it nothing."""

    def __exit__(self, kind, error, trace) -> bool:
        return isinstance(error, FileNotFoundError) and not self._context.worktree.is_dir()


class RecordsALostCheckout(LosesTheCheckout):
    """A recovery road's block a checkout gone from disk cuts short, that loss recorded before the road unwinds.

    The reset is recorded against what a finish captured or settled for the
    landed head, and that retired as over it, each in a write of its own, by
    the recorder `context` carries (`records_before_a_reset`), over the
    comment as the tick last read it, so nothing the road staged rides them;
    the tick's state is withheld from every whole-state write behind, and the
    road's caller holds the tick. Where the comment carries nothing a finish
    captured or settled for the head, the failure goes on as before.
    """

    def __exit__(self, kind, error, trace) -> bool:
        state = self._context.state
        records = self._context.records_before_a_reset
        lost = super().__exit__(kind, error, trace)
        if not lost or records is None or state.synced is None:
            return False
        read = PinnedState(comment_id=state.comment_id, state_data=json.loads(state.synced))
        read.synced = state.synced
        if _landing_records.captured(read) is None and _landing_records.settled(read) is None:
            return False
        records(replace(self._context, state=read))
        state.withheld = True
        return True


def asks_every_reading(
    context: _AutoRebaseRecoveryContext, asks: Callable[[PinnedState], object],
) -> _AutoRebaseRecoveryContext:
    """`context` reading the GitHub client through `AsksEveryReading`, each reading of its issue's comment `asks`ed.

    Every other input is `context`'s own, its state the very one, so a finish
    built over the answer reads and writes as one built over `context` would.
    """
    return replace(context, gh=AsksEveryReading(context.gh, context.issue.number, asks))


def stands_as_recovered(context: _AutoRebaseRecoveryContext) -> bool:
    """Whether `context.state` still carries the attempt `context` recovers, rather than another in its place.

    The proof's rechecks lay an attempt another road put in place over the
    tick's state as read, so the caller holds over it rather than routing past
    it. The anchor and the replay the attempt records are what name it; its
    base tip and the bookkeeping a finish of its landing puts down move under
    the very same attempt, so neither counts.
    """
    state = context.state
    read = (state.get(_base_sync_state._PENDING_PUSH_SHA), _attempt_records._pending_rewrite(state))
    return read == (context.pending_pre_rebase_sha, context.pending_rewrite)


def tip_moves(
    comment: PinnedState, attempt: _commit_models.PinnedCommit | None,
) -> tuple[ReportEvidence | None, ReportEvidence | None]:
    """What `comment`'s base tip records moving: under evidence the tick held, then under evidence it never held.

    `attempt` is the attempt the tick read, where its reading recorded a tip
    (`rewrite_landing_retirement.attempt_as_read`): `comment` reading that tip
    blank or repointed, every other member as the tick read it, moves both.
    Evidence the tick never held is moved too where `comment` still carries an
    attempt and records no tip -- a blank the tick read as well, which the
    proofs of the evidence it held already read. None for each nothing moves.
    """
    tipped = None
    if attempt is not None and attempt.moved(comment.data) == _TIP_ALONE:
        tipped = _TIP_MOVED_UNDER_THE_RECORD
    unbased = tipped
    if comment.get(_base_sync_state._PENDING_PUSH_SHA) and not _attempt_records._recorded_onto(comment):
        unbased = unbased or _SETTLED_UNBASED
    return tipped, unbased


def owed_moves(comment: PinnedState, pending: _records.PendingEvidence) -> tuple[ReportEvidence | None, ...]:
    """What `comment` refuses `pending`, a transaction captured for the head, over: records, then a revision past it.

    A review or report record off its binding (`verification_proof.recorded_verdict`)
    and a readable revision spent past it (`rewrite_finish_outranking.outranks_the_owed`),
    as a finish held to the settled-evidence policy reads a transaction still owed
    (`rewrite_finish_settled.reads_moving`); None for each that holds.
    """
    spent = _SPENT_PAST_THE_OWED if outranks_the_owed(comment, pending) else None
    return _proof.recorded_verdict(comment, pending.binding), spent
