# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the set-token tests share: a home of their own, and what one run did."""
from __future__ import annotations

import io
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import NamedTuple, TextIO
from unittest.mock import patch

from orchestrator.service import tokens
from tests.service.service_test_support import FakeAnswer, fake_github

REPOSITORY = "acme/api"
REACHED = (200, {"full_name": REPOSITORY})
OLD_TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
LOOSE_FILE = 0o644

_LOOSE_DIRECTORY = 0o755
_PRIVATE_DIRECTORY = 0o700
_PRIVATE_FILE = 0o600


class TokenRun(NamedTuple):
    """What one set-token run answered, printed, and asked GitHub."""

    status: int
    stdout: str
    stderr: str
    requests: list[tuple[str, str]]


class Terminal(io.StringIO):
    """Standard input attached to a terminal, which only a hidden prompt reads."""

    def isatty(self) -> bool:
        return True

    def read(self, *_size: object) -> str:
        raise AssertionError("a terminal's token is read at the hidden prompt, not from stdin")


def mode(path: Path) -> int:
    """The permission bits of ``path``."""
    return stat.S_IMODE(path.stat().st_mode)


def tree(root: Path) -> list[str]:
    """Everything under ``root``, relative to it."""
    found = (path.relative_to(root) for path in root.rglob("*"))
    return sorted(map(str, found))


class TokenHomeTest(unittest.TestCase):
    """Each test runs in a home of its own, under a umask that grants every bit.

    The permissive umask is what shows the modes are set rather than
    inherited: a file or directory left to the umask here is readable by
    every account on the host.
    """

    def setUp(self) -> None:
        scratch = self.enterContext(tempfile.TemporaryDirectory())
        self.home = Path(scratch)
        self.enterContext(patch.dict(os.environ, {"HOME": scratch}))
        self.addCleanup(os.umask, os.umask(0))
        self.path = self.home / ".config" / REPOSITORY / "token"

    def set_token(self, stdin: TextIO, answer: FakeAnswer = REACHED) -> TokenRun:
        """Run the command with GitHub answering the repository with ``answer``."""
        answers = {f"/repos/{REPOSITORY}": answer}
        stdout = io.StringIO()
        stderr = io.StringIO()
        with fake_github(answers) as github, redirect_stdout(stdout), redirect_stderr(stderr):
            status = tokens.set_token(REPOSITORY, stdin)
            return TokenRun(status, stdout.getvalue(), stderr.getvalue(), github.requests)

    def keep_old_token(self) -> None:
        """A token already kept, readable by everyone in a directory everyone lists."""
        self.path.parent.mkdir(parents=True)
        self.path.write_text(f"{OLD_TOKEN}\n")
        self.path.chmod(LOOSE_FILE)
        self.path.parent.chmod(_LOOSE_DIRECTORY)

    def assert_kept(self, token: str) -> None:
        """``token`` alone is kept, owner-only in an owner-only directory."""
        self.assertEqual(self.path.read_text(), f"{token}\n")
        self.assertEqual(mode(self.path), _PRIVATE_FILE)
        self.assertEqual(mode(self.path.parent), _PRIVATE_DIRECTORY)
        self.assertEqual(tree(self.path.parent), ["token"])

    def assert_created_private(self) -> None:
        """The owner's directory and ``~/.config``, both created here, are owner-only."""
        for created in (self.path.parents[1], self.path.parents[2]):
            self.assertEqual(mode(created), _PRIVATE_DIRECTORY, created)
