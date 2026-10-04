# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A poller that fetched the repository before it was renamed, beside one after.

Each poller names a repository as GitHub answered when it fetched it, so two
started on either side of a rename name it two ways for as long as both run.
The one started before is a real second process here, running its own
dispatch seam over a client GitHub described under the old name, and claiming
in the namespace `tests/support/writer_claim_processes.py` shares with this
test. Nothing it holds is known to this interpreter except through the lock.
"""
from __future__ import annotations

import contextlib

from tests.support.writer_claim_processes import HELD, SharedNamespaceCase
from tests.workflow.engine.writer_claim_test_support import HeldIssuesCase

# The name another poller fetched the same repository under, before it was
# renamed to the one this process's client answers: a claim keyed on either
# name would meet no holder under the other.
PRE_RENAME_SLUG = "acme/widget-before-rename"

# Another poller's own dispatch seam, over a client whose repository GitHub
# described with the id and name it is handed. It takes the writer claim of
# every issue it is handed, says whether it got them all, and holds them until
# told to let go.
_POLLER = """
import contextlib
import sys
from pathlib import Path

from github import Github
from github.Repository import Repository

from orchestrator.config.models import RepoSpec
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import issue_processing

repo_id, name, numbers = int(sys.argv[1]), sys.argv[2], [int(arg) for arg in sys.argv[3:]]
described = {"id": repo_id, "full_name": name, "url": "https://api.github.com/repos/" + name}
gh = GitHubClient.__new__(GitHubClient)
gh._repo_slug = name
gh.repo = Repository(Github().requester, {}, described, completed=True)
spec = RepoSpec(slug=name, target_root=Path.cwd(), base_branch="main")
with contextlib.ExitStack() as claims:
    held = [claims.enter_context(issue_processing._writer_claim(gh, spec, number)) for number in numbers]
    print("held" if all(held) else "refused", flush=True)
    sys.stdin.readline()
"""


class RenamedRepositoryCase(SharedNamespaceCase, HeldIssuesCase):
    """The held-issue ticks, with the issues held by the poller started before the rename."""

    @contextlib.contextmanager
    def held_before_the_rename(self, *issue_numbers: int):
        """Hold these issues for the block, from the poller started before the rename."""
        poller = self.run_elsewhere(_POLLER, self.github.repo_id, PRE_RENAME_SLUG, *issue_numbers)
        self.assertEqual(poller.said(), HELD, "the poller started before the rename holds them")
        yield
        self.assertEqual(poller.let_go(), 0)
