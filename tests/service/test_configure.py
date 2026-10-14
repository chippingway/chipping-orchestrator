# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What `configure` writes: the basic template with its settings set in place."""
from __future__ import annotations

import os
import unittest

from tests.service import configure_test_support as _support
from tests.service.service_test_support import add_remote
from tests.support.checkouts import committed_checkout

_AGY = "agy"
# Takes the owner's own write bit away from everything created under it.
_RESTRICTIVE_UMASK = 0o277


class ConfigureWriteTest(_support.ConfigureCase):
    """Each setting is set on the template's own line, and `LOG_DIR` is added."""

    def test_defaults_fill_the_template_in_place(self) -> None:
        written = self._configure(authors="@alice, bob")

        self.assertEqual(written, self._settings_file)
        self.assertEqual(self._set_lines(), (
            f"REPOS={_support.ACME}|{self._clone}|{_support.TRUNK}",
            "HITL_HANDLE=alice,bob",
            "ALLOWED_ISSUE_AUTHORS=alice,bob",
            f"DEV_AGENT={_support.CLAUDE}",
            f"REVIEW_AGENT={_support.CODEX}",
            f"DECOMPOSE_AGENT={_support.CLAUDE}",
        ))
        self.assertNotIn(_support.TOKEN, written.read_text(encoding=_support.ENCODING))
        self.assertEqual(_support.mode(written.parent), _support.PRIVATE_DIRECTORY)
        self.assertEqual(_support.mode(written), _support.PRIVATE_FILE)
        self.assertEqual(os.listdir(written.parent), [written.name])

    def test_a_restrictive_umask_on_a_fresh_home(self) -> None:
        """The missing `~/.config` is made private too, so the directory under it can be made."""
        self.addCleanup(os.umask, os.umask(_RESTRICTIVE_UMASK))

        written = self._configure()

        self.assertEqual(
            [_support.mode(path) for path in (written.parent.parent, written.parent, written)],
            [_support.PRIVATE_DIRECTORY, _support.PRIVATE_DIRECTORY, _support.PRIVATE_FILE],
        )

    def test_explicit_answers_replace_each_default(self) -> None:
        # An origin reached through an SSH host alias names no repository, so
        # the one given is the only one there is.
        aliased = committed_checkout(self._scratch / "aliased")
        add_remote(aliased, _support.ORIGIN, "git@github-work:acme/api.git")
        _support.install_agents(self._bin, _AGY)

        self._configure(
            clone=str(aliased),
            repo=_support.ACME,
            base_branch=" release ",
            notify="carol, @dave",
            dev_agent=_AGY,
            review_agent=_support.CLAUDE,
            decompose_agent=_support.CODEX,
        )

        self.assertEqual(self._set_lines(), (
            f"REPOS={_support.ACME}|{aliased}|release",
            "HITL_HANDLE=carol,dave",
            "ALLOWED_ISSUE_AUTHORS=alice",
            f"DEV_AGENT={_AGY}",
            f"REVIEW_AGENT={_support.CLAUDE}",
            f"DECOMPOSE_AGENT={_support.CODEX}",
        ))

    def test_a_non_origin_remote_is_recorded(self) -> None:
        forked = committed_checkout(self._scratch / "forked")
        add_remote(forked, _support.ORIGIN, "https://gitlab.com/acme/api.git")
        add_remote(forked, "upstream", _support.ACME_URL, _support.TRUNK)

        self._configure(clone=str(forked))

        repos_line = self._set_lines()[0]
        self.assertEqual(repos_line, f"REPOS={_support.ACME}|{forked}|{_support.TRUNK}|upstream")


if __name__ == "__main__":
    unittest.main()
