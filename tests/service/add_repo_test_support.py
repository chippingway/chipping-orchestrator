# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the `add-repo` tests share: a configured home and a clone of a second repository."""
from __future__ import annotations

from orchestrator.service.add_repo import AddRepoAnswers, AddRepoRefusal, add_repo
from orchestrator.service.repos_entry import RepositoryEntry
from tests.service import configure_test_support as _support
from tests.service.service_test_support import add_remote
from tests.support.checkouts import committed_checkout

WEB = "acme/web"
MAIN = "main"
MIRROR = "mirror"
NEXT = "next"


class AddRepoCase(_support.ConfigureCase):
    """The home `configure` writes for acme/api, and a clone of acme/web.

    The web clone's `origin` points at acme/web and records `main` as its
    default branch, and its `mirror` points there too, over SSH, recording
    `next`.
    """

    def setUp(self) -> None:
        super().setUp()
        self._configure()
        self._configured = self._settings_file.read_text(encoding=_support.ENCODING)
        self._api_entry = f"{_support.ACME}|{self._clone}|{_support.TRUNK}"
        self._web = committed_checkout(self._scratch / "web")
        add_remote(self._web, _support.ORIGIN, "https://github.com/acme/web.git", MAIN)
        add_remote(self._web, MIRROR, "git@github.com:acme/web.git", NEXT)

    def _add(self, **answers: str) -> RepositoryEntry:
        """Run the core for the web clone unless ``answers`` say otherwise."""
        chosen = AddRepoAnswers(**{"clone": str(self._web), **answers})
        return add_repo(chosen, package_root=self._package_root)

    def _refused(self, **answers: str) -> str:
        """The words ``add-repo`` refuses ``answers`` with, other than a field's."""
        try:
            self._add(**answers)
        except AddRepoRefusal as refused:
            return str(refused)
        raise AssertionError(f"add-repo wrote {self._settings_file} for {answers!r}")

    def _settings(self) -> str:
        """What the installed `.env` holds, its line ends as they are."""
        with self._settings_file.open(encoding=_support.ENCODING, newline="") as stream:
            return stream.read()

    def _write_settings(self, text: str) -> None:
        """Write ``text`` as the installed `.env`, its line ends as they are."""
        self._settings_file.write_text(text, encoding=_support.ENCODING, newline="")

    def _with_web(self, *fields: str) -> str:
        """The `.env` `configure` wrote, the web clone's entry added to its `REPOS` with ``fields``."""
        written = f"REPOS={self._api_entry}\n"
        joined = f"REPOS={self._api_entry};{self._web_entry(*fields)}\n"
        return self._configured.replace(written, joined, 1)

    def _web_entry(self, *fields: str) -> str:
        """The web clone's entry, its fields after the clone being ``fields``, else its default branch."""
        after_clone = fields or (MAIN,)
        return "|".join((WEB, str(self._web), *after_clone))
