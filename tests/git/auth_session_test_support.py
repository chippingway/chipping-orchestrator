# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one part of the authenticated envelope a test on disk cannot run.

Every authenticated git operation resolves a token and builds an askpass
session whose URL points at GitHub. A test driving that operation against a
bare repository on disk has to replace exactly that -- and nothing else, so
the hardened argv prefix, the detached config, the transport-config refusal in
front of it, and the per-target-root lock all still run as they do in
production.

It lives at the `git/` level rather than inside one subpackage's fixtures
because two of them drive real transport: the snapshot refs, and the remote
evidence a terminal artifact is judged by. One registry serves both, so a
nested fixture adds its repository to the same table instead of replacing
whatever was installed outside it.
"""

from __future__ import annotations

import contextlib
import os
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import credentials


class _LocalAuthSession:
    """The askpass session, pointed at a path instead of at GitHub.

    Resolved per SLUG rather than bound to one URL, because a shared
    `target_root` carries two repositories and each has its own remote: a
    session that answered with whichever URL was installed last would have
    both of them pushing to one. What it replaces is the ONLY part of the
    envelope these tests do not exercise for real.
    """

    def __init__(self) -> None:
        self._urls: dict[str, str] = {}

    @contextlib.contextmanager
    def __call__(self, spec, token, **_options):
        yield credentials._GitAuthSession(
            token=token, auth_url=self._urls[spec.slug], env=self._env(),
        )

    @contextlib.contextmanager
    def registered(self, slug: str, auth_url: str):
        """Point this repository's authenticated calls at a path."""
        self._urls[slug] = auth_url
        try:
            with patch.object(
                config, "_resolve_github_token", return_value="token",
            ), patch.object(
                credentials, "_git_auth_session", self,
            ):
                yield
        finally:
            self._urls.pop(slug, None)

    def _env(self) -> dict[str, str]:
        """The environment a token-bearing command runs under, token aside."""
        return {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "orchestrator",
            "GIT_AUTHOR_EMAIL": "orchestrator@example.invalid",
            "GIT_COMMITTER_NAME": "orchestrator",
            "GIT_COMMITTER_EMAIL": "orchestrator@example.invalid",
        }


# One session object for the whole suite, so a nested fixture adds its
# repository to the same registry rather than replacing the one outside it.
_SESSIONS = _LocalAuthSession()
