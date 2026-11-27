# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Commit identity, Git hardening, and rollback during squash publication."""

from __future__ import annotations

import unittest

from tests.workflow.stages.validating import squash_git_support as squash_support

EXECUTABLE_MODE = 0o755
GIT_LOG = "log"
LAST_COMMIT = "-1"
AUTHOR_FORMAT = "--pretty=%an <%ae>"
COMMITTER_FORMAT = "--pretty=%cn <%ce>"
ORCHESTRATOR_IDENTITY = "orch-bot <orch-bot@example.com>"


class SquashRewriteRealGitTest(
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """Preserve branches and worktrees across the destructive rewrite."""

    def test_push_failure_rollback_restores_branch(self) -> None:
        # The whole point of saving original_head: a push failure after
        # the soft-reset + squash commit must not leave the branch
        # pointing at the squash commit. The original commits must still
        # be on the branch so the operator can decide what to do.
        original_head = self._head_sha()
        original_subjects = self._commits_on_branch()
        self.assertEqual(len(original_subjects), 3)

        squash_run = self._squash(push_result=False)
        self.assertFalse(squash_run.success)
        self.assertIsNone(squash_run.sha)
        self.assertEqual(squash_run.count, 0)
        self.assertIn("force-push", squash_run.error or "")
        # HEAD restored.
        self.assertEqual(
            self._head_sha(),
            original_head,
            "rollback must restore HEAD to the pre-squash SHA",
        )
        # All three original commits still on the branch.
        self.assertEqual(self._commits_on_branch(), original_subjects)
        # The mixed reset restores the index, and the working tree already
        # matched the original HEAD, so the checkout should be clean.
        status = squash_support.run_git("status", "--porcelain", cwd=self.work)
        self.assertEqual(status.strip(), "")

    def test_never_executes_planted_fsmonitor(self) -> None:
        # Every index-refreshing git command in the squash helper -- the
        # pre-rewrite dirty check, the soft reset, the squash commit, and the
        # mixed reset after a refused push -- runs inside a worktree whose
        # `.git/config` the agent can write. A planted `core.fsmonitor` helper
        # would run during any of them with the orchestrator's process
        # environment (ambient secrets) attached, so each must go through the
        # hardened git path that disables fsmonitor. This drives the whole
        # helper to the rollback branch (push mocked to fail) and asserts the
        # planted hook fired NOWHERE inside it -- while first proving the hook
        # is genuinely usable, so the negative assertion is not vacuous.
        marker = self._install_fsmonitor()
        original_head = self._head_sha()
        original_subjects = self._commits_on_branch()
        self.assertEqual(len(original_subjects), 3)

        squash_run = self._squash(push_result=False)

        fired = marker.read_text() if marker.exists() else ""
        # The security property: no git command inside the squash helper
        # executed the planted fsmonitor. A plain `_git` dirty check / reset
        # would appear here with the orchestrator environment attached.
        self.assertEqual(
            fired,
            "",
            f"a git command inside the squash helper executed the planted fsmonitor: {fired!r}",
        )
        # Push failed, so the rollback ran and restored the original commits.
        self.assertFalse(squash_run.success)
        self.assertIn("force-push", squash_run.error or "")
        self.assertEqual(
            self._head_sha(),
            original_head,
            "rollback must restore HEAD to the pre-squash SHA",
        )
        self.assertEqual(self._commits_on_branch(), original_subjects)

    def test_squash_commit_uses_orchestrator_identity(self) -> None:
        # The squash commit must be authored under AGENT_GIT_NAME /
        # AGENT_GIT_EMAIL regardless of the dev's commit identity. This
        # keeps a single attribution for orchestrator-owned commits and
        # matches the agent-spawn `agent_env` behavior.
        squash_run = self._squash(
            AGENT_GIT_NAME="orch-bot",
            AGENT_GIT_EMAIL="orch-bot@example.com",
        )
        self.assertTrue(squash_run.success, squash_run.error)

        for pretty in (AUTHOR_FORMAT, COMMITTER_FORMAT):
            with self.subTest(pretty=pretty):
                stamped = squash_support.run_git(
                    GIT_LOG,
                    LAST_COMMIT,
                    pretty,
                    cwd=self.work,
                ).strip()
                self.assertEqual(stamped, ORCHESTRATOR_IDENTITY)

    def _install_fsmonitor(self):
        marker = self.tmpdir / "fsmonitor_invocations.txt"
        hook = self.tmpdir / "fsmonitor_hook.sh"
        hook_lines = (
            "#!/bin/sh",
            rf"tr '\0' ' ' < /proc/$PPID/cmdline >> '{marker}'",
            rf"printf '\n' >> '{marker}'",
            r"printf '/\000'",
        )
        hook.write_text("\n".join((*hook_lines, "")))
        hook.chmod(EXECUTABLE_MODE)
        squash_support.run_git(
            "config",
            "core.fsmonitor",
            str(hook),
            cwd=self.work,
        )
        squash_support.run_git("status", "--porcelain", cwd=self.work)
        self.assertTrue(
            marker.exists() and marker.read_text().strip(),
            "planted fsmonitor did not run for a plain git status",
        )
        marker.unlink()
        return marker


if __name__ == "__main__":
    unittest.main()
