# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Frozen external obligations and updates that preserve unreadable ledgers.

Resources are keyed by kind and target; consumers are positive issue numbers
kept in sorted order without duplicates. The opaque copies preserve the whole
wire ledger when a reader cannot type every entry, so updates to that ledger
must refuse rather than disappear at the next pinned write.

The ordered child register belongs to the generation: its positions name
manifest slices, while these ledgers account for resources still owed even
when the generation's identity is damaged or its adjudication has ended.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from orchestrator.workflow.late_split import formats as _formats

# A pinned resource target must be a bounded identifier. Telemetry carries
# only its fingerprint, while reconciliation reads the target from the ledger.
MAX_RESOURCE_TARGET = 512

# What a caller is told when it tries to update a ledger the write would not
# carry its update into. Spelled once because both transforms refuse alike.
_OPAQUE_LEDGER = "{0} cannot be updated while the ledger is opaque"


class LateResourceKind(StrEnum):
    """What kind of external thing a ledger entry holds the generation to."""

    SNAPSHOT_REF = "snapshot_ref"
    BRANCH = "branch"
    PLAN_PR = "plan_pr"
    CHILD = "child"


class LateResourceState(StrEnum):
    """How far one recorded external obligation has been reconciled.

    `RETAINED` is not a failure: a snapshot whose direct consumers are still
    live is deliberately kept, and saying so is what keeps a retained ref
    apart from one whose deletion was refused.

    `RECLAIMING` is the decision, written before the delete that carries it
    out, so a tick that died between the delete landing and the record of it
    has something durable to come back to. It is not a pass on the proof: the
    consumers are read again on every visit that would delete, and one that
    came back keeps the ref with the entry left here. What the state buys is
    the retry of a delete that may already have happened -- a ref the remote
    no longer has is finished without re-proving anything, since what is left
    is the record and the receipts rather than the deletion. Every state but
    `RECONCILED` is still owed, so a record left here holds a terminal exactly
    as `RETAINED` does.
    """

    PENDING = "pending"
    RETAINED = "retained"
    RECLAIMING = "reclaiming"
    RECONCILED = "reconciled"
    FAILED = "failed"


@dataclass(frozen=True)
class LateResource:
    """One external resource this generation owes the remote.

    `target` is the resource's own identifier -- a ref, a branch, a pull
    request number, an issue number -- and is recorded so a reconciliation
    acts on the exact thing the generation created rather than on whatever
    currently looks like it.
    """

    kind: LateResourceKind
    target: str
    resource_state: LateResourceState = LateResourceState.PENDING


@dataclass(frozen=True)
class LateObligations:
    """The resource and consumer ledgers, including any unreadable contents."""

    resources: tuple[LateResource, ...] = ()
    consumers: tuple[int, ...] = ()
    opaque_resources: str | None = None
    opaque_consumers: str | None = None

    @property
    def is_opaque(self) -> bool:
        """Whether an external obligation here is one this binary cannot type.

        The one answer a reclamation may not read past: an unknown consumer or
        an unknown resource is still an obligation, so nothing may treat the
        cleanup as complete or the snapshot as reclaimable while this holds.
        """
        return (
            self.opaque_resources is not None
            or self.opaque_consumers is not None
        )

    def with_resource(self, resource: LateResource) -> LateObligations:
        """Return these obligations with one external obligation recorded.

        Keyed on kind and target, so a reconciliation that repeats after a
        crash updates the entry it already wrote instead of appending a second
        one -- the ledger stays as bounded as the resources actually created.

        Refused while the resource ledger is opaque. What gets written back
        then is the verbatim copy, so the update would be returned here and
        lost at the next write -- and merging into a ledger this binary could
        not read is exactly the rewrite the verbatim copy exists to prevent. A
        caller that reaches this has a ledger a human has to settle first.
        """
        if self.opaque_resources is not None:
            raise _formats.InvalidLateValue(_OPAQUE_LEDGER.format("resources"))
        kept = tuple(
            entry for entry in self.resources
            if (entry.kind, entry.target) != (resource.kind, resource.target)
        )
        return replace(self, resources=(*kept, resource))

    def with_consumers(self, numbers: tuple[int, ...]) -> LateObligations:
        """Return these obligations with direct snapshot consumers recorded.

        Deduplicated and ordered, because the ledger is what a reclamation
        sweep walks: a child recorded twice would be asked about twice, and
        the order it was created in is not what decides anything.

        Only a positive whole number is an issue: converting anything else
        would put a consumer nobody can ask about into the one ledger that
        decides whether a snapshot may be reclaimed -- `True` is not issue 1,
        2.5 is not issue 2, and "7" is a string somebody hand-edited.

        Refused while the consumer ledger is opaque, for the reason
        `with_resource` is: the verbatim copy is what a write puts back, so an
        update accepted here would disappear at the next one.
        """
        if self.opaque_consumers is not None:
            raise _formats.InvalidLateValue(_OPAQUE_LEDGER.format("consumers"))
        for number in numbers:
            if not _formats.whole_number(number) or number <= 0:
                raise _formats.InvalidLateValue(
                    f"consumer is not an issue ({type(number).__name__})",
                )
        merged = set(self.consumers) | set(numbers)
        return replace(self, consumers=tuple(sorted(merged)))
