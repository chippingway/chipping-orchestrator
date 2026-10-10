# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval squashed, documented, and put in review, then rebased: the ticks that refresh its report.

The squashed-round world (`squash_evidence_test_support`) walked on past its
approval. The reviewer approves the report settled about `HEAD`, the squash
publishes `SQUASHED` on the same tree and carries the approved run onto it,
the carry settles and the label moves, the docs pass changes nothing, and
`in_review` pings for merge. Then the base moves: the per-tick base refresh
rebases the squash and publishes `REBASED` through its exact-candidate push,
records the report debt that push leaves, and hands the issue back to
`validating`. A case may move the base a second time onto `ADVANCED`, lose the
push's answer, or interrupt the refresh's publication.

Every tick past the approval is a whole dispatch of whatever label the issue
carries -- its guards and reconciliations included -- over a checkout and a
branch standing where the pull request stands, and every base refresh goes
through the entry the tick takes, which logs and swallows what the refresh
raises. The refresh reads its lag and a fetched branch's head through git
commands no stage patch stands in for, so they are answered here
(`_BaseGit`): the lag the case names, and the branch standing wherever the
pull request stands. Each run a dispatch spawns past the walk into review is
recorded by role with the prompt it was handed (`spawned`).
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock

from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.workflow.engine import base_refresh as _base_refresh, issue_processing as _issue_processing
from tests.workflow import drift_reports as _drift_world, fix_reports as _fix_world
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA, _agent
from tests.workflow.git_owners import seam_patch
from tests.workflow.repo_values import _FAKE_WT, _TEST_SPEC
from tests.workflow.stages.validating import (
    evidence_round_test_support as _round,
    review_verdict_test_support as _world,
    squash_evidence_test_support as _squash,
)

HEAD = _world.HEAD

SQUASHED = _squash.SQUASHED

# The head the first rebase of the squash publishes, and the one a second base
# advance moves it to.
REBASED = MEASURED_CANDIDATE_SHA

ADVANCED = "f" * len(REBASED)

# What the developer writes about each rebased head.
REBASED_REPORT = "Rebased onto the moved base; the approved change reads as before and the suite passes."

ADVANCED_REPORT = "Rebased again onto the base that moved since; nothing else changed and the suite passes."

# The roles `spawned` records a run under.
REFRESHER = "refresher"

REVIEWER = "reviewer"

DOCUMENTER = "documenter"

# What a docs pass that changed nothing answers.
DOCS = (DOCUMENTER, _agent(last_message="DOCS: NO_CHANGE"))

# How many commits the branch counts behind a base that moved.
LAG = 2

# The notice the reviewer road parks an undeliverable report with.
UNDELIVERABLE_NOTICE = "cannot be delivered"


def refresh(text: str = REBASED_REPORT) -> tuple:
    """A report refresh's run, ending on a fresh report of the rebased head ready for publication."""
    return (REFRESHER, _agent(session_id=_world.DEV_SESSION, last_message=_drift_world.reported(text)))


def approval_on(head: str) -> tuple:
    """A reviewer approving the report it was handed, declaring a passing run of the suite on `head`."""
    return (REVIEWER, _round.reviewer(
        "LGTM\n\n"
        f"VERIFICATION: RUN {head}\n"
        f"COMMAND: {_world.SUITE}\n"
        "EXIT: 0\n"
        f"{_world.SUITE_OUTPUT}\n"
        "VERIFICATION: END\n\n"
        "VERDICT: APPROVED",
    ))


def uninterrupted(_case):
    """No window opened at all: the tick runs through."""
    return contextlib.nullcontext()


class LandsThenDies:
    """A push that lands and leaves the pull request on the commit it sent, then loses the process."""

    def __init__(self, pull_request) -> None:
        self._pull_request = pull_request

    def __call__(self, spec, worktree, branch, *, force_with_lease=None, revision=None):
        if revision:
            self._pull_request.head.sha = revision
        raise RuntimeError("the process died before the push was answered")


class _BaseGit:
    """The git commands a base refresh reads through: the lag behind the base, and a fetched branch's head."""

    def __init__(self, pull_request, lag: int) -> None:
        self._pull_request = pull_request
        self._lag = lag

    def __call__(self, *command, **_options):
        answers = {"rev-list": self._lag, "rev-parse": self._pull_request.head.sha}
        answer = answers.get(command[0], "")
        return MagicMock(returncode=0, stdout=f"{answer}\n", stderr="")


class _Staged:
    """One run a dispatch spawns, recorded on the case by role with the prompt it was handed."""

    def __init__(self, case, role: str, answer) -> None:
        self._case = case
        self._role = role
        self._answer = answer

    def __call__(self, _backend, prompt, *_called, **_options):
        self._case.spawns.append((self._role, prompt))
        return self._answer


class _SquashRebaseJourney(_squash.SquashedRoundWorld):
    """The squashed round walked into review and on through the base refreshes that rebase it."""

    def setUp(self) -> None:
        super().setUp()
        self.spawns: list[tuple[str, str]] = []

    def walks_into_review(self) -> None:
        """Approve, squash, settle the carry, pass the docs unchanged, and ping for merge.

        Nothing spawned on the way is kept, and what the issue has spent by
        then is `charged`, so a case reads its runs and charges from here on.
        """
        self.approves()
        self.later()
        self.dispatched(DOCS)
        self.dispatched()
        self.spawns.clear()
        self.charged = self.spent()

    def dispatched(self, *staged: tuple, **run_options) -> dict:
        """One whole dispatch of the issue's label, whose runs answer `staged` -- role and result -- in order."""
        head = self.pull_request.head.sha
        run_options.setdefault("head_shas", (head,))
        run_options.setdefault("fetched_branch_tip", head)
        runs = _fix_world._Runs(*(_Staged(self, *run) for run in staged))
        return self._run(
            lambda: _issue_processing._route_issue_to_handler(
                self.github, _TEST_SPEC, self.issue, self.github.workflow_label(self.issue),
            ),
            run_agent=MagicMock(side_effect=runs),
            **run_options,
        )

    def base_refresh(self, onto: str | None = None, *, push=None, **run_options) -> None:
        """One per-tick base refresh, the base moved under the pull request's head by a rebase onto `onto`.

        With no `onto` the base has not moved, which is the tick a crash
        recovery finishes an attempt on. The push lands unless `push` stands
        in for it. `run_options` are the run's own readings beside those --
        `checkout_tree=None` leaves every tree to the reading a case installed.
        """
        head = self.pull_request.head.sha
        git = _BaseGit(self.pull_request, LAG if onto else 0)
        with (
            seam_patch("_rebase_base_into_worktree", MagicMock(return_value=(True, []))),
            seam_patch("_git", git),
            seam_patch("_git_hardened", git),
        ):
            self._run(
                lambda: _base_refresh._sync_discovered_worktree(
                    self.github, _TEST_SPEC, _FAKE_WT, _world.ISSUE, None,
                ),
                run_agent=[],
                head_shas=(head, onto or head),
                fetched_branch_tip=head,
                candidate_commit=FrozenCommit(sha=onto or head),
                push_branch=push or _drift_world._LandingPush(self.pull_request),
                **run_options,
            )

    def approved_into_review(self, head: str) -> None:
        """Dispatch until another reviewer, approving on `head`, is spawned, then the docs pass and the ping behind it.

        Two dispatches at most for the reviewer: a tick may be spent ahead of
        it retiring the squash's carry, which no longer answers once another
        report is owed or settled -- a tick of its own, by design, that
        spawns nothing.
        """
        reviewed = len(self.spawned(REVIEWER))
        for _ in range(2):
            if len(self.spawned(REVIEWER)) == reviewed:
                self.dispatched(approval_on(head))
        self.dispatched(DOCS)
        self.dispatched()

    def roles(self) -> tuple:
        """The role of every run recorded, in order."""
        return tuple(role for role, _ in self.spawns)

    def spawned(self, role: str) -> list[str]:
        """The prompt every run recorded under `role` was handed, in order."""
        return [prompt for spawned_as, prompt in self.spawns if spawned_as == role]
