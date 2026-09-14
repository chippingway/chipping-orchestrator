# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Late-event fixtures for family, failure, cleanup, and transfer contracts."""
from __future__ import annotations

from orchestrator.workflow.late_split import events as _events
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateResource,
    LateVerdict,
)
from orchestrator.workflow.late_split.rewrite_values import LateRewriteKind, LateRewriteProof
from tests.workflow.late_split.generation_test_support import (
    CHILD_COUNT,
    FIRST_CHILD,
    SNAPSHOT,
    TRANSFERRED_FROM_BASE_SHA,
    TRANSFERRED_FROM_SHA,
)


def verdict_event(**fields) -> _events.LateEvent:
    """One adjudication's verdict, described by whatever it decided."""
    return _events.LateEvent(family=_events.LateEventFamily.VERDICT, **fields)


def cleanup_event(resource: LateResource) -> _events.LateEvent:
    """One external obligation reconciled, or found still owed."""
    return _events.LateEvent(
        family=_events.LateEventFamily.CLEANUP, resource=resource,
    )


def transfer_event(**fields) -> _events.LateEvent:
    """One exemption carried onto the commit a rewrite produced."""
    return _events.LateEvent(**{
        "family": _events.LateEventFamily.TRANSFER,
        "rewrite_kind": LateRewriteKind.SQUASH,
        "transfer_proof": LateRewriteProof.PUSHED,
        "transferred_from_sha": TRANSFERRED_FROM_SHA,
        "transferred_from_base_sha": TRANSFERRED_FROM_BASE_SHA,
        **fields,
    })


def every_family() -> tuple:
    """One valid event per family in the vocabulary, the transfer included."""
    return (*family_cases(), transfer_event())


def family_cases() -> tuple:
    """One valid event per family whose record reads over any generation.

    The transfer is deliberately not among them: its record is only written
    past a publication, so a walk that built one over the pre-publication
    generation beside this would be asserting on a record the contract
    refuses. `every_family` is what a test covering the vocabulary walks.
    """
    cases = [
        _events.LateEvent(family=_events.LateEventFamily.MEASUREMENT),
        _events.LateEvent(
            family=_events.LateEventFamily.VERDICT,
            verdict=LateVerdict.SPLIT,
            child_count=CHILD_COUNT,
        ),
        _events.LateEvent(
            family=_events.LateEventFamily.FAILURE,
            failure=LateFailure.MEASUREMENT_FAILED,
        ),
        _events.LateEvent(
            family=_events.LateEventFamily.SNAPSHOT, resource=SNAPSHOT,
        ),
        _events.LateEvent(
            family=_events.LateEventFamily.CLEANUP, resource=FIRST_CHILD,
        ),
        _events.LateEvent(family=_events.LateEventFamily.CANCELLATION),
        _events.LateEvent(
            family=_events.LateEventFamily.RESTART,
            restart_step=_events.LateRestartStep.PENDING,
        ),
    ]
    return tuple(cases)

_FAMILY = _events.LateEventFamily


def _failure(**fields) -> _events.LateEvent:
    """One typed late failure, described by whatever refused it."""
    return _events.LateEvent(
        family=_FAMILY.FAILURE,
        failure=LateFailure.MEASUREMENT_FAILED,
        **fields,
    )
