# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Writer claims taken by other processes, over a namespace a test shares with them.

A claim is only worth testing against a holder this interpreter knows nothing
about, so the holder here is a real second process: it runs a program of the
caller's, imports what that program claims through fresh, resolves the
namespace from its own environment, and says over a pipe what it was granted.
The test process points its own configuration at the same checkout root, so
the two meet in one namespace exactly as two pollers do.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.scheduler import writer_claims

# Read before any test runs, so it is the owner's own namespace rather than the
# per-test one the suite's autouse fixture installs over it.
_REAL_NAMESPACE = writer_claims._namespace

_REPO_ROOT = Path(__file__).resolve().parents[2]

# How long another process is given to answer. Generous, since what it
# separates is an answer from a process that never gave one.
_ANSWER_SECONDS = 10.0

HELD = "held"
REFUSED = "refused"
RELEASED = "released"


class OtherProcess:
    """One program claiming in a separate interpreter on this host."""

    def __init__(self, root: Path, program: str, *arguments: object) -> None:
        environment = dict(os.environ)
        environment["WORKTREES_DIR"] = str(root)
        environment["ORCHESTRATOR_SKIP_DOTENV"] = "1"
        self._process = subprocess.Popen(
            [sys.executable, "-c", program, *map(str, arguments)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env=environment,
            cwd=_REPO_ROOT,
        )

    def said(self) -> str:
        """The next thing the process reported, or "" if it ended first."""
        return self._process.stdout.readline().strip()

    def let_go(self) -> int:
        """Tell the process to finish, and wait for it to exit."""
        self._process.stdin.write("\n")
        self._process.stdin.flush()
        return self.exited()

    def killed(self) -> int:
        """End the process the way a crash or an OOM kill does."""
        self._process.kill()
        return self.exited()

    def exited(self) -> int:
        self._process.wait(timeout=_ANSWER_SECONDS)
        return self._process.returncode

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.kill()
            self._process.wait(timeout=_ANSWER_SECONDS)
        self._process.stdin.close()
        self._process.stdout.close()


class SharedNamespaceCase(unittest.TestCase):
    """A checkout root of this test's own, claimed in by real processes."""

    def setUp(self) -> None:
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        for patched in (
            patch.object(config, "WORKTREES_DIR", self.root),
            patch.object(writer_claims, "_namespace", _REAL_NAMESPACE),
        ):
            patched.start()
            self.addCleanup(patched.stop)

    def run_elsewhere(self, program: str, *arguments: object) -> OtherProcess:
        """Start `program` in another process claiming in this test's namespace."""
        other = OtherProcess(self.root, program, *arguments)
        self.addCleanup(other.close)
        return other
