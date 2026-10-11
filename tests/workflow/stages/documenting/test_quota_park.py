# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A docs pass an account quota stopped parks as the session limit where another park would take it."""

from __future__ import annotations

import unittest

from tests.workflow.agent_failure_values import agy_quota_stop
from tests.workflow.session_limit_parks import assert_session_limit_park
from tests.workflow.stages.documenting.documenting_test_support import (
    PUSH_BRANCH,
    SHA_BEFORE,
    _FreshDocumentingFixture,
)

# A docs commit the pass left on top of the head it began on.
DOCS_COMMIT = "d0c5" * 10

# The passes a quota stopped where the timeout's park or the tree's would
# otherwise take them, beside the checkout each left: one past its timeout
# over a clean tree, one with a tool step still open over docs edits it never
# committed, and one that committed over a tree whose status nobody could
# take -- which lists no dirty paths and is still no tree proved clean, so its
# commit is not published.
QUOTA_STALLS = (
    (agy_quota_stop(timed_out=True), {"dirty_files": (), "head_shas": [SHA_BEFORE, SHA_BEFORE]}),
    (agy_quota_stop(unfinished=True), {"dirty_files": ("docs/new.md",), "head_shas": [SHA_BEFORE, SHA_BEFORE]}),
    (agy_quota_stop(), {"tree_readable": False, "head_shas": [SHA_BEFORE, DOCS_COMMIT]}),
)


class DocumentingQuotaParkTest(unittest.TestCase, _FreshDocumentingFixture):
    """The quota outranks the timeout and the dirty tree alike."""

    def test_quota_stop_parks_as_session_limit(self) -> None:
        # Nothing such a pass left is published, and the park names the quota
        # and its reset, staying the retryable one a bare continue answers once
        # the quota resets -- the edits left in the checkout for that run.
        for run_agent, checkout in QUOTA_STALLS:
            with self.subTest(checkout=tuple(checkout.items())):
                gh, issue = self._seeded()
                with self.assertLogs("orchestrator.workflow", level="WARNING"):
                    mocks = self._run_documenting(
                        gh,
                        issue,
                        run_agent=run_agent,
                        push_branch=True,
                        branch_ahead_behind=(0, 0),
                        **checkout,
                    )

                mocks[PUSH_BRANCH].assert_not_called()
                assert_session_limit_park(self, gh, issue.number)
