# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A published verification artifact is tracked as orchestrator output.

Both halves, because each survives what the other does not. The marker rides
in the artifact's own rendering and outlives eviction from the bounded id
list; the id is what still says the comment is ours after somebody edits the
marker out of it. Without the id, the orchestrator's own evidence reads back
to a feedback scan as a human asking for something.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.workflow.engine import (
    comments as _comments,
    verification_comments as _verification,
)
from tests.support.fakes import (
    FakeGitHubClient,
    FakePR,
    make_developer_report,
    make_verification_artifact,
)

_GITHUB_LOG = "orchestrator.github"
_WARNING = "WARNING"
_LEDGER_KEY = "orchestrator_comment_ids"
_PR_NUMBER = 77


class VerificationArtifactLedgerTest(unittest.TestCase):
    """The comment an artifact landed as is recorded, once, whoever finds it."""

    def setUp(self) -> None:
        self.gh = FakeGitHubClient()
        self.pull_request = FakePR(number=_PR_NUMBER)
        self.gh.add_pr(self.pull_request)
        self.state = PinnedState(state_data={})
        self.artifact = make_verification_artifact(_PR_NUMBER)

    def publish(self):
        """Publish this case's artifact through the ledger-aware owner."""
        return _verification._publish_verification_artifact(
            self.gh, self.pull_request, self.state, self.artifact,
        )

    def test_an_artifact_enters_the_ledger_once(self) -> None:
        # A post whose response was lost hands back no id and records nothing,
        # so the retry that finds the comment is where it is recorded -- once,
        # however many readings find it after -- and its body carries the
        # marker the user-content filters pass over.
        self.gh.report_failures.lost.add(_PR_NUMBER)
        with self.assertLogs(_GITHUB_LOG, _WARNING):
            lost = self.publish()
        unrecorded = self.state.get(_LEDGER_KEY)
        self.gh.report_failures.lost.clear()

        found = [self.publish() for _ in range(2)]

        posted = self.pull_request.issue_comments[-1]
        self.assertIs(lost.presence, ReportPresence.UNCONFIRMED)
        self.assertFalse(unrecorded)
        self.assertEqual(
            [(reading.presence, reading.found) for reading in found],
            [(ReportPresence.PRESENT, posted), (ReportPresence.PRESENT, posted)],
        )
        self.assertEqual(self.state.get(_LEDGER_KEY), [posted.id])
        self.assertIn(_comments._ORCH_COMMENT_MARKER, posted.body)

    def test_one_ledger_covers_both_kinds_of_evidence(self) -> None:
        # A report and an artifact on one pull request are two publications
        # into the single id list every "is this ours?" scan consults, so
        # neither can be read back as the other's absence.
        report = make_developer_report(_PR_NUMBER)

        artifact_reading = self.publish()
        report_reading = _comments._publish_developer_report(
            self.gh, self.pull_request, self.state, report,
        )

        self.assertEqual(
            self.state.get(_LEDGER_KEY),
            [artifact_reading.landed_id, report_reading.landed_id],
        )
        self.assertEqual(len(self.pull_request.issue_comments), 2)


if __name__ == "__main__":
    unittest.main()
