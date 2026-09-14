# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the lifetime ledger has to leave exactly as it found it.

A ceiling on agent runs arrives on issues that are already running, under
counters that already exist, in front of caps that already refuse work. Each
case here is one of those: an issue whose only meter is the legacy one, an
ending that has to report what the whole issue cost, and a stage cap that has
always fired before anything spawns. None of them is about the ledger
deciding something -- they are about it deciding nothing it was not asked to.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    run_ledger_values as _run_ledger_values,
    run_limit_values as _run_limit_values,
)
from tests.workflow.engine import (
    lifetime_journeys as journeys,
    lifetime_models as _lifetime_models,
    lifetime_test_support as support,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    KEY_AWAITING_HUMAN,
    KEY_ISSUE_AGENT_RUNS,
    KEY_PARK_REASON,
    LABEL_DONE,
    _agent,
    _PatchedWorkflowMixin,
)

# The park the reviewer's own round cap takes, which is not this ledger's.
_REVIEW_CAP = "review_cap"

# What a terminal receipt opens with, and the only comment on a thread that
# reports what the whole issue spent.
_RECEIPT_PREFIX = ":receipt:"

# How many runs an issue that predates the ledger has already spent on the
# meter the usage accounting has always kept. One short of the allowance, so
# what the walk under it buys is a single run and not a fresh lifetime.
_LEGACY_SPEND = _lifetime_models.ALLOWANCE - 1


class LegacyMeterTest(unittest.TestCase, _PatchedWorkflowMixin):
    """An issue already running when the ledger arrived keeps its spend."""

    def test_a_legacy_issue_keeps_what_it_spent(self) -> None:
        walked = support.walk(
            self,
            journeys.ROTATED_SESSIONS,
            seeded_on=support.seeded(
                journeys.ROTATED_SESSIONS,
                used=None,
                **{KEY_ISSUE_AGENT_RUNS: _LEGACY_SPEND},
            ),
        )

        self.assertEqual(walked.total, _lifetime_models.ALLOWANCE - _LEGACY_SPEND)
        self.assertEqual(walked.spent, _lifetime_models.ALLOWANCE)
        self.assertTrue(walked.parked)
        self.assertIn(
            f"({_lifetime_models.ALLOWANCE}/{_lifetime_models.ALLOWANCE} runs)",
            walked.notices[0],
        )


class StageCapOrderTest(unittest.TestCase, _PatchedWorkflowMixin):
    """A cap that always refused first still refuses first."""

    def test_a_spent_cap_answers_a_spent_ledger(self) -> None:
        # Both are out at once, and the order is the whole point: the cap
        # fires ahead of the spawn, so the boundary is never reached, no run
        # is charged, and the park a human reads is the one about the rounds
        # they can buy back rather than the lifetime they cannot.
        journey = journeys.REPEATED_FIXES
        capped = replace(
            journeys.REVIEWING_LEG,
            staged=dict(journeys.REVIEWING_LEG.staged) | {
                # The cap the walk holds every deployment setting at, spent
                # to the last round: what the walk pins the ceiling to is what
                # a case about that ceiling has to seed against.
                "review_round": support.HELD_CAP,
            },
        )

        walked = support.walk(
            self,
            replace(journey, legs=(capped,)),
            1,
            seeded_on=support.seeded(journey, used=_lifetime_models.ALLOWANCE),
        )

        self.assertEqual(walked.total, 0)
        self.assertEqual(walked.spent, _lifetime_models.ALLOWANCE)
        self.assertNotIn(_run_ledger_values.AGENT_RUN_RESERVATION, walked.pinned)
        self.assertEqual(walked.pinned.get(KEY_PARK_REASON), _REVIEW_CAP)


class TerminalReceiptTest(unittest.TestCase, _PatchedWorkflowMixin):
    """An issue that ran out still ends, and still says what it cost."""

    def test_the_ending_reports_and_returns_nothing(self) -> None:
        # The hold steps aside for a closed issue on purpose: what a close
        # reaches below is a terminal that ENDS the issue rather than a road
        # that spends anything on it. So the receipt is posted and it reports
        # what the walk actually spent -- and the ledger and the park under it
        # are left exactly as they were, since an ending buys back no run and
        # an issue reopened after one is the same spent issue it was.
        walked = support.walk(self, journeys.REPEATED_FIXES)
        self._merge_and_close(walked)

        self._drain(walked)

        self.assertIn(
            f"this issue: {_lifetime_models.ALLOWANCE} agent runs",
            self._receipt(walked),
        )
        self.assertIn(
            (walked.issue.number, LABEL_DONE), walked.github.label_history,
        )
        self._assert_ledger_untouched(walked)

    def _assert_ledger_untouched(self, walked: _lifetime_models.Walk) -> None:
        """The counts and the park the ending was handed, still there."""
        pinned = walked.pinned
        self.assertEqual(
            pinned.get(_run_ledger_values.AGENT_RUNS_USED), _lifetime_models.ALLOWANCE,
        )
        self.assertEqual(
            pinned.get(_run_ledger_values.AGENT_RUN_ALLOWANCE), _lifetime_models.ALLOWANCE,
        )
        self.assertTrue(pinned.get(KEY_AWAITING_HUMAN))
        self.assertEqual(
            pinned.get(KEY_PARK_REASON), _run_limit_values.PARK_AGENT_RUN_LIMIT,
        )

    def _merge_and_close(self, walked: _lifetime_models.Walk) -> None:
        """The ending a human reaches for an issue that ran out of runs."""
        merged = walked.github.get_pr(support.PR_NUMBER)
        merged.merged = True
        merged.state = "closed"
        walked.issue.closed = True

    def _drain(self, walked: _lifetime_models.Walk) -> None:
        """One more tick, on the label the walk left the issue wearing."""
        self._run(
            lambda: _issue_processing._route_issue_to_handler(
                walked.github,
                _TEST_SPEC,
                walked.issue,
                walked.github.workflow_label(walked.issue),
            ),
            run_agent=_agent(last_message="never asked"),
        )

    def _receipt(self, walked: _lifetime_models.Walk) -> str:
        """The one comment a terminal posts about what the issue spent."""
        receipts = [
            body
            for number, body in walked.github.posted_comments
            if number == walked.issue.number
            and body.startswith(_RECEIPT_PREFIX)
        ]
        self.assertEqual(len(receipts), 1)
        return receipts[0]


if __name__ == "__main__":
    unittest.main()
