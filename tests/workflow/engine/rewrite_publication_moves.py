# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What can move under issue #7's clean rebase between the gate's measurement and its push.

Each is a function of the case, run at one of the moments
`rewrite_publication_test_support` races: work landing on the checkout, the
base ref repointed or made uncountable, the pull request moved -- somebody's push to its branch,
or GitHub catching up with the remote -- a remote that stops answering, and
the publication ending: a close a poll latched, or the pull request merged or
closed.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.workflow.engine import observations as _observations
from tests.git.base_sync import refresh_test_support as base
from tests.workflow.engine.rewrite_publication_test_support import FOREIGN, REPLAY, REWOUND_BASE
from tests.workflow.observation_support import read_now


def lands_on_the_checkout(case) -> None:
    """Work landing on top of the replay, where the checkout proves to it."""
    case.world.head = base.MOVED_CHECKOUT_SHA


class BaseOn:
    """The base ref moved to `tip`, None for one whose count against the replay nobody can take."""

    def __init__(self, tip: str | None) -> None:
        self._tip = tip

    def __call__(self, case) -> None:
        case.world.base_tip = self._tip


# The base ref repointed off the tip the replay was read over, and one that can
# no longer be counted against it.
REWOUND = BaseOn(REWOUND_BASE)
BASE_UNREADABLE = BaseOn(None)


class PullRequestOn:
    """PR #42 moved onto `head`: somebody's push to its branch, or GitHub catching up with the remote."""

    def __init__(self, head: str) -> None:
        self._head = head

    def __call__(self, case) -> None:
        pull = case.gh.pulls[base.PR_NUMBER]
        pull.head = replace(pull.head, sha=self._head)


# Somebody else's push to PR #42's branch, and GitHub catching up with a
# remote that already carried the replay.
PUSHED_OVER = PullRequestOn(FOREIGN)
CAUGHT_UP = PullRequestOn(REPLAY)


def silences_the_remote(case) -> None:
    """A remote that stops answering the branch reading."""
    case.world.answers = False


def latches_a_close(case) -> None:
    """A poll on another worker reading issue #7 closed."""
    _observations.observe_close(case.spec.slug, base.ISSUE, read_now())


def merges_the_pull_request(case) -> None:
    """PR #42 merged by a human."""
    case.gh.pulls[base.PR_NUMBER].merged = True
    closes_the_pull_request(case)


def closes_the_pull_request(case) -> None:
    """PR #42 closed."""
    case.gh.pulls[base.PR_NUMBER].state = "closed"
