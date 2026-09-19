# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What changes while the handoff takes its last readings.

Once the report has settled, the handoff reads the issue's requirements, then
the report where it settled, then the checkout, and the description last. Each
of those is read after every request that could change it unseen, so a report
edited while the issue is re-read, or a checkout moved or dirtied while either
request is out, holds the work rather than reaching `validating`.
`test_report_publication` covers the description's own two readings.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.workflow.fixtures import LABEL_VALIDATING, SHA_LENGTH
from tests.workflow.git_owners import GIT_SEAM_OWNERS
from tests.workflow.stages.implementing import report_test_support as support

# The pull request the tick opens: this client numbers them from 1.
OPENED_PR = 1

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

# What a checkout that changed after the push is parked under.
CANDIDATE_MOVED = "late_candidate_moved"

# The two requests the last readings make of GitHub: the issue, for its
# requirements, and the place the report settled.
GET_ISSUE = "get_issue"

REREAD_REPORT = "reread_report_location"

# The seams the checkout is read through, whose doubles a change rewires.
PROVE_CANDIDATE = "_prove_candidate_commit"

WORKTREE_STATUS = "_worktree_status"

# Where a checkout moved to while a request was out.
MOVED_SHA = "e" * SHA_LENGTH

EDITED = "\n\nEdited while the issue was read again."


class LastReadingsTest(unittest.TestCase, support._ReportDeliveryMixin):
    def test_a_change_during_the_last_reads_holds(self) -> None:
        # The report is settled on the pull request and the handoff is reading
        # everything once more. Whatever changes while one of those requests
        # is out is read after it, so the work parks rather than handing
        # review a report or a checkout nobody read as it now stands.
        for request, change, parked in (
            (GET_ISSUE, self._edits_the_report, _report_delivery.UNDELIVERABLE_REPORT),
            (GET_ISSUE, self._moves_the_checkout, CANDIDATE_MOVED),
            (REREAD_REPORT, self._dirties_the_checkout, CANDIDATE_MOVED),
        ):
            with self.subTest(request=request, change=change.__name__):
                github = self._changed_during(request, change)

                self._assert_held(github, parked)

    def _changed_during(self, request: str, change):
        """Deliver a report, with `change` made during one last `request`."""
        github, issue = self.seeded()
        during = _ChangesDuring(github, getattr(github, request), change)

        with patch.object(github, request, during):
            self.deliver(github, issue, support.ready_message())

        self.assertTrue(during.changed)
        return github

    def _assert_held(self, github, parked: str) -> None:
        """The work parked under `parked`, and nothing handed on."""
        pinned = github.pinned_data(support.REPORT_ISSUE)
        self.assertEqual(
            (pinned.get(AWAITING_HUMAN), pinned.get(PARK_REASON)),
            (True, parked),
        )
        self.assertNotIn(
            (support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history,
        )

    def _edits_the_report(self, github) -> None:
        """A human edits the report comment that settled."""
        settled = support.published_reports(github, OPENED_PR)[0]
        settled.body = f"{settled.body}{EDITED}"

    def _moves_the_checkout(self, _github) -> None:
        """The worktree's head moves off the commit that was pushed."""
        proved = getattr(GIT_SEAM_OWNERS[PROVE_CANDIDATE], PROVE_CANDIDATE)
        proved.side_effect = None
        proved.return_value = FrozenCommit(sha=MOVED_SHA)

    def _dirties_the_checkout(self, _github) -> None:
        """Loose work appears in the worktree beside the pushed commit."""
        status = getattr(GIT_SEAM_OWNERS[WORKTREE_STATUS], WORKTREE_STATUS)
        status.side_effect = None
        status.return_value = _WorktreeStatus(readable=True, paths=("stray.py",))


class _ChangesDuring:
    """One request the last readings make, during which something changes.

    Only once the report has settled, which is what makes it one of the last
    readings rather than the publication's own: the change is made once, then
    the request is answered as GitHub would answer it.
    """

    def __init__(self, github, request, change) -> None:
        self._github = github
        self._request = request
        self._change = change
        self.changed = False

    def __call__(self, *args, **kwargs):
        """Make the change once the report has settled, then answer."""
        settled = self._github.pinned_data(support.REPORT_ISSUE).get(
            support.CURRENT_RECORD,
        )
        if settled and not self.changed:
            self.changed = True
            self._change(self._github)
        return self._request(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
