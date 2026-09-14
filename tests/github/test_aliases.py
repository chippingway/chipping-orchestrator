# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The stateless helpers a client attribute answers with are the module's own."""
from __future__ import annotations

import unittest

from orchestrator.github import labels, pull_request_reads as _pr_reads
from orchestrator.github.aliases import StaticMethodAlias
from orchestrator.github.client import GitHubClient

_STATIC_HELPERS = (
    ("workflow_label", labels.workflow_label),
    ("pr_has_label", _pr_reads.pr_has_label),
    ("pr_state", _pr_reads.pr_state),
    ("pr_is_mergeable", _pr_reads.pr_is_mergeable),
)


def _module_function(argument: object) -> object:
    return argument


class _AliasOwner:
    aliased = StaticMethodAlias(_module_function)


class StaticMethodAliasTest(unittest.TestCase):
    def test_access_yields_the_function(self) -> None:
        self.assertIs(_AliasOwner.aliased, _module_function)
        self.assertIs(_AliasOwner().aliased, _module_function)


class ClientStaticHelperTest(unittest.TestCase):
    """A helper read off the client is the module function, not a bound method.

    Callers reach these four either way round, so the two spellings have to
    hand back one object: a bound method would take the client as its first
    argument and silently shift every caller's positional arguments along.
    """

    def test_static_helper_identity(self) -> None:
        github_client = GitHubClient.__new__(GitHubClient)
        for attribute_name, module_function in _STATIC_HELPERS:
            with self.subTest(attribute_name=attribute_name):
                self.assertIs(
                    getattr(GitHubClient, attribute_name),
                    module_function,
                )
                self.assertIs(
                    getattr(github_client, attribute_name),
                    module_function,
                )


if __name__ == "__main__":
    unittest.main()
