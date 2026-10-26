# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the question and PR-terminal teardowns may take: the issue's own only.

A teardown is handed one repository and one issue rather than a listing, so it
asks for itself what the scheduled scan asks of every candidate: whether the
checkout at the issue's path is proven the issue's own -- at that path itself,
not through a symlink -- before the forced removal takes whatever it holds,
and whether another configured repository derives the same branch name or
checkout directory.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from itertools import product
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.worktrees import terminal
from tests.git.worktrees.lifecycle_test_support import ISSUE_NUMBER, _worktree_fixture
from tests.support.foreign_checkouts import LINKED_CHECKOUT, LINKED_PARENT, LOOSE_CONTENT, foreign_checkout

WARNING = "WARNING"
FOREIGN_CHECKOUT_ISSUE_NUMBER = 804

# A slug the sanitizer cannot tell from `acme/widget`: both become
# `acme__widget`, as a checkout directory and as a branch segment.
COLLIDING_SLUG = "acme__widget"


class _RemoteBranches:
    """Stand in for the GitHub side, recording every branch it was told to delete."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_remote_branch(self, branch: str) -> bool:
        self.deleted.append(branch)
        return True


def _question_teardown(gh, spec, issue_number, **options) -> None:
    """The question stage's teardown, which never touches the remote."""
    terminal._cleanup_question_worktree(spec, issue_number, **options)


def _terminal_teardown(gh, spec, issue_number, **options) -> None:
    """The PR-terminal teardown, remote branch included."""
    terminal._cleanup_terminal_branch(gh, spec, issue_number, **options)


_TEARDOWNS = (("question", _question_teardown), ("terminal", _terminal_teardown))


class CollidingRepositoryTest(unittest.TestCase):
    """A repository the sanitizer cannot tell from another owns nothing here.

    Two configured entries deriving one branch name and one checkout directory
    could each be the issue of this number, so neither teardown touches the
    tree or the ref.
    """

    def test_neither_teardown_touches_anything(self) -> None:
        for name, teardown in _TEARDOWNS:
            with self.subTest(teardown=name), _worktree_fixture() as fixture:
                gh = _RemoteBranches()
                fixture.plant_issue_worktree()
                colliding = replace(fixture.spec, slug=COLLIDING_SLUG)
                with (
                    patch.object(config, "_REPO_SPECS", [fixture.spec, colliding]),
                    self.assertLogs(terminal.log, level=WARNING),
                ):
                    teardown(gh, fixture.spec, ISSUE_NUMBER)
                self.assertEqual(fixture.git.calls, [])
                self.assertEqual(gh.deleted, [])


class ForeignCheckoutRealGitTest(unittest.TestCase):
    """A real tree at the issue's path, on a branch it does not own, survives.

    Each teardown is handed the flat branch the tree stands on as the record's,
    and keeps the tree, its uncommitted file, and the branch alike.
    """

    def test_neither_teardown_removes_it(self) -> None:
        for name, teardown in _TEARDOWNS:
            with self.subTest(teardown=name), foreign_checkout(FOREIGN_CHECKOUT_ISSUE_NUMBER) as foreign:
                gh = _RemoteBranches()

                with self.assertLogs(terminal.log, level=WARNING):
                    teardown(gh, foreign.spec, FOREIGN_CHECKOUT_ISSUE_NUMBER, branch=foreign.branch)

                self.assertEqual(foreign.loose.read_text(), LOOSE_CONTENT)
                self.assertTrue(foreign.branch_present())
                self.assertEqual(gh.deleted, [])


class SymlinkedCheckoutRealGitTest(unittest.TestCase):
    """A flat checkout the issue's path reaches through a symlink survives.

    The tree is a worktree of the clone on the issue's own current branch, so
    its identity alone would pass; what fails is the path, which resolves
    somewhere the layout does not put the issue's checkout. Through a symlink
    at the issue's path or a per-repository parent that is one, each teardown
    leaves the flat checkout, its uncommitted file, and the branch under it.
    """

    def test_neither_teardown_follows_it(self) -> None:
        for (name, teardown), link in product(_TEARDOWNS, (LINKED_CHECKOUT, LINKED_PARENT)):
            with self.subTest(teardown=name, link=link), foreign_checkout(FOREIGN_CHECKOUT_ISSUE_NUMBER, link) as flat:
                with self.assertLogs(terminal.log, level=WARNING):
                    teardown(_RemoteBranches(), flat.spec, FOREIGN_CHECKOUT_ISSUE_NUMBER)

                self.assertEqual(flat.loose.read_text(), LOOSE_CONTENT)
                self.assertTrue(flat.branch_present())


if __name__ == "__main__":
    unittest.main()
