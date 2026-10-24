# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Cleanup dispatch over a closed owner whose pinned record admission refuses.

The record reads back empty, which is what an owner no cycle ever touched
reads as -- so a poll would drop its close as ending nothing, and a pass
would find nothing owed. Neither is what the record says; it says nothing at
all. So the reading is held as a read that established nothing holds it, on
every label and whether or not the issue is open again, and nothing is
written for it -- no receipt, mark, label, terminal, pull-request close, or
reclamation -- whichever route reaches the owner and however the pass ends: a
free tick, a refused submission, a retained reading retried off every swept
label, a pass that breaks, and a reopen between the poll and the pass. The
one trace is a local line naming the issue and the version found, and the
reading kept is what ends the cycle once a current record is back.

The same owner over a current record is `test_dispatch_cleanup_deferral.py`'s.
"""
from __future__ import annotations

import importlib
import unittest
from unittest.mock import Mock, patch

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.workflow.engine import (
    dispatch_partition as _dispatch_partition,
    dispatch_workers as _dispatch_workers,
    poll_models as _poll_models,
)
from tests.support.writer_claims import claimable
from tests.workflow.engine import cleanup_deferral_support as _support
from tests.workflow.engine.unfinished_cleanup_support import UnfinishedCleanupCase
from tests.workflow.fixtures import LABEL_DONE
from tests.workflow.observation_support import left_on_github, refuse_record
from tests.workflow.stages.decomposition.late_cancel_support import hold_plan_pr

_OWED = frozenset((_support.OWNER_NUMBER,))

# The local line a refused record leaves -- the issue, and the version found
# against the one this build admits -- and what the poll and the pass each
# say they withheld over it.
_REFUSED_RECORD = f"issue=#{_support.OWNER_NUMBER} pinned comment"
_FOUND_VERSION = "found schema_version None, supported 1"
_NO_RECEIPT = "posting no close receipt"
_NO_CLEANUP = "running no cleanup"


class RefusedRecordDeferralTest(UnfinishedCleanupCase, unittest.TestCase):
    """Whole ticks over the refused owner, each leaving it exactly as it stood.

    The owner holds a plan pull request as well as its snapshot ref, which a
    current record's ending would close and reclaim.
    """

    def setUp(self) -> None:
        super().setUp()
        hold_plan_pr(self.github, self.github.get_issue(_support.OWNER_NUMBER))
        refuse_record(self.github, _support.OWNER_NUMBER)
        self.scheduler = self._scheduler()
        self.remote = Mock()
        self.before = left_on_github(self.github, _support.OWNER_NUMBER)

    def test_a_free_pass_leaves_it_as_it_stands(self) -> None:
        # Its swept label would bring a later tick back, but only to another
        # refusal: the pass marked nothing, so the reading is the one thing
        # left that ends the cycle once a current record is back.
        said = self._refused_tick()

        self._assert_untouched(said)
        self.stage.assert_not_called()
        self.assertEqual(self._observed(_support.REPO_SLUG), _OWED)

    def test_a_refused_submit_keeps_it_unwritten(self) -> None:
        # The receipt a held owner is owed is posted from the record, and this
        # one names no cycle to scope it to; nor does it say nothing is owed.
        said = self._tick_a_worker_held(self.scheduler)

        self._assert_untouched(said)
        self.assertEqual(self._observed(_support.REPO_SLUG), _OWED)

    def test_a_retained_reading_retried_off_label(self) -> None:
        # Off every swept label, where a current record's owed ending gets a
        # queried label back: this one gets nothing, and keeps the reading,
        # since nothing on it says the ending is over.
        self._tick_a_worker_held(self.scheduler)
        self._relabelled(LABEL_DONE)
        self.before = left_on_github(self.github, _support.OWNER_NUMBER)

        said = self._refused_tick()

        self._assert_untouched(said)
        self.assertEqual(self._label(), LABEL_DONE)
        self.assertEqual(self._observed(_support.REPO_SLUG), _OWED)

    def test_a_failed_pass_posts_nothing_on_its_exit(self) -> None:
        # The exit that hands a broken pass's reading back writes its receipt
        # from the record, read again behind the refetch that broke.
        failing = _FailingOnce(self.github.get_issue)

        with patch.object(self.github, "get_issue", side_effect=failing):
            said = self._refused_tick()

        self.assertTrue(failing.failed)
        self._assert_untouched(said)
        self.assertEqual(self._observed(_support.REPO_SLUG), _OWED)
        self.assertTrue(any(_support.PASS_FAILED in line for line in said), said)

    def _refused_tick(self) -> list[str]:
        """One tick the scheduler is free for, saying what it said."""
        with self.assertLogs(_support.WORKFLOW_LOG) as logged:
            self._ticked(self.scheduler, remote=self.remote)
            return list(logged.output)

    def _assert_untouched(self, said: list[str]) -> None:
        """Nothing changed on GitHub or the remote, and the local line that says why."""
        self.assertEqual(left_on_github(self.github, _support.OWNER_NUMBER), self.before)
        self.remote.assert_not_called()
        named = [line for line in said if _REFUSED_RECORD in line]
        self.assertTrue(any(_FOUND_VERSION in line for line in named), said)


class RefusedRecordReopenTest(_support.DeferralCase, unittest.TestCase):
    """The refused owner reopened inside one tick, between its poll and its pass.

    The route binds, so the sweep is what the pass reaches. Over a current
    record it marks the cancellation and stops; over this one the poll posts
    nothing and the pass marks nothing, whether the record parses under no
    version or not at all -- and the reading is kept, since no mark was left
    for the dispatcher's guard to own the reopened owner by.
    """

    def test_a_reopen_before_the_pass_changes_nothing(self) -> None:
        for parsed in (True, False):
            with self.subTest(parsed=parsed):
                self.setUp()
                hold_plan_pr(self.github, self.github.get_issue(_support.OWNER_NUMBER))
                refuse_record(self.github, _support.OWNER_NUMBER, parsed=parsed)
                before = left_on_github(self.github, _support.OWNER_NUMBER)

                said = self._polled_then_reopened()

                self.assertEqual(left_on_github(self.github, _support.OWNER_NUMBER), {**before, "closed": False})
                self.assertEqual(self._observed(_support.REPO_SLUG), _OWED, "no mark hands it to the guard")
                for withheld in (_NO_RECEIPT, _NO_CLEANUP):
                    self.assertTrue(any(withheld in line for line in said), said)

    def test_a_repaired_record_ends_the_cycle_it_held(self) -> None:
        # Kept through the refusal, the reading routes the next pass to the
        # cleanup once a current record is back, which marks the cycle the
        # close ended rather than handing it to its stage. The issue has been
        # written on this host before, as an owner whose cycle it worked has.
        self.assertTrue(claimable(self.github.repo_id, _support.OWNER_NUMBER))
        current = self.github.pinned_data(_support.OWNER_NUMBER)
        refuse_record(self.github, _support.OWNER_NUMBER)
        self._polled_then_reopened()
        self.github.seed_state(_support.OWNER_NUMBER, **current)
        stage_owner, stage_name = _support.UMBRELLA_TARGET

        with self.assertLogs(_support.WORKFLOW_LOG), patch.object(
            importlib.import_module(stage_owner), stage_name, self.stage,
        ):
            _dispatch_workers._fanout_task(
                self.github, self._spec(), _support.OWNER_NUMBER, reading=_poll_models._POLLED_OPEN,
            )()

        self.assertTrue(self._cancelled())
        self.stage.assert_not_called()
        self.assertEqual(self._observed(_support.REPO_SLUG), frozenset())

    def _polled_then_reopened(self) -> list[str]:
        """Poll the owner closed, reopen it, and run the cleanup the poll handed on."""
        remote = Mock()
        with self.assertLogs(_support.WORKFLOW_LOG) as logged, patch.object(
            _snapshot_refs, "delete_snapshot_ref", remote,
        ):
            partition = _dispatch_partition._partition_pollable_issues(self.github, self._spec())
            self._reopened()
            reading = partition.reading(_support.OWNER_NUMBER)
            self.assertTrue(reading.cleanup_only)
            _dispatch_workers._fanout_task(self.github, self._spec(), _support.OWNER_NUMBER, reading=reading)()
            remote.assert_not_called()
            return list(logged.output)


class _FailingOnce:
    """The first refetch failing as an outage does, and every read after it answered."""

    def __init__(self, reading) -> None:
        self._reading = reading
        self.failed = False

    def __call__(self, number: int):
        """Fail the first read, answering the rest."""
        if self.failed:
            return self._reading(number)
        self.failed = True
        raise ConnectionError("github unreachable")


if __name__ == "__main__":
    unittest.main()
