# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick reads once an issue's writer claim is granted.

The claim is granted after the poll read the issue, and another poller on this
host may have advanced, closed, or reopened it and let go in between. So every
dispatch path reads the issue again behind the claim: the handler is the one
the current label names, and a close the poll read is carried over that read
rather than lost to it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import dispatch as _dispatch, stage_targets as _stage_targets
from tests.support.fakes import make_issue
from tests.support.writer_claims import claimable, held_elsewhere
from tests.workflow.engine import refused_submit_support as _closed
from tests.workflow.engine.writer_claim_test_support import (
    DISPATCH_MODES,
    StandInHandler,
    WriterClaimDispatchCase,
)
from tests.workflow.fixtures import LABEL_IMPLEMENTING, LABEL_READY, LABEL_VALIDATING
from tests.workflow.observation_support import ObservedCloseCase, read_now

# An issue another poller moves from `ready` to `validating`, and lets go of,
# between this tick's poll and its claim.
_ADVANCED = 13


class AcquisitionGapTest(WriterClaimDispatchCase):
    """An issue another poller advanced before this tick's claim is routed as it reads now.

    The claim is granted, because that poller has let go -- but the
    enumeration read the issue before it did, and its `ready` would hand an
    issue already past implementation to the stage that relabels it
    `implementing` and starts a developer on it again.
    """

    def test_routed_by_the_label_it_reads_now(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self.fresh_repository()
                self.github.add_issue(make_issue(_ADVANCED, label=LABEL_READY))
                polled = make_issue(_ADVANCED, label=LABEL_READY)
                with held_elsewhere(self.github.repo_id, _ADVANCED):
                    self.github.set_workflow_label(self.github.get_issue(_ADVANCED), LABEL_VALIDATING)
                stand_in = StandInHandler()

                with patch.object(self.github, "list_pollable_issues", return_value=[polled]):
                    self.ticked(stand_in, limit=limit, scheduled=scheduled, labels=(LABEL_READY, LABEL_VALIDATING))

                self.assertEqual(stand_in.ran_on, [(_ADVANCED, LABEL_VALIDATING)])
                self.assertEqual(
                    self.github.label_history, [(_ADVANCED, LABEL_VALIDATING)], "only the holder relabelled it",
                )


class ClosedAcrossTheGapTest(ObservedCloseCase, unittest.TestCase):
    """A close the sequential poll read outlives the read it takes under the claim.

    The owner is a closed `implementing` issue whose late cycle is still live,
    and the poll read it closed. What the loop reads once the claim is its own
    can say less than that -- a human reopened the issue in between, or the
    read fails -- and the poll's reading is still the one the pass keeps.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.github = _closed.closed_owner(live=True)
        self.polled = make_issue(_closed.OWNER_NUMBER, label=LABEL_IMPLEMENTING, closed=True)
        owner, name = _stage_targets._STAGE_HANDLER_TARGETS[LABEL_IMPLEMENTING]
        stage = patch(f"{owner}.{name}")
        self.stage = stage.start()
        self.addCleanup(stage.stop)

    def test_a_reopen_in_the_gap_ends_the_cycle(self) -> None:
        # The issue has been written on this host before the poll read it,
        # which is what ties the reading to the record the claim finds.
        self.assertTrue(claimable(self.github.repo_id, _closed.OWNER_NUMBER))
        read_at = read_now()
        self.github.get_issue(_closed.OWNER_NUMBER).closed = False

        with self.assertLogs(_closed.WORKFLOW_LOG):
            _dispatch._process_polled_issue(self.github, _closed.SPEC, self.polled, read_at=read_at)

        self.assertTrue(self.github.pinned_data(_closed.OWNER_NUMBER).get(_closed.KEY_CANCELLED))
        self.stage.assert_not_called()

    def test_a_first_claim_unties_an_older_reading(self) -> None:
        # The issue's first claim on this host finds a file that cannot say
        # whether another poller held the key just before it, so a reading
        # older than that claim proves nothing about the record behind it.
        # The cycle stays live, the handler stays off it, and the reading is
        # left for the cleanup pass that settles it with nothing marked.
        read_at = read_now()
        self.github.get_issue(_closed.OWNER_NUMBER).closed = False

        with self.assertLogs(_closed.WORKFLOW_LOG):
            _dispatch._process_polled_issue(self.github, _closed.SPEC, self.polled, read_at=read_at)

        owed = frozenset((_closed.OWNER_NUMBER,))
        self.assertFalse(self.github.pinned_data(_closed.OWNER_NUMBER).get(_closed.KEY_CANCELLED))
        self.stage.assert_not_called()
        self.assertEqual(self._observed(_closed.SPEC.slug), owed)

    def test_a_failed_read_keeps_the_reading(self) -> None:
        with (
            patch.object(self.github, "get_issue", side_effect=_closed.OUTAGE),
            self.assertRaises(ConnectionError),
        ):
            _dispatch._process_polled_issue(self.github, _closed.SPEC, self.polled, read_at=read_now())

        owed = frozenset((_closed.OWNER_NUMBER,))
        self.assertEqual(self._observed(_closed.SPEC.slug), owed)
        self.stage.assert_not_called()

if __name__ == "__main__":
    unittest.main()
