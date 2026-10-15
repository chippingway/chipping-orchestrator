# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What `add-repo` refuses, leaving the `.env` exactly as it was."""
from __future__ import annotations

import os
import unittest
from collections.abc import Callable
from pathlib import Path

from orchestrator.service import paths
from orchestrator.service.clone_defaults import clone_entry
from orchestrator.service.repos_entry import validate_parallel_limit, validate_remote, writable_field
from orchestrator.service.validation import validate_branch, validate_clone, validate_repository
from tests.service import add_repo_test_support as _add_repo
from tests.service.service_test_support import add_remote, refusal
from tests.support.checkouts import committed_checkout

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARALLEL = "--parallel"
# A name git allows for a remote that a `REPOS` entry, split on `;`, cannot carry.
_SPLIT_REMOTE = "old;mirror"


def _field_case(
    option: str,
    raw: str,
    validator: Callable[..., object],
) -> tuple[dict[str, str], str]:
    """Answers giving ``raw`` as ``option``, and that option's refusal of it.

    The refusal is the field validator's own words with the option in front,
    as `configure` prints them for the options the two commands share.
    """
    field = option.removeprefix("--").replace("-", "_")
    return {field: raw}, f"{option}: {refusal(validator, raw)}"


class AddRepoRefusalTest(_add_repo.AddRepoCase):
    """A refused answer, a listed repository, or a setup it cannot add to writes nothing."""

    def test_a_listed_repository_is_refused(self) -> None:
        """Compared as GitHub compares names, and quoted as `REPOS` spells it."""
        listed = f"REPOS in {self._settings_file} already lists acme/api; edit its entry there to change it"
        for repo in (None, "ACME/API"):
            with self.subTest(repo=repo):
                refused = self._refused(clone=str(self._clone), repo=repo)

                self.assertEqual(refused, listed)
                self.assertEqual(self._settings(), self._configured)

    def test_each_refused_answer_names_its_option(self) -> None:
        missing = str(self._scratch / "missing")
        add_remote(self._web, _SPLIT_REMOTE, "https://github.com/acme/web.git")
        for answers, expected in (
            _field_case("--clone", missing, validate_clone),
            _field_case("--repo", "acme", validate_repository),
            _field_case("--base-branch", "feature branch", validate_branch),
            _field_case("--remote", " ", validate_remote),
            _field_case(_PARALLEL, "0", validate_parallel_limit),
            _field_case(_PARALLEL, "two", validate_parallel_limit),
            ({"remote": _SPLIT_REMOTE}, f"--remote: {refusal(writable_field, _SPLIT_REMOTE)}"),
            # Read off the clone rather than given, so no option is named.
            ({"remote": "nowhere"}, refusal(clone_entry, self._web, remote="nowhere")),
        ):
            with self.subTest(answers=answers):
                self.assertEqual(refusal(self._add, **answers), expected)
                self.assertEqual(self._settings(), self._configured)

    def test_answers_are_checked_before_the_clone(self) -> None:
        """A clone naming no repository is not read while another answer is refused."""
        unpublished = committed_checkout(self._scratch / "unpublished")

        refused = refusal(self._add, clone=str(unpublished), parallel="0")

        self.assertEqual(refused, f"{_PARALLEL}: {refusal(validate_parallel_limit, '0')}")

    def test_a_setup_it_cannot_add_to_is_refused(self) -> None:
        """No `.env`, or one setting no `REPOS`, is refused before any answer is read."""
        self._write_settings("# REPOS=acme/api|/srv/api|main\nLOG_DIR=/srv/logs\n")
        no_repos = (
            f"no line of {self._settings_file} sets REPOS, which add-repo adds the "
            "repository to; give it a REPOS line naming the repositories it already manages"
        )
        unconfigured = (
            f"no configuration exists at {self._settings_file}, and add-repo adds a "
            "repository to one; write it for the first repository with "
            "chipping-orchestrator configure --clone PATH --authors LOGINS, then add "
            "each further one"
        )

        self.assertEqual(self._refused(clone=""), no_repos)
        self._settings_file.unlink()
        self.assertEqual(self._refused(clone=""), unconfigured)
        self.assertEqual(os.listdir(self._settings_file.parent), [])

    def test_a_source_checkout_is_refused_first(self) -> None:
        self._package_root = _REPO_ROOT
        self._settings_file.unlink()

        # Before the `.env` or the answers are read: neither is named.
        self.assertEqual(self._refused(clone=""), paths.source_checkout_refusal("add-repo", _REPO_ROOT))


if __name__ == "__main__":
    unittest.main()
