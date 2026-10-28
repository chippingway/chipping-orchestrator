# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout a dev resume runs in, over a real clone.

Every dev resume builds its run through one checkout reading, and a tree
standing at the issue's path is used only once it is proven the issue's own:
a worktree of the clone on the issue's current branch. A record pinning that
branch proves nothing about the tree, so one switched onto the flat branch
refuses the resume before any agent is launched -- and a body edit's resume
refuses before its notice, so a refusal held across ticks says nothing.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.git.worktrees import naming, paths
from orchestrator.workflow.engine import usage
from orchestrator.workflow.stages.implementing import handler, resume, resume_request
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.support.git import _run_git

ISSUE = 7
PR_NUMBER = 42
SESSION = "resume-session"
_FLAT_BRANCH = f"orchestrator/issue-{ISSUE}"
_BASE = "main"
_QUIET = "-q"

# A requirements baseline the issue's body does not hash to, so it reads as edited.
_EDITED_BASELINE = "requirements-before-the-edit"


class ResumeCheckoutTest(unittest.TestCase):
    """A resume under a current branch pin, over the tree standing at the issue's path."""

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="orch-resume-")))
        self.enterContext(patch.object(config, "WORKTREES_DIR", root / "worktrees"))
        target = root / "clone"
        target.mkdir()
        _run_git("init", _QUIET, "-b", _BASE, cwd=target)
        _run_git("commit", _QUIET, "--allow-empty", "-m", "base", cwd=target)
        self.target = target
        self.spec = config.RepoSpec("acme/widget", target, _BASE)
        self.checkout = paths._worktree_path(self.spec, ISSUE)
        self.checkout.parent.mkdir(parents=True)
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label="workflow:implementing")
        self.gh.add_issue(self.issue)
        self.gh.seed_state(
            ISSUE, branch=naming._branch_name(self.spec, ISSUE), pr_number=PR_NUMBER,
            dev_agent="claude", dev_session_id=SESSION, awaiting_human=True,
        )

    def test_a_flat_checkout_launches_nothing(self) -> None:
        self._checked_out(_FLAT_BRANCH)

        launches = self._resumes()

        self.assertEqual(launches, 0)
        standing = _run_git("symbolic-ref", "--short", "HEAD", cwd=self.checkout)
        self.assertEqual(standing.stdout.strip(), _FLAT_BRANCH)

    def test_a_flat_checkout_hears_of_no_edit(self) -> None:
        self._checked_out(_FLAT_BRANCH)
        edited = {**self.gh.pinned_data(ISSUE), "user_content_hash": _EDITED_BASELINE}
        self.gh.seed_state(ISSUE, **edited)
        launch = MagicMock()

        with patch.object(usage, "_run_agent_tracked", launch):
            self.assertRaises(naming.BranchRefused, handler._handle_implementing, self.gh, self.spec, self.issue)

        launch.assert_not_called()
        self.assertEqual(self.gh.posted_comments, [])

    def test_the_issue_s_own_checkout_is_resumed(self) -> None:
        self._checked_out(naming._branch_name(self.spec, ISSUE))

        self.assertEqual(self._resumes(), 1)

    def _checked_out(self, branch: str) -> None:
        """Add the worktree at the issue's path on a new `branch` off the base."""
        added = ("worktree", "add", _QUIET, "-b", branch)
        _run_git(*added, str(self.checkout), _BASE, cwd=self.target)

    def _resumes(self) -> int:
        """Resume the session over the tree at the issue's path; how many agents launched."""
        request = resume_request._DevResumeRequest(
            self.gh, self.spec, self.issue, self.gh.read_pinned_state(self.issue), "Please continue.",
        )
        launch = MagicMock(return_value=AgentResult(SESSION, "Done.", 0, False, "", ""))
        with patch.object(usage, "_run_agent_tracked", launch):
            try:
                resume._resume_dev_with_text(request)
            except naming.BranchRefused:
                return launch.call_count
        return launch.call_count


if __name__ == "__main__":
    unittest.main()
