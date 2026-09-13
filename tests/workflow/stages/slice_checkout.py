# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real repository carrying one slice's implementation, tests and docs.

The world a cumulative reading has to be taken against. What a candidate adds
over its base is a question about BYTES -- which paths git finds lines in, how
many it pairs up, and what a three-dot range between two ids covers -- and
every double that stands in for the count answers whatever a case seeded
rather than what the objects say.

So this builds the commits instead: a base, then a slice landed the way a
developer really lands one, over several commits and across paths of every
kind. Beside the arithmetic that says what any subset of them comes to, so a
case can name the reading a narrower gate would have taken and show it is not
the one the ceiling is applied to.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from types import MappingProxyType

_BASE_BRANCH = "main"

# What the repository carries before the slice starts, so the base is a commit
# with content in it rather than an empty tree.
_BASE_FILE = "README.md"

_BASE_TEXT = "the repository as this slice found it\n"

IMPLEMENTATION_PATHS = (
    "orchestrator/widget/slice.py",
    "orchestrator/widget/wiring.py",
)

TEST_PATHS = ("tests/widget/test_slice.py",)

DOCUMENTATION_PATHS = ("docs/widget/slice.md",)

# One slice as a developer really lands it: three commits, each adding to more
# than one kind of path, and two of the paths grown by a later commit than the
# one that created them. Neither a single commit nor a single family of paths
# is the whole of it, which is what lets a case name a narrower reading and
# show the gate does not take it.
SLICE_COMMITS = (
    MappingProxyType({IMPLEMENTATION_PATHS[0]: 26}),
    MappingProxyType({IMPLEMENTATION_PATHS[1]: 9, TEST_PATHS[0]: 31}),
    MappingProxyType({TEST_PATHS[0]: 6, DOCUMENTATION_PATHS[0]: 18}),
)

# Who every commit this fixture writes is authored by, stated on the command
# line rather than configured or left to the environment: a repository created
# in a temporary directory inherits no identity, and a commit without one fails
# outright on a host whose ambient environment supplies none either.
_IDENTITY = ("-c", "user.name=Dev", "-c", "user.email=dev@example.com")


def _added_over(commits, paths) -> int:
    """The lines the named commits add to the named paths."""
    return sum(
        lines
        for written in commits
        for path, lines in written.items()
        if path in paths
    )


_EVERY_PATH = (*IMPLEMENTATION_PATHS, *TEST_PATHS, *DOCUMENTATION_PATHS)

# What the whole slice adds, and the three narrower readings of it a gate
# could be tempted to take instead: the last commit on its own, the paths that
# carry the implementation, and everything that is not documentation. Each is
# derived from the same written record the commits are, so a case naming one
# is naming an actual subset of this candidate rather than a second literal
# that could drift from it.
WHOLE_SLICE = _added_over(SLICE_COMMITS, _EVERY_PATH)

LATEST_COMMIT_ONLY = _added_over(SLICE_COMMITS[-1:], _EVERY_PATH)

IMPLEMENTATION_ONLY = _added_over(SLICE_COMMITS, IMPLEMENTATION_PATHS)

WITHOUT_DOCUMENTATION = _added_over(
    SLICE_COMMITS, (*IMPLEMENTATION_PATHS, *TEST_PATHS),
)

# The largest reading a gate that measured anything less than the whole
# candidate could come back with, which is the ceiling every one of them would
# have published under.
LARGEST_NARROWER_READING = max(
    LATEST_COMMIT_ONLY, IMPLEMENTATION_ONLY, WITHOUT_DOCUMENTATION,
)


def _git(*args: str, cwd: Path) -> str:
    """Run one git command in `cwd`, failing the test if git does."""
    return subprocess.run(
        ["git", *_IDENTITY, *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


class SliceCheckout:
    """A real repository whose branch carries one child slice's commits.

    Local and remoteless on purpose: the count is taken between two commit ids
    in one worktree, so a bare remote and a transport pointed at it would be
    scaffolding no reading here consults.
    """

    def __init__(self) -> None:
        self._root = tempfile.TemporaryDirectory(prefix="orch-late-child-")
        self.worktree = Path(self._root.name) / "checkout"
        self.base = ""
        self.commits: tuple[str, ...] = ()

    def prepare(self, test_case) -> None:
        """Raise the base commit and the slice over it, and hand over teardown."""
        test_case.addCleanup(self._root.cleanup)
        self.worktree.mkdir(parents=True)
        _git("init", "--quiet", "-b", _BASE_BRANCH, cwd=self.worktree)
        (self.worktree / _BASE_FILE).write_text(_BASE_TEXT)
        self.base = self._commit("the base this slice was cut from")
        self.commits = tuple(
            self._write(written) for written in SLICE_COMMITS
        )

    @property
    def candidate(self) -> str:
        """The commit the slice is finished at."""
        return self.commits[-1]

    def commit_on_top(self, lines: int) -> str:
        """Add one more commit past the candidate, and return it.

        What a developer resumed on a human's guidance leaves behind: work
        nobody adjudicated and nobody authorized, standing on top of a commit
        somebody may have done both for.
        """
        return self._write({IMPLEMENTATION_PATHS[0]: lines})

    def _write(self, written) -> str:
        """Append the named lines to each path, and commit the lot."""
        for path, lines in written.items():
            target = self.worktree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a") as opened:
                opened.writelines(
                    # Distinct lines, so the algorithm that pairs a change
                    # with repeated lines has nothing to pair: what the count
                    # reports is then exactly what was written.
                    f"{path} line {numbered}\n"
                    for numbered in range(lines)
                )
        named = " ".join(written)
        return self._commit(f"write {named}")

    def _commit(self, message: str) -> str:
        _git("add", "-A", cwd=self.worktree)
        _git("commit", "--quiet", "-m", message, cwd=self.worktree)
        return _git("rev-parse", "HEAD", cwd=self.worktree).strip()
