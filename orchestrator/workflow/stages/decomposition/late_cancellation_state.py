# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist late-cycle cancellation and reconstruct an interrupted retirement identity.

The cancelled phase and cleared owner claim are durable before telemetry.
Reconstruction keeps surviving obligations and derives ancestry for this issue.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from github.Issue import Issue

from orchestrator.github import (
    client as _client,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import (
    usage as _usage,
)
from orchestrator.workflow.late_split import (
    events as _events,
    lineage as _lineage,
    models as _late_models,
    phases as _late_phases,
    state as _late_state,
    telemetry as _telemetry,
)
from orchestrator.workflow.state import (
    stage_name,
)

log = logging.getLogger("orchestrator.workflow")



def _reconstructed(
    issue: Issue, state: _pinned_state.PinnedState, retired: int,
) -> _late_models.LateGeneration:
    """Rebuild enough of a dropped cycle for the ending to be recorded by.

    The ledgers are already there -- a retirement carries them across, since
    an obligation does not stop being owed because the identity beside it was
    cleared -- and the cycle comes from the correlation. What has to be put
    back beside them is the IDENTITY every record of this cycle is correlated
    by: a cancellation is reported on two sinks, and a record that cannot name
    the root of its own lineage is one the domain refuses outright, so a
    reconstruction short of it would end the cycle and say nothing about it.

    The root is read off the ancestry, which survives the clear because it is
    a fact about the split this issue was CUT from rather than about the cycle
    this issue ran -- and an owner with no ancestry is the root of its own
    lineage, which is what the split writes for one. The depth comes with it,
    for the same reason and from the same place.

    The boundary is the one a finished cycle stands at. A retirement is the
    last write of a publication that created no child and preserved no ref,
    and of a terminal whose every obligation was already reclaimed, so there
    is no consumer ledger for the reclamation rule to find short.
    """
    ancestry = _lineage.read_late_ancestry(state)
    return replace(
        _late_state.read_late_generation(state),
        cycle_id=retired,
        current_issue=issue.number,
        root_issue=ancestry.root_issue or issue.number,
        lineage_depth=ancestry.lineage_depth,
        phase=_late_phases.LatePhase.CLEANING_UP,
    )


def _marked(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Record that this cycle is over, once, before anything acts on it.

    A record that already carries the mark is handed straight back: the flag,
    the stamp, and the boundary the cancellation interrupted are all decided
    by the FIRST observation, and a human who reopened the issue and closed it
    again has not started a new cleanup obligation. Skipping the write is also
    what bounds the record of it -- one `late_cancellation` per cycle, emitted
    by the visit that made the mark true rather than by every visit that reads
    it back.

    The pending owner read goes with it, for the reason the post-agent guard
    drops it: what that marker exists for is bringing a tick back to a fresh
    read of this issue, and this pass is one.
    """
    if generation.cancelled:
        return generation
    log.warning(
        "issue=#%d was closed while its late cycle %d stood at %s; "
        "cancelling it and reconciling what it owes the remote",
        issue.number, generation.cycle_id, generation.phase,
    )
    cancelled = replace(
        generation.cancel(_usage._now_iso()),
        phase=_late_phases.LatePhase.CANCELLING,
        owner_check_pending=False,
    )
    _persisted(gh, issue, state, cancelled)
    _telemetry.emit_late_event(
        gh,
        _events.LateEvent(family=_events.LateEventFamily.CANCELLATION),
        cancelled,
        stage=stage_name(gh.workflow_label(issue)),
    )
    return cancelled


def _persisted(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> None:
    """Make one step of this pass durable before the next one acts."""
    _late_state.write_late_generation(state, generation)
    gh.write_pinned_state(issue, state)
