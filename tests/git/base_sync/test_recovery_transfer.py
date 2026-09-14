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

from orchestrator.git.base_sync import outcomes, recovery, transfers
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.measurement.models import FrozenCommit, MeasurementFailure
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.workflow.late_split import rewrites as _rewrites
from orchestrator.workflow.stages.implementing import (
    late_push as _push,
    late_transfer as _transfer,
)
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    transfers_test_support as seed,
)

RETRY_PUSH = "_retry_recovery_push"

UNFINISHED = "_park_unfinished_recovery"

# Every terminal an unpublished checkout can select, on the owner it lives on.
_ANSWERS = MappingProxyType({
    "_park_foreign_publication_recovery": outcomes,
    "_park_rolled_back_recovery": outcomes,
    "_park_unvouched_recovery": outcomes,
    "_park_unrecorded_recovery": outcomes,
    "_park_diverged_recovery": outcomes,
    "_reject_unknown_recovery_comparison": outcomes,
    RETRY_PUSH: recovery,
})

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


def _snapshot(remote_head: str = _ON_ANCHOR, **counts):
    """The completed comparison the unpublished road is handed."""
    return fixtures._snapshot(
        local_head=seed.REPLAYED_SHA, remote_head=remote_head, **counts,
    )


def _pushed(**answer) -> _push._PushedCandidate:
    """What one gated publication answered, in the shape the retry reads."""
    return _push._PushedCandidate(**answer)


@contextlib.contextmanager
def _every_answer(selected: dict):
    """Patch every terminal the road can select, recording them by name."""
    with contextlib.ExitStack() as stack:
        for name, owner in _ANSWERS.items():
            selected[name] = MagicMock(return_value=True)
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
                self._assert_selects("_park_foreign_publication_recovery")

    def test_terms_in_flight_are_held_too(self) -> None:
        # The terms go down before `git rebase` and can say which publication
        # the attempt was for with no replay recorded beside them.
        self._fresh(pending_rewrite=replace(
            seed.DECLARED, pr_number=seed.OTHER_PR_NUMBER,
        ))

        self._assert_selects("_park_foreign_publication_recovery")

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
        seed.granted(self.state, replace(seed.GRANTED, to_sha=seed.NEWER_SHA))

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


class LicensedRetryTest(seed.TransferCase):
    """What the permit decides for a push nothing else may license."""

    def test_assembled_evidence_reaches_the_permit(self) -> None:
        # The grant never landed, so the evidence is re-derived and handed to
        # the permit -- and the gate behind it is told the permit is the whole
        # of what may let this push out.
        self._fresh(pending_rewrite=seed.DECLARED)
        rebuilt = seed.GRANTED
        permits = MagicMock(return_value=True)

        entered = self._retries(
            reconstructed=MagicMock(return_value=rebuilt), permits=permits,
        )

        self.assertIs(permits.call_args.args[2], rebuilt)
        self.assertIs(entered.rewrite, rebuilt)
        self.assertTrue(entered.permit_only)

    def test_a_standing_permission_is_the_evidence(self) -> None:
        # The record IS the evidence there, so nothing is assembled and the
        # gate re-asks the permission the grant left.
        seed.granted(self.state)

        entered = self._retries(permits=MagicMock(return_value=True))

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
        seed.granted(self.state)

        self._parks(
            "_park_refused_permit_recovery",
            permits=MagicMock(return_value=False),
        )

    def test_a_permit_the_gate_refuses_parks_too(self) -> None:
        # The permit is asked twice -- here and inside the gate -- so one that
        # stops holding in between is refused there rather than measured.
        seed.granted(self.state)

        self._parks(
            "_park_refused_permit_recovery",
            published=_pushed(held=True, refused=True),
        )

    def test_a_push_that_moved_no_verdict_parks(self) -> None:
        # The push went out and the rotation did not ride it, so the
        # permission is still outstanding and the anchor stays pinned.
        seed.granted(self.state)

        parked = self._parks(UNFINISHED, published=_pushed(landed=True))

        self.assertIn(seed.REPLAYED_SHA, parked.call_args.args[2])

    def _parks(self, park: str, **retry) -> MagicMock:
        """Run the retry and pin the single park it takes."""
        parked = MagicMock(return_value=True)
        with patch.object(outcomes, park, parked):
            self.assertTrue(self._retry(**retry))
        parked.assert_called_once()
        return parked

    def _retries(self, **retry):
        """Run the retry and hand back the terms the gate was entered on."""
        publishes = MagicMock(return_value=_pushed(landed=True))
        with patch.object(
            transfers, "_rotated_onto", MagicMock(return_value=True),
        ):
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
                transfers, "_permits_the_publication",
                permits or MagicMock(return_value=True),
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

    def test_an_unenterable_publication_refuses(self) -> None:
        # The entry is the pull request read before any effect, and the terms
        # the record claims are checked against it. Nothing to check them
        # against is a refusal rather than a fall-through.
        seed.granted(self.state)
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
        seed.granted(self.state)
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
