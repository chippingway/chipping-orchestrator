# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The client a base rewrite's dormant recovery proof reads the pinned comment through, every reading asked first.

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
what it records moving under a transaction captured for the head, as the
complete dormant finish reads one still owed.

It is dormant, as that proof is: no recovery context the workflow builds
reaches it.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace

from github.Issue import Issue

from orchestrator.git.base_sync import attempt_records as _attempt_records, state as _base_sync_state
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedEdit, PinnedState
from orchestrator.workflow.engine import verification_proof as _proof, verification_records as _records
from orchestrator.workflow.engine.pinned_commit_models import PinnedCommit
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
    """`gh` for one issue's dormant recovery proof: every call passed through, each reading of its comment asked."""

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


def asks_every_reading(
    context: _AutoRebaseRecoveryContext, asks: Callable[[PinnedState], object],
) -> _AutoRebaseRecoveryContext:
    """`context` reading the GitHub client through `AsksEveryReading`, each reading of its issue's comment `asks`ed.

    Every other input is `context`'s own, its state the very one, so a finish
    built over the answer reads and writes as one built over `context` would.
    """
    return replace(context, gh=AsksEveryReading(context.gh, context.issue.number, asks))


def tip_moves(
    comment: PinnedState, attempt: PinnedCommit | None,
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
    as the complete dormant finish reads a transaction still owed
    (`rewrite_finish_settled.reads_moving`); None for each that holds.
    """
    spent = _SPENT_PAST_THE_OWED if outranks_the_owed(comment, pending) else None
    return _proof.recorded_verdict(comment, pending.binding), spent
