# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What ends one worktree's sync before the refresh rewrites anything."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.git.base_sync import recovery_holds, refresh
from orchestrator.github.labels import BACKLOG_LABEL, PAUSED_LABEL
from tests.git.base_sync import base_sync_helpers as fixtures
from tests.git.base_sync.sync_test_support import _patch_base_sync
from tests.support.fakes import FakeGitHubClient, FakeLabel, make_issue

LABEL_IN_REVIEW = "in_review"

LABEL_IMPLEMENTING = "workflow:implementing"

LABEL_RESOLVING_CONFLICT = "workflow:resolving_conflict"

THREE_BEHIND_STDOUT = "3\n"

STALE_ANCHOR = "stale-anchor"

AUTO_REBASE_PARK = "auto_base_rebase_push_failed"

UNREADABLE_RETURNCODE = 128

# The two roads an anchored PR worktree takes: a base lag the refresh can
# count, and one it cannot.
LAG_READINGS = (
    fixtures._git_result(stdout=THREE_BEHIND_STDOUT),
    fixtures._git_result(returncode=UNREADABLE_RETURNCODE),
)

# The operator-owned controls the dispatcher hard-skips on, exercised against
# a pre-PR worktree and a PR-having one because each takes its own route.
HARD_SKIP_CONTROLS = (BACKLOG_LABEL, PAUSED_LABEL)

PINNED_PR_CASES = (False, True)


class RefreshGuardTest(unittest.TestCase):
    """No control-skipped or handler-owned worktree is rewritten or relabeled."""

    def test_hard_skip_controls_end_the_sync(self) -> None:
        for control in HARD_SKIP_CONTROLS:
            for pinned_pr in PINNED_PR_CASES:
                with self.subTest(control=control, pinned_pr=pinned_pr):
                    self._assert_control_skips(control, pinned_pr)

    def test_conflict_label_skips_reroute(self) -> None:
        # The handler runs this tick anyway and will do the rebase -- a second
        # label flip is pointless and would re-post the PR notice.
        gh = self._seeded_client(label=LABEL_RESOLVING_CONFLICT)
        fixtures._add_pr(gh)

        self._run_sync(gh)

        self.assertEqual(gh.label_history, [])
        self.assertEqual(gh.posted_pr_comments, [])

    def test_terminal_pr_clears_a_stale_anchor(self) -> None:
        gh = self._seeded_client(
            pending_auto_base_rebase_push_sha=STALE_ANCHOR,
        )
        fixtures._add_pr(gh, merged=True, pr_state="closed")
        rebase = MagicMock()
        push = MagicMock()

        self._run_sync(gh, rebase=rebase, push=push)

        rebase.assert_not_called()
        push.assert_not_called()
        self.assertEqual(gh.label_history, [])
        # A merged PR advances base on its own, so the recovery target the
        # crashed tick pinned is meaningless and must not survive.
        self.assertIsNone(
            gh.pinned_data(fixtures.ISSUE).get(fixtures.KEY_PENDING_PUSH_SHA),
        )

    def test_terminal_pr_ends_an_anchor_under_a_park(self) -> None:
        # A park this refresh left waits on a reply, but the anchor under it
        # is still ended once the pull request is over: left standing, it holds
        # the handler that finalizes the issue for as long as nobody replies.
        for reading in LAG_READINGS:
            with self.subTest(readable=not reading.returncode):
                gh = self._seeded_client(
                    pending_auto_base_rebase_push_sha=STALE_ANCHOR,
                    awaiting_human=True,
                    park_reason=AUTO_REBASE_PARK,
                )
                fixtures._add_pr(gh, merged=True, pr_state="closed")

                self._run_sync(gh, git=MagicMock(return_value=reading))

                issue = gh._issues[fixtures.ISSUE]
                state = gh.read_pinned_state(issue)
                self.assertIsNone(state.get(fixtures.KEY_PENDING_PUSH_SHA))
                self.assertEqual(state.get(fixtures.KEY_PARK_REASON), AUTO_REBASE_PARK)
                self.assertFalse(recovery_holds._recovery_holds_dispatch(
                    issue, LABEL_IN_REVIEW, state, fixtures.WORKTREE,
                ))

    def _assert_control_skips(self, control: str, pinned_pr: bool) -> None:
        gh = self._seeded_client(
            label=LABEL_IN_REVIEW if pinned_pr else LABEL_IMPLEMENTING,
            extra_labels=(control,),
            pinned_pr=pinned_pr,
        )
        if pinned_pr:
            fixtures._add_pr(gh)
        rebase = MagicMock()

        self._run_sync(gh, rebase=rebase)

        rebase.assert_not_called()
        self.assertEqual(gh.label_history, [])
        self.assertEqual(gh.posted_pr_comments, [])

    def _seeded_client(
        self,
        *,
        label: str = LABEL_IN_REVIEW,
        extra_labels: tuple = (),
        pinned_pr: bool = True,
        **state_fields,
    ) -> FakeGitHubClient:
        gh = FakeGitHubClient()
        issue = make_issue(fixtures.ISSUE, label=label)
        for name in extra_labels:
            issue.labels.append(FakeLabel(name))
        gh.add_issue(issue)
        if pinned_pr:
            gh.seed_state(
                fixtures.ISSUE,
                pr_number=fixtures.PR_NUMBER,
                branch=fixtures.BRANCH,
                **state_fields,
            )
        return gh

    def _run_sync(self, gh: FakeGitHubClient, **mocks) -> None:
        patches = {
            "dirty": MagicMock(return_value=[]),
            "git": MagicMock(
                return_value=fixtures._git_result(
                    stdout=THREE_BEHIND_STDOUT,
                ),
            ),
        }
        patches.update(mocks)
        with _patch_base_sync(**patches):
            refresh._sync_worktree_with_base(
                gh, fixtures.SPEC, fixtures.WORKTREE, fixtures.ISSUE,
            )


if __name__ == "__main__":
    unittest.main()
