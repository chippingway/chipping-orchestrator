# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Writer claims taken by other processes, over a namespace a test shares with them.

A claim is only worth testing against a holder this interpreter knows nothing
about, so the holder here is a real second process: it runs a program of the
caller's, imports what that program claims through fresh, resolves the
namespace from its own environment, and says over a pipe what it was granted.
The test process points its own configuration at the same checkout root, so
the two meet in one namespace exactly as two pollers do. Two programs are
another poller's own writers, for a caller that contends with one: its
dispatch seam, holding what it is granted, and its base refresh, holding
the issue it is granted mid-route or saying it read none.
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

# What another poller's refresh reports: that it is reading an issue it was
# granted, or that it read none.
READ = "read"
UNTOUCHED = "untouched"

# Another poller's client, over the repository GitHub described with the id
# and name its program is handed, and the spec it polls that repository under.
# Neither asks the network for anything a claim is keyed on.
_ANOTHER_POLLER = """
import contextlib
import sys
from pathlib import Path

from github import Github
from github.Repository import Repository

from orchestrator.config.models import RepoSpec
from orchestrator.github.client import GitHubClient

repo_id, name, numbers = int(sys.argv[1]), sys.argv[2], [int(arg) for arg in sys.argv[3:]]
described = {"id": repo_id, "full_name": name, "url": "https://api.github.com/repos/" + name}
gh = GitHubClient.__new__(GitHubClient)
gh._repo_slug = name
gh.repo = Repository(Github().requester, {}, described, completed=True)
spec = RepoSpec(slug=name, target_root=Path.cwd(), base_branch="main")
"""

# Another poller's own dispatch seam. It takes the writer claim of every issue
# it is handed, says whether it got them all, and holds them until told to
# let go.
DISPATCHING_POLLER = f"""{_ANOTHER_POLLER}
from orchestrator.workflow.engine import issue_processing

with contextlib.ExitStack() as claims:
    held = [claims.enter_context(issue_processing._writer_claim(gh, spec, number)) for number in numbers]
    print("{HELD}" if all(held) else "{REFUSED}", flush=True)
    sys.stdin.readline()
"""

# Another poller's own base refresh, over each issue it is handed. Its client
# has no GitHub behind it, so the issue read is as far as a refresh granted the
# claim gets: it says so there, still holding the claim, and waits until told
# to let go before that read fails. A refresh that read nothing says so and
# exits.
REFRESHING_POLLER = f"""{_ANOTHER_POLLER}
from orchestrator.git.base_sync import refresh

read = []


def get_issue(number):
    read.append(number)
    print("{READ}", flush=True)
    sys.stdin.readline()
    raise ConnectionError("this poller has no GitHub to read")


gh.get_issue = get_issue
for number in numbers:
    refresh._sync_worktree_with_base(gh, spec, Path.cwd(), number)
if not read:
    print("{UNTOUCHED}", flush=True)
"""


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
        self.root = shared_namespace(self)

    def run_elsewhere(self, program: str, *arguments: object) -> OtherProcess:
        """Start `program` in another process claiming in this test's namespace."""
        other = OtherProcess(self.root, program, *arguments)
        self.addCleanup(other.close)
        return other


def shared_namespace(case: unittest.TestCase) -> Path:
    """Give `case` a checkout root of its own that real processes claim in too.

    For a case whose own setup is somebody else's: it is undone with the case.
    """
    root = tempfile.TemporaryDirectory()
    case.addCleanup(root.cleanup)
    for patched in (
        patch.object(config, "WORKTREES_DIR", Path(root.name)),
        patch.object(writer_claims, "_namespace", _REAL_NAMESPACE),
    ):
        patched.start()
        case.addCleanup(patched.stop)
    return Path(root.name)
