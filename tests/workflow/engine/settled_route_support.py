# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a landed rewrite's direct finish left behind its route.

The real-git case whose finishes a test hands the coordinator directly
(`settled_finish_support.SettledRunCase.finalizes`), reading back what they
made together: a run invalidated whole with its provenance kept
(`assert_retired_whole`), a head said and routed once with its attempt
retired (`assert_routed_once`), how often anything was run, pushed, or
launched (`assert_made`), and the pinned fields a case reads side by side
(`pinned_fields`).
"""
from __future__ import annotations

from orchestrator.workflow.engine import verification_settlement_state as _settlement
from tests.workflow.engine import (
    rewrite_finish_git_support as _git_support,
    rewrite_finish_readings as _readings,
    rewrite_handoff_test_support as _handoff,
    rewrite_verification_recovery_support as _support,
    settled_finish_support as _settled,
)


class SettledRouteCase(_settled.SettledRunCase):
    """`SettledRunCase`, read back for what its direct finishes routed, retired, said, and made."""

    def assert_retired_whole(self, run, pending=None) -> None:
        """`run` invalidated whole behind the evidence the rewrite moved past, nothing current, `pending` beside it.

        The entry keeps the run's revision and whole binding -- tested commit
        and tree, configuration, source, and the review it answered for -- so
        history names the one execution the run was.
        """
        retired = (*_git_support.invalidated(self), (run.receipt, _readings.INVALIDATED))
        self.assertEqual(_readings.pinned_records(self), (pending, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (run.revision, run.binding))

    def assert_routed_once(self, *heads: str, ran: int = 1) -> None:
        """Each of `heads` announced once, in order, routed once, and its attempt retired; the command run `ran` times.

        One notice and one `base_rebased` event each, one relabel and one
        stage-entry event, and nothing pushed or launched.
        """
        said = (_support.announced(self), len(_readings.notices(self)))
        self.assertEqual(said, (list(heads), len(heads)))
        routed = (_readings.relabels(self), _handoff.stage_entries(self.gh, _git_support.ISSUE))
        self.assertEqual(routed, (_readings.ROUTED, ["validating"]))
        self.assertEqual(_readings.attempt(_readings.pinned(self)), _readings.RETIRED)
        self.assert_made(ran)

    def assert_made(self, ran: int = 1) -> None:
        """The configured command run `ran` times, and nothing pushed or launched."""
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (ran, 0, 0))

    def pinned_fields(self, *keys: str) -> tuple:
        """What the pinned comment now carries under each of `keys`, None where it carries nothing."""
        pinned = _readings.pinned(self)
        return tuple(pinned.get(key) for key in keys)
