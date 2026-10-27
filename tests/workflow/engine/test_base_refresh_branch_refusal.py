# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a refresh does with a checkout whose branch live work may not stand on.

An admitted record that names no branch the live resolver answers for -- a
pull request with no branch beside it, a pinned flat name -- gets no route,
and neither does a checkout that is not proven the issue's own on its current
branch: nothing is read, rebased, reset, or pushed for either, and nothing is
written, posted, or relabelled. The current checkouts walked beside them are
carried over as ever, and an interrupted attempt's recovery still reads its
checkout as the attempt left it.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import evidence as _evidence
from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import base_refresh
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine.refresh_checkouts_support import (
    AFTER_SHA,
    ONE_PUBLICATION,
    Checkouts,
    Walked,
    observed,
    pr_of,
    seed_open_pr,
)

SLUG = "acme/widget"
BASE_BRANCH = "main"
LABEL_IMPLEMENTING = "workflow:implementing"
LABEL_VALIDATING = "workflow:validating"
_REFRESH_LOG = "orchestrator.base_sync"

# A pull request recorded with no branch beside it, a pre-PR record pinning
# the flat name, and a current pull request whose checkout stands on another
# branch than the issue's.
_BRANCHLESS_PR = 41
_FLAT_PRE_PR = 42
_FOREIGN_CHECKOUT = 43
_REFUSED = frozenset((_BRANCHLESS_PR, _FLAT_PRE_PR, _FOREIGN_CHECKOUT))

# The current pull request and the current pre-PR branch walked beside them.
_CURRENT_PR = 45
_CURRENT_PRE_PR = 46

# What each refusal says, and which issues say it.
_UNNAMED = "records no branch live work may use"
_UNPROVEN = "is not proven this issue's own"
_SAID = ((_UNNAMED, _BRANCHLESS_PR), (_UNNAMED, _FLAT_PRE_PR), (_UNPROVEN, _FOREIGN_CHECKOUT))

# An interrupted attempt's anchor, the one record a checkout is routed over
# without being asked whose it is.
_ANCHORED = PinnedState(data={
    "pr_number": pr_of(_FOREIGN_CHECKOUT),
    "branch": f"orchestrator/acme__widget/issue-{_FOREIGN_CHECKOUT}",
    "pending_auto_base_rebase_push_sha": "a1c40f2e" * 5,
})


def _identity(_spec, issue_number: int, _worktree) -> ProbeAnswer:
    """The foreign checkout's tree is on another branch; every other is its issue's own."""
    if issue_number == _FOREIGN_CHECKOUT:
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _says(output: list[str], refusal: str, issue_number: int) -> bool:
    """Whether one warning line gives this issue this refusal."""
    named = f"issue=#{issue_number} "
    return any(named in line and refusal in line for line in output)


class UntrustedBranchRefreshTest(unittest.TestCase):
    """Checkouts a refresh may not route, walked beside current ones."""

    def setUp(self) -> None:
        self.spec = _config_models.RepoSpec(
            slug=SLUG, target_root=Path("/tmp/refresh-target"), base_branch=BASE_BRANCH,
        )
        self.gh = FakeGitHubClient()
        for number in (_BRANCHLESS_PR, _FOREIGN_CHECKOUT, _CURRENT_PR):
            seed_open_pr(self.gh, number)
        self.gh.seed_state(_BRANCHLESS_PR, pr_number=pr_of(_BRANCHLESS_PR), review_round=3)
        for number, branch in (
            (_FLAT_PRE_PR, f"orchestrator/issue-{_FLAT_PRE_PR}"),
            (_CURRENT_PRE_PR, f"orchestrator/acme__widget/issue-{_CURRENT_PRE_PR}"),
        ):
            self.gh.add_issue(make_issue(number, label=LABEL_IMPLEMENTING))
            self.gh.seed_state(number, branch=branch)
        self.checkouts = Checkouts(self, *_REFUSED, _CURRENT_PR, _CURRENT_PRE_PR)

    def test_no_route_runs_off_an_untrusted_branch(self) -> None:
        standing = self._standing()

        with (
            self.assertLogs(_REFRESH_LOG, level="WARNING") as logged,
            self.checkouts.walked(),
            patch.object(_evidence, "_checkout_identity", side_effect=_identity),
        ):
            base_refresh._refresh_base_and_worktrees(self.gh, self.spec)
            said = [pair for pair in _SAID if _says(logged.output, *pair)]

        self.assertEqual(said, list(_SAID))
        self.assertEqual(self.checkouts.fetch.call_count, 1, "the shared base fetch still runs")
        self.assertEqual(self.checkouts.touched() & _REFUSED, set())
        self.assertEqual(self._standing(), standing)
        self.assertEqual(observed(self.gh, self.checkouts), Walked(
            rebased=[_CURRENT_PR, _CURRENT_PRE_PR],
            published={_CURRENT_PR: ONE_PUBLICATION},
            relabelled=[(_CURRENT_PR, LABEL_VALIDATING)],
            noticed=[pr_of(_CURRENT_PR)],
            announced={_CURRENT_PR: [AFTER_SHA]},
            rounds={
                _BRANCHLESS_PR: 3, _FLAT_PRE_PR: None, _FOREIGN_CHECKOUT: 3,
                _CURRENT_PR: 0, _CURRENT_PRE_PR: None,
            },
        ))

    def test_an_anchor_is_routed_over_its_checkout(self) -> None:
        # A pinned anchor is pinned only over a checkout the refresh proved its
        # own, and its recovery reads that checkout as the interrupted attempt
        # left it -- mid-rebase, on no branch, included -- so the ownership
        # question is not asked again over it.
        with patch.object(_evidence, "_checkout_identity", side_effect=_identity):
            self.assertTrue(base_refresh._stands_on_its_branch(
                self.spec, Path("/tmp/refresh-wt"), _FOREIGN_CHECKOUT, _ANCHORED,
            ))

    def _standing(self) -> dict:
        """Each refused issue's record, labels, and thread."""
        return {
            number: (
                self.gh._pinned[number],
                [label.name for label in self.gh.get_issue(number).labels],
                [(comment.id, comment.body) for comment in self.gh.get_issue(number).comments],
            )
            for number in _REFUSED
        }


if __name__ == "__main__":
    unittest.main()
