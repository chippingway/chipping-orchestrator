# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A `REPOS` entry as a setup writes it, and as the configuration reads it back."""

import sys
import unittest
from pathlib import Path

from orchestrator.config.models import RepoSpec
from orchestrator.config.repositories import parse_repos_env
from orchestrator.service.repos_entry import RepositoryEntry
from tests.service.service_test_support import refusal

_ACME = "acme/api"
_CLONE = Path("/home/alice/src/api")
_MAIN = "main"
_UPSTREAM = "upstream"
_UNWRITABLE = (
    "cannot be written into a REPOS entry, which splits on '|', ';', and line "
    "breaks and strips the blanks around each field"
)

# Fields the configuration would split: a path can only be broken this way,
# since it is never blank and keeps its inner blanks.
_SEPARATED = ("feat|x", "feat;x", "feat\nx", "feat\x0bx")


def _unwritable_entries() -> list[RepositoryEntry]:
    """Entries with one field the configuration would read back changed."""
    entries = [RepositoryEntry(_ACME, Path(f"/srv/{field}/api"), _MAIN) for field in _SEPARATED]
    for field in (*_SEPARATED, " main", "main ", ""):
        entries.append(RepositoryEntry(_ACME, _CLONE, field))
        entries.append(RepositoryEntry(_ACME, _CLONE, _MAIN, field, 2))
    return entries


def _spec_for(entry: RepositoryEntry) -> RepoSpec:
    """The target the configuration should read `entry` back as."""
    return RepoSpec(
        slug=entry.repository,
        target_root=entry.clone,
        base_branch=entry.base_branch,
        remote_name=entry.remote,
        parallel_limit=entry.parallel_limit or 1,
    )


class RenderedEntryTest(unittest.TestCase):
    """Each entry is written in the fewest fields that carry it, and reads back whole.

    The remote is written once it is not `origin`, and a parallel limit is
    written behind its remote, `origin` included, because the fields are
    positional.
    """

    def test_entries_read_back_as_written(self) -> None:
        for entry, written in (
            (RepositoryEntry(_ACME, _CLONE, _MAIN), f"{_ACME}|{_CLONE}|main"),
            (
                RepositoryEntry(_ACME, _CLONE, "release/2.x", _UPSTREAM),
                f"{_ACME}|{_CLONE}|release/2.x|{_UPSTREAM}",
            ),
            (
                RepositoryEntry(_ACME, _CLONE, _MAIN, parallel_limit=3),
                f"{_ACME}|{_CLONE}|main|origin|3",
            ),
            (
                RepositoryEntry(_ACME, Path("/srv/my clones/api"), _MAIN, _UPSTREAM, 1),
                f"{_ACME}|/srv/my clones/api|main|{_UPSTREAM}|1",
            ),
        ):
            with self.subTest(written=written):
                self.assertEqual(entry.render(), written)
                read_back = parse_repos_env(written, default_parallel_limit=1, config_error=sys.exit)
                self.assertEqual(read_back, [_spec_for(entry)])


class UnwritableEntryTest(unittest.TestCase):
    """A field the configuration would read back as something else is refused."""

    def test_split_or_stripped_fields_are_refused(self) -> None:
        for entry in _unwritable_entries():
            with self.subTest(entry=entry):
                self.assertIn(_UNWRITABLE, refusal(entry.render))

    def test_a_repository_is_held_to_owner_name(self) -> None:
        # Which also keeps an entry from reading as a `#` comment.
        self.assertTrue(
            refusal(RepositoryEntry("#acme/api", _CLONE, _MAIN).render).startswith(
                "repository '#acme/api' is not written owner/name",
            ),
        )

    def test_a_parallel_limit_below_one_is_refused(self) -> None:
        for limit in (0, -2):
            with self.subTest(limit=limit):
                self.assertEqual(
                    refusal(RepositoryEntry(_ACME, _CLONE, _MAIN, parallel_limit=limit).render),
                    f"parallel limit {limit} is below 1, which would block all work for the repository",
                )


if __name__ == "__main__":
    unittest.main()
