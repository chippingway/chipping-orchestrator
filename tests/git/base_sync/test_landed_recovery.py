# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite's route is finished once, and only where the comment accounts for it.
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    attempts,
    landed_recovery as _landed_recovery,
    landed_settlement as _landed_settlement,
    replay_publication_parks as _replay_publication_parks,
    replay_transfer_parks as _replay_transfer_parks,
    transfer_publication as _transfer_publication,
    transfers,
)
from orchestrator.git.verification import status as _worktree_status
from orchestrator.workflow.late_split import rewrite_reading as _rewrite_reading
from orchestrator.workflow.state import WorkflowLabel
from tests.git.base_sync import (
    base_sync_helpers as fixtures,
    recovery_transfer_test_support as _recovery_cases,
    transfers_test_support as seed,
)

BASE_REBASED = "base_rebased"

LATE_TRANSFER = "late_transfer"

RELABEL_ONLY = "crash_recovery_relabel_only"

RETRY_COMMENT_ID = 4100

# The mark a finish leaves between its announcement and its clear.
KEY_ANNOUNCED_SHA = "pending_auto_base_rebase_announced_sha"

_CLEAN = _worktree_status._WorktreeStatus(readable=True)

# The pull request standing on the replay the attempt recorded making.
_LANDED = _recovery_cases._snapshot(remote_head=seed.REPLAYED_SHA)


class _RefusesTheClear:
    """A pinned comment that takes every write but the one ending the attempt."""

    def __init__(self, writes) -> None:
        self._writes = writes

    def __call__(self, issue, state):
        """Refuse the write that blanks the mark, and take every other."""
        if state.data.get(KEY_ANNOUNCED_SHA, "") is None:
            raise RuntimeError("the clearing write was lost")
        return self._writes(issue, state)


class _LandedCase(seed.TransferCase):
    """An interrupted attempt whose push the pull request already carries."""

    def setUp(self) -> None:
        super().setUp()
        self.tree = self.enterContext(patch.object(
            _worktree_status, "_worktree_status", MagicMock(return_value=_CLEAN),
        ))

    def _finish(self, context=None) -> bool:
        """One pass of the landed route over the comment as it now reads."""
        context = context or self.context
        return _landed_recovery._finish_published_recovery(
            context, _LANDED, transfers._carried_by(context, _LANDED.head),
        )

    def _events(self, name: str) -> list[dict]:
        return [
            record for record in self.context.gh.recorded_events
            if record.get("event") == name
        ]

    def _assert_announced_nothing(self) -> None:
        """No `base_rebased` on the stream and no notice on the pull request."""
        self.assertEqual(self._events(BASE_REBASED), [])
        self.assertEqual(self.context.gh.posted_pr_comments, [])

    def _durable(self):
        return self.context.gh.read_pinned_state(self.context.issue)


class RefusedLandingTest(_LandedCase):
    """Every landing nobody can account for holds its anchor and says nothing."""

    def test_a_foreign_publication_parks_in_place(self) -> None:
        self._fresh(pending_rewrite=replace(seed.RECORDED, pr_number=seed.OTHER_PR_NUMBER))

        self._assert_parks(_replay_publication_parks, "_park_foreign_publication_recovery")

    def test_a_foreign_mark_holds_the_route(self) -> None:
        # One naming another head cannot say whether the notice and the event
        # are out, and read as "not announced" both would be said again.
        attempts._announces(self.context, seed.FOREIGN_SHA)

        self._assert_unfinished(_landed_recovery._FOREIGN_MARK)

    def test_an_unrecorded_landing_holds_the_route(self) -> None:
        # The remote and the checkout agreeing proves only that they agree.
        unproven = _landed_recovery._UNPROVEN_LANDING.format(published=seed.REPLAYED_SHA)
        for described, recorded in (
            ("a record naming another head", replace(seed.RECORDED, sha=seed.FOREIGN_SHA)),
            ("a damaged record", seed.DAMAGED),
            ("no record at all", seed.ABSENT),
            ("terms in flight with no permission to vouch", seed.DECLARED),
        ):
            with self.subTest(described):
                self._fresh(pending_rewrite=recorded)

                self._assert_unfinished(unproven)

    def test_a_loose_tree_holds_the_route(self) -> None:
        # Under a verdict only; a tree nobody could read is not a clean one.
        seed.settled(self.state)
        for described, status in (
            ("uncommitted work", _worktree_status._WorktreeStatus(readable=True, paths=("scratch.txt",))),
            ("a tree nobody could read", _worktree_status._WorktreeStatus(readable=False)),
        ):
            with self.subTest(described):
                self.tree.return_value = status

                self._assert_unfinished(_landed_recovery._LOOSE_TREE)

    def test_an_unaccounted_transfer_holds_the_route(self) -> None:
        # A settled transfer whose debt still stands is a write that did not
        # land whole; a mark beside a permission still outstanding is too.
        seed.settled(self.state)
        seed.owes(self.state, seed.REPLAYED_SHA, seed.ACCEPTED_SHA)

        self._assert_unfinished(_transfer_publication._UNPAID.format(owed=seed.REPLAYED_SHA))

        self._fresh()
        seed.granted(self.state)
        attempts._announces(self.context, seed.REPLAYED_SHA)

        self._assert_unfinished(_landed_recovery._ANNOUNCED_UNSETTLED)

    def _assert_unfinished(self, detail: str) -> None:
        parked = self._assert_parks(_replay_transfer_parks, "_park_unfinished_recovery")
        self.assertEqual(parked.call_args.args[2], detail)

    def _assert_parks(self, owner, park: str) -> MagicMock:
        parked = _recovery_cases._handled()
        with patch.object(owner, park, parked):
            self.assertTrue(self._finish())
        parked.assert_called_once()
        self._assert_announced_nothing()
        return parked


class LandedFinishTest(_LandedCase):
    """The record picks exactly one of the three finishes a landing can owe."""

    def test_an_ordinary_landing_is_finished(self) -> None:
        # No verdict: nothing to account for and no tree to prove.
        self.context = seed.context()
        self.tree.return_value = _worktree_status._WorktreeStatus(readable=False)

        self.assertTrue(self._finish())

        methods = [record["method"] for record in self._events(BASE_REBASED)]
        self.assertEqual(methods, [RELABEL_ONLY])
        self.assertEqual(len(self.context.gh.posted_pr_comments), 1)

    def test_an_outstanding_permission_owes_a_no_op(self) -> None:
        seed.granted(self.state)
        settles = _recovery_cases._handled()

        with patch.object(_landed_settlement, "_settle_published_recovery", settles):
            self.assertTrue(self._finish())

        settles.assert_called_once()
        self.assertEqual(self._events(BASE_REBASED), [])

    def test_a_lost_report_is_made_before_the_finish(self) -> None:
        # The settlement's proof is still on the comment, so its record never
        # reached the sinks; it is made once and the proof dropped durably.
        seed.settled(self.state)

        self.assertTrue(self._finish())

        self.assertEqual(len(self._events(LATE_TRANSFER)), 1)
        self.assertEqual(len(self._events(BASE_REBASED)), 1)
        self.assertIsNone(_rewrite_reading.unreported_transfer(self._durable()))

    def test_an_announced_finish_owes_only_its_route(self) -> None:
        # The notice and the event already went out ahead of the mark, and the
        # reply that re-entered the parked attempt is spent by the same write.
        seed.settled(self.state)
        attempts._announces(self.context, seed.REPLAYED_SHA)
        self.state.set(fixtures.KEY_AWAITING_HUMAN, True)
        self.context = replace(self.context, unparking_consumed_max=RETRY_COMMENT_ID)

        self.assertTrue(self._finish())

        self._assert_announced_nothing()
        self.assertIn((fixtures.ISSUE, WorkflowLabel.VALIDATING), self.context.gh.label_history)
        durable = self._durable()
        self.assertIsNone(durable.get(KEY_ANNOUNCED_SHA))
        self.assertFalse(durable.get(fixtures.KEY_AWAITING_HUMAN))
        self.assertEqual(durable.get(fixtures.KEY_LAST_ACTION_COMMENT_ID), RETRY_COMMENT_ID)

    def test_an_advanced_base_leaves_the_route(self) -> None:
        # The announced head is already behind the base, so the finish is made
        # durable and nobody is routed to a commit this tick will replace.
        seed.settled(self.state)
        attempts._announces(self.context, seed.REPLAYED_SHA)
        self.context = replace(self.context, behind=fixtures.BEHIND_BY)

        self.assertFalse(self._finish())

        self.assertEqual(self.context.gh.label_history, [])
        durable = self._durable()
        self.assertIsNone(durable.get(KEY_ANNOUNCED_SHA))
        self.assertEqual(durable.get(fixtures.KEY_REVIEW_ROUND), 0)


class RepeatedPollTest(_LandedCase):
    """A finish lost in either window past its announcement is never said twice."""

    def test_each_window_resumes_into_one_finish(self) -> None:
        for window, crash in (
            ("before the relabel", self._crashes_at_the_relabel),
            ("before the clearing write", self._crashes_at_the_clearing_write),
        ):
            with self.subTest(window):
                self._fresh()
                seed.settled(self.state)
                with crash(), self.assertRaises(RuntimeError):
                    self._finish()

                self.assertTrue(self._finish(self._resumed()))

                self.assertEqual(len(self._events(BASE_REBASED)), 1)
                self.assertEqual(len(self._events(LATE_TRANSFER)), 1)
                self.assertEqual(len(self.context.gh.posted_pr_comments), 1)
                self.assertEqual(self.context.gh.label_history, [(fixtures.ISSUE, WorkflowLabel.VALIDATING)])
                self.assertIsNone(self._durable().get(KEY_ANNOUNCED_SHA))

    def _resumed(self):
        """The same attempt as a process starting now reads it."""
        return replace(
            self.context,
            state=self._durable(),
            label=self.context.gh.workflow_label(self.context.issue),
        )

    def _crashes_at_the_relabel(self):
        return patch.object(self.context.gh, "set_workflow_label", side_effect=RuntimeError("lost"))

    def _crashes_at_the_clearing_write(self):
        gh = self.context.gh
        return patch.object(gh, "write_pinned_state", _RefusesTheClear(gh.write_pinned_state))
