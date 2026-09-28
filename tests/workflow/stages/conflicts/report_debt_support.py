# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report debt a conflict round leaves, and the ticks that read it back.

The reviewed pull request the report worlds build -- its report of the head it
stands on published and settled -- put on `workflow:resolving_conflict`, so a
round rewrites the very head that report is about and the `validating` ticks
behind it run as production runs them.
"""
from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock

from orchestrator import config
from orchestrator.workflow.engine import report_rewrite_debt as _rewrite_debt
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import (
    drift_reports as _drift_world,
    fix_reports as _fix_world,
    reviewed_reports as _reviewed,
)
from tests.workflow.fixtures import LABEL_RESOLVING_CONFLICT, _agent, _issue_branch
from tests.workflow.git_owners import seam_patch
from tests.workflow.repo_values import BACKEND_CLAUDE, CONTRIBUTION_DIGEST, DIGEST_LENGTH

DEBT = _rewrite_debt.REWRITE_DEBT

ISSUE = 2_008

PR = 20_080

RUN_AGENT = "run_agent"

# The head the settled report is about, and the commit the round leaves the
# pull request on -- the one the size gate proves the checkout to.
REPORTED_HEAD = _drift_world.PUBLISHED_HEAD

REWRITTEN_HEAD = _drift_world.FIXED_HEAD

# What the developer writes about the head the round published.
FRESH_REPORT = "Carried onto the updated base; the suite passes on the rewritten head."

# What `git rebase` answers when it stops on a file for the dev to resolve.
CONFLICTED = (False, ["a.py"])

# What each head contributes over its base, where a resolution CHANGED it: the
# agent wrote content the head the settled report is about does not carry, so
# the two fingerprint apart and nothing about the old report describes the new.
RESOLVED_DIGEST = "e" * DIGEST_LENGTH

CHANGED = MappingProxyType({
    REPORTED_HEAD: CONTRIBUTION_DIGEST,
    REWRITTEN_HEAD: RESOLVED_DIGEST,
})


def owed(case, previous: str, rewritten: str) -> dict:
    """The debt a rewrite of `previous` into `rewritten` on `case`'s pull request is recorded as."""
    return _rewrite_debt.RewriteDebt(
        pr_number=case.pr_number,
        branch=case.issue_branch,
        previous_head=previous,
        rewritten_head=rewritten,
    ).recorded()


def agents(mocks) -> list:
    """Which agent each run of a tick was spawned as, in order."""
    return [run.args[0] for run in mocks[RUN_AGENT].call_args_list]


class _RewrittenReports(_fix_world._FixReportMixin):
    """A reviewed pull request a conflict round rewrites, then `validating` behind it."""

    pr_number = PR

    issue_branch = _issue_branch(ISSUE)

    def rewritten(self, rebase: tuple, contributions):
        """One conflict round over the reviewed head, its push landing.

        `rebase` is what `git rebase` answers; a conflicted one resumes the
        dev, whose resolution is the commit the round publishes.
        `contributions` is what each head fingerprints to, read by this tick
        and by every tick behind it.
        """
        self.contributions = contributions
        self.seeded(ISSUE, PR, LABEL_RESOLVING_CONFLICT)
        with seam_patch("_rebase_base_into_worktree", MagicMock(return_value=rebase)):
            return self._run_resolving_conflict(
                self.github, self.issue,
                run_agent=_agent(session_id=_drift_world.DEV_SESSION, last_message="resolved"),
                head_shas=(REPORTED_HEAD, REWRITTEN_HEAD),
                push_branch=_drift_world._LandingPush(self.pull_request),
                fetched_branch_tip=REPORTED_HEAD,
                contribution_digest=contributions,
            )

    def refreshed(self):
        """The `validating` tick behind the round, whose dev answers with a fresh report."""
        return self._ticked(
            self._run_validating,
            MagicMock(side_effect=_fix_world._Runs(_drift_world.reported(FRESH_REPORT))),
            committed=False,
        )

    def assert_reported_before_review(self) -> None:
        """What the round hands `validating`, driven two ticks on.

        The first asks the developer -- and nobody else -- for a report of the
        head the round published, over the head the settled report is about,
        and parks for no human. The second finds that report paying the debt
        and hands it to the reviewer.
        """
        self.assertEqual(
            (self.pinned().get(DEBT), self.github.label_history[-1]),
            (owed(self, REPORTED_HEAD, REWRITTEN_HEAD), (ISSUE, WorkflowLabel.VALIDATING)),
        )
        refreshed = self.refreshed()
        asked = _reviewed.prompt(refreshed)
        self.assertEqual(
            (agents(refreshed), REWRITTEN_HEAD in asked, REPORTED_HEAD in asked),
            ([BACKEND_CLAUDE], True, True),
        )
        self.assertFalse(self.pinned().get(_reviewed.AWAITING_HUMAN))
        reviewed = self.reviewed()
        self.assertEqual(
            (agents(reviewed), self.pinned().get(DEBT)),
            ([config.REVIEW_AGENT], None),
        )
        self.assertIn(f"> {FRESH_REPORT}", _reviewed.prompt(reviewed))

    def _ticked(self, stage, run_agent, **run_options):
        """One `validating` tick, over the contributions the round was seeded with."""
        run_options.setdefault("contribution_digest", self.contributions)
        return super()._ticked(stage, run_agent, **run_options)
