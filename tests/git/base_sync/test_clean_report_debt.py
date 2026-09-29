# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a clean rebase leaves its pull request owing, and only where its push landed.

A clean rebase publishes a head no developer report is about: the settled
report names the head the push replaced. So the debt naming both is durable
before the attempt is cleared or the reviewer routed, a later rebase carries a
standing debt onto the head it lands, and a rebase that lands nothing -- or
lands over a claim it does not follow -- records nothing and leaves whatever
already stands.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.git.base_sync.refresh_scenarios import (
    _clean_rebase_scenario,
    _noop_rebase_scenario,
)
from tests.git.base_sync.refresh_test_support import (
    AFTER_SHA,
    BEFORE_SHA,
    ISSUE,
    KEY_PENDING_PUSH_SHA,
    LABEL_VALIDATING,
    PR_NUMBER,
    _SyncWorktreeWithBaseFixture,
)
from tests.git.base_sync.report_debt_test_support import (
    EARLIER_SHA,
    FOREIGN_SHA,
    KEY_REWRITE_DEBT,
    DurableAtTheRelabel,
    owed,
    pushed_over,
    refreshes,
    settles_a_report_of,
)
from tests.support.fakes import FakeGitHubClient

# The debt an earlier rebase left: from the head the settled report is about
# onto the head this refresh finds the pull request on.
_STANDING = owed(EARLIER_SHA, BEFORE_SHA)


def _refused_push_scenario():
    """A clean rebase whose force-push the remote refused."""
    return _clean_rebase_scenario(push_result=False)


class _ReportDebtFixture(_SyncWorktreeWithBaseFixture):
    """A refresh of PR #42 over a settled report and whatever debt stands."""

    def _seeded(self, standing, reported: str) -> None:
        """PR #42 on a fresh client, carrying a `standing` debt and a settled report of `reported`.

        Fresh each time, so a case looping over worlds starts every one from
        nothing. `standing` None is an issue carrying no debt key.
        """
        self.gh = FakeGitHubClient()
        self._seed_pr_issue(**({} if standing is None else {KEY_REWRITE_DEBT: standing}))
        settles_a_report_of(self.gh, reported)

    def _rebased(self, standing, reported: str, scenario=_clean_rebase_scenario) -> dict:
        """One refresh over `_seeded(standing, reported)`; the durable record."""
        self._seeded(standing, reported)
        scenario().run(self)
        return self.gh.pinned_data(ISSUE)


class LandedRebaseDebtTest(_ReportDebtFixture, unittest.TestCase):
    """The debt a landed push leaves is durable before anything routes, and names the latest head."""

    def test_the_debt_is_durable_before_the_route(self) -> None:
        # What a process lost in the relabel comes back to already owes the
        # landed head its report, with the anchor still there to bring the
        # tick back; the validating refresh then asks the developer for it.
        self._seed_pr_issue()
        settles_a_report_of(self.gh, BEFORE_SHA)
        relabel = DurableAtTheRelabel(self.gh)

        with patch.object(self.gh, "set_workflow_label", relabel):
            _clean_rebase_scenario().run(self)

        self.assertEqual(
            [(seen[KEY_REWRITE_DEBT], seen[KEY_PENDING_PUSH_SHA]) for seen in relabel.seen],
            [(owed(BEFORE_SHA, AFTER_SHA), BEFORE_SHA)],
        )
        durable = self.gh.pinned_data(ISSUE)
        self.assertEqual(
            (durable[KEY_REWRITE_DEBT], durable[KEY_PENDING_PUSH_SHA]),
            (owed(BEFORE_SHA, AFTER_SHA), None),
        )
        self.assertTrue(refreshes(durable, AFTER_SHA))

    def test_a_later_advance_owes_its_own_head(self) -> None:
        for described, reported, expected in (
            # The last rebase's head is rebased again before its own report
            # was asked for: the claim keeps the head the settled report is
            # about and moves onto the head this push landed.
            ("unreported", EARLIER_SHA, owed(EARLIER_SHA, AFTER_SHA)),
            # Its report settled and validating had not dropped the claim it
            # paid: this rebase's own debt takes that claim's place.
            ("reported", BEFORE_SHA, owed(BEFORE_SHA, AFTER_SHA)),
        ):
            with self.subTest(described):
                durable = self._rebased(_STANDING, reported)

                self.assertEqual(durable[KEY_REWRITE_DEBT], expected)
                self.assertTrue(refreshes(durable, AFTER_SHA))


class UnlandedRebaseDebtTest(_ReportDebtFixture, unittest.TestCase):
    """A rebase records only a head its own push landed over the head a claim names.

    A claim says this orchestrator made the head it names, so nothing else may
    be recorded -- and whatever already stands is still owed.
    """

    def test_an_unlanded_rebase_keeps_the_debt(self) -> None:
        # A refused push and a rebase that moved nothing leave the pull request
        # where it was, and route nobody.
        for described, scenario, standing in (
            ("a refused push", _refused_push_scenario, _STANDING),
            ("a no-op", _noop_rebase_scenario, _STANDING),
            ("a no-op with no claim", _noop_rebase_scenario, None),
        ):
            with self.subTest(described):
                durable = self._rebased(standing, EARLIER_SHA, scenario)

                self.assertEqual(durable.get(KEY_REWRITE_DEBT), standing)
                self.assertNotIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)

    def test_a_foreign_head_update_claims_nothing(self) -> None:
        # Somebody else pushed the pull request onto a head of their own:
        # before the refresh read it, so the gate will not publish over a pull
        # request it did not read, or as this push went out, so the lease
        # pinned to the head it read is refused. Nothing of this rebase's
        # landed, the foreign head is what the pull request carries, and
        # neither it nor the replay is claimed over what already stands.
        for described, at_the_push, standing in (
            ("before the refresh read it", False, _STANDING),
            ("as the push went out", True, _STANDING),
            ("as the push went out, over no claim", True, None),
        ):
            with self.subTest(described):
                self._seeded(standing, EARLIER_SHA)
                pull = self.gh.pulls[PR_NUMBER]

                pushed_over(self.gh, _clean_rebase_scenario(), at_the_push=at_the_push).run(self)

                self.assertEqual(self.gh.pinned_data(ISSUE).get(KEY_REWRITE_DEBT), standing)
                self.assertEqual(pull.head.sha, FOREIGN_SHA)
                self.assertNotIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)

    def test_an_unfollowed_claim_is_left_standing(self) -> None:
        # The push still lands and the reviewer is still routed; the reviewer
        # road refuses the stale report it finds, as it would with no claim.
        for described, standing in (
            ("a head somebody pushed over", owed(EARLIER_SHA, FOREIGN_SHA)),
            ("another pull request", owed(EARLIER_SHA, BEFORE_SHA, pr=PR_NUMBER + 1)),
            ("a claim nobody can read", {"previous_head": EARLIER_SHA}),
        ):
            with self.subTest(described):
                durable = self._rebased(standing, EARLIER_SHA)

                self.assertEqual(durable[KEY_REWRITE_DEBT], standing)
                self.assertIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)


if __name__ == "__main__":
    unittest.main()
