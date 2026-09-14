# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Frozen late-generation identity, measurement, and lifecycle state.

Verdict and failure vocabularies preserve their pinned JSON wire values.
Publication context and external obligations are frozen component records
with their own validation and updates. The generation owns the ordered child
register and transaction boundaries, including the first cancellation stamp
and the phase at which that cancellation was observed. The state reader and
encoders map these records onto the flat pinned-state contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.workflow.late_split import (
    formats as _formats,
    phases as _late_phases,
)
from orchestrator.workflow.late_split.obligations import LateObligations
from orchestrator.workflow.late_split.publication import PublicationContext

# How deep automatic splitting may go. The root issue of a lineage is depth 0,
# so a generation may only split while its own depth is strictly below this:
# the deepest child a split can create sits exactly at the bound and must
# resolve as one change or ask a human. It is a safety invariant, not a knob,
# which is why no configuration reads it.
MAX_LINEAGE_DEPTH = 3


class LateVerdict(StrEnum):
    """What one late adjudication decided about an oversized candidate."""

    SINGLE = "single"
    SPLIT = "split"
    QUESTION = "question"


class LateFailure(StrEnum):
    """The typed failures a late reconciliation records instead of guessing.

    None of them is "small": each names the step that could not be completed,
    so the retry that follows reconciles that step rather than re-running the
    agent whose work it was about to publish.
    """

    MEASUREMENT_FAILED = "measurement_failed"
    PLAN_PR_HOLD_FAILED = "plan_pr_hold_failed"
    OWNER_READ_FAILED = "owner_read_failed"
    PR_RECONCILE_FAILED = "pr_reconcile_failed"
    SNAPSHOT_FAILED = "snapshot_failed"
    CHILD_CREATE_FAILED = "child_create_failed"
    SUPERSESSION_FAILED = "supersession_failed"
    BRANCH_CLEANUP_FAILED = "branch_cleanup_failed"
    SNAPSHOT_DELETE_FAILED = "snapshot_delete_failed"
    RESTART_FAILED = "restart_failed"


@dataclass(frozen=True)
class LateGeneration:
    """One late generation's whole durable record.

    An issue that never entered the late gate reads back as this record's
    defaults, which is what `is_present` answers on: the fields are additive,
    so a legacy pinned comment needs no migration and writing an absent
    generation back adds no key to it.

    The obligations record's two `opaque_*` fields are the ledgers this binary
    could not fully type, kept verbatim rather than reduced to what it understood. An
    obligation dropped on read would be an obligation dropped on the next
    write, and a snapshot whose consumer ledger was silently emptied reads as
    one nobody is waiting on -- so what cannot be typed is carried through
    untouched and `obligations.is_opaque` says so out loud.

    `split_children` and `links_announced` are the split transaction's own
    receipts, and they live on the generation rather than beside the stage's
    shared keys precisely because they have to be scoped to ONE adjudication.
    The stage's `children` list belongs to whichever decomposition last wrote
    it -- an issue that was decomposed, saw its children resolve, and then
    implemented an oversized candidate still carries the old one -- so a
    transaction reading it would adopt completed issues by manifest index.
    `split_children` is ordered and positional for the same reason: entry `i`
    is the child that owns slice `i` of this manifest.

    `owner_check_pending` is the one field that records an unfinished READ
    rather than a fact about the candidate: a completed run whose owner could
    not be re-read leaves it set, and while it is set no later tick may treat
    this generation as settled, however small, decided, or parked it looks.
    It is durable because nothing else would bring the workflow back to that
    read -- a below-threshold revision and an issue parked for a human both
    stop the tick long before the guard would run again.

    `measurement_miss_count` and `measurement_failure` are the record of a
    reading that did NOT happen, and they are durable because nothing else
    remembers one: every tick is a fresh process, so a gate holding the count
    in memory would either re-read a permanently broken pair forever or spend
    a human on the first reading a fetch happened to interrupt. The count is
    how many consecutive readings this CANDIDATE has lost. The failure is the
    step a NOTICE about it named -- written by the roads that tell a human and
    by no other, so a park still standing can ask whether the sentence already
    on the thread covers what the reading in hand stopped at, and dropped by
    the verdict a reading that HAPPENED settles, which is the first point
    every step it could have stopped at is behind it. It is kept typed
    because the members are different next moves: a base this clone does not
    hold is a fetch that brought nothing back, and a diff nothing here can pin
    is a checkout an operator has to clear first. Both are scoped to the
    CANDIDATE rather than to the generation counter beside it: a base the
    remote would not name records no base at all, so the next reading of that
    same commit freezes afresh under a new generation, and misses reset there
    would never reach their bound. A candidate that MOVED is fresh work whose
    reading nobody has lost yet, so its own count starts at zero rather than
    inheriting one taken over a commit nothing measures any more.

    `plan_pr_number`, `plan_pr_head`, and `plan_pr_body` are one hold's whole
    record: the pull request a cycle-marked notice was written onto, the tip
    it was standing on when that happened, and the description the notice
    replaced. The `plan_pr` spelling is what live pinned comments carry, so it
    stays; what the group NAMES is whichever pull request the cycle holds --
    the plan one a discussion left standing where the generation was entered
    before publication, and the implementation one the work is already on
    where it was entered past it. The head is a reading rather than a claim:
    it says which change wore the notice, and it is not `published_sha` one
    field over, which is the tip the GATE was entered on and the evidence a
    settlement pins its push to. A hold reads the head it marks and never
    writes that one.

    The publication record's `post_publication`, `source_stage`,
    `published_pr_number`, and `published_sha` say a generation was
    entered on work the remote already has. A record carrying none of them was
    entered before publication, so a pinned comment written without the group
    answers the question without having been touched.
    `publication.is_complete` is what a caller asks about the context: the
    three fields are read as fail-closed as every other, a marker standing
    alone would claim a pull request nothing could name, and the stage is
    asked what it is rather than merely whether it is there -- only the five
    states that publish onto a pull request the remote already carries name
    an entry anything may be reconciled from.
    """

    cycle_id: int = 0
    generation: int = 0
    root_issue: int = 0
    current_issue: int = 0
    lineage_depth: int | None = None
    scope: str = ""
    candidate_sha: str = ""
    base_sha: str = ""
    threshold: int | None = None
    additions: int | None = None
    measurement_miss_count: int = 0
    measurement_failure: MeasurementFailure | None = None
    phase: _late_phases.LatePhase | None = None
    title_body_hash: str | None = None
    comment_hash: str | None = None
    comment_watermark_id: int | None = None
    plan_pr_number: int | None = None
    plan_pr_head: str = ""
    plan_pr_body: str | None = None
    publication: PublicationContext = field(default_factory=PublicationContext)
    obligations: LateObligations = field(default_factory=LateObligations)
    split_children: tuple[int, ...] = ()
    links_announced: bool = False
    owner_check_pending: bool = False
    cancelled: bool = False
    cancelled_at: str | None = None
    cancelled_phase: _late_phases.LatePhase | None = None
    restart_pending: bool = False
    restart_target: str | None = None
    restart_cycle_id: int | None = None
    restart_predecessor: int | None = None

    @property
    def is_present(self) -> bool:
        """Whether a late cycle was ever recorded on this issue."""
        return self.cycle_id > 0

    @property
    def is_oversized(self) -> bool:
        """Whether the measurement is strictly past the threshold it named.

        Strictly: a candidate exactly at the configured value is accepted, so
        the trigger cannot move by one line when the threshold is retuned. An
        unmeasured generation is not oversized -- a missing measurement is a
        typed failure to reconcile, never a small candidate.
        """
        if self.threshold is None or self.additions is None:
            return False
        return self.additions > self.threshold

    @property
    def may_split(self) -> bool:
        """Whether this generation is allowed to create another one.

        Read fail-closed, so every depth that is not a real one below the
        bound refuses the split rather than unlocking a generation the cap
        exists to forbid: a depth at or past the bound, a negative one, one
        that is not a whole number at all, and an unknown one -- which is what
        a damaged or missing field on a recorded cycle reads back as -- all
        answer False.
        """
        if not _formats.whole_number(self.lineage_depth):
            return False
        return 0 <= self.lineage_depth < MAX_LINEAGE_DEPTH

    @property
    def split_has_settled(self) -> bool:
        """Whether this record's candidate has been made into children.

        Two readings of one fact, because either can be the only one there.
        The register is what the transaction writes down as it creates them
        and what the retirement keeps -- it is what says which child owns
        which slice of the manifest -- while the phase is what answers in the
        window before the first of those writes lands, which is the window
        `IN_FLIGHT_PHASES` exists for.

        What it buys the readers behind it is the difference between a
        candidate nobody counted and one nobody needs to. A settled split
        drops the measurement, because a record still answering "oversized"
        pins `workflow:decomposing` and would put the umbrella label back on
        every tick, and keeps the publication group, because the umbrella
        re-asks it in front of every child it releases and every branch it
        deletes. A group with no number beside it is otherwise exactly the
        shape of a tick that died between the freeze and the diff.
        """
        return bool(self.split_children) or self.phase in _late_phases._PAST_THE_SNAPSHOT

    def with_split_children(self, numbers: tuple[int, ...]) -> LateGeneration:
        """Return this record with the ordered child register replaced.

        Replaced rather than merged, because the register is positional and a
        caller rebuilding it walks the whole manifest: merging would leave a
        stale tail behind whenever a re-run shortened it. Only positive whole
        numbers are children, for the reason the consumer ledger says so --
        a value nobody can ask GitHub about is not one to adopt by index.
        """
        for number in numbers:
            if not _formats.whole_number(number) or number <= 0:
                raise _formats.InvalidLateValue(
                    f"child is not an issue ({type(number).__name__})",
                )
        return replace(self, split_children=tuple(numbers))

    def at_phase(self, phase: _late_phases.LatePhase) -> LateGeneration:
        """Return this record standing at one reconciliation boundary.

        Ordinarily whatever the step that reached it says. The one move
        refused is BACKWARDS out of a transaction that has begun, and it is
        refused here rather than at each caller because every retry ABOVE the
        transaction makes it: the hold is reconciled on every tick, a
        spawn names its own boundary, and each completion claims the owner
        read. Any of them writing its own phase over `splitting` would erase
        the only evidence there is in the window that matters -- a child is
        created before the write that records it, so a loop that died between
        the two leaves an empty ledger and a real issue on GitHub. What a
        later reclamation reads then is a cycle that never started a split,
        and the ref that half-created child is still cutting from is one it
        would delete.

        A cancellation is not a rewind and is not refused: `cancelling` comes
        after every boundary here, and `cancel` keeps the one it interrupted
        beside the stamp. Nor is a fresh generation, which starts over at
        `measuring` by advancing the counter rather than by moving this one.
        """
        if phase in _late_phases._BEFORE_TRANSACTION and self.phase in _late_phases.IN_FLIGHT_PHASES:
            return self
        return replace(self, phase=phase)

    def cancel(self, stamp: str) -> LateGeneration:
        """Return this record marked cancelled, keeping the first stamp.

        Cancellation is irreversible within a cycle: once the owner has been
        observed closed, a later tick that observes it reopened re-runs this
        and must not move the moment the cleanup obligation was taken on.

        The boundary it was standing at is kept beside the stamp, because the
        `phase` field is about to name the cancellation itself and the answer
        it was carrying is one the reconciliation still needs: whether the
        consumer ledger accounts for every child cut from this generation's
        snapshot is read off the phase, and a record that forgot where it was
        cancelled from could never prove it again. Kept from the first marking
        for the same reason the stamp is -- a re-mark must not move it -- and
        a record whose first marking is the one being repeated answers with
        `cancelling`, which proves nothing and keeps the ref.
        """
        return replace(
            self,
            cancelled=True,
            cancelled_at=self.cancelled_at or stamp,
            cancelled_phase=self.cancelled_phase or self.phase,
        )
