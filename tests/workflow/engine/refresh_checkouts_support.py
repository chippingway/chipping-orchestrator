# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Several issue checkouts under one worktrees root, as a refresh walks them.

Each checkout stands behind base on the head its pull request carries until a
rebase carries it over, and stands on the rebased head from then on, so a
second refresh over the same root reads what the first one left. Everything
the refresh decides is real; what is stood in for is the git it reads and
writes the checkouts with, and the size gate's reads before a push.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

from tests.git.base_sync import refresh_test_support as support
from tests.git.base_sync.gate_reads_support import _gate_reads
from tests.git.base_sync.sync_test_support import _git_result, _patch_base_sync
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue

# The head every pull request stands on before its rebase, and the one the
# rebase leaves each checkout on -- which the size gate proves it to.
BEFORE_SHA = support.BEFORE_SHA
AFTER_SHA = support.AFTER_SHA

# One clean rebase published, as the commit pushed and the head it was leased
# against: the rebased head, over the one the pull request stood on.
ONE_PUBLICATION = ((AFTER_SHA, BEFORE_SHA),)

LABEL_IN_REVIEW = support.LABEL_IN_REVIEW
LABEL_VALIDATING = support.LABEL_VALIDATING
KEY_REVIEW_ROUND = support.KEY_REVIEW_ROUND

# The review round each pull request is seeded on, which a published rebase resets.
ROUND_BEFORE = 3

# How far behind base a checkout stands before a rebase carries it over, and after.
_BEHIND = "2\n"
_LEVEL = "0\n"

_ISSUE_PREFIX = "issue-"

_PR_OFFSET = 100

# One push, as the commit published and the head it was leased against.
_Push = tuple[str, str]


def pr_of(number: int) -> int:
    """The pull request issue `number` is seeded with."""
    return _PR_OFFSET + number


def seed_open_pr(github: FakeGitHubClient, number: int) -> None:
    """Issue `number` in review, with an open pull request on the head its checkout stands on."""
    branch = f"orchestrator/acme__widget/issue-{number}"
    head = FakePRRef(sha=BEFORE_SHA)
    github.add_issue(make_issue(number, label=LABEL_IN_REVIEW))
    github.seed_state(number, pr_number=pr_of(number), branch=branch, review_round=ROUND_BEFORE)
    github.add_pr(FakePR(number=pr_of(number), head_branch=branch, head=head))


class Checkouts:
    """The checkouts a refresh walks, and the git it walks them with.

    `failing` names the issues whose rebase raises rather than returns.
    """

    def __init__(self, case, *numbers: int) -> None:
        self._root = Path(case.enterContext(tempfile.TemporaryDirectory(prefix="orch-refresh-checkouts-")))
        self.numbers = numbers
        for number in numbers:
            self.path(number).mkdir()
        self.carried: set[int] = set()
        self.failing: set[int] = set()
        self.fetch = MagicMock(return_value=_git_result())
        self.rebase = MagicMock(side_effect=self._rebases)
        self.push = MagicMock(return_value=True)
        _gate_reads(case)

    def path(self, number: int) -> Path:
        """Issue `number`'s checkout."""
        return self._root / f"{_ISSUE_PREFIX}{number}"

    def walked(self):
        """The refresh's git for one pass over these checkouts."""
        return _patch_base_sync(
            target_fetch=self.fetch,
            worktrees_root=MagicMock(return_value=self._root),
            dirty=MagicMock(return_value=[]),
            git=self._lag,
            head_sha=self._head,
            rebase=self.rebase,
            push=self.push,
            hardened=MagicMock(return_value=_git_result()),
        )

    def published(self) -> dict[int, tuple[_Push, ...]]:
        """Each issue's pushes, in the order they went out."""
        pushes: dict[int, tuple[_Push, ...]] = {}
        for recorded in self.push.call_args_list:
            number = _issue_of(recorded.args[1])
            push = (recorded.kwargs.get("revision"), recorded.kwargs.get("force_with_lease"))
            pushes[number] = (*pushes.get(number, ()), push)
        return pushes

    def _rebases(self, _spec, worktree):
        number = _issue_of(worktree)
        if number in self.failing:
            raise RuntimeError(f"the rebase in issue #{number}'s checkout crashed")
        self.carried.add(number)
        return True, []

    def _lag(self, *_args, cwd=None, **_kwargs):
        if _issue_of(cwd) in self.carried:
            return _git_result(stdout=_LEVEL)
        return _git_result(stdout=_BEHIND)

    def _head(self, worktree) -> str:
        return AFTER_SHA if _issue_of(worktree) in self.carried else BEFORE_SHA


@dataclass(frozen=True)
class Walked:
    """What the refreshes so far left on the checkouts and on GitHub.

    `rebased` is the issues a rebase ran in, in walk order; `published`, each
    issue's pushes; `relabelled`, every label write; `noticed`, the pull
    requests a notice went out on; `announced`, each issue's `base_rebased`
    heads; `rounds`, the review round each issue's pinned comment holds now.
    """

    rebased: list = field(default_factory=list)
    published: dict = field(default_factory=dict)
    relabelled: list = field(default_factory=list)
    noticed: list = field(default_factory=list)
    announced: dict = field(default_factory=dict)
    rounds: dict = field(default_factory=dict)


def observed(github: FakeGitHubClient, checkouts: Checkouts) -> Walked:
    """Read what the refreshes so far left, as `Walked` spells it."""
    return Walked(
        rebased=[_issue_of(recorded.args[1]) for recorded in checkouts.rebase.call_args_list],
        published=checkouts.published(),
        relabelled=list(github.label_history),
        noticed=[number for number, _body in github.posted_pr_comments],
        announced=_announced(github),
        rounds={number: github.pinned_data(number).get(KEY_REVIEW_ROUND) for number in checkouts.numbers},
    )


def _announced(github: FakeGitHubClient) -> dict[int, list[str]]:
    events: dict[int, list[str]] = {}
    for event in github.recorded_events:
        if event.get(support.EVENT_FIELD) == support.EVENT_BASE_REBASED:
            heads = events.setdefault(event["issue"], [])
            heads.append(event.get(support.SHA_FIELD))
    return events


def _issue_of(worktree) -> int | None:
    name = Path(worktree or "").name
    if not name.startswith(_ISSUE_PREFIX):
        return None
    return int(name.removeprefix(_ISSUE_PREFIX))
