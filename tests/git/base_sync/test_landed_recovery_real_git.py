# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The recovery of a push that already landed, against a real repository and a real replay.

The interrupted rebase is a real `git rebase` onto an advanced base, and its
push reached the bare remote while the tick that made it never came back. The
recovery's own fetch is what finds the landing, the observation that hands it
to the finish reads the remote on disk, and the base the replay is counted
against is the ref the refresh fetched -- so whether the push is sent again,
said again, or routed past a base that moved is what git itself says.
"""
from __future__ import annotations

import unittest

from tests.git.base_sync import recovery_git_support as fixtures
from tests.git.base_sync.vouched_replay_git_support import VouchedReplayGitFixtureMixin

RELABEL_ONLY = "crash_recovery_relabel_only"

KEY_REWRITE_DEBT = "developer_report_rewrite_debt"
PREVIOUS_HEAD = "previous_head"
REWRITTEN_HEAD = "rewritten_head"

# What the notice of a landing one base advance has already left behind says.
ADVANCED_ONCE = "Base advanced again by 1 commit(s)"


class LandedRecoveryRealGitTest(VouchedReplayGitFixtureMixin, unittest.TestCase):
    """A landing the recovery's fetch finds is finished once, and never pushed again."""

    def setUp(self) -> None:
        super().setUp()
        self.publish_recovered_head()

    def test_a_landing_is_finished_once(self) -> None:
        # Observed at the remote rather than pushed again, announced as found
        # standing, its debt owed for the replay, and the tick after has no
        # anchor left to answer.
        self.assertTrue(self.recover())
        self.assertFalse(self.recover())

        self._assert_unpushed_and_said([RELABEL_ONLY])
        self.assertEqual(self.gh.label_history, [(fixtures.ISSUE, fixtures.VALIDATING)])
        debt = self.gh.pinned_data(fixtures.ISSUE).get(KEY_REWRITE_DEBT)
        self.assertEqual(debt[PREVIOUS_HEAD], self.anchor)
        self.assertEqual(debt[REWRITTEN_HEAD], self.recovered)

    def test_a_further_base_advance_leaves_the_route(self) -> None:
        # The base moved again while the process was down: the landing is
        # announced with the lag git counts against the fetched base, routed
        # nowhere, and its attempt retired, so this same tick's rebase goes
        # on from the head the pull request carries.
        self.advance_the_base_again()

        self.assertFalse(self.recover())

        self._assert_unpushed_and_said([RELABEL_ONLY])
        self.assertEqual(self.gh.label_history, [])
        self.assertIn(ADVANCED_ONCE, self.gh.posted_pr_comments[-1][1])

    def test_an_announced_landing_finishes_its_route(self) -> None:
        # The finish announced the landing and was lost at its relabel: the
        # recovery says nothing again and makes the relabel.
        self._recovers_an_announced_landing(fixtures.LABEL)

        self.assertEqual(self.gh.label_history, [(fixtures.ISSUE, fixtures.VALIDATING)])

    def test_a_relabelled_route_is_only_written(self) -> None:
        # Lost after its relabel landed, so the issue is already where the
        # route goes: nothing is said or relabelled, and only the write that
        # retires the attempt is made.
        self._recovers_an_announced_landing(fixtures.VALIDATING)

        self.assertEqual(self.gh.label_history, [])

    def _recovers_an_announced_landing(self, label: str) -> None:
        """Recover the landing under `label` past a mark naming it; nothing pushed or said, the attempt retired."""
        self.announce_a_finish(self.recovered)

        self.assertTrue(self.recover(label=label))

        self._assert_unpushed_and_said([])

    def _assert_unpushed_and_said(self, methods: list[str]) -> None:
        """Nothing pushed, the remote on the replay, the attempt retired, and a notice per event `methods` names."""
        self.assertEqual(self.push.leases, [])
        self.assertEqual(fixtures.head_sha(self.remote, fixtures.BRANCH_REF), self.recovered)
        self.assertIsNone(self.gh.pinned_data(fixtures.ISSUE).get(fixtures.KEY_PENDING_PUSH_SHA))
        said = [event.get(fixtures.METHOD_FIELD) for event in self.rebase_events()]
        self.assertEqual(said, methods)
        self.assertEqual(len(self.gh.posted_pr_comments), len(methods))


if __name__ == "__main__":
    unittest.main()
