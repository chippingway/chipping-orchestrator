# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval whose push never happened, read by the dispatcher over a record no live work may use.

The reconciliation ahead of every stage pays such a debt, or parks for the
checkout it would be paid from, and either acts on the issue's branch. So a
record naming no branch live work may use -- a pull request recorded with no
branch beside it, or a pinned flat name -- holds the tick with the record and
the thread as they were, the checkout missing or not. An issue a human closed
goes on to its stage terminal all the same, which keeps the branch the record
pins.
"""
from __future__ import annotations

import tempfile
import unittest
from itertools import product
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import dispatch_guards
from tests.support.fakes import FakeGitHubClient, FakePR, make_issue
from tests.workflow.fixtures import SHA_LENGTH

ISSUE = 7
PR_NUMBER = 42
_VALIDATING = "workflow:validating"
_FLAT_BRANCH = f"orchestrator/issue-{ISSUE}"

# An approval granted on a reading, the head it was leased against, and the
# pull request it owes the push onto.
_OWED = MappingProxyType({
    "pr_number": PR_NUMBER,
    "late_approved_sha": "a" * SHA_LENGTH,
    "late_approved_lease": "b" * SHA_LENGTH,
    "late_approved_basis": "reading",
})

# What the record pins beside it, each naming no branch live work may use,
# on an issue still open and on one a human closed.
_CASES = tuple(product(
    (("a branchless pull request", {}), ("a flat pin", {"branch": _FLAT_BRANCH})),
    (False, True),
))


class OwedPushRefusalTest(unittest.TestCase):
    """The dispatcher's reconciliation of an owed push, with no checkout on this host."""

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="orch-owed-push-")))
        self.enterContext(patch.object(config, "WORKTREES_DIR", root / "worktrees"))
        self.spec = config.RepoSpec("acme/widget", root / "clone", "main")

    def test_only_ended_work_gets_past(self) -> None:
        for (name, pinned), closed in _CASES:
            with self.subTest(name, closed=closed):
                self.assertEqual(self._ticks(pinned, closed=closed), (not closed, True))

    def _ticks(self, pinned: dict, *, closed: bool) -> tuple[bool, bool]:
        """One dispatcher reading of the issue owing the push: whether it held, and whether record and thread stand."""
        github = FakeGitHubClient()
        issue = make_issue(ISSUE, label=_VALIDATING)
        issue.closed = closed
        github.add_issue(issue)
        github.add_pr(FakePR(number=PR_NUMBER, head_branch=_FLAT_BRANCH))
        github.seed_state(ISSUE, **_OWED, **pinned)
        before = github.pinned_data(ISSUE)
        held = dispatch_guards._record_stops_the_tick(
            github, self.spec, issue, _VALIDATING, github.read_pinned_state(issue),
        )
        return held, (github.pinned_data(ISSUE), github.posted_comments) == (before, [])


if __name__ == "__main__":
    unittest.main()
