# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One guarded split whose candidate was measured on an existing publication.

The `late_transaction_support` fixture beside this one is the split itself.
What this adds is the side of publication it was entered on: no plan PR was
ever opened, and what the verdict was taken over is the implementation pull
request the work is already on.

Seeded unheld, which is the narrower of the two shapes a transaction meets: a
publication that was open when the adjudication started wears this cycle's
hold, and one settled by then does not. `held_publication` is the other.

Two seedings rather than one, because the road is entered from two depths: a
case is either handed the guarded split the transaction runs on, or drives a
whole tick at the coordinator and lets the hold, the run, and the transaction
happen to it.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import late_hold_text as _late_hold_text
from tests.support.fakes import FakeGitHubClient, FakeIssue, FakePR
from tests.workflow.fixtures import _issue_branch
from tests.workflow.stages.decomposition.late_published_support import (
    published_generation,
    seed_published_pr,
)
from tests.workflow.stages.decomposition.late_test_support import (
    LATE_ISSUE_NUMBER,
    PUBLISHED_PR_NUMBER,
    generation_state,
    seed_late_issue,
)
from tests.workflow.stages.decomposition.late_transaction_support import (
    KEY_PR_NUMBER,
    LateSplitCase,
)

# The description an implementation pull request was opened with, and what
# the hold on it displaced.
PUBLISHED_BODY = "the change this publication was opened with"

KEY_BRANCH = "branch"

STATE_CLOSED = "closed"

STATE_OPEN = "open"

# A head somebody else pushed to the publication while the adjudication was
# open, so what the verdict was taken over is not what the branch carries now.
MOVED_PUBLISHED_HEAD = "cafef00d" * 5

# The branch a published issue's work is on: what the push that opened its
# pull request recorded, and what the reclamation behind the supersession
# resolves and takes down.
PUBLISHED_ISSUE_BRANCH = _issue_branch(LATE_ISSUE_NUMBER)


def seeded_published_split(
    **extra_state,
) -> tuple[FakeGitHubClient, FakeIssue, FakePR]:
    """A fresh client carrying the published road a whole tick drives.

    The same three facts `PublishedSplitCase` seeds, on a client of their own
    rather than on a case: what a coordinator-driven test needs is the issue
    and the publication as a tick would find them, and none of the transaction
    fixtures beside it.
    """
    github = FakeGitHubClient()
    issue = seed_late_issue(
        github,
        published_generation(),
        **{
            KEY_PR_NUMBER: PUBLISHED_PR_NUMBER,
            KEY_BRANCH: PUBLISHED_ISSUE_BRANCH,
            **extra_state,
        },
    )
    return github, issue, seed_published_pr(github)


class PublishedSplitCase(LateSplitCase):
    """A split whose candidate was measured on a pull request that exists.

    There is no plan PR here and there never was: the gate was entered past
    the first push, so what the verdict was taken over is the implementation
    pull request the work is already on. Seeded that way rather than reached
    through a gate, for the reason the held case is seeded: getting here
    through an adjudication would cost a recorded verdict, which is what stops
    the next tick spawning the run under test.

    The branch is on the pinned comment because a published issue's is: the
    push that opened that pull request recorded it, and it is what the
    reclamation behind the supersession resolves and takes down. Left off, the
    resolver would answer with the legacy ref while `pr_number` stands and
    with the namespaced one once the retirement clears it, so a case about the
    branch obligation would be reading two names for one branch.
    """

    def setUp(self) -> None:
        super().setUp()
        self.generation = published_generation()
        self.branch = PUBLISHED_ISSUE_BRANCH
        self.github.seed_state(
            self.issue.number,
            **{
                **generation_state(self.generation),
                KEY_PR_NUMBER: PUBLISHED_PR_NUMBER,
                KEY_BRANCH: self.branch,
            },
        )
        self.published_pr = seed_published_pr(self.github)

    def merged(self) -> None:
        """A human landing the very work a supersession says is replaced."""
        self.published_pr.merged = True
        self.published_pr.state = STATE_CLOSED

    def closed(self) -> None:
        """A human settling the change themselves, without landing it."""
        self.published_pr.state = STATE_CLOSED

    def pushed(self) -> None:
        """Somebody putting a commit on the branch behind the change."""
        self.published_pr.head.sha = MOVED_PUBLISHED_HEAD

    def reopened(self) -> None:
        """A human reopening the change a supersession has just closed."""
        self.published_pr.state = STATE_OPEN

    def held_publication(self) -> LateGeneration:
        """The same generation with this cycle's hold on its publication.

        What a tick that reached the transaction over an OPEN pull request is
        actually carrying: the hold goes on before the agent starts, on the
        pull request the entry names, and the description it displaced is
        preserved beside the identity and the head it was taken over.
        """
        held = replace(
            self.generation,
            plan_pr_number=PUBLISHED_PR_NUMBER,
            plan_pr_head=self.published_pr.head.sha,
            plan_pr_body=PUBLISHED_BODY,
        )
        self.published_pr.body = _late_hold_text._hold_body(held)
        return held
