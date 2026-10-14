# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What `configure` refuses an answer with, before anything is written."""
from __future__ import annotations

import unittest
from collections.abc import Callable
from pathlib import Path

from orchestrator.service import paths
from orchestrator.service.clone_defaults import clone_entry
from orchestrator.service.repos_entry import writable_field
from orchestrator.service.validation import (
    validate_agent,
    validate_branch,
    validate_clone,
    validate_logins,
    validate_repository,
)
from tests.service import configure_test_support as _support
from tests.service.service_test_support import add_remote, refusal
from tests.support.checkouts import committed_checkout

_REPO_ROOT = Path(__file__).resolve().parents[2]
# A name git allows for a branch that a `REPOS` entry, split on `;`, cannot carry.
_SPLIT_BRANCH = "release;2.x"
_BASE_BRANCH = "--base-branch"


def _field_case(
    option: str,
    raw: str,
    validator: Callable[..., object],
    *context: str,
) -> tuple[dict[str, str], str]:
    """Answers giving ``raw`` as ``option``, and that option's refusal of it.

    The refusal is the field validator's own words with the option in front.
    """
    field = option.removeprefix("--").replace("-", "_")
    return {field: raw}, f"{option}: {refusal(validator, raw, *context)}"


class ConfigureRefusalTest(_support.ConfigureCase):
    """A refused answer, or a source checkout, writes nothing."""

    def test_each_refused_answer_names_its_option(self) -> None:
        missing = str(self._scratch / "missing")
        unpublished = committed_checkout(self._scratch / "unpublished")
        search_path = str(self._bin)
        for answers, expected in (
            _field_case("--clone", missing, validate_clone),
            _field_case("--authors", "alice bob", validate_logins),
            _field_case("--repo", "acme", validate_repository),
            _field_case(_BASE_BRANCH, " ", validate_branch),
            _field_case(_BASE_BRANCH, "feature branch", validate_branch),
            _field_case("--notify", " , @", validate_logins),
            _field_case("--dev-agent", "gpt", validate_agent, search_path),
            _field_case("--review-agent", "agy", validate_agent, search_path),
            _field_case("--decompose-agent", "", validate_agent, search_path),
            # Read off the clone rather than given, so no option is named.
            ({"clone": str(unpublished)}, refusal(clone_entry, unpublished)),
        ):
            with self.subTest(answers=answers):
                self.assertEqual(refusal(self._configure, **answers), expected)
                self.assertFalse(self._settings_file.parent.exists())

    def test_answers_are_checked_before_the_clone(self) -> None:
        """A clone naming no repository is not read while another answer is refused."""
        unpublished = committed_checkout(self._scratch / "unpublished")

        refused = refusal(self._configure, clone=str(unpublished), dev_agent="gpt")

        self.assertEqual(refused, f"--dev-agent: {refusal(validate_agent, 'gpt', str(self._bin))}")

    def test_an_unwritable_entry_field_names_option(self) -> None:
        """What the `REPOS` entry cannot carry is refused under the option answering for it.

        A branch read off the clone is named as `--base-branch` too, since
        another one given there replaces it.
        """
        split_default = committed_checkout(self._scratch / "split-default")
        add_remote(split_default, _support.ORIGIN, _support.ACME_URL, _SPLIT_BRANCH)
        split_path = committed_checkout(self._scratch / "split;path")
        add_remote(split_path, _support.ORIGIN, _support.ACME_URL, _support.TRUNK)
        for answers, option, field in (
            ({"base_branch": _SPLIT_BRANCH}, _BASE_BRANCH, _SPLIT_BRANCH),
            ({"clone": str(split_default)}, _BASE_BRANCH, _SPLIT_BRANCH),
            ({"clone": str(split_path)}, "--clone", str(split_path)),
        ):
            with self.subTest(answers=answers):
                self.assertEqual(
                    refusal(self._configure, **answers),
                    f"{option}: {refusal(writable_field, field)}",
                )
                self.assertFalse(self._settings_file.parent.exists())

    def test_a_source_checkout_is_refused_first(self) -> None:
        self._package_root = _REPO_ROOT

        # Before the answers are read: an empty author list is never named.
        self.assertEqual(self._refused(authors=""), paths.source_checkout_refusal("configure", _REPO_ROOT))
        self.assertFalse(self._settings_file.parent.exists())


if __name__ == "__main__":
    unittest.main()
