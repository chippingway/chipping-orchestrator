# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one discussion round costs the issue's running counters.

A real round is counted exactly once, as it returns, so the per-issue receipt
covers the discussion the same way it covers every other agent the issue
spent. A killed round is counted too -- its disposition is withheld, its usage
is not -- and the case that proves it is counted once is the one where the
tick still writes: an interrupted round that left commits parks (and
persists), and that whole-state write behind the accounting neither adds the
round again nor puts the count back.
"""

from __future__ import annotations

import unittest

from tests.workflow.fixtures import (
    KEY_ISSUE_AGENT_RUNS,
    KEY_ISSUE_TOTAL_TOKENS,
    KEY_PARK_REASON,
    _agent,
)
from tests.workflow.stages.discussion.discussion_test_support import (
    DISCUSSION_RESPONSE,
    DISCUSSION_SESSION,
    MOVED_HEAD,
    PARK_DISCUSSION_PLAN_INVALID,
    _DiscussionWorkflowMixin,
    _seed_discussion,
)

_COUNTED_ISSUE_NUMBER = 940
_INTERRUPTED_ISSUE_NUMBER = 941
_NO_USAGE_SOURCE = "no-usage"
_ISSUE_COST_SOURCES = "issue_cost_sources"
_USAGE_RECEIPTS = "issue_usage_receipts"


class DiscussionUsageTest(unittest.TestCase, _DiscussionWorkflowMixin):

    def test_a_finished_round_counts_once(self) -> None:
        gh, issue = _seed_discussion(_COUNTED_ISSUE_NUMBER)

        self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=DISCUSSION_SESSION,
                last_message=DISCUSSION_RESPONSE,
            ),
        )

        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(pinned_data[KEY_ISSUE_AGENT_RUNS], 1)
        self.assertEqual(pinned_data[KEY_ISSUE_TOTAL_TOKENS], 0)
        self.assertEqual(pinned_data[_ISSUE_COST_SOURCES], [_NO_USAGE_SOURCE])

    def test_a_killed_round_that_parks_counts_once(self) -> None:
        gh, issue = _seed_discussion(_INTERRUPTED_ISSUE_NUMBER)

        self._run_discussion(
            gh,
            issue,
            run_agent=_agent(
                session_id=DISCUSSION_SESSION,
                last_message="",
                interrupted=True,
            ),
            head_shas=MOVED_HEAD,
        )

        pinned_data = gh.pinned_data(issue.number)
        # The moved HEAD is what makes this case worth testing: the read-only
        # park runs ahead of the interruption guard, so this tick DOES write,
        # over the state the accounting was laid back onto.
        self.assertEqual(
            (
                pinned_data[KEY_PARK_REASON],
                pinned_data[KEY_ISSUE_AGENT_RUNS],
                len(pinned_data[_USAGE_RECEIPTS]["recent"]),
            ),
            (PARK_DISCUSSION_PLAN_INVALID, 1, 1),
        )


if __name__ == "__main__":
    unittest.main()
