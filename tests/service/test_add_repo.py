# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What `add-repo` writes: one more entry on the `REPOS` line in effect, every other line kept."""
from __future__ import annotations

import os
import unittest

from tests.service import add_repo_test_support as _add_repo, configure_test_support as _support

_SHARED = 0o644


class AddRepoWriteTest(_add_repo.AddRepoCase):
    """The entry joins the `REPOS` line the configuration reads, and nothing else changes."""

    def test_the_entry_joins_the_line_in_effect(self) -> None:
        """The file is written private, whatever mode it was left with."""
        self._settings_file.chmod(_SHARED)

        added = self._add()

        self.assertEqual(added.render(), self._web_entry())
        self.assertEqual(self._settings(), self._with_web())
        self.assertEqual(_support.mode(self._settings_file), _support.PRIVATE_FILE)
        self.assertEqual(os.listdir(self._settings_file.parent), [self._settings_file.name])

    def test_surrounding_lines_are_kept_byte_for_byte(self) -> None:
        """Only the first live `REPOS` line changes, whatever surrounds or spells it.

        A commented-out example before it and a later `REPOS` line nothing
        reads stay, as do its line end and a file with no final one; the
        value is read as the configuration reads it, quotes and blanks taken
        off -- blanks inside the quotes too, which each entry is read without
        -- and joined with one `;`.
        """
        web_entry = self._web_entry()
        head = "# REPOS=acme/old|/srv/old|main\r\nHITL_HANDLE=alice\r\n"
        tail = "\r\nREPOS=acme/later|/srv/later|main\r\n# kept\r\nLOG_DIR=/srv/logs"
        for spelled, joined in (
            (f'  REPOS = "{self._api_entry}"  ', f"{self._api_entry};{web_entry}"),
            (f'REPOS="  {self._api_entry}  "', f"{self._api_entry};{web_entry}"),
            (f"REPOS={self._api_entry};", f"{self._api_entry};{web_entry}"),
            ("REPOS=", web_entry),
            # A commented-out entry lists no repository.
            (f"REPOS=#{web_entry}", f"#{web_entry};{web_entry}"),
        ):
            with self.subTest(spelled=spelled):
                self._write_settings(f"{head}{spelled}{tail}")

                self._add()

                self.assertEqual(self._settings(), f"{head}REPOS={joined}{tail}")

    def test_defaults_and_explicit_answers(self) -> None:
        """A parallel limit is written behind its remote, `origin` included."""
        for answers, fields in (
            ({}, (_add_repo.MAIN,)),
            ({"repo": " acme/web "}, (_add_repo.MAIN,)),
            ({"remote": _add_repo.MIRROR}, (_add_repo.NEXT, _add_repo.MIRROR)),
            ({"parallel": "2"}, (_add_repo.MAIN, _support.ORIGIN, "2")),
            (
                {"base_branch": "release", "remote": f" {_add_repo.MIRROR} ", "parallel": " 3 "},
                ("release", _add_repo.MIRROR, "3"),
            ),
        ):
            with self.subTest(answers=answers):
                self._write_settings(self._configured)

                self._add(**answers)

                self.assertEqual(self._settings(), self._with_web(*fields))

    def test_a_symlink_is_edited_where_it_leads(self) -> None:
        """The link stays a link, and the file it leads to is written in its own directory."""
        kept = self._scratch / "dotfiles" / "orchestrator.env"
        kept.parent.mkdir()
        self._settings_file.rename(kept)
        self._settings_file.symlink_to(kept)

        self._add()

        self.assertEqual(self._settings_file.readlink(), kept)
        self.assertEqual(kept.read_text(encoding=_support.ENCODING), self._with_web())
        self.assertEqual(os.listdir(kept.parent), [kept.name])


if __name__ == "__main__":
    unittest.main()
