# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Historical base-sync keyword calls arriving at typed context boundaries."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from orchestrator.git.base_sync import conflicts, models, recovery

_SPEC = "spec"
_ISSUE = "issue"
_STATE = "state"
_RECOVERY_PR_NUMBER = 41
_CONFLICT_PR_NUMBER = 51

# Each of the two is still reached by its pre-context argument list -- an
# eligibility gate drives the crash recovery, and a failed rebase the conflict
# route -- so every owner pins the signature it binds and normalizes into the
# context entrypoint beside it, which is the boundary the patches below
# intercept.
_EXPECTED_SIGNATURES = (
    (
        recovery,
        "_recover_pending_auto_base_rebase",
        (
            "(gh, spec, issue, state, worktree, *, pr_number, label, "
            "pending_pre_rebase_sha, pending_rewrite=_PendingRewrite(sha='', "
            "pr_number=0, stage=None, damaged=False), behind=0, "
            "unparking_consumed_max=None)"
        ),
    ),
    (
        conflicts,
        "_route_pr_worktree_to_resolving_conflict",
        (
            "(gh, spec, issue, state, pr_number, *, label, behind, "
            "conflicted_files, pr_head_sha)"
        ),
    ),
)


class BaseSyncCompatibilityAdapterTest(unittest.TestCase):
    def test_recovery_applies_historical_defaults(self) -> None:
        recover = Mock(return_value=True)
        with patch.object(
            recovery,
            "_recover_pending_auto_base_rebase_context",
            recover,
        ):
            recovered = recovery._recover_pending_auto_base_rebase(
                "gh",
                _SPEC,
                _ISSUE,
                _STATE,
                Path("worktree"),
                pr_number=_RECOVERY_PR_NUMBER,
                label="workflow:validating",
                pending_pre_rebase_sha="before",
            )

        self.assertTrue(recovered)
        context = recover.call_args.args[0]
        self.assertEqual(context.behind, 0)
        self.assertIsNone(context.unparking_consumed_max)
        # A caller from before the attempt record existed says nothing about
        # what the replay produced, and the empty record is what the routing
        # reads as "fall back to the counts" rather than as a claim.
        self.assertEqual(context.pending_rewrite, models._PendingRewrite())

    def test_conflict_route_builds_typed_context(self) -> None:
        route = Mock()
        with patch.object(
            conflicts,
            "_route_pr_worktree_conflict_context",
            route,
        ):
            conflicts._route_pr_worktree_to_resolving_conflict(
                "gh",
                _SPEC,
                _ISSUE,
                _STATE,
                _CONFLICT_PR_NUMBER,
                label="in_review",
                behind=3,
                conflicted_files=["one.py"],
                pr_head_sha="head",
            )

        context = route.call_args.args[0]
        self.assertEqual(context.pr_number, _CONFLICT_PR_NUMBER)
        self.assertEqual(context.conflicted_files, ["one.py"])
        self.assertEqual(context.pr_head_sha, "head")

    def test_adapters_expose_historical_signatures(self) -> None:
        for owner, adapter_name, expected in _EXPECTED_SIGNATURES:
            with self.subTest(adapter=adapter_name):
                self.assertEqual(
                    str(inspect.signature(getattr(owner, adapter_name))),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
