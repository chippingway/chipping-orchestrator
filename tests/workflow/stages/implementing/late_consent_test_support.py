# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One adjudicated candidate parked for the person nobody can show.

The fixture the authorization park's own contract is driven through, at both
altitudes it has to be asked at. Most of what the park promises is a thread
and a pinned comment -- which reply a reading acts on, what the record it
writes says, and how far it consumes -- and driving that through a whole stage
handler would put a publication seam between the case and the answer it is
asserting on. What the ROUTING promises is the opposite: that a parked tick
reaches the gate at all, and that the park survives whatever the real seam
does with it, neither of which a double in that seam's place can answer. So
`_run_tick` runs the whole handler over the same seeded issue.

The generation carries the PAIR and no count, which is exactly what the park
leaves: a record answering "oversized" is what this workflow means by an
adjudication in flight, and the dispatcher puts `workflow:decomposing` back
over one before any stage runs. So the reading is re-taken by the tick that
acts, and the count a case hands in is that tick's own.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from orchestrator.git.measurement import (
    additions as _additions,
    fingerprint as _fingerprint,
)
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_consent as _consent,
    late_freeze as _freeze,
    late_gate as _gate,
    late_reading as _reading,
)
from tests.workflow.fixtures import (
    MEASURED_CANDIDATE_SHA,
)
from tests.workflow.stages.implementing import (
    late_consent_case as _consent_case,
    late_consent_crashes as _consent_crashes,
    late_consent_payloads as _consent_payloads,
)


class FreezesThePair:
    """Stand in for the freeze, persisting the pair it froze as it does.

    The WRITE is why this is a double rather than a stubbed return value.
    What the entry ordering turns on is that the freeze puts the pair in hand
    onto the pinned comment before anything reads which commit the park is
    standing over -- so a stub that answered without writing would hide the
    question these cases ask.

    `None` is a base this host could not name, which is a reading that did not
    happen and leaves the record exactly as found.
    """

    def __init__(self, pair: LateGeneration | None) -> None:
        self._pair = pair

    def __call__(self, gate, recorded, candidate_sha):
        if self._pair is None:
            return None
        frozen = replace(
            self._pair, candidate_sha=candidate_sha, additions=None,
        )
        _late_state.write_late_generation(gate.state, frozen)
        gate.gh.write_pinned_state(gate.issue, gate.state)
        return frozen


class SettlesWithItsOwnWrite:
    """The settlement's durable write, without its cycle bookkeeping.

    What a case here asserts is that the park comes off IN that write, so the
    double has to make one -- and it keeps the record it was handed, so a case
    can ask what the settlement was given as well as what landed.
    """

    def __init__(self) -> None:
        self.given: list[dict] = []

    def __call__(self, gate, generation) -> bool:
        self.given.append(dict(gate.state.data))
        gate.gh.write_pinned_state(gate.issue, gate.state)
        return False


class _ConsentCase(_consent_case._ParkedCase):
    """One gate call asking whether this candidate may publish as it stands."""

    def _authorizes(self, contribution=_consent_payloads.CONTRIBUTED, **entered) -> bool:
        """The reply half alone, over the reading the gate has already taken."""
        with patch.object(
            _fingerprint, _consent_payloads.FINGERPRINT_CONTRIBUTION, return_value=contribution,
        ):
            return _consent._authorizes_the_park(
                self._gate(**entered), _consent_payloads.measured(),
            )

    def _holds(self, counted=_consent_payloads.OVERSIZED, pair=..., **entered) -> bool:
        """The whole ordinary reading this park is reached from.

        The gate's own freeze-and-count rather than a road of this owner's,
        because that is what a tick actually walks: the park is what an
        oversized answer to it earns, and every way the reading can fail is
        the measurement's own. The record this tick writes and the record the
        last one left are two different things, which is what every case about
        a lost write and a moved candidate turns on.
        """
        frozen = _consent_payloads.measured() if pair is ... else pair
        with (
            patch.object(_freeze, _consent_payloads.FROZEN_PAIR, FreezesThePair(frozen)),
            patch.object(_additions, _consent_payloads.COUNT_ADDED_LINES, return_value=counted),
            patch.object(
                _fingerprint, _consent_payloads.FINGERPRINT_CONTRIBUTION,
                return_value=_consent_payloads.CONTRIBUTED,
            ),
        ):
            return _reading._freshly_measured(
                self._gate(**entered), _consent_payloads.measured(), MEASURED_CANDIDATE_SHA,
            )

    def _decides(self, counted=_consent_payloads.OVERSIZED, **entered) -> _consent_payloads.GateDecision:
        """One whole gate decision over this candidate, reading and all.

        The measurement is RUN rather than stubbed, because the road this park
        is reached down is the ordinary one: a case that cut the reading out
        would answer a question no tick asks. What says which road was taken
        is whether a count was needed at all.
        """
        with (
            patch.object(_freeze, _consent_payloads.FROZEN_PAIR, FreezesThePair(_consent_payloads.measured())),
            patch.object(
                _additions, _consent_payloads.COUNT_ADDED_LINES, return_value=counted,
            ) as counting,
            patch.object(
                _fingerprint, _consent_payloads.FINGERPRINT_CONTRIBUTION,
                return_value=_consent_payloads.CONTRIBUTED,
            ),
        ):
            gate = self._gate(**entered)
            verdict = _gate._decided(
                gate,
                _late_state.read_late_generation(gate.state),
                MEASURED_CANDIDATE_SHA,
            )
            ordinary = counting.called
        return _consent_payloads.GateDecision(verdict=verdict, measured=ordinary)

    def _crashes_past_our_sentence(self, *, parked: bool = True) -> None:
        """Run one whole call, and lose the write past whatever it posted.

        The window itself rather than a count of writes, so the same helper
        reproduces it for the park's notice and for the refusal alike: what it
        kills is always the write that would have recorded the sentence this
        call just said.

        `parked=False` is the call that TAKES the park, which is the only one
        that says its notice: a park already standing over the pair the freeze
        just wrote has said that sentence on an earlier tick, so a case
        seeding one would reproduce the quiet road instead of the window.
        """
        self._seed(parked=parked)
        with (
            patch.object(
                self.github, _consent_payloads.WRITE_PINNED_STATE,
                side_effect=_consent_crashes.DiesPastTheNotice(self.github),
            ),
            self.assertRaises(_consent_crashes.CrashedTick),
        ):
            self._holds()
