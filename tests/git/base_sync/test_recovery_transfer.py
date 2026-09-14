# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which road an unpublished replay takes, and what licenses its push.

The routing above the reissued push, and the permit inside it. Both are about
the same refusal: a rebase of a commit an adjudication accepted may be
published without a reading, and every other way past the gate is the wrong
answer for it -- a count under the ceiling reports a landing with the verdict
still on the commit a human ruled on, and one over it sends an adjudicated
change back into adjudication with a pull request already open over the work.
"""
from __future__ import annotations

import contextlib
import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    attempts,
    outcomes,
    recovery,
    snapshot,
    transfers,
)
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.measurement.models import FrozenCommit, MeasurementFailure
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.workflow.late_split import rewrites as _rewrites
from orchestrator.workflow.stages.implementing import (
    late_push as _push,
    late_transfer as _transfer,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    transfers_test_support as seed,
)

RETRY_PUSH = "_retry_recovery_push"

FOREIGN_PUBLICATION = "_park_foreign_publication_recovery"

ANNOUNCED = "_park_announced_recovery"

UNFINISHED = "_park_unfinished_recovery"

# Every terminal an unpublished checkout can select, on the owner it lives on.
_ANSWERS = MappingProxyType({
    FOREIGN_PUBLICATION: outcomes,
    ANNOUNCED: outcomes,
    "_park_rolled_back_recovery": outcomes,
    "_park_unvouched_recovery": outcomes,
    "_park_unrecorded_recovery": outcomes,
    "_park_diverged_recovery": outcomes,
    "_reject_unknown_recovery_comparison": outcomes,
    RETRY_PUSH: recovery,
})

# The one label this route's own finish writes.
_VALIDATING = WorkflowLabel.VALIDATING

# A remote standing where the attempt's anchor says it left it, and one
# somebody else moved.
_ON_ANCHOR = seed.ACCEPTED_SHA
_MOVED = seed.FOREIGN_SHA

# A base the remote would not name, which is the half of the re-derived
# evidence no local reading can stand in for.
_NO_BASE = FrozenCommit(
    failure=MeasurementFailure.BASE_UNREADABLE, detail="no token",
)

_UNREADABLE_TREE = _verification_probes._WorktreeStatus(readable=False)


def _snapshot(
    remote_head: str = _ON_ANCHOR,
    local_head: str = seed.REPLAYED_SHA,
    **counts,
):
    """The comparison one recovery road is handed."""
    return fixtures._snapshot(
        local_head=local_head, remote_head=remote_head, **counts,
    )


def _pushed(**answer) -> _push._PushedCandidate:
    """What one gated publication answered, in the shape the retry reads."""
    return _push._PushedCandidate(**answer)


def _handled() -> MagicMock:
    """A collaborator stub that reports the tick as handled."""
    return MagicMock(return_value=True)


def _grants(case, rewrite=seed.GRANTED) -> None:
    """Put the permission and the debt one grant leaves on the comment."""
    seed.granted(case.state, rewrite)


@contextlib.contextmanager
def _every_answer(selected: dict):
    """Patch every terminal the road can select, recording them by name."""
    with contextlib.ExitStack() as stack:
        for name, owner in _ANSWERS.items():
            selected[name] = _handled()
            stack.enter_context(patch.object(owner, name, selected[name]))
        yield


class UnpublishedRouteTest(seed.TransferCase):
    """One checkout the pull request is not standing on selects one road."""

    def test_an_attempt_for_another_publication_parks(self) -> None:
        # Every road behind this posts a notice to the pull request this tick
        # holds and files an audit event under the stage it reads, so terms
        # the issue no longer has are refused before any of them -- including
        # on an issue carrying no verdict, where no permit would catch it.
        for described, terms in (
            ("a repointed pull request", {"pr_number": seed.OTHER_PR_NUMBER}),
            ("a relabelled issue", {"stage": seed.OTHER_STAGE}),
        ):
            with self.subTest(described):
                self._fresh(pending_rewrite=replace(seed.RECORDED, **terms))
                self._assert_selects(FOREIGN_PUBLICATION)

    def test_terms_in_flight_are_held_too(self) -> None:
        # The terms go down before `git rebase` and can say which publication
        # the attempt was for with no replay recorded beside them.
        self._fresh(pending_rewrite=replace(
            seed.DECLARED, pr_number=seed.OTHER_PR_NUMBER,
        ))

        self._assert_selects(FOREIGN_PUBLICATION)

    def test_an_announced_publication_the_remote_lost(self) -> None:
        # The mark stands only past a finish's notice and audit event, so it
        # says a push had landed. This road is reached over a remote that is
        # not standing on the checkout, so whatever was announced is gone --
        # and a retry would overwrite the rollback and announce it twice.
        for described, announced in (
            ("naming this replay", seed.REPLAYED_SHA),
            ("naming some other head", seed.FOREIGN_SHA),
            ("naming the anchor no finish announces", seed.ACCEPTED_SHA),
        ):
            with self.subTest(described):
                self._fresh()
                attempts._announces(self.context, announced)

                self._assert_selects(ANNOUNCED)

    def test_its_own_finish_relabel_is_not_foreign(self) -> None:
        # A finish relabels to `validating` past the mark and before the clear,
        # so that label beside a mark naming this head is this route's own
        # last step -- and the remote not standing on it is the announced
        # publication the next question refuses.
        self._fresh(label=_VALIDATING)
        attempts._announces(self.context, seed.REPLAYED_SHA)

        self._assert_selects(ANNOUNCED)

    def test_every_other_relabel_is_still_foreign(self) -> None:
        for described, label, number, announced in (
            ("validating with nothing announced", _VALIDATING, None, ""),
            (
                "validating beside a mark naming another head",
                _VALIDATING, None, seed.FOREIGN_SHA,
            ),
            (
                "a stage this route never writes",
                seed.OTHER_STAGE, None, seed.REPLAYED_SHA,
            ),
            (
                "validating on a pull request somebody repointed",
                _VALIDATING, seed.OTHER_PR_NUMBER, seed.REPLAYED_SHA,
            ),
        ):
            with self.subTest(described):
                self._fresh(label=label)
                if number is not None:
                    self.context = replace(self.context, pr_number=number)
                if announced:
                    attempts._announces(self.context, announced)

                self._assert_selects(FOREIGN_PUBLICATION)

    def test_a_settled_transfer_reads_as_a_rollback(self) -> None:
        # The write that settled says the pull request HAD this commit, so a
        # remote standing anywhere else was rolled back -- and the head it was
        # rolled back to is the very anchor a retry would lease against.
        seed.settled(self.state)

        self._assert_selects("_park_rolled_back_recovery")

    def test_a_receipt_for_the_replay_says_so_too(self) -> None:
        seed.receipted(self.state)

        self._assert_selects("_park_rolled_back_recovery")

    def test_a_transfer_nobody_can_vouch_for_parks(self) -> None:
        # A permission naming a commit this checkout is not standing on is a
        # claim nothing can check, and every other road from here would leave
        # the ordinary gate to measure an adjudicated change again.
        _grants(self, replace(seed.GRANTED, to_sha=seed.NEWER_SHA))

        self._assert_selects("_park_unvouched_recovery")

    def test_a_record_that_disowns_the_checkout_parks(self) -> None:
        for described, pending in (
            ("in pieces", seed.DAMAGED),
            ("naming another commit", replace(seed.RECORDED, sha=_MOVED)),
        ):
            with self.subTest(described):
                self._fresh(pending_rewrite=pending)
                self._assert_selects("_park_unrecorded_recovery")

    def test_a_recorded_replay_is_retried(self) -> None:
        retried = self._assert_selects(RETRY_PUSH)

        # The record already names the checkout, so the permit is not the
        # only thing that could vouch for it.
        self.assertIs(retried.call_args.kwargs.get("permit_alone"), False)

    def test_a_replay_in_flight_is_retried(self) -> None:
        # The window between `git rebase` returning and the write that names
        # what it produced: the terms are on the comment, no id names the
        # head, and the verdict is the only thing that can vouch for it.
        self._fresh(pending_rewrite=seed.DECLARED)

        retried = self._assert_selects(RETRY_PUSH)

        self.assertIs(retried.call_args.kwargs.get("permit_alone"), True)
        self.assertEqual(
            retried.call_args.args[2], transfers._Handoff.UNRECORDED,
        )

    def test_this_routes_own_grant_reopens_that_road(self) -> None:
        # The retry above persists its permission before it pushes, so a crash
        # there leaves terms with no head beside an outstanding grant. Refused
        # as the plain in-flight window, this route would park every crash its
        # own durable write caused -- on counts that read a replay as
        # divergence -- and leave the permission with nothing to spend it.
        self._fresh(pending_rewrite=seed.DECLARED)
        _grants(self)

        retried = self._assert_selects(RETRY_PUSH)

        self.assertEqual(
            retried.call_args.args[2], transfers._Handoff.OUTSTANDING,
        )

    def test_a_grant_from_another_attempt_still_parks(self) -> None:
        # The permission is what vouches for the head above, so one this
        # build cannot tie to the attempt in hand vouches for nothing.
        self._fresh(pending_rewrite=seed.DECLARED)
        _grants(self, replace(seed.GRANTED, source_stage=seed.OTHER_STAGE))

        self._assert_selects("_park_unvouched_recovery")

    def test_a_moved_remote_falls_back_to_the_counts(self) -> None:
        for described, counts, answer in (
            ("no reading happened", {}, "_reject_unknown_recovery_comparison"),
            ("commits of its own", {"behind": 1}, "_park_diverged_recovery"),
            ("strictly ahead", {"ahead": 1}, RETRY_PUSH),
        ):
            with self.subTest(described):
                self._fresh()
                self._assert_selects(
                    answer, _snapshot(remote_head=_MOVED, **counts),
                )

    def _assert_selects(self, answer: str, completed=None) -> MagicMock:
        """Route one completed comparison and pin the single road it takes."""
        selected = {}
        completed = completed or _snapshot()
        with _every_answer(selected):
            self.assertTrue(recovery._route_an_unpublished_head(
                self.context, completed,
                transfers._carried_by(self.context, completed.head),
            ))
        taken = selected.pop(answer)
        taken.assert_called_once()
        for unselected in selected.values():
            unselected.assert_not_called()
        return taken


class UnmovedHeadTest(seed.TransferCase):
    """A checkout on the anchor is a shortcut only where nothing is left.

    HEAD equalling the pinned anchor is two states at once: an attempt that
    got no further than pinning it, and one that got a long way and was UNDONE
    -- a reset whose park write was lost, or a hand at the checkout. Only the
    first may drop the anchor and hand the branch to a fresh rebase.
    """

    def setUp(self) -> None:
        super().setUp()
        # The anchor and the verdict, with no record of a replay: the shape
        # every case here starts from and adds one leftover to.
        self._fresh(pending_rewrite=seed.ABSENT)

    def test_an_unstarted_attempt_hands_the_tick_back(self) -> None:
        # Nothing was left behind, so the anchor costs the issue nothing and
        # the normal rebase flow does the work again on this same tick.
        self.assertFalse(self._answers(shortcut=True))

    def test_a_previous_rotation_is_not_a_rollback(self) -> None:
        # A settled transfer is never cleared, so an issue that ever earned
        # one would fail this test for the rest of its life.
        seed.settled(self.state)

        self.assertFalse(self._answers(shortcut=True))

    def test_every_leftover_is_finished_as_a_rollback(self) -> None:
        for described, leave in (
            ("a replay the attempt recorded", self._recorded_replay),
            ("a record something took apart", self._damaged_record),
            ("a permission nobody spent", self._unspent_permission),
            ("a mark naming another head", self._foreign_announcement),
            ("a mark naming the anchor itself", self._anchor_announcement),
        ):
            with self.subTest(described):
                self._fresh(pending_rewrite=seed.ABSENT)
                leave()

                self.assertTrue(self._answers(shortcut=False))

    def _recorded_replay(self) -> None:
        self.context = replace(self.context, pending_rewrite=seed.RECORDED)

    def _damaged_record(self) -> None:
        self.context = replace(self.context, pending_rewrite=seed.DAMAGED)

    def _unspent_permission(self) -> None:
        _grants(self)

    def _foreign_announcement(self) -> None:
        attempts._announces(self.context, seed.REPLAYED_SHA)

    def _anchor_announcement(self) -> None:
        # No finish announces the anchor, so a mark naming it is a checkpoint
        # something took apart -- and read against the head in hand it would
        # answer as no announcement at all.
        attempts._announces(self.context, seed.ACCEPTED_SHA)

    def _answers(self, *, shortcut: bool) -> bool:
        """Route the unmoved head and pin which of the two roads it takes."""
        cleared = MagicMock(return_value=False)
        parked = _handled()
        with patch.object(
            snapshot, "_clear_unchanged_recovery", cleared,
        ), patch.object(outcomes, "_park_undone_recovery", parked):
            answered = recovery._finish_an_unmoved_head(
                self.context, _snapshot(local_head=seed.ACCEPTED_SHA),
            )
        taken, refused = (
            (cleared, parked) if shortcut else (parked, cleared)
        )
        taken.assert_called_once()
        refused.assert_not_called()
        return answered


class LicensedRetryTest(seed.TransferCase):
    """What the permit decides for a push nothing else may license."""

    def setUp(self) -> None:
        super().setUp()
        # The permission the interrupted grant left, which is what every case
        # below but the two that start over is decided on.
        _grants(self)

    def test_assembled_evidence_reaches_the_permit(self) -> None:
        # The grant never landed, so the evidence is re-derived and handed to
        # the permit -- and the gate behind it is told the permit is the whole
        # of what may let this push out.
        self._fresh(pending_rewrite=seed.DECLARED)
        rebuilt = seed.GRANTED
        permits = _handled()

        entered = self._retries(
            reconstructed=MagicMock(return_value=rebuilt), permits=permits,
        )

        self.assertIs(permits.call_args.args[2], rebuilt)
        self.assertIs(entered.rewrite, rebuilt)
        self.assertTrue(entered.permit_only)

    def test_a_standing_permission_is_the_evidence(self) -> None:
        # The record IS the evidence there, so nothing is assembled and the
        # gate re-asks the permission the grant left.
        entered = self._retries(permits=_handled())

        self.assertIsNone(entered.rewrite)
        self.assertTrue(entered.permit_only)
        self.assertEqual(entered.candidate, seed.REPLAYED_SHA)

    def test_an_ordinary_replay_is_still_measured(self) -> None:
        # An issue carrying no verdict has no transfer to license anything,
        # so the reissued push is the cumulative gate's as it always was.
        self.context = seed.context()

        entered = self._retries()

        self.assertFalse(entered.permit_only)

    def test_a_replay_no_verdict_can_prove_parks(self) -> None:
        # In flight, with evidence that will not assemble: measuring says how
        # big a change is, never whose it is, so there is nothing left to
        # publish it on.
        self._fresh(pending_rewrite=seed.DECLARED)

        with patch.object(
            _measurement_commits, "_freeze_base_commit",
            MagicMock(return_value=_NO_BASE),
        ):
            self._parks("_park_unproven_replay_recovery", permit_alone=True)

    def test_a_refused_permit_parks_unmeasured(self) -> None:
        self._parks(
            "_park_refused_permit_recovery",
            permits=MagicMock(return_value=False),
        )

    def test_a_permit_the_gate_refuses_parks_too(self) -> None:
        # The permit is asked twice -- here and inside the gate -- so one that
        # stops holding in between is refused there rather than measured.
        self._parks(
            "_park_refused_permit_recovery",
            published=_pushed(held=True, refused=True),
        )

    def test_a_push_that_moved_no_verdict_parks(self) -> None:
        # The push went out and the rotation did not ride it, so the
        # permission is still outstanding and the anchor stays pinned.
        parked = self._parks(UNFINISHED, published=_pushed(landed=True))

        self.assertIn(seed.REPLAYED_SHA, parked.call_args.args[2])

    def _parks(self, park: str, **retry) -> MagicMock:
        """Run the retry and pin the single park it takes."""
        parked = _handled()
        with patch.object(outcomes, park, parked):
            self.assertTrue(self._retry(**retry))
        parked.assert_called_once()
        return parked

    def _retries(self, **retry):
        """Run the retry and hand back the terms the gate was entered on."""
        publishes = MagicMock(return_value=_pushed(landed=True))
        with patch.object(transfers, "_rotated_onto", _handled()):
            self.assertTrue(self._retry(publishes=publishes, **retry))
        return publishes.call_args.args[2]

    def _retry(
        self,
        *,
        publishes=None,
        permits=None,
        reconstructed=None,
        published=None,
        permit_alone: bool = False,
    ) -> bool:
        """One reissued push, with the gate and the permit answered."""
        gated = MagicMock()
        gated._publishes = publishes or MagicMock(
            return_value=published or _pushed(),
        )
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(
                transfers, "_permits_the_publication", permits or _handled(),
            ))
            if reconstructed is not None:
                stack.enter_context(patch.object(
                    transfers, "_reconstructed", reconstructed,
                ))
            stack.enter_context(patch.object(
                recovery.publication, "_gated_publication",
                MagicMock(return_value=gated),
            ))
            stack.enter_context(patch.object(
                recovery.persistence, "_finalize_recovered_rebase",
                MagicMock(return_value=True),
            ))
            stack.enter_context(patch.object(
                _verification_probes, "_worktree_dirty_files",
                MagicMock(return_value=[]),
            ))
            return recovery._retry_recovery_push(
                self.context, _snapshot(),
                transfers._carried_by(self.context, seed.REPLAYED_SHA),
                permit_alone=permit_alone,
            )


class PermitEntryTest(seed.TransferCase):
    """The publication the permit is re-asked over is this tick's own read."""

    def setUp(self) -> None:
        super().setUp()
        _grants(self)

    def test_an_unenterable_publication_refuses(self) -> None:
        # The entry is the pull request read before any effect, and the terms
        # the record claims are checked against it. Nothing to check them
        # against is a refusal rather than a fall-through.
        carried = MagicMock()

        with patch.object(
            _transfer, "_carried_over", carried,
        ), patch.object(
            _verification_probes, "_worktree_status",
            MagicMock(return_value=_UNREADABLE_TREE),
        ):
            permitted = transfers._permits_the_publication(
                self.context, seed.REPLAYED_SHA,
            )

        self.assertFalse(permitted)
        carried.assert_not_called()

    def test_the_permit_reads_the_frozen_entry(self) -> None:
        carried = MagicMock(return_value="carried")

        with patch.object(_transfer, "_carried_over", carried), patch.object(
            _verification_probes, "_worktree_status",
            MagicMock(return_value=_verification_probes._WorktreeStatus(
                readable=True,
            )),
        ):
            permitted = transfers._permits_the_publication(
                self.context, seed.REPLAYED_SHA, _rewrites.LateRewrite(),
            )

        self.assertTrue(permitted)
        gate = carried.call_args.args[0]
        self.assertEqual(gate.entry.pr_number, fixtures.PR_NUMBER)
        self.assertEqual(gate.candidate, seed.REPLAYED_SHA)
        self.assertTrue(gate.reconciling)


if __name__ == "__main__":
    unittest.main()
