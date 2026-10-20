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
finish held to the dormant settled-evidence policy reads one still owed.
`stands_as_recovered` says whether a comment the proof read -- or the tick's
state, where it read none -- still carries the attempt the recovery
recovers, not one another road put in its place, which the proof asks of
every reading it kept (`AsksEveryReading.every`), so an attempt put in place
and put back between two readings holds it all the same. `LosesTheCheckout` lets the
proof read a checkout gone from disk under one of its own requests as that
loss, not raise it past the record it owes, and answers a proof whose finish
read the checkout off the landing as that loss too (`proves`), a checkout
its last word reads off the landing owed the same way (`hears`);
`RecordsALostCheckout` records that loss for a road owing it, over the
tick's state staged with what the tick staged ahead of the road alone.

They are dormant, as that proof is: no recovery context or road the workflow
builds reaches them.
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
    owed_events as _owed_events,
    pinned_commit_models as _commit_models,
    rewrite_evidence_proof as _evidence_proof,
    rewrite_landing_records as _landing_records,
    verification_proof as _proof,
    verification_records as _records,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.rewrite_finish_outranking import outranks_the_owed

# The base tip the attempt recorded its replay as made onto, the one member of
# the attempt a comment may read moved -- blanked, as a reset is recorded, or
# repointed -- beside every other member as the tick read it, a finish's
# bookkeeping aside, where any other member moved is another attempt (`tip_moves`).
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

# A checkout read off the landing -- back on the anchor, or gone from disk --
# under every evidence the tick held, however soon it is put back.
LEFT_THE_CHECKOUT = ReportEvidence(ReportEvidenceVerdict.DEFER, "the checkout left the landing: on the anchor, or gone")

# A readable revision read spent past a transaction captured for the head: it
# outranks that transaction for good, however soon the floor is put back.
_SPENT_PAST_THE_OWED = ReportEvidence(
    ReportEvidenceVerdict.DEFER, "a revision past the transaction captured for the head was read spent, outranking it",
)


class AsksEveryReading:
    """`gh` for one issue's dormant recovery proof: every call passed through, each reading of its comment asked.

    `readings` are those readings, in the order they were taken.
    """

    def __init__(self, gh: GitHubClient, issue_number: int, asks: Callable[[PinnedState], object]) -> None:
        self._gh = gh
        self._issue_number = issue_number
        self._asks = asks
        self.readings: list[PinnedState] = []

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

    def every(self, check: Callable[[PinnedState | None], bool]) -> bool:
        """Whether `check` holds of every reading taken, however soon what one read was put back; of None with none."""
        return all(check(reading) for reading in self.readings or [None])

    def _hears(self, issue: Issue, readings: Iterable[PinnedState]) -> None:
        """Hand each of `readings` that parsed to the classifier, where it is this proof's issue's comment."""
        if issue.number != self._issue_number:
            return
        for reading in readings:
            if reading.parsed:
                self.readings.append(reading)
                self._asks(reading)


class LosesTheCheckout:
    """A block a checkout gone from disk cuts short: a request of it there answered by that loss, not raised.

    For the recovery's proof (`rewrite_landing_retirement.retires_unproved`):
    a git request in a checkout gone meanwhile fails with `FileNotFoundError`,
    swallowed where the checkout is gone by then or the failure names it, for
    the proof to record that loss however soon it returned. Any other goes on.
    """

    def __init__(self, context: _AutoRebaseRecoveryContext) -> None:
        self._context = context

    def __enter__(self) -> None:
        """Enter the block, handing it nothing."""

    def __exit__(self, kind, error, trace) -> bool:
        worktree = self._context.worktree
        named = str(getattr(error, "filename", None)) == str(worktree)
        return isinstance(error, FileNotFoundError) and (named or not worktree.is_dir())

    def proves(self, *proofs: Callable[[], bool]) -> bool | None:
        """Whether every one of `proofs` answers inside the block, each asked; None for the loss the checkout is.

        None where the checkout was gone before them or a request of theirs found it gone, and where one of their own
        finishes read it off the landing (`owed_events.loss_owed`) while what a finish captured or settled for the head
        still stands, so the caller records that loss before it answers, however soon the checkout was put back.
        """
        state = self._context.state
        proved = None
        if self._context.worktree.is_dir():
            with self:
                answers = [proof() for proof in proofs]
                proved = all(answers)
        held = _landing_records.captured(state) or _landing_records.settled(state)
        if proved and held and _owed_events.loss_owed(self._context):
            return None
        return proved

    def hears(self, checkout: object) -> None:
        """Owe a checkout the last word read off the landed head as the loss of the attempt the proof recovers.

        Handed every such reading as it is taken (`rewrite_finish_models.LandedFinish.hears_the_checkout`), however a
        refusal read ahead of it is weighed, so the proof's own later readings count as its first does
        (`owed_events.owes_a_loss`), and a retirement over them refused, the head put back, still leaves the evidence
        read moving to the next proof.
        """
        if checkout is _evidence_proof.LEFT_THE_LANDING:
            _owed_events.owes_a_loss(self._context)


class RecordsALostCheckout(LosesTheCheckout):
    """A recovery road's block a checkout gone from disk cuts short, that loss recorded before the road unwinds.

    The recorder `context` carries, or `records` where handed, records the reset against the evidence for the landed
    head and retires it in writes of its own, however soon the checkout returns, the tick's state withheld for the
    road's caller to hold; over a comment carrying neither, the failure goes on. Those writes are made over the tick's
    state staged with what the tick staged ahead of the block alone -- usage, a gate's record -- so the recorder
    carries it, taken in where it lands, and nothing the block staged itself before the loss cut it short.
    """

    def __init__(self, context: _AutoRebaseRecoveryContext, records=None) -> None:
        super().__init__(replace(context, records_before_a_reset=records) if records else context)
        self._staged: dict = {}
        self._read: dict | None = None

    def __enter__(self) -> None:
        """Enter the block, what the tick's state stages as it does kept for a loss to be recorded with."""
        state = self._context.state
        self._staged = json.loads(json.dumps(state.data))
        self._read = None if state.synced is None else json.loads(state.synced)

    @classmethod
    def as_read(cls, state: PinnedState) -> PinnedState:
        """`state` as the tick last read it, nothing it staged since."""
        synced = json.loads(state.synced)
        read = PinnedState(comment_id=state.comment_id, state_data=synced, parsed=state.parsed)
        read.synced = state.synced
        return read

    def __exit__(self, kind, error, trace) -> bool:
        state = self._context.state
        records = self._context.records_before_a_reset
        lost = super().__exit__(kind, error, trace)
        if not lost or records is None or state.synced is None:
            return False
        read = self.as_read(state)
        if _landing_records.captured(read) is None and _landing_records.settled(read) is None:
            return False
        self._stages_the_ticks_own(state)
        records(self._context, lost=(self._context.worktree,))
        state.withheld = True
        return True

    def _stages_the_ticks_own(self, state: PinnedState) -> None:
        """Lay `state` as the comment it last read, staging over it what the tick staged ahead of the block alone.

        Each field the tick staged then that no write of the block has landed since is staged again as the tick
        staged it; whatever the block staged itself is dropped.
        """
        synced = json.loads(state.synced)
        before = synced if self._read is None else self._read
        own = {
            field for field in self._staged.keys() | before.keys()
            if _commit_models.spelled(self._staged, field) != _commit_models.spelled(before, field)
            and _commit_models.spelled(synced, field) == _commit_models.spelled(before, field)
        }
        state.data = {
            **{field: written for field, written in synced.items() if field not in own},
            **{field: written for field, written in self._staged.items() if field in own},
        }


def asks_every_reading(
    context: _AutoRebaseRecoveryContext, asks: Callable[[PinnedState], object],
) -> _AutoRebaseRecoveryContext:
    """`context` reading the GitHub client through `AsksEveryReading`, each reading of its issue's comment `asks`ed.

    Every other input is `context`'s own, its state the very one, so a finish
    built over the answer reads and writes as one built over `context` would.
    """
    return replace(context, gh=AsksEveryReading(context.gh, context.issue.number, asks))


def stands_as_recovered(context: _AutoRebaseRecoveryContext, read: PinnedState | None = None) -> bool:
    """Whether `read`, or `context.state` where none is handed, carries the attempt `context` recovers.

    Named by the anchor and replay it records, for a caller to hold over an
    attempt another road put in place; its base tip and bookkeeping never count.
    A caller hands the comment as it last read it, since the tick's state keeps
    the attempt it was read with however the comment was rewritten since.
    """
    state = context.state if read is None else read
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
    as a finish held to the dormant settled-evidence policy reads a transaction still owed
    (`rewrite_finish_settled.reads_moving`); None for each that holds.
    """
    spent = _SPENT_PAST_THE_OWED if outranks_the_owed(comment, pending) else None
    return _proof.recorded_verdict(comment, pending.binding), spent
