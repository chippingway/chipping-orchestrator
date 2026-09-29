# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a rebase leaves its pull request owing, seeded and read back.

The base-sync cases stand on issue #7 and PR #42 of the shared refresh
fixture. What they vary is which head the settled report is about and which
debt already stands, and what they read back is the debt on the pinned comment
-- as a literal, since it is a compatibility contract -- and whether it is the
one the validating refresh asks the developer about.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_rewrite_debt as _rewrite_debt
from tests.git.base_sync.refresh_scenarios import PUSH_PATCH
from tests.git.base_sync.refresh_test_support import ISSUE, PR_BRANCH, PR_NUMBER
from tests.workflow.published_reports import publishes_the_report

KEY_REWRITE_DEBT = "developer_report_rewrite_debt"

# A head an earlier rebase replaced, which the settled report is still about.
EARLIER_SHA = "ea41e700" * 5

# A head somebody else put on the pull request, which no rebase here made.
FOREIGN_SHA = "f0e1a900" * 5


def owed(previous: str, rewritten: str, *, pr: int = PR_NUMBER) -> dict:
    """The pinned debt a rebase of PR #42's branch from `previous` onto `rewritten` leaves.

    `pr` names another pull request, for a claim this issue's does not follow.
    """
    return {
        "pr": pr,
        "branch": PR_BRANCH,
        "previous_head": previous,
        "rewritten_head": rewritten,
    }


def stands_on(github, head: str) -> str:
    """Move PR #42 onto `head`, as a push that landed does; the head it left."""
    pull = github.pulls[PR_NUMBER]
    left = pull.head.sha
    pull.head = replace(pull.head, sha=head)
    return left


def settles_a_report_of(github, head: str) -> None:
    """Leave a published report of `head` settled on PR #42, as its delivery would.

    Written while the pull request stands on `head`, since a delivery reports
    the head it publishes, and the pull request is put back where the case had
    it.
    """
    left = stands_on(github, head)
    publishes_the_report(github, github._issues[ISSUE])
    stands_on(github, left)


def refreshes(durable: dict, head: str) -> bool:
    """Whether the validating refresh asks the developer for a report of `head`.

    Asked of the durable record the way the report hold asks it: the claim has
    to read, and the settled report has to be of one of the heads it names.
    """
    debt = _rewrite_debt.RewriteDebt.read(durable.get(KEY_REWRITE_DEBT))
    if debt is None:
        return False
    return debt.owes_a_refresh(PinnedState(data=dict(durable)), head)


class DurableAtTheRelabel:
    """A relabel that remembers what the pinned comment durably said when it came.

    What the finish has made durable by then is what a process lost in the
    relabel comes back to, so it is the record the route is held to.
    """

    def __init__(self, github) -> None:
        self._github = github
        self._relabel = github.set_workflow_label
        self.seen: list[dict] = []

    def __call__(self, issue, label) -> None:
        """Read the durable record, then apply the label."""
        self.seen.append(self._github.pinned_data(issue.number))
        self._relabel(issue, label)


class PushedOverFirst:
    """A remote somebody else pushes `FOREIGN_SHA` to just before this tick's push reaches it.

    The tick's push is leased against the head it read, so the remote refuses
    it as a real one would, and the foreign head is what PR #42 carries.
    """

    def __init__(self, github) -> None:
        self._github = github

    def __call__(self, *_args, force_with_lease: str | None = None, **_options) -> bool:
        """Land the foreign push, then answer this one against the head the remote carries."""
        stands_on(self._github, FOREIGN_SHA)
        return force_with_lease == FOREIGN_SHA


def pushed_over(github, scenario, *, at_the_push: bool):
    """`scenario` over a PR #42 somebody else pushes onto `FOREIGN_SHA`.

    Before the refresh reads it, or as this tick's push goes out.
    """
    if at_the_push:
        scenario[PUSH_PATCH].side_effect = PushedOverFirst(github)
    else:
        stands_on(github, FOREIGN_SHA)
    return scenario
