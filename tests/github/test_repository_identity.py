# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which repository a client speaks for, and whether a head belongs to it.

Three owners refuse a publication on this answer -- the size gate's entry
freeze, the delivery proof behind a publication receipt, and the settlement's
own reconciliation -- and each of them is deciding whether a pull request it
just read is one THIS repository could have published. Nothing on the pull
request itself says so: a fork carries this repository's ref names over its
commits, so the branch and the head agree while the publication is somebody
else's entirely.
"""
from __future__ import annotations

import unittest

from orchestrator.github.client import GitHubClient

_CONFIGURED_SLUG = "chippingway/chipping-orchestrator"

# The same repository as GitHub spells it back, which is the spelling a
# refusal quotes at a human and the one an exact comparison gets wrong.
_CANONICAL_SLUG = "ChippingWay/Chipping-Orchestrator"

_FORK_SLUG = "somebody-else/orchestrator"


class _NamedRepo:
    """The repository object a client resolved, as PyGithub answers with one."""

    def __init__(self, full_name: str) -> None:
        self.full_name = full_name


def _bare_client(repo) -> GitHubClient:
    """A client wired with only what the identity surface reads."""
    gh = GitHubClient.__new__(GitHubClient)
    gh.repo = repo
    gh._repo_slug = _CONFIGURED_SLUG
    return gh


class RepositoryIdentityTest(unittest.TestCase):
    """The canonical name, and what it is allowed to match."""

    def test_the_repository_object_names_it(self) -> None:
        # Answered off the resolved repository rather than off configuration,
        # so what a park quotes back is the name GitHub uses rather than
        # whatever an operator typed.
        client = _bare_client(_NamedRepo(_CANONICAL_SLUG))

        self.assertEqual(client.repo_slug, _CANONICAL_SLUG)

    def test_an_undescribed_repository_falls_back(self) -> None:
        # A client whose repository could not be described still has to name
        # itself: the configured slug is the only spelling left, and it
        # resolves the same repository.
        for described, repo in (
            ("no repository at all", None),
            ("one that names nothing", _NamedRepo("")),
        ):
            with self.subTest(client=described):
                self.assertEqual(
                    _bare_client(repo).repo_slug, _CONFIGURED_SLUG,
                )

    def test_case_alone_is_not_a_stranger(self) -> None:
        # Owner and repository names are case-insensitive on GitHub, so the
        # same repository is one spelling in a hand-typed setting and another
        # in every answer the API gives. Compared exactly, this repository's
        # own publication reads as a fork's and the push behind it is refused
        # for a human who has nothing to reconcile.
        client = _bare_client(_NamedRepo(_CANONICAL_SLUG))

        self.assertTrue(client.is_own_repository(_CONFIGURED_SLUG))

    def test_a_head_elsewhere_is_refused(self) -> None:
        # A fork, and a pull request whose head repository is gone -- a
        # deleted fork is the plain case. Nothing about either says it was
        # ever this repository's.
        client = _bare_client(_NamedRepo(_CANONICAL_SLUG))

        for described, named in (
            ("a fork", _FORK_SLUG),
            ("no repository", None),
            ("nothing at all", ""),
        ):
            with self.subTest(head=described):
                self.assertFalse(client.is_own_repository(named))


if __name__ == "__main__":
    unittest.main()
