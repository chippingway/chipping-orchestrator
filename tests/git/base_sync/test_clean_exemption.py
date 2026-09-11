# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one clean auto rebase hands the size gate, and what the gate does with it.

The refresh is the seam: it knows the pre-rebase anchor its force-push is
leased against, the head the replay left, and the base that replay was made
onto, and none of the three survives anything else running. What it does with
them is assemble the evidence a transfer is decided on -- beside the pair the
adjudication already recorded, which is the only pair a verdict may move off.

Nothing here rules on that evidence. What these cases pin is the wiring: the
terms the gate is handed, that an equivalent replay publishes and rotates
without a reading, that a base advance which changed the contribution falls
back to the ordinary cumulative gate, and that evidence this refresh cannot
assemble is no claim at all.

The crash road is here for the same reason. The gate records the debt this
push is owed BEFORE the push goes out, so a process dying in between comes
back to a rebased branch, an unpushed remote, and an anchor still pinned --
and what has to happen next is this refresh's own recovery finishing the
route, not a later stage landing the push and leaving the reviewer looking at
a head nothing routed them to.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.git.measurement.models import (
    FrozenCommit,
    MeasurementFailure,
)
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    rewrites as _rewrites,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.git.base_sync import refresh_test_support as _support
from tests.git.base_sync.exemption_test_support import (
    ACCEPTED_BASE_SHA,
    ACCEPTED_DIGEST,
    ACCEPTED_SHA,
    CHANGED_DIGEST,
    REPLAYED_BASE_SHA,
    adjudicated,
    readings,
)
from tests.git.base_sync.refresh_scenarios import (
    PUSH_PATCH,
    _clean_rebase_scenario,
    _scenario,
)
from tests.git.base_sync.refresh_test_support import _RemoteHeadGit, _SyncWorktreeWithBaseFixture
from tests.git.base_sync.sync_test_support import _diverged, _git_result
from tests.workflow.fixtures import LABEL_DECOMPOSING

EVENT_MEASUREMENT = "late_measurement"
EVENT_TRANSFER = "late_transfer"

# The keyword a gated push names the commit it publishes by, and the one it
# pins that push to.
REVISION = "revision"
LEASE = "force_with_lease"

# What a process that never came back looks like from inside the tick, and the
# method the recovery that finishes its route records itself under.
DIED = "the process died before the push returned"
RECOVERY_PUSHED = "crash_recovery_pushed"


class _CleanRebaseCase(_SyncWorktreeWithBaseFixture):
    """One behind-base issue in review whose head a human already ruled on."""

    def setUp(self) -> None:
        super().setUp()
        self.reading = readings(self)
        self._seed_pr_issue(review_round=3)

    def _rebases(self, **scenario_options):
        """Run one refresh over the seeded world and hand back its scenario."""
        scenario = _clean_rebase_scenario(
            _support.THREE_BEHIND_STDOUT, **scenario_options,
        )
        scenario.run(self)
        return scenario

    def _durable(self):
        """The pinned comment as a process starting now would read it."""
        return self.gh.read_pinned_state(self.gh._issues[_support.ISSUE])

    def _events_of(self, family: str) -> list[dict]:
        return [
            record for record in self.gh.recorded_events
            if record.get("event") == family
        ]

    def _assert_measured(self) -> None:
        """The ordinary cumulative gate read this replay and published it."""
        self.assertEqual(len(self._events_of(EVENT_MEASUREMENT)), 1)
        self.assertEqual(self._events_of(EVENT_TRANSFER), [])
        durable = self._durable()
        self.assertTrue(_exemption.is_exempt(durable, _support.BEFORE_SHA))
        self.assertFalse(_rewrites.carries_rewrite_authorization(durable))


class TransferredRebaseTest(_CleanRebaseCase, unittest.TestCase):
    """The replay that contributes what the adjudication already accepted."""

    def setUp(self) -> None:
        super().setUp()
        adjudicated(self)
        self.scenario = self._rebases()

    def test_the_evidence_names_the_whole_rewrite(self) -> None:
        # The pair the verdict came from is the one the record already holds;
        # the pair it goes to is this rebase's own, and the anchor beside it
        # is the head the force-push was leased against rather than a third
        # spelling of the commit that was replaced.
        authorized = _rewrites.read_rewrite_authorization(self._durable())

        self.assertEqual(authorized.rewrite, _rewrites.LateRewrite(
            kind=_rewrites.LateRewriteKind.AUTO_CLEAN_REBASE,
            from_sha=_support.BEFORE_SHA,
            from_base_sha=ACCEPTED_BASE_SHA,
            to_sha=_support.AFTER_SHA,
            to_base_sha=REPLAYED_BASE_SHA,
            pr_number=_support.PR_NUMBER,
            source_stage=WorkflowLabel.IN_REVIEW,
            lease=_support.BEFORE_SHA,
        ))

    def test_the_receipt_carries_the_exemption_over(self) -> None:
        durable = self._durable()

        self.assertTrue(_exemption.is_exempt(durable, _support.AFTER_SHA))
        identity = _exemption.read_semantic_identity(durable)
        self.assertEqual(identity.base_sha, REPLAYED_BASE_SHA)
        self.assertEqual(
            _rewrites.read_rewrite_authorization(durable).phase,
            _rewrites.LateRewritePhase.PUBLISHED,
        )

    def test_no_generation_or_adjudication_is_created(self) -> None:
        self.assertEqual(self._events_of(EVENT_MEASUREMENT), [])
        self.assertNotIn((_support.ISSUE, LABEL_DECOMPOSING), self.gh.label_history)
        self.assertEqual(len(self._events_of(EVENT_TRANSFER)), 1)

    def test_the_refresh_tail_is_unchanged(self) -> None:
        # The push is still named against the replay and pinned to the anchor,
        # and the reviewer is still sent back to it.
        pushed = self.scenario[PUSH_PATCH].call_args.kwargs
        self.assertEqual(pushed[REVISION], _support.AFTER_SHA)
        self.assertEqual(pushed[LEASE], _support.BEFORE_SHA)
        self.assertIn((_support.ISSUE, _support.LABEL_VALIDATING), self.gh.label_history)
        self.assertEqual(self.gh.pinned_data(_support.ISSUE)[_support.KEY_REVIEW_ROUND], 0)


class MeasuredRebaseTest(_CleanRebaseCase, unittest.TestCase):
    """The replays no transfer is granted for, measured as they always were."""

    def test_a_changed_contribution_is_measured(self) -> None:
        # A base advance that moved what the branch adds to it produces a
        # contribution nobody adjudicated, so the cumulative gate reads it.
        adjudicated(self)
        self.reading.digests[(REPLAYED_BASE_SHA, _support.AFTER_SHA)] = CHANGED_DIGEST

        self._rebases()

        self._assert_measured()

    def test_a_legacy_exemption_claims_nothing(self) -> None:
        # A comment with no semantic record has no accepted pair to name, so
        # the refresh assembles no evidence at all.
        adjudicated(self, identity=False)

        self._rebases()

        self._assert_measured()

    def test_an_unnameable_base_claims_nothing(self) -> None:
        # The base a replay sits over is one end of the contribution it
        # produced, and it is the REMOTE's answer rather than a local ref the
        # agent can repoint. A remote that would not name the branch leaves
        # nothing to fingerprint the replay over, so no transfer is claimed --
        # and the ordinary reading, which freezes the same base, cannot be
        # taken either.
        adjudicated(self)
        self.reading.base = FrozenCommit(
            failure=MeasurementFailure.BASE_UNREADABLE, detail="no token",
        )

        self._rebases()

        self.assertEqual(self._events_of(EVENT_TRANSFER), [])
        durable = self._durable()
        self.assertTrue(_exemption.is_exempt(durable, _support.BEFORE_SHA))
        self.assertFalse(_rewrites.carries_rewrite_authorization(durable))


class RolledBackRebaseTest(_CleanRebaseCase, unittest.TestCase):
    """What a refused push owes when the permit was granted off the anchor."""

    def test_a_refused_push_drops_the_permission(self) -> None:
        # The commit a human ruled on and the head this rebase found are two
        # commits carrying one contribution, which is all a permit is granted
        # on -- so the permission names the accepted commit while the anchor
        # it leases against is the branch's own head. A push the remote
        # refuses resets the branch back onto that anchor, leaving the
        # rewritten commit on no branch, so the permission goes with it.
        adjudicated(self, accepted=ACCEPTED_SHA)
        self.reading.digests[(ACCEPTED_BASE_SHA, ACCEPTED_SHA)] = (
            ACCEPTED_DIGEST
        )

        self._rebases(push_result=False)

        durable = self._durable()
        self.assertTrue(_exemption.is_exempt(durable, ACCEPTED_SHA))
        self.assertFalse(_rewrites.carries_rewrite_authorization(durable))
        pinned = self.gh.pinned_data(_support.ISSUE)
        self.assertEqual(pinned[_support.KEY_PARK_REASON], _support.PARK_PUSH_FAILED)


class InterruptedRebaseTest(_CleanRebaseCase, unittest.TestCase):
    """The tick that dies between the grant and the push it licensed."""

    def setUp(self) -> None:
        super().setUp()
        adjudicated(self)
        self._crashes()
        self.resumed = self._resumes()

    def test_the_recovery_publishes_and_settles(self) -> None:
        # The permit is re-asked over the record the grant left -- the
        # recovery has no evidence of its own -- and the receipt behind the
        # reissued push is what finally carries the verdict over.
        pushed = self.resumed[PUSH_PATCH].call_args.kwargs
        self.assertEqual(pushed[REVISION], _support.AFTER_SHA)
        self.assertEqual(pushed[LEASE], _support.BEFORE_SHA)
        durable = self._durable()
        self.assertTrue(_exemption.is_exempt(durable, _support.AFTER_SHA))
        self.assertEqual(
            _rewrites.read_rewrite_authorization(durable).phase,
            _rewrites.LateRewritePhase.PUBLISHED,
        )

    def test_the_refresh_tail_is_finished(self) -> None:
        # The debt the grant recorded is what freezes this branch, and it
        # freezes it out of the very recovery the anchor beside it exists for.
        # Left there, a later stage lands the push and the reviewer is never
        # routed at the rewritten head.
        pinned = self.gh.pinned_data(_support.ISSUE)
        self.assertIsNone(pinned[_support.KEY_PENDING_PUSH_SHA])
        self.assertEqual(pinned[_support.KEY_REVIEW_ROUND], 0)
        self.assertIn((_support.ISSUE, _support.LABEL_VALIDATING), self.gh.label_history)
        rebased = self._events_of(_support.EVENT_BASE_REBASED)
        self.assertEqual(len(rebased), 1)
        self.assertEqual(rebased[0][_support.METHOD_FIELD], RECOVERY_PUSHED)

    def _crashes(self) -> None:
        """Rebase, grant the transfer, and die on the way to the remote."""
        crashing = _clean_rebase_scenario(_support.THREE_BEHIND_STDOUT)
        crashing[PUSH_PATCH].side_effect = RuntimeError(DIED)
        with self.assertRaises(RuntimeError):
            crashing.run(self)

    def _resumes(self):
        """The next tick, over the world that crash left behind.

        The checkout is on the replay, the remote is still on the anchor, and
        the branch is one commit ahead of it -- which is what the recovery
        classifies before it reissues the push the dead tick never made.
        """
        resumed = _scenario(
            dirty=MagicMock(return_value=[]),
            rebase=MagicMock(),
            push=MagicMock(return_value=True),
            head_sha=MagicMock(return_value=_support.AFTER_SHA),
            git=MagicMock(return_value=_git_result(stdout=_support.UP_TO_DATE_STDOUT)),
            hardened=MagicMock(side_effect=_RemoteHeadGit(_support.BEFORE_SHA)),
            fetch=MagicMock(return_value=_git_result()),
            ahead_behind=MagicMock(return_value=_diverged(1, 0)),
        )
        resumed.run(self)
        return resumed


if __name__ == "__main__":
    unittest.main()
