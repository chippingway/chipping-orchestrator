# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The base-rewrite coordinator's entry, reached by the refresh's argument list."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from orchestrator.workflow.engine import base_rewrite

_PR_NUMBER = 31

_BEHIND = 2

# The refresh beside the coordinator still reaches it by its pre-context
# argument list, so the entry pins the signature it binds and normalizes that
# list into the context entrypoint beside it, which is the boundary the patch
# below intercepts.
_SIGNATURE = "(gh, spec, issue, state, worktree, pr_number, behind)"


class SyncEntryAdapterTest(unittest.TestCase):
    def test_sync_accepts_historical_keywords(self) -> None:
        gh = Mock()
        gh.workflow_label.return_value = "workflow:validating"
        state = Mock()
        state.get.return_value = "pre-rebase"
        run_sync = Mock()
        with patch.object(base_rewrite, "_sync_pr_worktree_context", run_sync):
            base_rewrite._sync_pr_worktree_to_base(
                gh=gh,
                spec="spec",
                issue="issue",
                state=state,
                worktree=Path("worktree"),
                pr_number=_PR_NUMBER,
                behind=_BEHIND,
            )

        context = run_sync.call_args.args[0]
        self.assertEqual(context.pr_number, _PR_NUMBER)
        self.assertEqual(context.behind, _BEHIND)
        self.assertEqual(context.label, "workflow:validating")
        self.assertEqual(context.pending_pre_rebase_sha, "pre-rebase")

    def test_sync_exposes_its_historical_signature(self) -> None:
        self.assertEqual(
            str(inspect.signature(base_rewrite._sync_pr_worktree_to_base)), _SIGNATURE,
        )


if __name__ == "__main__":
    unittest.main()
