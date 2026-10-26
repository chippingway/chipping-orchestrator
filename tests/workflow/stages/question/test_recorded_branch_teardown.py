# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A closed question's teardown is tested against the branch its record names.

Driven through the question handler against a real clone: the live resolver
reads a pin outside the `orchestrator/` namespace as the derived name, so a
teardown handed its answer would delete the derived branch in place of the one
the record named. The teardown is handed the pin itself instead, refuses it,
and deletes neither.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.stages.question import handler
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.support.git import _run_git, _seed_target_root, _spec_for
from tests.workflow.fixtures import LABEL_QUESTION

_ISSUE_NUMBER = 7301

# Two names a record can pin that are not the issue's own: one outside the
# namespace, which the resolver reads as the derived name, and the flat name an
# earlier layout left.
_REFUSED_PINS = ("feature/manual", f"orchestrator/issue-{_ISSUE_NUMBER}")

_LIFECYCLE_LOGGER = "orchestrator.worktree_lifecycle"


def _local_branches(target: Path) -> list[str]:
    """Every branch the clone still carries."""
    listed = _run_git("for-each-ref", "--format=%(refname:short)", "refs/heads/", cwd=target)
    return listed.stdout.split()


class RecordedBranchTeardownTest(unittest.TestCase):
    """What a closed question's teardown deletes, by the branch its record names."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory(prefix="question-pin-")
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        target, base = _seed_target_root(root)
        self.target = target
        self.base = base
        self.spec = _spec_for(self.target)
        self.derived = _naming._branch_name(self.spec, _ISSUE_NUMBER)
        _run_git("branch", self.derived, self.base, cwd=self.target)
        for patcher in (
            patch.object(config, "WORKTREES_DIR", root / "worktrees"),
            patch.object(config, "_REPO_SPECS", [self.spec]),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def closed(self, **pinned) -> None:
        """Finalize this issue as a question closed by hand, with `pinned` recorded."""
        issue = make_issue(_ISSUE_NUMBER, label=LABEL_QUESTION)
        issue.closed = True
        gh = FakeGitHubClient([issue], repo_slug=self.spec.slug)
        gh.seed_state(issue.number, **pinned)
        handler._handle_question(gh, self.spec, issue)

    def test_a_refused_pin_keeps_both_branches(self) -> None:
        for pinned in _REFUSED_PINS:
            with self.subTest(pinned=pinned):
                _run_git("branch", "-f", pinned, self.base, cwd=self.target)

                with self.assertLogs(_LIFECYCLE_LOGGER, level="WARNING"):
                    self.closed(branch=pinned)

                self.assertIn(self.derived, _local_branches(self.target))
                self.assertIn(pinned, _local_branches(self.target))

    def test_an_unpinned_question_takes_its_branch(self) -> None:
        # Nothing pinned and no pull request recorded: the derived name is the
        # issue's own, and the teardown takes it as it always has.
        self.closed()

        self.assertNotIn(self.derived, _local_branches(self.target))


if __name__ == "__main__":
    unittest.main()
