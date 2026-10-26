# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Question and PR-terminal teardown of a per-issue branch."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import commands
from orchestrator.git.worktrees import terminal
from orchestrator.git.worktrees.models import ProbeAnswer
from tests.git.worktrees.lifecycle_test_support import (
    ISSUE_BRANCH,
    ISSUE_NUMBER,
    LEGACY_BRANCH,
    REV_PARSE,
    _worktree_fixture,
)
from tests.git.worktrees.terminal_test_support import (
    _branch_exists,
    _flat_branch,
    _seed_cleanup_fixture,
)
from tests.support.git import (
    _seed_target_root,
    _spec_for,
)

GIT_HELPER = "_git"
WORKTREES_DIR_ATTR = "WORKTREES_DIR"
WORKTREES_SUBDIR = "wts"
GIT_BRANCH = "branch"
GIT_WORKTREE = "worktree"
GIT_MISSING_MESSAGE = "git not found"
REMOTE_FAILURE_MESSAGE = "api went away"
REMOTE_DELETE = "remote-delete"

CLEANUP_WORKTREE_ISSUE_NUMBER = 800
EMPTY_CLEANUP_ISSUE_NUMBER = 801
BRANCH_ONLY_ISSUE_NUMBER = 802
REFUSED_PIN_ISSUE_NUMBER = 803
LINKED_ROOT_ISSUE_NUMBER = 805

# What a record can name that is no proof this issue owns the branch: the flat
# name an earlier layout left, another repository's name for the same issue
# number, which a prefix-and-tail reading would let through, and a branch
# outside the namespace altogether.
FOREIGN_BRANCH = "orchestrator/acme__gadget/issue-300"
REFUSED_PINS = (LEGACY_BRANCH, FOREIGN_BRANCH, "feature/manual")

_LOCAL_TEARDOWN = (GIT_WORKTREE, REV_PARSE, GIT_BRANCH)


class _Timeline:
    """One ordered log across the local git calls and the remote delete.

    Separate per-surface recorders can only say each step happened, not
    that the local teardown came first, so both surfaces append here.
    """

    def __init__(self, recorder) -> None:
        self.events: list[str] = []
        self._recorder = recorder

    def git(self, *args: str, cwd):
        self.events.append(args[0])
        return self._recorder(*args, cwd=cwd)


class _RemoteBranches:
    """Stand in for the GitHub side of the terminal cleanup."""

    def __init__(
        self, *, raises: bool = False, timeline: _Timeline | None = None,
    ) -> None:
        self.deleted: list[str] = []
        self._raises = raises
        self._timeline = timeline

    def delete_remote_branch(self, branch: str) -> bool:
        if self._timeline is not None:
            self._timeline.events.append(REMOTE_DELETE)
        if self._raises:
            raise RuntimeError(REMOTE_FAILURE_MESSAGE)
        self.deleted.append(branch)
        return True


class CleanupQuestionWorktreeTest(unittest.TestCase):
    """The question agent is read-only and never pushes, so its teardown is
    local-only: worktree first, then the branch it had checked out.
    """

    def test_local_teardown_runs_in_order(self) -> None:
        with _worktree_fixture() as fixture:
            fixture.plant_issue_worktree()
            terminal._cleanup_question_worktree(fixture.spec, ISSUE_NUMBER)
            self.assertEqual(
                tuple(args[0] for args, _cwd in fixture.git.calls),
                _LOCAL_TEARDOWN,
            )

    def test_a_refused_pin_touches_nothing(self) -> None:
        # The tree is standing on the branch the record names, which is not
        # the issue's own: the identity read refuses the checkout, the pin
        # refuses the branch, and no derived name is deleted in its place.
        for pinned in REFUSED_PINS:
            with (
                self.subTest(branch=pinned),
                _worktree_fixture(checkout_identity=ProbeAnswer.REFUTED) as fixture,
            ):
                fixture.plant_issue_worktree()
                with self.assertLogs(terminal.log, level="WARNING") as logs:
                    terminal._cleanup_question_worktree(
                        fixture.spec, ISSUE_NUMBER, branch=pinned,
                    )
                    self.assertIn(pinned, "\n".join(logs.output))
                self.assertEqual(fixture.git.calls, [])


class CleanupTerminalBranchTest(unittest.TestCase):
    """Teardown once the PR reached `done` or `rejected`.

    The issue already carries its terminal label by the time this runs, so
    a stale ref is tidiness rather than correctness: every step swallows
    its own failure, and the remote delete -- the one the operator sees in
    the repo's branch list -- runs last so no local failure can skip it.
    """

    def test_locals_precede_the_remote_delete(self) -> None:
        # git refuses to delete a checked-out branch, and the remote delete
        # has to survive a local-side failure, so the four steps are one
        # ordered sequence rather than four independent ones.
        with _worktree_fixture() as fixture:
            timeline = _Timeline(fixture.git)
            gh = _RemoteBranches(timeline=timeline)
            fixture.plant_issue_worktree()
            with patch.object(commands, GIT_HELPER, timeline.git):
                terminal._cleanup_terminal_branch(
                    gh, fixture.spec, ISSUE_NUMBER,
                )
            self.assertEqual(
                tuple(timeline.events), (*_LOCAL_TEARDOWN, REMOTE_DELETE),
            )
            self.assertEqual(gh.deleted, [ISSUE_BRANCH])

    def test_absent_worktree_reaps_both_branches(self) -> None:
        with _worktree_fixture() as fixture:
            gh = _RemoteBranches()
            terminal._cleanup_terminal_branch(gh, fixture.spec, ISSUE_NUMBER)
            self.assertEqual(
                [args[0] for args, _cwd in fixture.git.calls],
                [REV_PARSE, GIT_BRANCH],
            )
            self.assertEqual(gh.deleted, [ISSUE_BRANCH])

    def test_absent_local_branch_reaps_the_remote(self) -> None:
        with _worktree_fixture(local_branch_present=False) as fixture:
            gh = _RemoteBranches()
            terminal._cleanup_terminal_branch(gh, fixture.spec, ISSUE_NUMBER)
            self.assertNotIn(
                GIT_BRANCH, [args[0] for args, _cwd in fixture.git.calls],
            )
            self.assertEqual(gh.deleted, [ISSUE_BRANCH])

    def test_local_failure_still_deletes_remote(self) -> None:
        with _worktree_fixture() as fixture:
            gh = _RemoteBranches()
            fixture.plant_issue_worktree()
            with (
                patch.object(
                    commands,
                    GIT_HELPER,
                    side_effect=OSError(GIT_MISSING_MESSAGE),
                ),
                self.assertLogs(terminal.log, level="ERROR"),
            ):
                terminal._cleanup_terminal_branch(
                    gh, fixture.spec, ISSUE_NUMBER,
                )
            self.assertEqual(gh.deleted, [ISSUE_BRANCH])

    def test_swallows_a_raising_remote_delete(self) -> None:
        with _worktree_fixture() as fixture:
            gh = _RemoteBranches(raises=True)
            with self.assertLogs(terminal.log, level="ERROR") as logs:
                terminal._cleanup_terminal_branch(
                    gh, fixture.spec, ISSUE_NUMBER,
                )
                self.assertIn(
                    REMOTE_FAILURE_MESSAGE, "\n".join(logs.output),
                )

    def test_a_pinned_current_name_is_reaped(self) -> None:
        with _worktree_fixture() as fixture:
            gh = _RemoteBranches()
            terminal._cleanup_terminal_branch(
                gh, fixture.spec, ISSUE_NUMBER, branch=ISSUE_BRANCH,
            )
            self.assertEqual(gh.deleted, [ISSUE_BRANCH])

    def test_a_refused_pin_deletes_nothing(self) -> None:
        # Neither host loses a branch the record names but this issue does not
        # own, and the derived name is not reaped in its place: the merged
        # pull request stood on the pinned one, and anything on the derived
        # one is work nobody published. The tree standing on the pinned branch
        # is not the issue's own checkout either, so it stays too.
        for pinned in REFUSED_PINS:
            with (
                self.subTest(branch=pinned),
                _worktree_fixture(checkout_identity=ProbeAnswer.REFUTED) as fixture,
            ):
                gh = _RemoteBranches()
                fixture.plant_issue_worktree()
                with self.assertLogs(terminal.log, level="WARNING"):
                    terminal._cleanup_terminal_branch(
                        gh, fixture.spec, ISSUE_NUMBER, branch=pinned,
                    )
                self.assertEqual(gh.deleted, [])
                self.assertEqual(fixture.git.calls, [])


class CleanupQuestionWorktreeRealGitTest(unittest.TestCase):
    """Question cleanup against a real worktree and local branch.

    The stage-handler tests mock this helper on the owner; here the real
    `git worktree remove` + `git branch -D` plumbing runs, so a regression
    in argument order, lock acquisition, or error-swallowing surfaces.
    """

    def test_removes_worktree_and_local_branch(self) -> None:
        # Stand up a worktree at the path `_worktree_path` will
        # compute. Patch WORKTREES_DIR so the slug-derived
        # subdirectory lives inside this temp dir.
        with (
            tempfile.TemporaryDirectory(prefix="cqw-both-") as td,
            patch.object(config, WORKTREES_DIR_ATTR, Path(td) / WORKTREES_SUBDIR),
        ):
            fixture = _seed_cleanup_fixture(
                Path(td),
                CLEANUP_WORKTREE_ISSUE_NUMBER,
                create_worktree=True,
            )
            self.assertTrue(fixture.worktree.exists())
            # Branch should exist locally.
            self.assertTrue(_branch_exists(fixture))

            terminal._cleanup_question_worktree(
                fixture.spec,
                CLEANUP_WORKTREE_ISSUE_NUMBER,
            )

            self.assertFalse(fixture.worktree.exists())
            # Local branch is gone.
            self.assertFalse(_branch_exists(fixture))

    def test_idempotent_when_nothing_exists(self) -> None:
        # No worktree on disk, no local branch -- the cleanup must
        # not raise (best-effort contract: cleanup never propagates
        # out of the handler).
        with tempfile.TemporaryDirectory(prefix="cqw-nothing-") as td:
            tdp = Path(td)
            target, _ = _seed_target_root(tdp)
            with patch.object(config, WORKTREES_DIR_ATTR, tdp / WORKTREES_SUBDIR):
                spec = _spec_for(target)
                # Should not raise.
                terminal._cleanup_question_worktree(
                    spec,
                    EMPTY_CLEANUP_ISSUE_NUMBER,
                )

    def test_missing_tree_still_deletes_branch(self) -> None:
        # A prior tick's worktree directory was removed (manual cleanup,
        # or partial cleanup) but the local branch survived. The cleanup
        # must still tear the branch down so a later `_ensure_worktree`
        # cannot reuse it.
        with tempfile.TemporaryDirectory(prefix="cqw-branchOnly-") as td, patch.object(
            config,
            WORKTREES_DIR_ATTR,
            Path(td) / WORKTREES_SUBDIR,
        ):
            fixture = _seed_cleanup_fixture(
                Path(td),
                BRANCH_ONLY_ISSUE_NUMBER,
                create_worktree=False,
            )
            # Sanity: worktree path does not exist.
            self.assertFalse(fixture.worktree.exists())

            terminal._cleanup_question_worktree(
                fixture.spec,
                BRANCH_ONLY_ISSUE_NUMBER,
            )

            self.assertFalse(_branch_exists(fixture))

    def test_a_linked_worktrees_dir_takes_its_own(self) -> None:
        # `WORKTREES_DIR` may itself be configured through a symlink; only a
        # link below it -- at the issue's path or its per-repository parent --
        # makes the path one the forced removal will not follow.
        with tempfile.TemporaryDirectory(prefix="cqw-linked-root-") as temp_dir:
            root = Path(temp_dir)
            (root / "real-worktrees").mkdir()
            linked_root = root / WORKTREES_SUBDIR
            linked_root.symlink_to(root / "real-worktrees", target_is_directory=True)
            with patch.object(config, WORKTREES_DIR_ATTR, linked_root):
                fixture = _seed_cleanup_fixture(
                    root, LINKED_ROOT_ISSUE_NUMBER, create_worktree=True,
                )

                terminal._cleanup_question_worktree(fixture.spec, LINKED_ROOT_ISSUE_NUMBER)

                self.assertFalse(fixture.worktree.exists())
                self.assertFalse(_branch_exists(fixture))

    def test_a_refused_pin_leaves_both_branches(self) -> None:
        # The checkout comes down; the flat branch the record names and the
        # current one beside it both survive in the real ref store.
        with tempfile.TemporaryDirectory(prefix="cqw-refused-") as td, patch.object(
            config,
            WORKTREES_DIR_ATTR,
            Path(td) / WORKTREES_SUBDIR,
        ):
            fixture = _seed_cleanup_fixture(
                Path(td),
                REFUSED_PIN_ISSUE_NUMBER,
                create_worktree=True,
            )
            flat = _flat_branch(fixture, REFUSED_PIN_ISSUE_NUMBER)

            with self.assertLogs(terminal.log, level="WARNING"):
                terminal._cleanup_question_worktree(
                    fixture.spec, REFUSED_PIN_ISSUE_NUMBER, branch=flat.branch,
                )

            self.assertFalse(fixture.worktree.exists())
            self.assertTrue(_branch_exists(fixture))
            self.assertTrue(_branch_exists(flat))


if __name__ == "__main__":
    unittest.main()
