# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import checks and owner identity for the github package."""

from __future__ import annotations

import unittest

from orchestrator import github as _github
from orchestrator.github import (
    client as _github_client,
    comments as _comments,
    issue_polling as _issue_polling,
    pinned_state as _pinned_state,
)
from tests.support.import_probes import probe_import

_TRUST_OWNER = "orchestrator.github.comments"

# The package and every owner module. The initializer imports the `client`
# owner, which pulls the whole mixin chain, and chain leaves import the package
# back for their sibling owners, so importing any owner first must run the
# initializer without re-entering a half-built one.
_MODULES = (
    "orchestrator.github",
    "orchestrator.github.aliases",
    "orchestrator.github.checks",
    "orchestrator.github.client",
    _TRUST_OWNER,
    "orchestrator.github.developer_reports",
    "orchestrator.github.events",
    "orchestrator.github.issue_polling",
    "orchestrator.github.issues",
    "orchestrator.github.labels",
    "orchestrator.github.pinned_state",
    "orchestrator.github.pull_requests",
    "orchestrator.github.pull_request_reads",
    "orchestrator.github.pull_request_reports",
    "orchestrator.github.pull_request_retirement",
    "orchestrator.github.pull_request_verification",
    "orchestrator.github.reviews",
    "orchestrator.github.verification_artifacts",
    "orchestrator.github.verification_evidence",
)

# Owner-only names the facade must not resolve: the domain surfaces each have an
# owner module callers import directly.
_OWNER_ONLY_NAMES = (
    "PINNED_STATE_MARKER",
    "WORKFLOW_LABELS",
    "hard_skip_control_label",
    "build_event_record",
    "filter_trusted",
    "is_trusted_author",
    "_iter_new_non_pr_issues",
    "_review_state_for_head",
    "_normalize_check_runs",
)

# The trust owner is what the git base-sync gates and the workflow stage leaves
# both ask, so it has to stay reachable without either of them: the stage tree
# and the process entrypoint.
_FORBIDDEN_PREFIXES = (
    "orchestrator.cli",
    "orchestrator.runtime",
    "orchestrator.workflow.stages",
)

# The allowlist gate the git base-sync eligibility check and the workflow stage
# leaves bind at import time.
_TRUST_NAMES = ("filter_trusted", "is_trusted_author")


class CleanProcessImportTest(unittest.TestCase):
    """Each affected module imports standalone in a fresh interpreter.

    The owners are submodules of the same package, and both the `issues` owner
    and the mixin chain the initializer imports reach back into the package for
    their sibling owners, so importing the package or any of its submodules
    directly must run the initializer without a partially-initialized-module
    error. A recording per module gives each a clean `sys.modules` no other test
    has already populated, exposing an import-order cycle a package-first suite
    run would mask. The layering check below reads its planted set off that same
    recording, so the trust owner answers both questions for one interpreter.
    """

    def test_each_module_imports_standalone(self) -> None:
        for module in _MODULES:
            with self.subTest(module=module):
                probe = probe_import(module)
                self.assertEqual(probe.returncode, 0, msg=probe.stderr)


class LayeringTest(unittest.TestCase):
    """The trust owner reaches nothing above the GitHub domain."""

    def test_trust_owner_stays_in_its_layer(self) -> None:
        probe = probe_import(_TRUST_OWNER)
        self.assertEqual(probe.returncode, 0, msg=probe.stderr)
        for imported in sorted(probe.orchestrator_modules):
            with self.subTest(imported=imported):
                self.assertFalse(
                    imported.startswith(_FORBIDDEN_PREFIXES),
                    f"the trust owner inverts the dependency via {imported}",
                )


class PublicSurfaceTest(unittest.TestCase):
    """The facade publishes a narrow `__all__` backed by owner identities.

    Everything past that surface stays reachable only through its owner.
    """

    def test_all_names_the_narrow_public_surface(self) -> None:
        self.assertEqual(
            _github.__all__,
            (
                "GitHubClient",
                "PinnedState",
            ),
        )

    def test_public_names_are_owner_re_exports(self) -> None:
        # Each public name resolves to the owning module's object rather than a
        # rebuilt copy, so a caller reaching through the facade sees the owner's
        # definition.
        self.assertIs(_github.GitHubClient, _github_client.GitHubClient)
        self.assertIs(_github.PinnedState, _pinned_state.PinnedState)

    def test_facade_hides_owner_only_names(self) -> None:
        for owner_only_name in _OWNER_ONLY_NAMES:
            with self.subTest(name=owner_only_name), self.assertRaises(AttributeError):
                getattr(_github, owner_only_name)

    def test_trust_owner_defines_the_gated_names(self) -> None:
        # The facade hides both names, so the owner is the one import site
        # every consumer gates on: it defines the policy rather than
        # re-exporting it, leaving a single object to patch.
        for trust_name in _TRUST_NAMES:
            with self.subTest(name=trust_name):
                self.assertEqual(
                    getattr(_comments, trust_name).__module__,
                    _comments.__name__,
                )

    def test_client_inherits_the_state_mixin_owner(self) -> None:
        # The pinned-state read/write and comment-watermark methods reach the
        # client through the owner's mixin, so the owner class stays in the MRO.
        self.assertIn(
            _pinned_state.GitHubStateMixin,
            _github.GitHubClient.__mro__,
        )

    def test_client_inherits_the_polling_mixin_owner(self) -> None:
        # The repository-wide issue walk is what every tick is served from, and
        # it reaches the client by composition rather than through the issue
        # chain, so the owner class has to be named among the bases itself.
        self.assertIn(
            _issue_polling.GitHubIssuePollingMixin,
            _github.GitHubClient.__mro__,
        )


if __name__ == "__main__":
    unittest.main()
