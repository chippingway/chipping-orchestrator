# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finished issues on a real host, as a launch form's maintenance pass meets them.

The runtime tests beside this one stand the pass in and keep the host out of
them. Here it runs whole, from the entry point a launch form calls down to the
teardown, because what a launch form has to carry that far is the issue's
writer claim and the admission of its pinned record: neither is relaxed by
the barrier, the host hold, or the schedule above them. The host and the issues
are the git package's own fixtures -- three issues finished alike, one pinned
under a version admission refuses, one under the supported version, and one
with nothing pinned -- and what is read back is the bounded record each
candidate earns, the host, and every thread.
"""
from __future__ import annotations

from typing import NamedTuple
from unittest.mock import patch

from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.scheduler.service import IssueScheduler
from tests.git.worktrees import maintenance_test_support as _host, refused_record_support as _records
from tests.support import writer_claims as _writer_claims

LIFECYCLE_LOGGER = _host.LIFECYCLE_LOGGER

# The issues by the record each carries, the version the refused one is pinned
# under, and what is left of an issue whose artifacts were reclaimed.
REFUSED = _records.REFUSED
ADMITTED = _records.ADMITTED
UNPINNED = _records.UNPINNED
REFUSED_VERSION = _records.REFUSED_VERSION
GONE = _records.GONE

# One issue at a time, since nothing here submits: what a live scheduler is
# built for in these tests is the barrier the pass is held under.
_LIVE_CAP = 1


class RefusedPassCase(_host._MaintenanceTestCase):
    """The three finished issues, a live scheduler, and the records a pass leaves."""

    def setUp(self) -> None:
        super().setUp()
        self.issues = _records.FinishedIssues(self)
        self.scheduler = IssueScheduler(global_cap=_LIVE_CAP, per_repo_cap=_LIVE_CAP)
        self.addCleanup(self.scheduler.shutdown)

    @property
    def clients(self) -> list:
        """The one configured repository, paired with its client as a connect pairs them."""
        return [(self.spec, self.gh)]

    def contended(self):
        """The unpinned issue's writer claim, held as another poller on this host holds it."""
        return _writer_claims.held_elsewhere(self.gh.repo_id, _records.UNPINNED)

    def recorded(self, run, *args) -> Recorded:
        """Run `run(*args)`, and answer what it returned, what each candidate's record says, and what was logged."""
        with (
            patch.object(_recording_events, "append_record") as appended,
            self.assertLogs(LIFECYCLE_LOGGER, level="INFO") as logs,
        ):
            answer = run(*args)
            written = [call.args[0] for call in appended.call_args_list]
            output = logs.output
        return Recorded(answer, _by_issue(written), output)


class Recorded(NamedTuple):
    """One run's return, the outcome and reason each candidate's analytics record carries by issue, and its log."""

    answer: object
    records: dict[int, tuple[str, str]]
    output: list[str]


def _by_issue(written: list[dict]) -> dict[int, tuple[str, str]]:
    """The outcome and reason each written record carries, by the issue it is about."""
    return {record["issue"]: (record["outcome"], record["reason"]) for record in written}
