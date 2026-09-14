# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Durable late-generation phases and the transaction boundaries they describe.

The wire values identify persisted steps. In-flight boundaries protect the
window where a child exists before its ledger entry, and settled-split
boundaries distinguish completed work from a candidate still awaiting a count."""
from __future__ import annotations

from enum import StrEnum


class LatePhase(StrEnum):
    """The reconciliation boundary a generation last reached.

    Each member names a step that persists before it acts, so a tick that
    crashed mid-step reads the phase back and reconciles the same step rather
    than starting a new one.
    """

    MEASURING = "measuring"
    HOLDING_PLAN_PR = "holding_plan_pr"
    ADJUDICATING = "adjudicating"
    OWNER_CHECK = "owner_check"
    SNAPSHOTTING = "snapshotting"
    SPLITTING = "splitting"
    SUPERSEDING = "superseding"
    CLEANING_UP = "cleaning_up"
    CANCELLING = "cancelling"
    RESTARTING = "restarting"


# The boundaries a split TRANSACTION owns. A record standing at one of them
# has begun creating children and may be mid-loop, and that is the only thing
# saying so in the window where nothing is recorded yet -- a child is created
# before the write that records it, so the ledger is empty and the phase is
# the whole evidence.
IN_FLIGHT_PHASES = frozenset((
    LatePhase.SNAPSHOTTING,
    LatePhase.SPLITTING,
    LatePhase.SUPERSEDING,
))

# The boundaries at which the candidate has been committed to becoming
# children: every boundary the transaction owns past the ref it cuts, and the
# tail its retirement leaves the record standing at. Assembled from the set
# above rather than listed again, so a boundary that transaction gains is one
# this reading gains with it.
#
# `snapshotting` is the one taken out, and taking it out costs nothing. A
# record standing there still carries the measurement that sent it to the
# adjudication -- the retirement is what drops that -- and a transaction
# retried from there over a split that really did create children carries the
# register, which answers on its own.
_PAST_THE_SNAPSHOT = (
    IN_FLIGHT_PHASES | frozenset((LatePhase.CLEANING_UP,))
) - frozenset((LatePhase.SNAPSHOTTING,))

# The boundaries that come before a transaction. Every retry above one -- the
# hold reconciled on each tick, the spawn, the owner read a completion
# claims -- writes one of these, and writing it over an in-flight boundary is
# the rewind `at_phase` refuses.
_BEFORE_TRANSACTION = frozenset((
    LatePhase.MEASURING,
    LatePhase.HOLDING_PLAN_PR,
    LatePhase.ADJUDICATING,
    LatePhase.OWNER_CHECK,
))
