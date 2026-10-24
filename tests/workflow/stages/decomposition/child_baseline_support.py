# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the drift-baseline cases plant on a split's children, and what they read back.

A child's recorded baseline is held to the drift check's own reading of the
thread, computed through the same entry point that check calls, and the check
itself answers whether what landed since is drift. The rest reach into the
windows a baseline is decided in: the child as its create answered it,
something landing on a child once its claim is granted, and a seed write -- or
a recovery's read of the child's record -- that never comes back.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from orchestrator.workflow.engine import content_hash as _content_hash, drift as _drift
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeIssue, FakeUser

# What a child's drift baseline is recorded under.
KEY_BASELINE = "user_content_hash"


def reading(issue: FakeIssue) -> str:
    """What the drift check reads off a thread as it stands -- the baseline of a child nobody has edited since."""
    return _content_hash._compute_user_content_hash(issue, set())


def drifted(gh: FakeGitHubClient, number: int) -> bool:
    """Whether the child's own drift check reads its thread as changed since the baseline its record carries.

    Asked only of a record carrying one, which the check compares against
    and writes nothing over.
    """
    child = gh.get_issue(number)
    return _drift._detect_user_content_change(gh, child, gh.read_pinned_state(child)) is not None


class ReadAtCreation:
    """A child create that notes what the drift check reads off each child the moment the create returns.

    `pinned` is a record another writer reached the child with first, pinned
    on it raw before anything of the split's own reads it.
    """

    def __init__(self, gh: FakeGitHubClient, pinned: Mapping[str, object] | None = None) -> None:
        self._gh = gh
        self._create = gh.create_child_issue
        self._pinned = pinned
        self.readings: list[str] = []

    def __call__(self, **fields):
        """Create the child, read it as created, and pin what that other writer left."""
        child = self._create(**fields)
        self.readings.append(reading(child))
        if self._pinned is not None:
            self._gh.seed_state(child.number, raw=True, **self._pinned)
        return child


class LandedOnce:
    """Something landing once on each issue it is handed but `spared`, the first time it is handed one."""

    def __init__(self, gh: FakeGitHubClient, land, spared: int) -> None:
        self._gh = gh
        self._land = land
        self._spared = spared
        self._landed: set[int] = set()

    def __call__(self, number: int) -> None:
        """Land it on an issue not landed on yet."""
        if number != self._spared and number not in self._landed:
            self._landed.add(number)
            self._land(self._gh, self._gh.get_issue(number))


@dataclass(frozen=True)
class Commented:
    """A comment landing on an issue: its author's login, the kind of account behind it, and its words."""

    login: str
    kind: str = "User"
    body: str = "Also cover the docs."

    def __call__(self, gh: FakeGitHubClient, issue: FakeIssue) -> None:
        """Post it on the issue's thread, numbered as the thread numbers its next reply."""
        author = FakeUser(self.login, self.kind)
        number = gh.next_reply_id(issue)
        issue.comments.append(FakeComment(id=number, body=self.body, user=author))


class LostSeed:
    """A child's seed write that never comes back, once: dying before it lands, or landing with its answer lost.

    Every write to `parent` lands as asked, which is what records the child
    on the register before its seed.
    """

    def __init__(self, gh: FakeGitHubClient, parent: int, *, lands: bool) -> None:
        self._write = gh.write_pinned_state
        self._parent = parent
        self._lands = lands
        self._lost = False

    def __call__(self, issue, state):
        """Write the parent, or lose the first child write the way this one is lost."""
        if issue.number == self._parent or self._lost:
            return self._write(issue, state)
        self._lost = True
        if not self._lands:
            raise KeyboardInterrupt("seed")
        self._write(issue, state)
        raise RuntimeError("the seed's answer was lost")


class UnreadableRecord:
    """A pinned read GitHub does not answer for one issue, and answers for every other."""

    def __init__(self, gh: FakeGitHubClient, number: int) -> None:
        self._read = gh.read_pinned_state
        self._number = number

    def __call__(self, issue):
        """Read the record, unless it is that issue's."""
        if issue.number == self._number:
            raise RuntimeError("github did not answer the read")
        return self._read(issue)
