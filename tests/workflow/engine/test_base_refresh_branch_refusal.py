# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a refresh does with a checkout whose branch live work may not stand on.

An admitted record that names no branch the live resolver answers for -- a
pull request with no branch beside it, a pinned flat name -- gets no route,
and neither does a checkout that is not proven the issue's own on its current
branch: nothing is read, rebased, reset, or pushed for either, and nothing is
written, posted, or relabelled. The current checkouts walked beside them are
carried over as ever. An interrupted attempt's anchor is held to the same
question before its recovery resets anything: the issue's own checkout, left
detached in the middle of rebasing its branch, is still recovered, and a tree
switched onto the flat branch since keeps its head and every file. So does the
dispatcher's hold on a label the refresh does not drive: over a flat checkout
or a flat pin, the anchor stands and nothing is cleared, parked, or posted.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import evidence as _evidence
from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.workflow.engine import base_refresh, dispatch_guards
from tests.support.fakes import FakeGitHubClient, FakeLabel, make_issue
from tests.workflow.engine import refresh_anchor_support as _anchored
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

# What an unreadable remote parks a recovery under.
_RECOVERY_PARK = "auto_base_rebase_push_failed"

# A label the refresh does not drive, where the dispatcher answers a held anchor itself.
_HELD_LABEL = "question"


def _identity(_spec, issue_number: int, _worktree, **_options) -> ProbeAnswer:
    """The foreign checkout's tree is on another branch; every other is its issue's own."""
    if issue_number == _FOREIGN_CHECKOUT:
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _says(output: list[str], refusal: str, issue_number: int) -> bool:
    """Whether one warning line gives this issue this refusal."""
    named = f"issue=#{issue_number} "
    return any(named in line and refusal in line for line in output)


def _pins_the_flat_branch(world) -> None:
    """Pin the flat `orchestrator/issue-<n>` on the anchored issue's record."""
    state = world.gh.read_pinned_state(world.gh.get_issue(_anchored.ISSUE))
    state.set("branch", f"orchestrator/issue-{_anchored.ISSUE}")
    world.gh.write_pinned_state(world.gh.get_issue(_anchored.ISSUE), state)


# What leaves a held anchor on a branch live work may not stand on.
_FLATTENED = (
    ("a flat checkout", _anchored.AnchoredCheckout.switched_to_the_flat_branch),
    ("a flat pin", _pins_the_flat_branch),
)


def _holds(world) -> bool:
    """Whether the dispatcher's guards hold a tick of the anchored issue relabelled `_HELD_LABEL`."""
    issue = world.gh.get_issue(_anchored.ISSUE)
    issue.labels = [FakeLabel(_HELD_LABEL)]
    state = world.gh.read_pinned_state(issue)
    return dispatch_guards._record_stops_the_tick(world.gh, world.spec, issue, _HELD_LABEL, state)


def _held_reading(world) -> tuple:
    """The anchored issue's pinned comment and every comment posted, as one reading."""
    posted = list(world.gh.posted_comments)
    return world.gh.pinned_data(_anchored.ISSUE), posted


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


class AnchoredRefreshTest(unittest.TestCase):
    """An interrupted attempt's recovery, over a real checkout at the issue's path."""

    def setUp(self) -> None:
        self.world = _anchored.AnchoredCheckout(self)

    def test_an_anchor_authorizes_no_flat_checkout(self) -> None:
        # The anchor was pinned over the issue's checkout, and the tree at the
        # path has been switched onto the flat branch since, carrying a commit
        # of its own. The recovery's reset would take it, so it is refused:
        # head, file, and record all stand.
        self.world.switched_to_the_flat_branch()
        before = self.world.standing()

        self.world.syncs()

        self.assertEqual(self.world.standing(), before)
        self.assertTrue((self.world.checkout / _anchored.FOREIGN_FILE).exists())

    def test_a_held_anchor_answers_no_flat_branch(self) -> None:
        # The dispatcher holds the handler back over the anchor and answers it
        # itself, reading the checkout's head as the attempt's. Over a flat
        # checkout or a flat pin it answers nothing: the tick is held, every
        # record kept, and nothing posted.
        for name, flattens in _FLATTENED:
            with self.subTest(name):
                self.setUp()
                flattens(self.world)
                before = _held_reading(self.world)

                self.assertTrue(_holds(self.world))

                self.assertEqual(_held_reading(self.world), before)

    def test_an_interrupted_rebase_is_still_recovered(self) -> None:
        # The issue's own checkout, detached mid-replay by an interrupted
        # rebase of its own branch, is the checkout the anchor was pinned for:
        # the recovery runs over it, and with the remote unreadable it resets
        # and parks as ever.
        self.world.left_mid_rebase()

        self.world.syncs()

        pinned = self.world.gh.pinned_data(_anchored.ISSUE)
        self.assertEqual(pinned.get("park_reason"), _RECOVERY_PARK)
        self.assertIsNone(pinned.get("pending_auto_base_rebase_push_sha"))


if __name__ == "__main__":
    unittest.main()
