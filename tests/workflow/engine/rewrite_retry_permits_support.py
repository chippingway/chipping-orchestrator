# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A granted transfer over an interrupted replay, retried with the permit and the gate answered.

The adjudicated issue the transfer cases are seeded on, with the grant the
interrupted tick left standing, and the retry run with what decides it
answered: the permit, the evidence re-derived for a grant the crash came
before, and the gated publication -- whose call is what says the terms the
gate was entered on. The readings the candidate is prepared on get their
ordinary answers, and a landing is handed to a finish that is stood in for,
since what these cases pin is what licenses the push rather than how a landing
is finished.
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    replay_transfer_parks as _replay_transfer_parks,
    transfer_evidence as _transfer_evidence,
    transfer_permits as _transfer_permits,
    transfers,
)
from orchestrator.git.base_sync.rewrite_handoffs import _LandedRewrite, _PushOutcome
from orchestrator.git.ref_transport import _RefRead
from orchestrator.workflow.engine import rewrite_finish as _finish, rewrite_retry as _rewrite_retry
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from orchestrator.workflow.stages.implementing import late_push as _late_push
from tests.git.base_sync import (
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)
from tests.git.base_sync.gate_reads_support import _gate_reads


class _Gated:
    """The gated publication answering `answer`, its transport left with the landing a landed answer is.

    The gate's own call is stood in for, so the push its transport makes is
    too: a landed answer leaves the transport holding the candidate accepted
    at the remote, as the git owner's push reports it.
    """

    def __init__(self, answer) -> None:
        self._answer = answer

    def __call__(self, _gate, _branch, _entered, *, transport):
        if self._answer.landed:
            rewritten = transport.candidate.rewritten_head
            transport.landing = _LandedRewrite(
                candidate=transport.candidate, outcome=_PushOutcome.ACCEPTED, remote=_RefRead(sha=rewritten),
            )
        return self._answer


def gated(answer) -> MagicMock:
    """A watched gated publication answering `answer`."""
    return MagicMock(side_effect=_Gated(answer))


class LicensedRetryCase(seed.TransferCase):
    """A granted transfer with the permit and the gated publication controlled."""

    def setUp(self) -> None:
        super().setUp()
        _gate_reads(self)
        # The permission the interrupted grant left, which is what every case
        # but the two that start over is decided on.
        seed.granted(self.state)

    def parks(self, park: str, **retry) -> MagicMock:
        """Run the retry and pin the single park it takes."""
        parked = _recovery_cases._handled()
        with patch.object(_replay_transfer_parks, park, parked):
            self.assertTrue(self.retry(**retry))
        parked.assert_called_once()
        return parked

    def retries(self, **retry):
        """Run a retry that lands, and hand back the terms the gate was entered on."""
        publishes = gated(_recovery_cases._pushed(landed=True))
        with patch.object(transfers, "_rotated_onto", _recovery_cases._handled()):
            self.assertTrue(self.retry(publishes=publishes, **retry))
        return publishes.call_args.args[2]

    def retry(
        self,
        *,
        publishes=None,
        permits=None,
        reconstructed=None,
        published=None,
        permit_alone: bool = False,
    ) -> bool:
        """One reissued push, with the gate and the permit answered."""
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(
                _transfer_permits, "_permits_the_publication", permits or _recovery_cases._handled(),
            ))
            if reconstructed is not None:
                stack.enter_context(patch.object(_transfer_evidence, "_reconstructed", reconstructed))
            stack.enter_context(patch.object(
                _late_push, "_publishes", publishes or gated(published or _recovery_cases._pushed()),
            ))
            stack.enter_context(patch.object(
                _finish, "finalizes", MagicMock(return_value=FinishOutcome.ROUTED),
            ))
            return _rewrite_retry.retries(
                self.context, _recovery_cases._snapshot(),
                transfers._carried_by(self.context, seed.REPLAYED_SHA),
                permit_alone=permit_alone,
            )
