# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real checkout a squash was interrupted inside, the approved issue it belongs to, and the real tick over them.

The repository is real and the checkout is a genuine worktree at the path the
stage derives, and the tick is the real handler over it. Only the two hops
that leave this host are stood in for -- the agent spawn and the authenticated
push -- so what a case asserts about the checkout is what the tick really left
there.

Every squash is begun under an approval recorded beside it, so the issue
carries the one a squash leaves: of the report the pull request carries, on
the head the collapse was planned over, resting on passing evidence settled
on that pull request (`verified_approvals.verifies_the_approval`).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator.agents import runner as _agent_runner
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.workflow.engine import issue_processing as _issue_processing
from orchestrator.workflow.late_split import collapses as _collapses
from orchestrator.workflow.stages.validating import handler as _validating
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow import verified_approvals as _verified
from tests.workflow.stages.validating.squash_tick_git_support import (
    APPROVED_COMMITS,
    ISSUE_NUMBER,
    PR_NUMBER,
    ApprovedCheckoutMixin,
)

LABEL_VALIDATING = "workflow:validating"

PARK_EVENT = "park_awaiting_human"


class HalfMadeCollapseWorld(ApprovedCheckoutMixin):
    """A checkout a squash was interrupted inside, the issue it belongs to, and the real tick over them."""

    def setUp(self) -> None:
        self.repo = self.build_checkout()
        self.github = self._seeded_client()
        self.issue = self.github.get_issue(ISSUE_NUMBER)
        _verified.verifies_the_approval(self.github, self.issue)
        self._crashes_between_the_reset_and_the_commit()

    def _parks_reported(self) -> int:
        """How many parks awaiting a human the ticks reported."""
        return sum(event["event"] == PARK_EVENT for event in self.github.recorded_events)

    def _staged_over_the_base(self) -> tuple[bool, int]:
        """Whether the checkout still stands on the base, and how many paths its index stages over it."""
        rewound = self.repo.head() == self.repo.base
        return rewound, len(self.repo.staged())

    def _runs_the_tick(self):
        """One real validating tick, with only the two remote hops stood in."""
        agent = MagicMock()
        push = MagicMock(return_value=True)
        with patch.object(
            _agent_runner, "run_agent", agent,
        ), patch.object(
            _branch_transport, "_push_branch", push,
        ):
            _validating._handle_validating(
                self.github, self.repo.spec, self.issue,
            )
        return agent, push

    def _dispatches(self) -> MagicMock:
        """One real dispatch of the issue -- every guard ahead of the handler, then the handler; the push.

        Only the agent spawn and the push are stood in, as on the tick.
        """
        push = MagicMock(return_value=True)
        with patch.object(_agent_runner, "run_agent", MagicMock()), patch.object(
            _branch_transport, "_push_branch", push,
        ):
            _issue_processing._process_issue(self.github, self.repo.spec, self.issue)
        return push

    def _crashes_between_the_reset_and_the_commit(self) -> None:
        """Rewind the branch with the collapse staged, and record the terms.

        The record goes down BEFORE the reset in production, so this is the
        world a process dying in that window leaves behind: the terms on the
        comment, HEAD on the base, and every collapsed change in the index.
        """
        self.repo.rewinds_onto_the_base()
        state = self.github.read_pinned_state(self.issue)
        _collapses.record_pending_collapse(
            state,
            head=self.repo.accepted,
            base_sha=self.repo.base,
            count=len(APPROVED_COMMITS),
        )
        self.github.write_pinned_state(self.issue, state)

    def _seeded_client(self) -> FakeGitHubClient:
        """The issue this branch belongs to, mid-review, with its PR open on the approved head."""
        github = FakeGitHubClient()
        github.add_issue(make_issue(ISSUE_NUMBER, label=LABEL_VALIDATING))
        github.add_pr(FakePR(
            number=PR_NUMBER,
            head_branch=self.repo.branch,
            head=FakePRRef(sha=self.repo.accepted),
        ))
        github.seed_state(
            ISSUE_NUMBER, pr_number=PR_NUMBER, branch=self.repo.branch,
        )
        return github
