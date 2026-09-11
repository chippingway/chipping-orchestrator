# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue and PR worktree creation and the unpushed-work probe it gates on."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport, commands
from orchestrator.git.worktrees import creation
from tests.git.worktrees import lifecycle_test_support as _support
from tests.git.worktrees.lifecycle_test_support import _GitRecorder
from tests.git.worktrees.real_git_test_support import (
    AMENDED_PLAN_TEXT,
    PLAN_PATH,
    PUBLISHED_PLAN_TEXT,
    _AmendedPlanRepo,
    _MergedPlanRepo,
    _run_git,
)

FAKE_WORKTREE = Path("/tmp/wt-not-real")
PRIVATE_REMOTE = "private"
ADD_FAILURE_STDERR = "fatal: invalid reference"
CREATORS = (creation._ensure_worktree, creation._ensure_pr_worktree)
# A well-formed object id no repository in this test ever created.
UNKNOWN_SHA = "0123456789abcdef0123456789abcdef01234567"
# What a remote answers about a branch it still has, when this host could not
# fetch it.
LIVE_REMOTE_SHA = "9e8d7c6b5a493827160fedcba9876543210abcde"
AUTHED_TARGET_FETCH = "_authed_target_fetch"
FETCH_FAILURE = "fatal: could not read Username for 'https://github.com'"
NEW_BRANCH_FLAG = "-b"
GIT_CONFIG = "config"
WORKTREE_SCOPE = "--worktree"
WORKTREE_CONFIG_EXTENSION = "extensions.worktreeConfig"
CORE_WORKTREE = "core.worktree"
SHADOW_DIR = "shadow"


class EnsureWorktreeTest(unittest.TestCase):
    """A fresh implementing worktree starts from the base branch.

    A brand-new per-issue branch has no remote head to restore from, so a
    missing local ref is created off `<remote>/<base>`.
    """

    def test_existing_local_branch_is_checked_out(self) -> None:
        with _support._worktree_fixture() as fixture:
            worktree = fixture.run(creation._ensure_worktree)
            self.assertEqual(
                fixture.git.worktree_adds[0][2:],
                (str(worktree), _support.ISSUE_BRANCH),
            )

    def test_missing_local_branch_starts_at_base(self) -> None:
        with _support._worktree_fixture(local_branch_present=False) as fixture:
            worktree = fixture.run(creation._ensure_worktree)
            self.assertEqual(
                fixture.git.worktree_adds[0][2:],
                (
                    NEW_BRANCH_FLAG,
                    _support.ISSUE_BRANCH,
                    str(worktree),
                    f"{_support.ORIGIN_REMOTE}/{_support.BASE_BRANCH}",
                ),
            )

    def test_pinned_branch_overrides_derivation(self) -> None:
        # An issue whose PR was opened before slug-namespacing keeps its
        # legacy ref in pinned state; forcing the derived name would orphan
        # that PR on a branch nothing pushes to.
        with _support._worktree_fixture(local_branch_present=False) as fixture:
            fixture.run(creation._ensure_worktree, branch=_support.LEGACY_BRANCH)
            add_args = fixture.git.worktree_adds[0]
            self.assertIn(_support.LEGACY_BRANCH, add_args)
            self.assertNotIn(_support.ISSUE_BRANCH, add_args)

    def test_only_the_base_branch_is_fetched(self) -> None:
        with _support._worktree_fixture() as fixture:
            fixture.run(creation._ensure_worktree)
            self.assertEqual(fixture.fetches.branches, [_support.BASE_BRANCH])
            self.assertEqual(fixture.git.plain_fetches, [])


class EnsurePrWorktreeTest(unittest.TestCase):
    """A PR worktree is restored from the PR's own remote head.

    `_ensure_worktree`'s base-branch fallback is right for a fresh run but
    wrong once a PR exists: rebuilding off `<remote>/<base>` would discard
    the dev's commits and leave the PR's conflicts unresolvable.
    """

    def test_missing_branch_restores_from_remote(self) -> None:
        with _support._worktree_fixture(local_branch_present=False) as fixture:
            worktree = fixture.run(creation._ensure_pr_worktree)
            self.assertEqual(
                fixture.git.worktree_adds[0][2:],
                (
                    NEW_BRANCH_FLAG,
                    _support.ISSUE_BRANCH,
                    str(worktree),
                    f"{_support.ORIGIN_REMOTE}/{_support.ISSUE_BRANCH}",
                ),
            )

    def test_existing_local_branch_is_checked_out(self) -> None:
        with _support._worktree_fixture() as fixture:
            worktree = fixture.run(creation._ensure_pr_worktree)
            add_args = fixture.git.worktree_adds[0]
            self.assertNotIn(NEW_BRANCH_FLAG, add_args)
            self.assertEqual(add_args[2:], (str(worktree), _support.ISSUE_BRANCH))

    def test_a_deleted_branch_falls_back_to_base(self) -> None:
        # The merged PR whose branch GitHub auto-deleted, seen from a host with
        # no local ref left. `pr_number` stays on the issue, so every later
        # tick routes here; anchoring on a ref neither side has would fail the
        # add on every one of them and no implementer would ever run again.
        with _support._worktree_fixture(
            local_branch_present=False, remote_branch_present=False,
        ) as fixture:
            worktree = fixture.run(creation._ensure_pr_worktree)
            self.assertEqual(
                fixture.git.worktree_adds[0][2:],
                (
                    NEW_BRANCH_FLAG,
                    _support.ISSUE_BRANCH,
                    str(worktree),
                    f"{_support.ORIGIN_REMOTE}/{_support.BASE_BRANCH}",
                ),
            )

    def test_an_unconfirmed_absence_refuses(self) -> None:
        # The same missing refs, and the remote saying something other than "no
        # such branch": a token that expired, a network that was down, or a
        # branch that is plainly still there. Rebuilding at base on any of those
        # hands the dev a tree the PR's commits are missing from, and the
        # publication that follows force-pushes it over the PR -- so the tick
        # ends with the branch, the checkout, and the PR untouched.
        for remote_tip in (LIVE_REMOTE_SHA, None):
            with (
                self.subTest(remote_tip=remote_tip),
                _support._worktree_fixture(
                    local_branch_present=False,
                    remote_branch_present=False,
                    remote_tip=remote_tip,
                ) as fixture,
                self.assertRaises(RuntimeError),
            ):
                fixture.run(creation._ensure_pr_worktree)

    def test_base_and_branch_fetches_are_authed(self) -> None:
        with _support._worktree_fixture() as fixture:
            fixture.run(creation._ensure_pr_worktree)
            self.assertEqual(
                fixture.fetches.branches, [_support.BASE_BRANCH, _support.ISSUE_BRANCH],
            )
            self.assertEqual(fixture.git.plain_fetches, [])

    def test_every_git_call_runs_in_target_root(self) -> None:
        # The parent clone is operator-owned; running any of these in the
        # agent-writable worktree would resolve its `.git/config` instead.
        with _support._worktree_fixture() as fixture:
            fixture.run(creation._ensure_pr_worktree)
            for args, cwd in fixture.git.calls:
                self.assertEqual(cwd, fixture.spec.target_root, args)


class StaleWorktreeTest(unittest.TestCase):
    """What happens to a worktree an earlier tick left on disk.

    Reuse is what lets the orchestrator survive a crash between the agent
    committing and the push -- without it the next tick would wipe the work
    and burn another agent run on the same prompt. A worktree with nothing
    unpushed carries no such value and is force-removed so creation can
    start from a current base.
    """

    def test_unpushed_commits_are_reused_and_logged(self) -> None:
        for ensure in CREATORS:
            with (
                self.subTest(ensure=ensure.__name__),
                _support._worktree_fixture(
                    commit_probe=_support._git_result(stdout="2\n"),
                ) as fixture,
            ):
                planted = fixture.plant_issue_worktree()
                with self.assertLogs(creation.log, level="INFO") as logs:
                    worktree = fixture.run(ensure)
                    self.assertIn("reusing", "\n".join(logs.output))
                self.assertEqual(worktree, planted)
                self.assertEqual(fixture.git.worktree_adds, [])
                self.assertEqual(fixture.git.worktree_removes, [])

    def test_clean_worktree_is_force_removed(self) -> None:
        for ensure in CREATORS:
            with (
                self.subTest(ensure=ensure.__name__),
                _support._worktree_fixture() as fixture,
            ):
                planted = fixture.plant_issue_worktree()
                fixture.run(ensure)
                self.assertEqual(
                    fixture.git.worktree_removes[0][3:], (str(planted),),
                )
                self.assertTrue(fixture.git.worktree_adds)

    def test_failed_add_raises_with_git_error(self) -> None:
        # The caller has no worktree to hand the agent, so failing loudly
        # beats returning a path that is not a checkout.
        for ensure in CREATORS:
            with (
                self.subTest(ensure=ensure.__name__),
                _support._worktree_fixture(
                    worktree_add=_support._git_result(
                        returncode=1, stderr=ADD_FAILURE_STDERR,
                    ),
                ) as fixture,
                self.assertRaisesRegex(RuntimeError, ADD_FAILURE_STDERR),
            ):
                fixture.run(ensure)


class HasNewCommitsTest(unittest.TestCase):
    """The probe behind every reuse decision."""

    def test_rev_list_references_per_spec_remote(self) -> None:
        # With REPOS driving a non-default remote, a hardcoded `origin`
        # would read the wrong upstream and report stale commits.
        recorder = _GitRecorder()
        with patch.object(commands, "_git", recorder):
            creation._has_new_commits(_support._spec(PRIVATE_REMOTE), FAKE_WORKTREE)
        args, cwd = recorder.calls[0]
        self.assertIn(f"{PRIVATE_REMOTE}/{_support.BASE_BRANCH}..HEAD", args)
        self.assertNotIn(f"{_support.ORIGIN_REMOTE}/{_support.BASE_BRANCH}..HEAD", args)
        self.assertEqual(cwd, FAKE_WORKTREE)

    def test_count_decides_the_verdict(self) -> None:
        # Empty output is what a worktree sitting exactly at base reports.
        for stdout, expected in (("3\n", True), ("0\n", False), ("", False)):
            recorder = _GitRecorder(commit_probe=_support._git_result(stdout=stdout))
            with (
                self.subTest(stdout=stdout),
                patch.object(commands, "_git", recorder),
            ):
                self.assertEqual(
                    creation._has_new_commits(_support._spec(), FAKE_WORKTREE),
                    expected,
                )

    def test_probe_failure_reports_no_commits(self) -> None:
        # A transient rev-list failure must not read as unpushed work, or
        # the creators would reuse a stale worktree indefinitely.
        recorder = _GitRecorder(commit_probe=_support._git_result(returncode=1))
        with patch.object(commands, "_git", recorder):
            self.assertFalse(
                creation._has_new_commits(_support._spec(), FAKE_WORKTREE),
            )


class MergedPrBranchTest(unittest.TestCase):
    """The PR-aware creator on a branch the merge took away.

    Real repositories because the whole lifecycle is refs: the branch existed,
    its work landed in the base, and the remote dropped it -- and the clone
    running the creator is a host that never had the local ref. What must not
    happen is what a mock cannot show: `worktree add` failing on a ref nobody
    has, on this tick and every tick after it.
    """

    def setUp(self) -> None:
        self._repo = _MergedPlanRepo()

    def test_a_live_branch_missed_by_a_fetch(self) -> None:
        # The same fresh host, one transient failure earlier: the branch is on
        # the remote, this clone has never fetched it, and the fetch that would
        # have brought it did not run. Read as a deletion, the PR (or an
        # in-flight published plan) is rebuilt at base and force-pushed away.
        self._repo.plant(self, _support.ISSUE_BRANCH, deleted=False)
        failed_fetch = MagicMock(
            return_value=_support._git_result(returncode=1, stderr=FETCH_FAILURE),
        )

        with patch.object(branch_transport, AUTHED_TARGET_FETCH, failed_fetch), self.assertRaises(RuntimeError):
            creation._ensure_pr_worktree(
                self._repo.spec, _support.ISSUE_NUMBER, branch=_support.ISSUE_BRANCH,
            )

    def test_a_stale_ref_a_failed_fetch_left(self) -> None:
        # The ref outlives the fetch that wrote it. This clone has
        # `origin/<branch>` at the commit it saw last time and the remote has
        # moved on; with the fetch that would have caught up failing, that ref
        # resolves perfectly well and names the wrong commit. Restored from it,
        # an interrupted publication comes back looking like a branch somebody
        # reset -- the recovery retires its marker and lets the conversation
        # carry on while the plan sits published on a PR nobody recorded.
        amended = _AmendedPlanRepo()
        amended.plant(self, _support.ISSUE_NUMBER, _support.ISSUE_BRANCH)
        # `origin/<branch>` was written by the push and never refreshed since,
        # so it names the published tip while the remote is on the amendment.
        self.assertNotEqual(amended.published, amended.amended)
        amended.remove_worktree()
        amended.delete_local_branch(_support.ISSUE_BRANCH)
        failed_fetch = MagicMock(
            return_value=_support._git_result(returncode=1, stderr=FETCH_FAILURE),
        )

        with patch.object(branch_transport, AUTHED_TARGET_FETCH, failed_fetch), self.assertRaises(RuntimeError):
            creation._ensure_pr_worktree(
                amended.spec, _support.ISSUE_NUMBER, branch=_support.ISSUE_BRANCH,
            )

    def test_a_live_branch_comes_from_remote(self) -> None:
        # The same host with the fetch working: the branch comes back from the
        # remote head, which is where the PR's commits are.
        self._repo.plant(self, _support.ISSUE_BRANCH, deleted=False)

        worktree = creation._ensure_pr_worktree(
            self._repo.spec, _support.ISSUE_NUMBER, branch=_support.ISSUE_BRANCH,
        )

        self.assertEqual(
            (worktree / PLAN_PATH).read_text(), PUBLISHED_PLAN_TEXT,
        )

    def test_a_merged_deleted_branch_rebuilds_at_base(self) -> None:
        self._repo.plant(self, _support.ISSUE_BRANCH)

        worktree = creation._ensure_pr_worktree(
            self._repo.spec, _support.ISSUE_NUMBER, branch=_support.ISSUE_BRANCH,
        )

        self.assertTrue(worktree.exists())
        # Rebuilt from the base, which is where the merge put the work: the
        # implementer starts from what landed rather than from nothing.
        self.assertEqual(
            (worktree / PLAN_PATH).read_text(), PUBLISHED_PLAN_TEXT,
        )
        self.assertEqual(
            self._repo.head_of(worktree), self._repo.base_tip(),
        )


class AnchorPrWorktreeTest(unittest.TestCase):
    """The handoff move, against a real remote a human has pushed to.

    Real repositories because the whole question is what the object store has:
    the head to move onto exists only on the remote until something fetches it,
    and no mock can show that the reset lands the reviewers' file in the tree.
    """

    def setUp(self) -> None:
        self._repo = _AmendedPlanRepo()
        self._repo.plant(self, _support.ISSUE_NUMBER, _support.ISSUE_BRANCH)

    def test_the_reviewed_head_replaces_the_old(self) -> None:
        # The checkout is on the plan this orchestrator published; the head its
        # reviewers left is on the remote. A developer handed the published one
        # builds on a design they have moved past, and the push that follows
        # sends a tip that does not contain their edit.
        self.assertEqual(
            self._repo.head_of(self._repo.worktree), self._repo.published,
        )

        anchored = self._anchor(self._repo.amended)

        self.assertEqual(anchored, self._repo.amended)
        self.assertEqual(
            self._repo.head_of(self._repo.worktree), self._repo.amended,
        )
        self.assertEqual(
            (self._repo.worktree / PLAN_PATH).read_text(), AMENDED_PLAN_TEXT,
        )

    def test_an_unfetchable_head_moves_nothing(self) -> None:
        # A head this host cannot fetch while the branch is plainly still on the
        # remote: a token that expired, a network that was down. Nothing was
        # established, and the caller is told so -- moving the branch anywhere
        # would put the developer behind the reviewers, and a base fallback here
        # would force-push the PR's own commits away.
        self.assertIsNone(self._anchor(UNKNOWN_SHA))

        self.assertEqual(
            self._repo.head_of(self._repo.worktree), self._repo.published,
        )
        self.assertEqual(
            (self._repo.worktree / PLAN_PATH).read_text(), PUBLISHED_PLAN_TEXT,
        )

    def test_a_head_the_humans_moved_past_holds(self) -> None:
        # The race the reviewed head is read across: the guard asked GitHub
        # while the PR was still on the commit this orchestrator published, and
        # the humans pushed their own edit before the anchor ran. The fetch
        # brings theirs and leaves ours resolving perfectly well underneath it
        # as an ancestor, so "the object is here" would put the branch back on
        # a head the pull request has moved past -- and the push that followed
        # would read their commit off the remote as its own lease and overwrite
        # it with one that does not contain it. Nothing is established, so
        # nothing moves and the handoff waits for a tick that reads the PR
        # again.
        self.assertNotEqual(self._repo.published, self._repo.amended)

        self.assertIsNone(self._anchor(self._repo.published))

        self.assertEqual(
            self._repo.branch_tip(_support.ISSUE_BRANCH), self._repo.published,
        )
        self.assertEqual(
            (self._repo.worktree / PLAN_PATH).read_text(), PUBLISHED_PLAN_TEXT,
        )

    def test_a_deleted_branch_with_a_head_named_holds(self) -> None:
        # The branch is gone and a head was still named for it, which is a
        # pull request somebody closed and cleaned up after: what it carried
        # went with the branch and is nowhere in the base. Anchored there
        # anyway, the caller retires the plan records and starts the developer
        # from a base the plan was never in. Only a caller that names NO head
        # has established the design landed, and only that one gets the base.
        self._repo.delete_on_remote(_support.ISSUE_BRANCH)

        self.assertIsNone(self._anchor(self._repo.amended))

        self.assertEqual(
            self._repo.head_of(self._repo.worktree), self._repo.published,
        )
        self.assertEqual(
            (self._repo.worktree / PLAN_PATH).read_text(), PUBLISHED_PLAN_TEXT,
        )

    def test_a_missing_checkout_moves_the_ref(self) -> None:
        # The directory can be gone while the branch survives -- a host
        # restart, an operator's cleanup. The creators rebuild the checkout
        # from that local ref, so the ref is what has to end up on the head.
        self._repo.remove_worktree()

        self.assertEqual(self._anchor(self._repo.amended), self._repo.amended)

        self.assertEqual(
            self._repo.branch_tip(_support.ISSUE_BRANCH), self._repo.amended,
        )

    def _anchor(self, head_sha: str):
        return creation._anchor_pr_worktree(
            self._repo.spec, _support.ISSUE_NUMBER, branch=_support.ISSUE_BRANCH,
            head_sha=head_sha,
        )


class MergedPlanHandoffTest(unittest.TestCase):
    """The same move for a plan PR that merged, which names no head at all.

    The design is in the base by then, along with everything else that landed
    while the PR was open, so the base is where the checkout belongs. Real
    repositories because the whole question is which base: this clone's
    remote-tracking ref still names the one from before the merge, and it
    resolves whether or not anything fetched it -- and because the reset that
    puts the checkout there can be talked out of the tree it was aimed at.
    """

    def setUp(self) -> None:
        self._repo = _AmendedPlanRepo()
        self._repo.plant(self, _support.ISSUE_NUMBER, _support.ISSUE_BRANCH)
        self._merged = self._repo.merge_into_base(_support.ISSUE_BRANCH)

    def test_a_merged_plan_takes_the_fetched_base(self) -> None:
        # The refresh is what puts the approved design in the tree the
        # developer is handed: the merge commit exists nowhere this clone can
        # name until something brings it in.
        anchored = self._anchor_on_base()

        self.assertEqual(anchored, self._merged)
        self.assertEqual(
            (self._repo.worktree / PLAN_PATH).read_text(), AMENDED_PLAN_TEXT,
        )

    def test_a_failed_base_refresh_holds_the_handoff(self) -> None:
        # The same merged plan on a host whose fetch did not run. The cached
        # ref resolves perfectly well and names the base from before the merge
        # -- the one base the plan is nowhere in. Anchored there, the handoff
        # retires the plan records and spawns the developer with neither the
        # approved artifact nor the checkout that carried it.
        failed_fetch = MagicMock(
            return_value=_support._git_result(returncode=1, stderr=FETCH_FAILURE),
        )

        with patch.object(branch_transport, AUTHED_TARGET_FETCH, failed_fetch):
            self.assertIsNone(self._anchor_on_base())

        self.assertEqual(
            self._repo.head_of(self._repo.worktree), self._repo.published,
        )
        self.assertEqual(
            (self._repo.worktree / PLAN_PATH).read_text(), PUBLISHED_PLAN_TEXT,
        )

    def test_a_redirected_worktree_is_not_reset(self) -> None:
        # `core.worktree` in the per-worktree config points every path
        # operation at another directory, and no `-c` override wins against it.
        # Left to discovery the reset reports success and moves the ref while
        # writing the commit's files somewhere else entirely: the issue's
        # checkout stays on the plan it had, the caller records a baseline the
        # tree does not match, and whatever was in that other directory is
        # overwritten on the way past.
        shadow = self._repo.worktree.parent / SHADOW_DIR
        shadow.mkdir()
        _run_git(
            GIT_CONFIG, WORKTREE_CONFIG_EXTENSION, "true",
            cwd=self._repo.worktree,
        )
        _run_git(
            GIT_CONFIG, WORKTREE_SCOPE, CORE_WORKTREE, str(shadow),
            cwd=self._repo.worktree,
        )

        self.assertEqual(self._anchor_on_base(), self._merged)

        # The real checkout is the one that moved, and the directory the
        # config pointed at was never written into.
        self.assertEqual(
            (self._repo.worktree / PLAN_PATH).read_text(), AMENDED_PLAN_TEXT,
        )
        self.assertEqual(list(shadow.iterdir()), [])

    def _anchor_on_base(self):
        """The handoff a finished pull request asks for: no head, the base."""
        return creation._anchor_pr_worktree(
            self._repo.spec, _support.ISSUE_NUMBER, branch=_support.ISSUE_BRANCH, head_sha="",
        )


if __name__ == "__main__":
    unittest.main()
