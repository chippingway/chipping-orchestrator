# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""HEAD, dirty-file, and tree probing owned by the verification probe module.

The two answers the status read can give are pinned separately on purpose. A
caller that refuses on what git NAMED wants the list, where an unreadable tree
and a clean one are both "nothing to refuse on"; a caller whose next step is a
push has to prove the tree is clean, and for it the difference between the two
is the whole question.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.git import commands
from orchestrator.git.verification import probes, status as _worktree_status
from tests.workflow.fixtures import TEST_BASE_BRANCH

GIT_COMMAND = "git"
QUIET_FLAG = "-q"
GIT_CONFIG = "config"
HARDENED_GIT = "_git_hardened"
SEED_FILE = "seed"
LEFTOVER_FILE = "leftover.txt"
EXECUTABLE_MODE = 0o755
HEAD_SHA = "f00dcafe"
GIT_FAILURE = 128
WORKTREE = Path("/tmp/orchestrator-test-verification-probes")
PLAN_PATH = "plans/issue-42.md"
REGULAR_MODE = "100644"
BLOB_TYPE = "blob"
TREE_OBJECT = "0f1e2d3c4b5a69788796a5b4c3d2e1f009182736"

# Every mode git can hold at one path, and whether it is the document the
# caller is asking about.
TREE_ENTRY_CASES = (
    ("100644", BLOB_TYPE, True),
    ("100755", BLOB_TYPE, True),
    ("120000", BLOB_TYPE, False),
    ("160000", "commit", False),
    ("040000", "tree", False),
)

# An untracked file named exactly as porcelain's line format spells a rename.
# Read that way, what follows the arrow is a lone quote, which is nothing --
# and the tree holding it reports clean.
ARROW_FILE = " -> "

# NUL-delimited porcelain v1 records and the paths they name. Nothing is
# quoted under `-z`, and a rename's source is its own record after the one
# naming where the file is now -- both halves are reported, since a caller
# permitting exactly one path is entitled to know a file left another behind.
PORCELAIN_CASES = (
    (" M src/app.py\0", ["src/app.py"]),
    ("?? leftover.txt\0", ["leftover.txt"]),
    ("R  new.py\0old.py\0", ["new.py", "old.py"]),
    ("?? quoted path.txt\0", ["quoted path.txt"]),
    (f"?? {ARROW_FILE}\0", [ARROW_FILE]),
    ("??\0", []),
    ("", []),
)


def _completed(returncode: int, stdout: str) -> subprocess.CompletedProcess:
    """Return a git result carrying the given exit status and stdout."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


def _run_git(*args: str, cwd: Path) -> None:
    subprocess.run(
        [GIT_COMMAND, *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


class HeadShaProbeTest(unittest.TestCase):
    """`_head_sha` snapshots HEAD so a verify-time commit can be detected."""

    def test_reports_the_trimmed_rev_parse_output(self) -> None:
        with patch.object(commands, "_git", return_value=_completed(0, f"{HEAD_SHA}\n")) as git:
            self.assertEqual(probes._head_sha(WORKTREE), HEAD_SHA)
            self.assertEqual(git.call_args.args, ("rev-parse", "HEAD"))
            self.assertEqual(git.call_args.kwargs["cwd"], WORKTREE)

    def test_unreadable_head_reports_no_snapshot(self) -> None:
        # An uninitialized repo has no HEAD to read. The runner treats the
        # empty baseline as "no HEAD ever existed" and accepts only an
        # unchanged "" afterwards, so the probe must not invent a SHA.
        with patch.object(commands, "_git", return_value=_completed(GIT_FAILURE, "fatal: bad revision")):
            self.assertEqual(probes._head_sha(WORKTREE), "")


class PorcelainParsingTest(unittest.TestCase):
    """`_worktree_dirty_files` turns NUL-delimited porcelain records into paths."""

    def test_each_status_record_yields_its_path(self) -> None:
        for record, expected in PORCELAIN_CASES:
            with (
                self.subTest(record=record),
                patch.object(commands, HARDENED_GIT, return_value=_completed(0, record)),
            ):
                self.assertEqual(_worktree_status._worktree_dirty_files(WORKTREE), expected)

    def test_all_reported_paths_are_collected(self) -> None:
        status = "".join(record for record, paths in PORCELAIN_CASES if paths)
        with patch.object(commands, HARDENED_GIT, return_value=_completed(0, status)):
            self.assertEqual(
                _worktree_status._worktree_dirty_files(WORKTREE),
                [
                    "src/app.py", LEFTOVER_FILE, "new.py", "old.py",
                    "quoted path.txt", ARROW_FILE,
                ],
            )

    def test_failed_probe_names_no_paths(self) -> None:
        # The list form is what a caller refusing on named paths reads, so a
        # probe that could not run names none. What it could not prove is the
        # status form's to say -- see below.
        with patch.object(commands, HARDENED_GIT, return_value=_completed(GIT_FAILURE, LEFTOVER_FILE)):
            self.assertEqual(_worktree_status._worktree_dirty_files(WORKTREE), [])


class WorktreeStatusProbeTest(unittest.TestCase):
    """`_worktree_status` says whether git could be asked, not just what it said."""

    def test_a_read_tree_reports_its_paths(self) -> None:
        with patch.object(commands, HARDENED_GIT, return_value=_completed(0, f"?? {LEFTOVER_FILE}")):
            status = _worktree_status._worktree_status(WORKTREE)

        self.assertTrue(status.readable)
        self.assertEqual(status.paths, (LEFTOVER_FILE,))

    def test_a_failed_read_is_not_a_clean_tree(self) -> None:
        # A corrupt index fails `git status` while a commit-to-commit diff
        # still succeeds. Reported as an empty path list, that would let a
        # publication push on the strength of a probe that never ran.
        with patch.object(commands, HARDENED_GIT, return_value=_completed(GIT_FAILURE, "fatal: bad index")):
            status = _worktree_status._worktree_status(WORKTREE)

        self.assertFalse(status.readable)
        self.assertEqual(status.paths, ())


class RevisionContainsPathProbeTest(unittest.TestCase):
    """`_revision_contains_path` tells a written document from everything else."""

    def test_the_named_commit_is_the_one_read(self) -> None:
        # Named, never `HEAD`: the caller decides by this reading and then
        # pushes the same SHA, so a symbolic read could answer for a commit
        # the branch has since moved off.
        read = _completed(0, self._entry(REGULAR_MODE))
        with patch.object(commands, HARDENED_GIT, return_value=read) as git:
            self.assertTrue(
                probes._revision_contains_path(WORKTREE, HEAD_SHA, PLAN_PATH),
            )
            self.assertEqual(
                git.call_args.args,
                ("ls-tree", "-z", "--full-tree", HEAD_SHA, "--", PLAN_PATH),
            )

    def test_a_missing_path_is_reported(self) -> None:
        # The case the base-relative diff cannot see: deleting a file the base
        # branch carries changes exactly the path writing it would. git reports
        # it as an empty reading rather than a failure.
        for read in (_completed(GIT_FAILURE, ""), _completed(0, "")):
            with self.subTest(returncode=read.returncode), patch.object(commands, HARDENED_GIT, return_value=read):
                self.assertFalse(
                    probes._revision_contains_path(
                        WORKTREE, HEAD_SHA, PLAN_PATH,
                    ),
                )

    def test_only_a_regular_file_answers_yes(self) -> None:
        # Every mode git can store at the path, and only two of them are the
        # document a reviewer opens there: a symlink resolves to whatever it
        # names, and a gitlink is a commit id for a submodule nobody fetches.
        for mode, object_type, expected in TREE_ENTRY_CASES:
            with self.subTest(mode=mode):
                read = _completed(0, self._entry(mode, object_type))
                with patch.object(commands, HARDENED_GIT, return_value=read):
                    self.assertEqual(
                        probes._revision_contains_path(
                            WORKTREE, HEAD_SHA, PLAN_PATH,
                        ),
                        expected,
                    )

    def _entry(self, mode: str, object_type: str = BLOB_TYPE) -> str:
        """One `ls-tree -z` record, in the layout git writes it."""
        return f"{mode} {object_type} {TREE_OBJECT}\t{PLAN_PATH}\0"


class WorktreeDirtyFilesHardeningTest(unittest.TestCase):
    """`_worktree_dirty_files` runs its `git status` probe through the
    hardened git path, so an agent-planted `core.fsmonitor` in the worktree
    config cannot execute with the orchestrator's process environment. Every
    caller passes an agent-writable worktree, so the probe is hardened
    unconditionally. Real modifications are still reported; only fsmonitor
    execution and the global-config trust boundary are dropped.
    """

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="orch-dirty-hardening-"))
        self.addCleanup(shutil.rmtree, str(self.tmpdir), ignore_errors=True)
        self.work = self.tmpdir / "work"
        self.work.mkdir()
        _run_git("init", QUIET_FLAG, "-b", TEST_BASE_BRANCH, cwd=self.work)
        _run_git(GIT_CONFIG, "user.email", "t@t", cwd=self.work)
        _run_git(GIT_CONFIG, "user.name", "t", cwd=self.work)
        (self.work / SEED_FILE).write_text("x\n")
        _run_git("add", ".", cwd=self.work)
        _run_git("commit", QUIET_FLAG, "-m", SEED_FILE, cwd=self.work)

    def test_blocks_planted_fsmonitor_reports_dirty(self) -> None:
        # Hook + marker live outside the worktree so they are not themselves
        # untracked files. The `/`+NUL response is fsmonitor v1 for "assume
        # everything changed" -- a scan hint only, so a clean tree reads clean.
        marker = self.tmpdir / "fsmonitor_ran.txt"
        hook = self.tmpdir / "fsmonitor_hook.sh"
        hook.write_text(
            f"#!/bin/sh\nprintf ran >> '{marker}'\nprintf '/\\000'\n"
        )
        hook.chmod(EXECUTABLE_MODE)
        _run_git(GIT_CONFIG, "core.fsmonitor", str(hook), cwd=self.work)

        (self.work / LEFTOVER_FILE).write_text("leak\n")
        # Prove the planted hook is genuinely honored: a plain, unhardened
        # index refresh fires it. Without this the empty-marker assertion
        # below could pass simply because the hook was never wired.
        _run_git("status", "--porcelain", cwd=self.work)
        self.assertTrue(
            marker.exists() and marker.read_text(),
            "planted fsmonitor never fired for a plain git status; the test cannot detect a regression",
        )
        marker.unlink()

        dirty = _worktree_status._worktree_dirty_files(self.work)

        # The real modification is still reported...
        self.assertIn(LEFTOVER_FILE, dirty)
        # ...but the hardened probe never executed the planted helper with
        # our process environment attached.
        self.assertFalse(
            marker.exists() and marker.read_text(),
            "hardened dirty probe executed the planted core.fsmonitor",
        )


if __name__ == "__main__":
    unittest.main()
