# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finished issue whose pinned record admission refuses keeps everything it holds.

Every candidate here is one the pass would reclaim on any other record: closed
on `done`, its branch already in the base, its pull request ended, its checkout
clean and quiet. The record on its thread is what decides, read from the
comment's own bytes the way a deployed poller reads it, and what is asserted
afterwards is the host, the remote, and every thread -- what an operator is left
with to dispose of by hand.
"""
from __future__ import annotations

from orchestrator.git.worktrees import maintenance
from orchestrator.git.worktrees.maintenance_results import MaintenanceOutcome, MaintenanceReason
from orchestrator.git.worktrees.models import Retention, RetentionReason
from orchestrator.github.pinned_state import PINNED_STATE_TEMPLATE, SUPPORTED_SCHEMA_VERSION
from tests.git.worktrees import (
    maintenance_payloads as _maintenance_payloads,
    maintenance_test_support as _support,
    refused_record_support as _records,
)

# Versions admission refuses on an object that is otherwise the record: none
# at all, as every build predating the field wrote one, a later build's, one
# before the first, and the spellings of 1 that are not the integer 1.
_REFUSED_VERSIONS = (None, _records.REFUSED_VERSION, 0, "1", 1.0, True)

# Bodies a bot-authored pinned comment can carry that are no state at all.
_MALFORMED_PAYLOADS = ("{bad json}", "[]", "null")


class RefusedRecordTest(_support._MaintenanceTestCase):
    """The refused record keeps its issue's artifacts, and the records beside it decide as ever."""

    def setUp(self) -> None:
        super().setUp()
        self.issues = _records.FinishedIssues(self)

    def kept(self) -> tuple:
        """One pass over the refused issue alone, and the warnings it left."""
        refused = [
            candidate for candidate in self.discovered()
            if candidate.artifacts.issue_number == _records.REFUSED
        ]
        with self.assertLogs(maintenance.log.name, level=_maintenance_payloads.WARNING) as logs:
            swept = self.swept(refused)
            output = logs.output
        self.assertEqual(len(swept), 1, f"expected one candidate, got {swept}")
        return swept[0], output

    def test_an_unsupported_version_keeps_it_whole(self) -> None:
        for version in _REFUSED_VERSIONS:
            with self.subTest(version=version):
                self.issues.pin(_records.REFUSED, version)
                standing, on_github = self.issues.standing(), self.issues.on_github()

                swept, output = self.kept()

                self.assertEqual(
                    (swept.outcome, swept.reason, swept.retentions),
                    (
                        MaintenanceOutcome.RETAINED,
                        MaintenanceReason.UNPROVEN,
                        (Retention(RetentionReason.STATE_UNSUPPORTED, f"#{_records.REFUSED}"),),
                    ),
                )
                self.assertEqual(self.issues.standing(), standing)
                self.assertEqual(self.issues.on_github(), on_github)
                self.assertEqual(self.issues.said(output), 1, output)

    def test_a_record_that_is_no_state_keeps_it_too(self) -> None:
        for payload in _MALFORMED_PAYLOADS:
            with self.subTest(payload=payload):
                self.issues.post(_records.REFUSED, PINNED_STATE_TEMPLATE.format(payload=payload))
                standing, on_github = self.issues.standing(), self.issues.on_github()

                swept, output = self.kept()

                self.assertEqual(
                    swept.retentions, (Retention(RetentionReason.STATE_MALFORMED, f"#{_records.REFUSED}"),),
                )
                self.assertEqual(self.issues.standing(), standing)
                self.assertEqual(self.issues.on_github(), on_github)
                self.assertEqual(self.issues.said(output), 1, output)

    def test_only_the_refused_record_is_kept(self) -> None:
        # One pass over all three: the record under the supported version and
        # the thread that pinned nothing are both reclaimed under every gate
        # they always passed, so what keeps the third is its record alone, and
        # an issue with no pin is not read as one with a refused pin.
        standing, on_github = self.issues.standing(), self.issues.on_github()

        with self.assertLogs(maintenance.log.name, level=_maintenance_payloads.WARNING) as logs:
            swept = self.swept()
            output = logs.output

        self.assertEqual(
            {answer.candidate.artifacts.issue_number: answer.outcome for answer in swept},
            {
                _records.REFUSED: MaintenanceOutcome.RETAINED,
                _records.ADMITTED: MaintenanceOutcome.CLEANED,
                _records.UNPINNED: MaintenanceOutcome.CLEANED,
            },
        )
        self.assertEqual(
            self.issues.standing(),
            {
                _records.REFUSED: standing[_records.REFUSED],
                _records.ADMITTED: _records.GONE,
                _records.UNPINNED: _records.GONE,
            },
        )
        self.assertEqual(self.issues.on_github(), on_github)
        self.assertEqual(self.issues.said(output), 1, output)

    def test_the_record_once_disposed_of_is_reclaimed(self) -> None:
        # Nothing is remembered between passes: a human who re-pins the record
        # under the supported version has the next pass take it like any other.
        self.kept()
        self.issues.pin(_records.REFUSED, SUPPORTED_SCHEMA_VERSION)

        swept = self.swept()

        self.assertEqual({answer.outcome for answer in swept}, {MaintenanceOutcome.CLEANED})
        self.assertEqual(self.issues.standing()[_records.REFUSED], _records.GONE)
