# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Measurement-miss retention, inherited lineage, and recordable generation identity.

A changed candidate starts a fresh miss count. An inherited child keeps its
recorded root and depth, and a generation must pass domain validation and
name this issue before its identity can be reported.
"""
from __future__ import annotations

from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
    formats as _formats,
    validation as _late_validation,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import late_gate_models as _late_gate_models

_UNRECORDABLE_IDENTITY = (
    "the identity it would be correlated by is not one a record may carry "
    "({refusal})"
)

_FOREIGN_RECORD = (
    "it was recorded against issue #{recorded} rather than this one"
)


def _misses_of(recorded: LateGeneration, candidate_sha: str) -> dict:
    """What a mint over this commit carries of the readings already lost."""
    if recorded.candidate_sha != candidate_sha:
        return {"measurement_miss_count": 0, "measurement_failure": None}
    return {
        "measurement_miss_count": recorded.measurement_miss_count,
        "measurement_failure": recorded.measurement_failure,
    }


def _lineage_of(
    gate: _late_gate_models._Gate, recorded: LateGeneration, ancestry: _ancestry.LateAncestry,
) -> tuple:
    """The root and the depth this generation is minted at.

    Both together because both come from the same place and have to agree: the
    ancestry is the record a SPLIT wrote about this issue, and the split
    transaction later checks its own generation against exactly that pair. A
    root taken from one source and a depth from another is the disagreement
    that refusal exists to catch.

    An issue no split created is the root of its own lineage at depth 0. One
    whose ancestry records no readable depth keeps that unknown rather than
    being read as a root, because a lineage that cannot show it has room may
    not split -- and reading a damaged field as 0 is how one buys itself
    another generation past the bound.
    """
    if ancestry.is_present:
        return ancestry.root_issue, ancestry.lineage_depth
    root = recorded.root_issue or gate.issue.number
    return root, (recorded.lineage_depth if recorded.is_present else 0)


def _unusable_identity(gate: _late_gate_models._Gate, recorded: LateGeneration) -> str | None:
    """Why this record is no generation of THIS issue, or None if it is.

    Asked through the domain's own record gate rather than by a second reading
    of the same fields, so the identity a record may be ACTED on under is
    exactly the identity a record of it may be WRITTEN under -- a rule spelled
    twice would let the pinned comment publish what the sinks refuse.

    The issue is the one part that gate cannot ask, because it does not know
    which issue is being decided. A positive `late_current_issue` is not the
    same claim as one naming this one: a record carrying somebody else's
    number describes a reading taken over there, and both sinks would file
    this issue's failure against that one.
    """
    try:
        _late_validation.check_generation(recorded)
    except _formats.InvalidLateValue as refused:
        return _UNRECORDABLE_IDENTITY.format(refusal=refused)
    if recorded.current_issue != gate.issue.number:
        return _FOREIGN_RECORD.format(recorded=recorded.current_issue)
    return None
