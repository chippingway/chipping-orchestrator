# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pinned-state fixtures for recorded and damaged semantic exemptions."""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    exemption as _exemption,
)
from tests.workflow.late_split.generation_test_support import (
    BASE_SHA,
    CANDIDATE_SHA,
    DIGEST_LENGTH,
)

# What the contribution the accepted candidate carries over its base
# fingerprints to, and the commit a developer makes on top of that candidate.
CONTRIBUTION_DIGEST = "e" * DIGEST_LENGTH


def empty_state() -> PinnedState:
    """A pinned comment carrying nothing at all."""
    return PinnedState(data={})


def exempted_state() -> PinnedState:
    """One accepted commit recorded, with nothing beside it."""
    state = empty_state()
    _exemption.record_exemption(state, CANDIDATE_SHA)
    return state


def identified_state() -> PinnedState:
    """One settled verdict's whole record: the commit, and what it carries."""
    state = exempted_state()
    _exemption.record_semantic_identity(
        state,
        base_sha=BASE_SHA,
        candidate_sha=CANDIDATE_SHA,
        fingerprint=CONTRIBUTION_DIGEST,
    )
    return state


def damaged_state(damage: dict) -> PinnedState:
    """That record with one field absent, or carrying what nobody here wrote."""
    state = identified_state()
    for key, written in damage.items():
        if written is None:
            state.data.pop(key, None)
        else:
            state.data[key] = written
    return state
