# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The commit a published rebase pushes is the one it then finalizes.

The candidate is read off the checkout once the rebase returns, and the size
gate proves the checkout's head again before it measures. Between the two
reads the worktree is writable, so what the push carries and what the notice,
the audit event, and the `validating` route name have to be one decision --
otherwise a commit landing in that window reaches the pull request while the
finish names the head the candidate was read on.
"""

from __future__ import annotations

import unittest

from tests.git.base_sync.gate_reads_support import _gate_candidates
from tests.git.base_sync.refresh_scenarios import (
    PUSH_PATCH,
    _clean_rebase_scenario,
)
from tests.git.base_sync.refresh_test_support import (
    AFTER_SHA,
    EVENT_BASE_REBASED,
    EVENT_FIELD,
    MOVED_CHECKOUT_SHA,
    SHA_FIELD,
    _SyncWorktreeWithBaseFixture,
)

ISSUE = 7

# The keyword a gated push names the commit it publishes by.
REVISION = "revision"

AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
PARK_MEASUREMENT_FAILED = "late_measurement_failed"

THREE_BEHIND_STDOUT = "3\n"


class CleanRebaseCandidateUnitTest(
    _SyncWorktreeWithBaseFixture, unittest.TestCase,
):
    """One published rebase, and the checkout that moved out from under it."""

    def test_the_push_names_the_head_it_finalizes(self) -> None:
        self._seed_pr_issue(review_round=3)
        self._add_pr()
        scenario = _clean_rebase_scenario(THREE_BEHIND_STDOUT)

        scenario.run(self)

        published = scenario[PUSH_PATCH].call_args.kwargs[REVISION]
        self.assertEqual(published, AFTER_SHA)
        self.assertEqual(self._rebased_sha(), published)

    def test_a_checkout_that_moved_refuses_the_push(self) -> None:
        # Unbound, the gate measures and publishes whatever landed in that
        # window while the finish behind it stamps the SHA the candidate was
        # read on -- so the pull request carries one commit and the event
        # names another.
        self._seed_pr_issue(review_round=3)
        self._add_pr()
        scenario = _clean_rebase_scenario(THREE_BEHIND_STDOUT)
        _gate_candidates(self, AFTER_SHA, MOVED_CHECKOUT_SHA)

        scenario.run(self)

        scenario[PUSH_PATCH].assert_not_called()
        self.assertEqual(self.gh.label_history, [])
        state = self.gh.pinned_data(ISSUE)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(PARK_REASON), PARK_MEASUREMENT_FAILED)

    def _rebased_sha(self):
        """The commit the published rebase's audit event names."""
        rebased = [
            event
            for event in self.gh.recorded_events
            if event.get(EVENT_FIELD) == EVENT_BASE_REBASED
        ]
        self.assertEqual(len(rebased), 1)
        return rebased[0].get(SHA_FIELD)


if __name__ == "__main__":
    unittest.main()
