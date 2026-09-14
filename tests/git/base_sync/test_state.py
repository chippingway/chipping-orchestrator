# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pinned-state keys, park reasons, detour labels, and the base-sync logger."""

from __future__ import annotations

import unittest

from orchestrator.git.base_sync import state
from orchestrator.workflow import transitions as _transitions
from orchestrator.workflow.state import WorkflowLabel

# Live issues already carry these strings in their pinned-state comment, so a
# rename here is a migration rather than a refactor: an in-flight rebase would
# stop finding the SHA it pinned and the unparking sweep would stop matching
# the reason it wrote.
_PINNED_CONTRACT = (
    (state._PARK_REASON, "park_reason"),
    (state._AWAITING_HUMAN, "awaiting_human"),
    (state._REVIEW_ROUND, "review_round"),
    (state._CONFLICT_ROUND, "conflict_round"),
    (state._PENDING_PUSH_SHA, "pending_auto_base_rebase_push_sha"),
    (state._PENDING_REWRITE_PR, "pending_auto_base_rebase_rewrite_pr"),
    (state._PENDING_REWRITE_STAGE, "pending_auto_base_rebase_rewrite_stage"),
    (state._PENDING_REWRITE_SHA, "pending_auto_base_rebase_rewrite_sha"),
    (state._PENDING_ANNOUNCED_SHA, "pending_auto_base_rebase_announced_sha"),
    (state._REASON_AUTO_BASE_REBASE_FAILED, "auto_base_rebase_failed"),
    (state._REASON_AUTO_BASE_REBASE_PUSH_FAILED, "auto_base_rebase_push_failed"),
)

_SNIPPET_BUDGET = 120


class PinnedStateKeyTest(unittest.TestCase):
    """The pinned-state keys and park reasons keep their published spelling."""

    def test_keys_and_reasons_keep_their_values(self) -> None:
        for constant, published_value in _PINNED_CONTRACT:
            with self.subTest(value=published_value):
                self.assertEqual(constant, published_value)

    def test_park_reasons_cover_every_park(self) -> None:
        # The refresh path parks under three distinct reasons and the
        # unparking sweep recognizes an auto-rebase park by this set alone, so
        # a reason missing here would strand the issue awaiting a human.
        self.assertEqual(
            state._AUTO_REBASE_PARK_REASONS,
            frozenset(
                (
                    state._REASON_AUTO_BASE_REBASE_FAILED,
                    "auto_base_rebase_dirty",
                    state._REASON_AUTO_BASE_REBASE_PUSH_FAILED,
                ),
            ),
        )

    def test_error_snippet_length(self) -> None:
        self.assertEqual(state._ERROR_SNIPPET_LEN, _SNIPPET_BUDGET)


class DetourLabelTest(unittest.TestCase):
    """Refresh only detours labels the transition graph lets detour."""

    def test_detour_labels_are_the_post_pr_stages(self) -> None:
        self.assertEqual(
            state._PR_REFRESH_DETOUR_LABELS,
            frozenset(
                (
                    WorkflowLabel.VALIDATING,
                    WorkflowLabel.DOCUMENTING,
                    WorkflowLabel.IN_REVIEW,
                    WorkflowLabel.FIXING,
                ),
            ),
        )

    def test_every_detour_label_may_reach_resolving(self) -> None:
        # A refresh-time conflict writes `resolving_conflict` over the label it
        # found; detouring a label the graph forbids would raise
        # `IllegalTransition` instead of parking the issue.
        self.assertTrue(
            state._PR_REFRESH_DETOUR_LABELS <= _transitions._DETOUR_TO_RESOLVING,
        )


class LoggerTest(unittest.TestCase):
    """The shared logger keeps the name operator filters select on."""

    def test_logger_name(self) -> None:
        self.assertEqual(state.log.name, "orchestrator.base_sync")


if __name__ == "__main__":
    unittest.main()
