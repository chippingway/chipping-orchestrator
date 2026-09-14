# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the receipt of a landed push does with the permission that licensed it.

The far end of the transfer, driven through the shared gated-publication push
tail rather than through the owner alone, because the two facts the settlement
turns on are made by that tail: the commit the push named, and the head the
entry froze the pull request at. Both roads a permit accounts for are here --
a remote still standing where the grant left it, and one a tick that pushed
and died before its receipt already moved -- and each is asserted on the
durable comment, the push the tail issued, and the one record the telemetry
owner left past that comment's own write.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    overrides as _overrides,
    rewrite_fields as _rewrite_fields,
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_push as _push,
    late_reconcile as _reconcile,
    late_rotation as _rotation,
    late_transfer_telemetry as _telemetry_owner,
    state as _state,
)
from tests.workflow import git_owners as _git_owners
from tests.workflow.stages.implementing import (
    late_transfer_adjudication as _transfer_adjudication,
    late_transfer_payloads as _transfer_payloads,
    late_transfer_readings as _transfer_readings,
    late_transfer_test_support as _support,
)

ACCEPTED_SHA = _transfer_payloads.ACCEPTED_SHA
MERGE_BASE_SHA = _transfer_payloads.MERGE_BASE_SHA
REWRITTEN_SHA = _transfer_payloads.REWRITTEN_SHA
LEASED_SHA = _transfer_payloads.LEASED_SHA
ACCEPTED_DIGEST = _transfer_payloads.ACCEPTED_DIGEST
PR_NUMBER = _transfer_payloads.PR_NUMBER
ISSUE_NUMBER = _transfer_payloads.ISSUE_NUMBER

# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"

# The receipt a landed gated push leaves, and the head it replaced.
KEY_RECEIPT_SHA = "implementing_published_sha"
KEY_RECEIPT_LEASE = "implementing_published_lease"

EVENT_TRANSFER = "late_transfer"
EVENT_VERDICT = "late_verdict"

PINNED_WRITE = "write_pinned_state"

# The telemetry owner's seam, which the push tail names for itself.
REPORTS_THE_TRANSFER = "_reports_the_transfer"

# The stage the transfer was entered from, as both sinks spell it.
STAGE_TAG = "validating"

# The state a relabel moved the issue to while the rewrite was being made,
# which the permit's own re-read of the issue is the only reading that sees.
RELABELLED = "workflow:fixing"

# The ceiling the fallback reading is taken against, high enough that the
# rewritten commit publishes on its count once the permit has refused.
MAX_ADDED_LINES = "MAX_ADDED_LINES"
CEILING = 100


class _RefusesTheReceipt:
    """A comment GitHub takes for the grant and refuses for the receipt.

    The narrow outage the settlement has to survive: the branch is on the
    remote and the write that would say so is lost, so nothing may be believed
    durable -- least of all a verdict, which would then name a commit no
    receipt accounts for.
    """

    def __init__(self, github) -> None:
        self.writes = 0
        self._writes = github.write_pinned_state

    def __call__(self, issue, state):
        self.writes += 1
        if self.writes > 1:
            raise RuntimeError("pinned comment rejected")
        return self._writes(issue, state)


class _SettlementCase(unittest.TestCase):
    """One gated push made over an issue whose exemption is about to move."""

    def setUp(self) -> None:
        adjudicated = _transfer_adjudication.adjudicated()
        self.github = adjudicated.github
        self.issue = adjudicated.issue
        self.state = adjudicated.state
        self.readings = _transfer_readings.readings(self)
        self.pushed = None
        self.published = None

    def _publishes(self, *, standing: str, granted: bool, **overrides) -> None:
        """Run the push tail over a remote standing on this head.

        `granted` seeds the comment a permit's own write already left, which
        is what a recovery answers from: the tick that granted it pushed and
        did not get its receipt down. A fresh transfer hands the evidence in
        instead, exactly as the squash that made the rewrite does.
        """
        _transfer_adjudication.open_pull_request(self.github, standing)
        if granted:
            _support.granted(self.state)
            self.github.write_pinned_state(self.issue, self.state)
        self.pushed = self.enterContext(
            _git_owners.seam_patch(_transfer_payloads.PUSH_BRANCH),
        )
        self.pushed.return_value = True
        self.published = _push._publishes(
            _support.gate(
                self.github, self.issue, self.state,
                candidate="", entry=None, rewrite=None,
            ),
            _transfer_payloads.BRANCH,
            _late_gate_models._Entered(**{
                "stage": _transfer_payloads.SOURCE_STAGE,
                "head": LEASED_SHA,
                "candidate": REWRITTEN_SHA,
                "reconciling": True,
                "answering": granted,
                "rewrite": None if granted else _support.rewrite(),
                **overrides,
            }),
        )

    def _records_of(self, family: str) -> list[dict]:
        return [
            record for record in self.github.recorded_events
            if record.get("event") == family
        ]

    def _reported(self) -> dict:
        """The one transfer record this tick left on the audit stream."""
        reported = self._records_of(EVENT_TRANSFER)
        self.assertEqual(len(reported), 1)
        return reported[0]

    def _durable(self):
        """The pinned comment as a process starting now would read it."""
        return self.github.read_pinned_state(self.issue)

    def _assert_carried(self) -> None:
        """The verdict is on the rewritten commit, with what it contributes.

        The operator authorization travels with it, because the two are one
        claim in two halves: left behind, the rewritten commit would carry a
        verdict with no gesture standing for it and the gate would stop a
        publication a human has already decided.
        """
        durable = self._durable()
        self.assertTrue(_exemption_reading.is_exempt(durable, REWRITTEN_SHA))
        identity = _exemption_reading.read_semantic_identity(durable)
        self.assertEqual(identity.base_sha, MERGE_BASE_SHA)
        self.assertEqual(identity.candidate_sha, REWRITTEN_SHA)
        self.assertEqual(identity.fingerprint, ACCEPTED_DIGEST)
        self.assertTrue(_overrides.is_authorized(durable, REWRITTEN_SHA))
        self.assertEqual(
            _rewrite_reading.read_rewrite_authorization(durable).phase,
            _rewrite_values.LateRewritePhase.PUBLISHED,
        )

    def _assert_left_put(self) -> None:
        """The verdict is exactly where the adjudication put it.

        The authorization with it: an exemption that did not move is still
        half a bypass, and one whose other half had moved would name a commit
        nobody granted it for.
        """
        durable = self._durable()
        self.assertTrue(_exemption_reading.is_exempt(durable, ACCEPTED_SHA))
        self.assertEqual(
            _exemption_reading.read_semantic_identity(durable).candidate_sha,
            ACCEPTED_SHA,
        )
        self.assertTrue(_overrides.is_authorized(durable, ACCEPTED_SHA))


class LandedTransferTest(_SettlementCase):
    """The push that moves the pull request onto the rewritten commit."""

    def setUp(self) -> None:
        super().setUp()
        self._publishes(standing=LEASED_SHA, granted=False)

    def test_the_exemption_moves_with_the_receipt(self) -> None:
        self.assertTrue(self.published.landed)
        self._assert_carried()
        pinned = self._durable().data
        self.assertEqual(pinned[KEY_RECEIPT_SHA], REWRITTEN_SHA)
        self.assertEqual(pinned[KEY_RECEIPT_LEASE], LEASED_SHA)

    def test_the_push_is_named_and_leased(self) -> None:
        # The grant licenses a push and nothing about how it is made: the
        # commit that was proved is what goes out, pinned to the head the
        # permit was granted against, so a pull request somebody moved in
        # between rejects it.
        self.pushed.assert_called_once()
        pushed = self.pushed.call_args.kwargs
        self.assertEqual(pushed[REVISION], REWRITTEN_SHA)
        self.assertEqual(pushed[LEASE], LEASED_SHA)

    def test_the_debt_the_grant_recorded_is_paid(self) -> None:
        pinned = self._durable().data
        self.assertIsNone(pinned.get(_state._APPROVED_SHA))
        self.assertIsNone(pinned.get(_state._APPROVED_LEASE))

    def test_the_record_names_both_pairs(self) -> None:
        # Both ends of both contributions, which is the whole of what says the
        # change carried over is the change a human ruled on.
        recorded = self._reported()

        self.assertEqual(recorded["transferred_from_sha"], ACCEPTED_SHA)
        self.assertEqual(recorded["transferred_from_base_sha"], MERGE_BASE_SHA)
        self.assertEqual(recorded["source_sha"], REWRITTEN_SHA)
        self.assertEqual(recorded["base_sha"], MERGE_BASE_SHA)

    def test_the_record_names_the_publication(self) -> None:
        recorded = self._reported()

        self.assertEqual(recorded["issue"], ISSUE_NUMBER)
        self.assertEqual(recorded["stage"], STAGE_TAG)
        self.assertEqual(recorded["published_pr_number"], PR_NUMBER)
        self.assertEqual(recorded["rewrite_kind"], "squash")
        self.assertEqual(recorded["transfer_proof"], "pushed")

    def test_no_second_verdict_is_reported(self) -> None:
        # A transfer carries a decision a human already made onto the object
        # that replaced the one they made it about. A `single` on the stream
        # here would read as a second adjudication of the same work.
        self.assertEqual(self._records_of(EVENT_VERDICT), [])


class AlreadyLandedTransferTest(_SettlementCase):
    """The retry that finds the pull request already on the rewritten commit.

    A tick that pushed and died before its receipt leaves the permission
    outstanding and the remote where its own push put it. The permit is
    re-asked in full over the record the grant left, the push is the leased
    no-op that proves the pull request is still standing there, and the
    receipt behind it settles the transfer the first tick could not.
    """

    def setUp(self) -> None:
        super().setUp()
        self._publishes(standing=REWRITTEN_SHA, granted=True)

    def test_the_lost_receipt_settles_the_transfer(self) -> None:
        self.assertTrue(self.published.landed)
        self._assert_carried()
        self.assertEqual(self._durable().data[KEY_RECEIPT_SHA], REWRITTEN_SHA)

    def test_the_no_op_is_leased_against_the_commit(self) -> None:
        # Never unleased, and never skipped: what the request buys is proof
        # taken at the remote that the publication is still the one the record
        # is about, which no local note could supply.
        self.pushed.assert_called_once()
        pushed = self.pushed.call_args.kwargs
        self.assertEqual(pushed[REVISION], REWRITTEN_SHA)
        self.assertEqual(pushed[LEASE], REWRITTEN_SHA)

    def test_the_record_says_which_reading_proved_it(self) -> None:
        recorded = self._reported()

        self.assertEqual(recorded["transfer_proof"], "already_published")
        self.assertEqual(recorded["source_sha"], REWRITTEN_SHA)


class ReceiptAndRecordTest(_SettlementCase):
    """The record rides the far side of the write that makes the move durable.

    The window the settlement exists to close, read from both of its sides.
    The branch is on the remote either way; what differs is whether the write
    that would say so landed. Refused, nothing may be believed durable --
    least of all a verdict, which would then name a commit no receipt accounts
    for -- and nothing is reported. Taken, the push tail asks the telemetry
    owner for itself, past that write, so the comment a reader finds at the
    moment the record is made already carries the verdict it is about.

    The window past the record is the same question once more. The proof is on
    the comment precisely because a process lost between the settlement and the
    record it owes could not re-derive which reading proved the push landed, so
    a comment still carrying one MEANS a report is owed -- and the reporting
    owner ends its life in a write of its own, ordered after the record.
    """

    def test_the_record_is_made_over_a_durable_move(self) -> None:
        durable = []
        reporting = self.enterContext(patch.object(
            _telemetry_owner, REPORTS_THE_TRANSFER,
            side_effect=lambda gate, rotation: durable.append(self._durable()),
        ))

        self._publishes(standing=LEASED_SHA, granted=False)

        reporting.assert_called_once()
        self.assertTrue(_exemption_reading.is_exempt(durable[0], REWRITTEN_SHA))
        self.assertEqual(durable[0].data[KEY_RECEIPT_SHA], REWRITTEN_SHA)
        self.assertEqual(
            self._records_of(EVENT_TRANSFER), [],
            "the push tail names the telemetry owner and nothing else",
        )

    def test_a_refused_receipt_moves_nothing(self) -> None:
        refusing = _RefusesTheReceipt(self.github)

        with patch.object(
            self.github, PINNED_WRITE, refusing,
        ), self.assertRaises(RuntimeError):
            self._publishes(standing=LEASED_SHA, granted=False)

        self._assert_left_put()
        self.assertEqual(
            _rewrite_reading.read_rewrite_authorization(self._durable()).phase,
            _rewrite_values.LateRewritePhase.AUTHORIZED,
        )
        self.assertNotIn(KEY_RECEIPT_SHA, self._durable().data)
        self.assertEqual(self._records_of(EVENT_TRANSFER), [])

    def test_a_reported_transfer_owes_nothing_after(self) -> None:
        self._publishes(standing=LEASED_SHA, granted=False)

        durable = self._durable()
        self._reported()
        self.assertNotIn(_rewrite_fields.LATE_REWRITE_PROOF, durable.data)
        self.assertIsNone(_rewrite_reading.unreported_transfer(durable))
        self.assertFalse(_rewrite_reading.stranded_transfer_proof(durable))

    def test_a_refused_drop_leaves_the_report_owed(self) -> None:
        # The safe way round: the record has been made and a later tick may
        # make it again, rather than a settled transfer nobody ever announced.
        # So the tick carries on and the proof stands for the next reader.
        _support.granted(self.state)
        _support.spent(self.state)
        # The settlement's own write, which is what the push tail makes before
        # it asks this owner for the record: the proof is durable from here,
        # and only the drop behind the record is refused below.
        self.github.write_pinned_state(self.issue, self.state)
        rotation = _rotation._Rotation(
            staged=True,
            rewrite=_support.rewrite(),
            proof=_rewrite_values.LateRewriteProof.PUSHED,
        )

        with patch.object(
            self.github, PINNED_WRITE, side_effect=RuntimeError("refused"),
        ):
            _telemetry_owner._reports_the_transfer(
                _support.gate(self.github, self.issue, self.state), rotation,
            )

        self.assertEqual(len(self._records_of(EVENT_TRANSFER)), 1)
        # Read off the comment rather than off this process's own object,
        # because the comment is what the next tick opens: the drop was
        # staged and the write that would have made it durable was refused,
        # so the report stands owed and may be made again.
        self.assertEqual(
            _rewrite_reading.unreported_transfer(self._durable()),
            _rewrite_values.LateRewriteProof.PUSHED,
        )

    def test_a_lost_record_is_made_on_the_next_poll(self) -> None:
        # The process dies between the settlement's write and its record. The
        # reconciliation every later tick opens with makes the record, and the
        # poll after that finds nothing left to report.
        with patch.object(
            _telemetry_owner, REPORTS_THE_TRANSFER, side_effect=RuntimeError("lost"),
        ), self.assertRaises(RuntimeError):
            self._publishes(standing=LEASED_SHA, granted=False)
        self.assertEqual(self._records_of(EVENT_TRANSFER), [])

        for _ in range(2):
            self.assertFalse(_reconcile._reconciles_published_work(
                self.github, _transfer_payloads.SPEC, self.issue,
                _transfer_payloads.SOURCE_STAGE, self._durable(),
            ))

        self._reported()
        self.assertIsNone(_rewrite_reading.unreported_transfer(self._durable()))

    def test_an_owed_record_is_made_once(self) -> None:
        # The settlement's own write kept the proof; the record behind it was
        # lost. The first ask makes it and drops the proof durably, so a
        # later poll reading the comment afresh has nothing left to say.
        _support.granted(self.state)
        _support.spent(self.state)
        self.github.write_pinned_state(self.issue, self.state)

        first = _telemetry_owner._reports_a_settled_transfer(
            _support.gate(self.github, self.issue, self.state),
        )
        again = _telemetry_owner._reports_a_settled_transfer(
            _support.gate(self.github, self.issue, self._durable()),
        )

        self.assertEqual((first, again), (True, False))
        self.assertEqual(self._reported()["transfer_proof"], "pushed")
        self.assertIsNone(_rewrite_reading.unreported_transfer(self._durable()))

    def test_nothing_owed_says_nothing(self) -> None:
        # A permission still outstanding has settled nothing, and a proof this
        # build cannot read is damage the recovery parks on, not a record.
        for described, damaged in (("an outstanding permission", False), ("a damaged proof", True)):
            with self.subTest(described):
                self.state = self.github.read_pinned_state(self.issue)
                _support.granted(self.state)
                if damaged:
                    _support.spent(self.state)
                    self.state.set(_rewrite_fields.LATE_REWRITE_PROOF, "not-a-reading")

                self.assertFalse(_telemetry_owner._reports_a_settled_transfer(
                    _support.gate(self.github, self.issue, self.state),
                ))
                self.assertEqual(self._records_of(EVENT_TRANSFER), [])


class SupersededPermissionTest(_SettlementCase):
    """A permission the commit this push published has gone past."""

    def test_a_rollback_republication_drops_it(self) -> None:
        # The branch went back onto the commit a human ruled on and that is
        # what reached the remote, so the head the permit was granted against
        # is gone and no later tick can be granted it. What is left is a claim
        # about a push that cannot happen, and the verdict never moved.
        _support.granted(self.state)
        self.github.write_pinned_state(self.issue, self.state)
        self.readings.stands_on(ACCEPTED_SHA)

        self._publishes(
            standing=LEASED_SHA, granted=False,
            candidate="", rewrite=None, answering=True,
        )

        self._assert_left_put()
        self.assertFalse(
            _rewrite_reading.carries_rewrite_authorization(self._durable()),
        )
        self.assertEqual(self._records_of(EVENT_TRANSFER), [])


class RefusedPermitTest(unittest.TestCase):
    """A permit that refuses settles nothing, whatever the reading then allows.

    The road the record alone cannot tell from a settled transfer. The
    permission is on the comment, outstanding, and names the very commit that
    reaches the remote -- and the permit `late_transfer` re-asks this tick
    refuses it, because the issue was relabelled while the rewrite was being
    made. That refusal is not a hold: the rewritten commit falls through to
    the ordinary cumulative gate, comes back under the ceiling, and is pushed
    on its count. What it may not do is carry a human's verdict with it.
    """

    def setUp(self) -> None:
        adjudicated = _transfer_adjudication.adjudicated(labels=(RELABELLED,))
        self.github = adjudicated.github
        self.issue = adjudicated.issue
        self.state = adjudicated.state
        _transfer_readings.readings(self)
        _transfer_readings.measures(self)
        _transfer_adjudication.open_pull_request(self.github, LEASED_SHA)
        _support.granted(self.state)
        self.github.write_pinned_state(self.issue, self.state)
        self.pushed = self.enterContext(
            _git_owners.seam_patch(_transfer_payloads.PUSH_BRANCH),
        )
        self.pushed.return_value = True
        with patch.object(config, MAX_ADDED_LINES, CEILING):
            self.published = _push._publishes(
                _support.gate(
                    self.github, self.issue, self.state,
                    candidate="", entry=None, rewrite=None,
                ),
                _transfer_payloads.BRANCH,
                _late_gate_models._Entered(
                    stage=_transfer_payloads.SOURCE_STAGE,
                    head=LEASED_SHA,
                    candidate=REWRITTEN_SHA,
                    reconciling=True,
                    answering=True,
                ),
            )

    def test_the_fallback_reading_published_it(self) -> None:
        # The premise: the refusal costs the transfer and not the push, so the
        # settlement really does run over a landed publication of the commit
        # the permission names.
        self.assertTrue(self.published.landed)
        self.pushed.assert_called_once()
        self.assertEqual(
            self.pushed.call_args.kwargs[REVISION], REWRITTEN_SHA,
        )
        self.assertEqual(
            self._durable().data[KEY_RECEIPT_SHA], REWRITTEN_SHA,
        )

    def test_the_verdict_does_not_move(self) -> None:
        durable = self._durable()

        self.assertTrue(_exemption_reading.is_exempt(durable, ACCEPTED_SHA))
        identity = _exemption_reading.read_semantic_identity(durable)
        self.assertEqual(identity.candidate_sha, ACCEPTED_SHA)
        self.assertEqual(identity.base_sha, MERGE_BASE_SHA)

    def test_the_permission_is_left_outstanding(self) -> None:
        # Not spent, because no permit vouched for it; not dropped either,
        # because the remote is now on a head the permit accounts for and a
        # later tick whose refusal has cleared can still settle it.
        authorization = _rewrite_reading.read_rewrite_authorization(self._durable())

        self.assertEqual(
            authorization.phase, _rewrite_values.LateRewritePhase.AUTHORIZED,
        )
        self.assertEqual(authorization.rewrite.to_sha, REWRITTEN_SHA)

    def test_nothing_is_reported_as_a_transfer(self) -> None:
        self.assertEqual(
            [
                record for record in self.github.recorded_events
                if record.get("event") == EVENT_TRANSFER
            ],
            [],
        )

    def _durable(self):
        """The pinned comment as a process starting now would read it."""
        return self.github.read_pinned_state(self.issue)
