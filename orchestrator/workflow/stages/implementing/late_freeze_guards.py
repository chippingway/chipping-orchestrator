# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reject incomplete or foreign frozen measurement records before their counts are used.

A retained candidate needs its base, threshold, phase, and valid issue
identity. Damage parks the record instead of turning it into a small verdict.
"""
from __future__ import annotations

import logging

from orchestrator.config import settings as config
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_identity_reading as _late_identity_reading,
    late_park_notices as _late_park_notices,
    late_records as _records,
)

log = logging.getLogger("orchestrator.workflow")


# The evidence a recorded pair has to carry to be acted on, named as the park
# reports a missing one. The base is first because it is the only one a road
# can legitimately be without.
_MEASUREMENT_FIELDS = (
    ("late_base_sha", lambda recorded: not recorded.base_sha),
    ("late_threshold", lambda recorded: recorded.threshold is None),
    ("late_phase", lambda recorded: recorded.phase is None),
)

# What a pair still waiting for its base is held to: the same evidence less
# the base itself. A base the remote would not name records none at all, and
# the freeze that follows is what supplies one -- but nothing else about that
# record is any less load-bearing for being written mid-freeze, and the mint
# the retry goes through re-stamps every one of these from the current
# process rather than from what the generation was frozen under.
_REFROZEN_FIELDS = _MEASUREMENT_FIELDS[1:]

_MISSING_FIELD = "`{field}` is missing from it"

_DAMAGED_RECORD_PARK = (
    "{mentions} this issue records a measurement of `{candidate}` that "
    "cannot be acted on: {damaged}. A count with no ceiling beside it is not "
    "a verdict and a count recorded against another issue is not this one's "
    "answer, so reading either as a small candidate would publish an "
    "implementation nobody measured. Nothing was published and nothing was "
    "re-run. Repair the pinned comment, or commit again so the candidate is "
    "measured afresh, and reply `/orchestrator continue`."
)


def _unusable_record(
    gate: _late_gate_models._Gate, recorded: LateGeneration, fields: tuple,
) -> str | None:
    """Why a recorded measurement may not be acted on, or None if it may.

    Named rather than counted, because the park has to tell a human which
    part to repair -- and because the parts are not interchangeable: a missing
    threshold and a missing base are two different reasons the number beside
    them means nothing.

    Which fields are asked for is the caller's, because it is the caller that
    knows what its road has established: a pair still waiting for its base is
    proved against everything but that one, and a pair that recorded one is
    proved against all of them.

    The identity carries the same weight as the count's own fields and is the
    half that is easy to forget, because nothing downstream reads it: a record
    with no cycle, no generation, or no root cannot be joined to the audit
    line the measurement was reported on, to the lineage a split would be
    bounded by, or to the verdict an adjudication files -- and a count that
    can be published but not correlated is a reading no operator can defend
    afterwards. One naming another issue is worse still: it is not this
    issue's answer at all, so publishing on it would ship work here on a
    reading taken over there.
    """
    for field, missing in fields:
        if missing(recorded):
            return _MISSING_FIELD.format(field=field)
    return _late_identity_reading._unusable_identity(gate, recorded)


def _damaged_record(gate: _late_gate_models._Gate, recorded: LateGeneration) -> bool:
    """Park a recorded pair whose metadata cannot be acted on, or pass it.

    Asked on BOTH roads into a recorded pair, because the fields it checks are
    written by the freeze rather than by the count: a record reused for a
    reading that has still to be taken is as damaged without them as one whose
    number is already in. The counted road would otherwise be the only one
    guarded, and the uncounted one -- the ordinary crash retry -- would carry
    a threshold-less record into `_verdict_owner._settled`, where the record's own comparison
    answers "not oversized" on a missing ceiling and publishes it.

    The whole record is asked here because a base is one of the fields: this
    is the road where one was recorded, so a pair short of it is damaged
    rather than mid-freeze.
    """
    return _parks_the_damage(
        gate, recorded, _unusable_record(gate, recorded, _MEASUREMENT_FIELDS),
    )


def _damaged_unfrozen_record(
    gate: _late_gate_models._Gate, recorded: LateGeneration,
) -> bool:
    """Park a record with no base this issue may not mint over, or pass it.

    The other half of the reuse proof, for the pair that has no base to
    re-prove. A base the remote would not name records no base at all, so the
    retry over that same candidate freezes afresh -- and the mint it freezes
    under INHERITS the record beside it: the cycle it is correlated by, the
    scope it was declared with, and the readings it has already spent, while
    re-stamping this issue's number, the configured ceiling, and the boundary
    from the process running NOW. Unproved, a reading taken against another
    issue becomes this one's to measure and then to publish, and a generation
    that lost the ceiling it was frozen under is re-judged against whatever
    the setting has been retuned to since.

    Everything but the base is asked for, because the base is the only field
    this road is legitimately without: it is what the failure being retried
    leaves behind, and the freeze below is what supplies one. Asking for it
    here would park every transport retry on the very pair it exists to keep
    re-reading.
    """
    return _parks_the_damage(
        gate, recorded, _unusable_record(gate, recorded, _REFROZEN_FIELDS),
    )


def _parks_the_damage(
    gate: _late_gate_models._Gate, recorded: LateGeneration, damaged: str | None,
) -> bool:
    """Hand back a record that may not be acted on, under the reason it fails.

    None is a record that may, which is what every caller passes on. The
    failure reaches both sinks like every other refusal, so a record that
    fails open in the log is not what an operator has to notice.
    """
    if damaged is None:
        return False
    log.error(
        "issue=#%d records a measurement of %s that cannot be acted on "
        "(%s); parking rather than reading it as an answer",
        gate.issue.number, recorded.candidate_sha, damaged,
    )
    return _late_park_notices._parked(
        gate, _records._reportable(gate, recorded), damaged,
        _DAMAGED_RECORD_PARK.format(
            mentions=config.HITL_MENTIONS,
            candidate=recorded.candidate_sha,
            damaged=damaged,
        ),
    )
