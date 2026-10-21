# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What object an id names in a real repository, and a read that established nothing told apart from absence.

A commit, its tree, and an annotated tag each answer git's own type. An id no
object of the repository has answers empty, which is git saying so. A read git
fails -- an object behind a directory it may not read, both requests refused,
a lookup a signal killed or that exited fatally without a word, or git not run
at all -- answers None, whatever the object is: a caller about to retire
evidence must not take it for absence.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

from orchestrator.git import commands
from orchestrator.git.verification import objects
from tests.workflow.fixtures import TEST_BASE_BRANCH

# An object id this repository has never held.
ABSENT = "deadbeef" * 5

# What a git read that fails on an object it cannot read exits with.
GIT_FAILURE = 128

# The status a git process SIGKILL ended reports.
KILLED = -9

SEED = "seed"

# The mode an object directory is given back once a case has shut git out of it.
_READABLE = 0o755

_REV_PARSE = "rev-parse"

# The identity and signing the setup's commit and tag are made under.
_IDENTITY = ("-c", "user.email=t@t", "-c", "user.name=t", "-c", "tag.gpgsign=false")


def _ending_the_lookup(ended: subprocess.CompletedProcess, real, *args, **kwargs):
    """`real`'s answer to a hardened git read, save the existence lookup, which ends as `ended`."""
    return ended if args[0] == _REV_PARSE else real(*args, **kwargs)


def _git(*args: str, cwd: Path) -> str:
    """Run git in `cwd` for the test's own setup, and hand back what it printed."""
    ran = subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    return ran.stdout.strip()


class ObjectKindTest(unittest.TestCase):
    """`_object_kind` over a repository holding one commit, its tree, and a tag of it."""

    def setUp(self) -> None:
        work = Path(tempfile.mkdtemp(prefix="orch-object-kind-"))
        self.addCleanup(shutil.rmtree, str(work), ignore_errors=True)
        _git("init", "-q", "-b", TEST_BASE_BRANCH, cwd=work)
        (work / SEED).write_text("x\n")
        _git("add", ".", cwd=work)
        _git(*_IDENTITY, "commit", "-q", "-m", SEED, cwd=work)
        _git(*_IDENTITY, "tag", "-a", "-m", SEED, SEED, cwd=work)
        self.work = work

    def test_each_object_answers_its_type(self) -> None:
        head = _git(_REV_PARSE, "HEAD", cwd=self.work)
        named = (
            (head, "commit"),
            (_git(_REV_PARSE, "HEAD^{tree}", cwd=self.work), "tree"),
            (_git("for-each-ref", "--format=%(objectname)", "refs/tags", cwd=self.work), "tag"),
            (ABSENT, ""),
        )
        for revision, kind in named:
            with self.subTest(kind=kind):
                self.assertEqual(objects._object_kind(self.work, revision), kind)

    def test_an_object_git_may_not_open_is_no_answer(self) -> None:
        # The commit sits behind a directory git may not read. Its existence
        # check exits as it would for a missing object, so only what git says
        # about the lookup tells the two apart -- and it is no answer.
        if os.geteuid() == 0:
            self.skipTest("directory permissions do not bind the superuser")
        head = _git(_REV_PARSE, "HEAD", cwd=self.work)
        directory = self.work / ".git" / "objects" / head[:2]
        directory.chmod(0)
        self.addCleanup(directory.chmod, _READABLE)

        self.assertIsNone(objects._object_kind(self.work, head))

    def test_a_failed_read_is_no_answer(self) -> None:
        # Git refusing both requests -- as an object it cannot read makes it --
        # or not running at all says nothing about the commit that is there.
        head = _git(_REV_PARSE, "HEAD", cwd=self.work)
        failed = subprocess.CompletedProcess([], GIT_FAILURE, "", "fatal: failed to read object")
        for answers in ({"return_value": failed}, {"side_effect": OSError("git is not installed")}):
            refused = patch.object(commands, "_git_hardened", **answers)
            with self.subTest(answers=sorted(answers)), refused:
                self.assertIsNone(objects._object_kind(self.work, head))

    def test_an_unfinished_lookup_is_no_answer(self) -> None:
        # The id is one the repository never held, so its type read fails as
        # git fails it. The lookup that would prove it absent ends without
        # git's own answer for a name that resolves to nothing -- killed by
        # SIGKILL, or a fatal exit with nothing said -- and proves nothing.
        for status in (KILLED, GIT_FAILURE):
            ended = subprocess.CompletedProcess([], status, "", "")
            answers = partial(_ending_the_lookup, ended, commands._git_hardened)
            with self.subTest(status=status), patch.object(commands, "_git_hardened", answers):
                self.assertIsNone(objects._object_kind(self.work, ABSENT))


if __name__ == "__main__":
    unittest.main()
