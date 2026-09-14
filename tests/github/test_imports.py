# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import checks and owner identity for the github package."""

from __future__ import annotations

import subprocess
import sys
import unittest

from orchestrator.github import (
    client as _github_client,
    comments as _comments,
    issue_polling as _issue_polling,
    pinned_state as _pinned_state,
)

# The package marker and API owners, each imported in a fresh interpreter.
_MODULES = (
    "orchestrator.github",
    "orchestrator.github.aliases",
    "orchestrator.github.checks",
    "orchestrator.github.client",
    "orchestrator.github.comments",
    "orchestrator.github.events",
    "orchestrator.github.issue_polling",
    "orchestrator.github.issues",
    "orchestrator.github.labels",
    "orchestrator.github.pinned_state",
    "orchestrator.github.pull_requests",
    "orchestrator.github.pull_request_reads",
    "orchestrator.github.pull_request_retirement",
    "orchestrator.github.reviews",
)

# The trust owner is what the git base-sync gates and the workflow stage leaves
# both ask, so it has to stay reachable without either of them: the stage tree
# and the process entrypoint.
_FORBIDDEN_PREFIXES = (
    "orchestrator.cli",
    "orchestrator.runtime",
    "orchestrator.workflow.stages",
)

_LAYERING_SCRIPT = """
import sys
import {module}
print(*sorted(name for name in sys.modules if name.startswith('orchestrator')))
"""

# The allowlist gate the git base-sync eligibility check and the workflow stage
# leaves bind at import time.
_TRUST_NAMES = ("filter_trusted", "is_trusted_author")


class CleanProcessImportTest(unittest.TestCase):
    """Each owner imports cleanly before any siblings are cached."""

    def test_each_module_imports_standalone(self) -> None:
        for module in _MODULES:
            with self.subTest(module=module):
                completed = subprocess.run(
                    [sys.executable, "-c", f"import {module}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, msg=completed.stderr)


class LayeringTest(unittest.TestCase):
    """The trust owner reaches nothing above the GitHub domain."""

    def test_trust_owner_stays_in_its_layer(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                _LAYERING_SCRIPT.format(module="orchestrator.github.comments"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        for imported in completed.stdout.split():
            with self.subTest(imported=imported):
                self.assertFalse(
                    imported.startswith(_FORBIDDEN_PREFIXES),
                    f"the trust owner inverts the dependency via {imported}",
                )


class PublicSurfaceTest(unittest.TestCase):
    """GitHub types and trust gates are reached on their defining owners."""

    def test_names_belong_to_their_defining_modules(self) -> None:
        for owner, name in (
            (_github_client, "GitHubClient"), (_pinned_state, "PinnedState"),
        ):
            with self.subTest(name=name):
                self.assertEqual(getattr(owner, name).__module__, owner.__name__)

    def test_trust_owner_defines_the_gated_names(self) -> None:
        for trust_name in _TRUST_NAMES:
            with self.subTest(name=trust_name):
                self.assertEqual(
                    getattr(_comments, trust_name).__module__, _comments.__name__,
                )

    def test_client_inherits_the_state_mixin_owner(self) -> None:
        self.assertIn(_pinned_state.GitHubStateMixin, _github_client.GitHubClient.__mro__)

    def test_client_inherits_the_polling_mixin_owner(self) -> None:
        self.assertIn(_issue_polling.GitHubIssuePollingMixin, _github_client.GitHubClient.__mro__)


if __name__ == "__main__":
    unittest.main()
