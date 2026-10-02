# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read outstanding branches, held snapshots, consumer issues, and snapshot ownership.

Opaque obligations remain blocking, unreadable consumers retain their refs --
a lazy issue's state or labels failing past the lookup included -- and only
the snapshot derived from this generation's identity belongs to it.
Consumers are the ones the ledger records, never the manifest the caller
tracks, so an umbrella whose edit replaced its children still reads the
originals its ref was preserved for, beside every replacement it pointed at
that ref.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.git.snapshots import namespace as _namespace
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import issue_is_closed
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.obligations import LateResourceKind, LateResourceState
from orchestrator.workflow.stages.decomposition import (
    late_cleanup_state as _late_cleanup_state,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan

log = logging.getLogger("orchestrator.workflow")


_SNAPSHOT = LateResourceKind.SNAPSHOT_REF

# What a terminal is blocked by when the ledger itself is the thing that
# cannot be read. It names no resource because there is no resource to name --
# only the fact that what is owed is unknown.
_OPAQUE = "an obligation this orchestrator cannot read"


def _owed_branches(generation: LateGeneration) -> tuple[str, ...]:
    """The superseded branches this generation has not seen reclaimed.

    Everything but `reconciled`, rather than the states this binary writes.
    A branch is owed until the remote is known to have let it go, and the
    ledger takes any state the vocabulary defines from any writer -- so an
    entry a newer binary, an older one, or a human left as `retained` is a
    branch nothing would ever retry and nothing would report as outstanding,
    which is a terminal closing over a branch still on the remote. The one
    reading that cannot do that is the one that treats every state except the
    settled one as unfinished.
    """
    return tuple(
        entry.target
        for entry in generation.obligations.resources
        if entry.kind == _late_cleanup_state._BRANCH
        and entry.resource_state != LateResourceState.RECONCILED
    )


def _held_snapshots(generation: LateGeneration) -> tuple[str, ...]:
    """The snapshot refs this generation still holds the remote to."""
    return tuple(
        entry.target
        for entry in generation.obligations.resources
        if entry.kind == _SNAPSHOT
        and entry.resource_state != LateResourceState.RECONCILED
    )


def _our_snapshot(
    issue_number: int, generation: LateGeneration, ref: str,
) -> bool:
    """Whether the recorded ref is the one this generation's snapshot is at.

    Derived, not parsed: the namespace mints one ref per issue, cycle, and
    generation, so the question is only whether the ledger still names it. A
    record whose identity is too damaged to derive a ref from owns no ref
    either, and answering no leaves the entry owed and the umbrella open --
    which is where an obligation nobody can correlate belongs.
    """
    try:
        expected = _namespace.snapshot_ref(
            issue_number=issue_number,
            cycle_id=generation.cycle_id,
            generation=generation.generation,
        )
    except _namespace.InvalidSnapshotRef:
        log.exception(
            "issue=#%d cannot derive the snapshot ref its own record would "
            "be under", issue_number,
        )
        return False
    return ref == expected


def _consumer_scan(
    gh: GitHubClient,
    issue: Issue,
    generation: LateGeneration,
    taken: _ChildScan | None = None,
) -> _ChildScan:
    """Read every recorded direct consumer as it stands right now.

    Fail-per-consumer rather than fail-per-pass. A read that raises leaves
    that consumer out of both maps, which the reclamation rule already reads
    as "not proved ended" and answers by keeping the ref -- while the branch
    half, which owes nothing to any consumer, is still settled on this visit.
    Abandoning the whole pass would instead let one unreadable child hold a
    superseded branch on the remote for as long as it stayed unreadable.

    `taken` is a scan this visit already took, and a consumer it was asked
    about keeps the answer it got rather than costing a second request. Every
    other consumer is read here, and that is the half that matters: the
    umbrella's scan is of the children it tracks NOW, which are this ledger's
    consumers only while the manifest that made them stands. A genuine edit
    re-decomposes the parent, the children it tracks after that are
    replacements, and the originals it orphaned are still ones the ref was
    preserved for. So the ledger decides who is read, never the manifest
    beside it, and an original that is open, was reopened, or cannot be read
    keeps the ref however finished its replacements are. A replacement that
    re-decomposition pointed at this ref was recorded here in the write that
    tracked it, so the scan the caller took answers for it the way it does
    for any child it tracks.

    Shaped as the parent scan the umbrella hands over, because the rule it
    feeds is the same rule and may not learn a second shape to ask it in.
    """
    return _ConsumerReading(gh=gh, issue=issue, taken=taken).scan(generation)


@dataclass(frozen=True)
class _ConsumerReading:
    """One visit's reading of the consumers a snapshot records.

    Held together because every consumer is asked the same two questions on
    the same visit: whether the scan the caller already took answers for it,
    and, where it does not, what GitHub says about it now.
    """

    gh: GitHubClient
    issue: Issue
    taken: _ChildScan | None

    def scan(self, generation: LateGeneration) -> _ChildScan:
        """Read every recorded consumer, leaving out each one that failed."""
        consumer_issues: dict[int, Issue] = {}
        consumer_labels: dict[int, str | None] = {}
        for consumer in generation.obligations.consumers:
            number = int(consumer)
            reading = self._read(number)
            if reading is None:
                continue
            consumer_issues[number] = reading[0]
            consumer_labels[number] = reading[1]
        return _ChildScan(
            list(generation.obligations.consumers), consumer_issues, consumer_labels,
        )

    def _read(self, consumer: int) -> tuple[Issue, str | None] | None:
        """One consumer's issue and label, or None where it could not be read.

        A consumer the scan this visit already took was asked about answers
        with what that scan found -- a failed read included, which stays
        failed rather than being asked twice on one visit.
        """
        if self._asked(consumer):
            return self._already_read(consumer)
        try:
            return self._fetched(consumer)
        except Exception:
            log.exception(
                "issue=#%s could not read snapshot consumer #%d; its snapshot "
                "stays retained", self.issue.number, consumer,
            )
            return None

    def _asked(self, consumer: int) -> bool:
        """Whether the caller's own scan was asked about this consumer."""
        if self.taken is None:
            return False
        return consumer in {int(number) for number in self.taken.children}

    def _already_read(self, consumer: int) -> tuple[Issue, str | None] | None:
        """What the caller's own scan found for one consumer it was asked about."""
        taken_issue = self.taken.issues.get(consumer)
        if taken_issue is None:
            return None
        return taken_issue, self.taken.labels.get(consumer)

    def _fetched(self, consumer: int) -> tuple[Issue, str | None]:
        """Fetch one consumer and take every read the proof will ask of it.

        The lookup is not the only request. The issue it hands back can be a
        lazy one, whose first attribute read IS the fetch -- so a consumer
        whose state or labels cannot be read fails past the lookup, and has
        to fail here, inside the one guard, rather than raise out of the pass
        and take the branch half down with it. The state is asked first for
        that reason alone: it is what the proof reads, and asking it here is
        what leaves the proof reading an issue that already answered.
        """
        fetched = self.gh.get_issue(consumer)
        issue_is_closed(fetched)
        return fetched, self.gh.workflow_label(fetched)


def _unwritable(generation: LateGeneration) -> bool:
    """Whether the RESOURCE ledger is one this binary may not update at all.

    Distinct from `LateObligations.is_opaque`, which folds in the consumer ledger
    beside it. The two are preserved and written independently, and they stop
    different things: an entry this binary cannot type on the RESOURCE ledger
    means no reclamation can be recorded, while one on the consumer ledger
    means no snapshot's proof can be taken. Reading them as one would leave a
    superseded branch on the remote because somebody hand-edited a list of
    issue numbers.
    """
    return generation.obligations.opaque_resources is not None


def _blocking(generation: LateGeneration) -> tuple[str, ...]:
    """What may not be left behind when this umbrella closes.

    Every obligation that is not `reconciled`, branch and ref alike. There is
    no reading under which a ref still on the remote is settled: one kept
    because a consumer could not be proved ended is an object this repository
    is holding, and an umbrella closed over it is an object nothing would ever
    come back for -- the parent is `done` by then and no pass revisits it. The
    label staying put IS the retry, and it is also the only thing that makes
    an unreclaimable ref visible to a human.

    An opaque RESOURCE ledger blocks whatever the typed view says, and it has
    to: the entries this binary could not read are still obligations, and the
    typed entries beside them are not the whole of what is owed. Closing on
    the strength of a projection is exactly the reading the verbatim copy
    exists to prevent.

    An opaque CONSUMER ledger needs no clause of its own. It is what a
    snapshot's proof is taken from, so a ref it covers is never reclaimed and
    is therefore already here as an unreconciled entry -- while a branch,
    which owes no consumer anything, is settled and closes as it always did.
    """
    if _unwritable(generation):
        return (_OPAQUE,)
    return _owed_branches(generation) + _held_snapshots(generation)
