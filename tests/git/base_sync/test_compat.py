# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Historical base-sync keyword calls arriving at typed context boundaries."""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import Mock, patch

from orchestrator.git.base_sync import conflicts

_SPEC = "spec"
_ISSUE = "issue"
_STATE = "state"
_CONFLICT_PR_NUMBER = 51

# A failed rebase still reaches the conflict route by its pre-context argument
# list, so the owner pins the signature it binds and normalizes into the
# context entrypoint beside it, which is the boundary the patch below
# intercepts.
_EXPECTED_SIGNATURES = (
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
