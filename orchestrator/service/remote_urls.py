# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which GitHub repository a git remote's URL points at.

``repository_from_url`` reads each form git accepts for a repository on
``github.com``: ``https://`` and ``http://``, credentials included,
``ssh://`` with or without a user and port, ``git://``, and the scp-like
``[user@]github.com:owner/name``, each with or without ``.git`` and a trailing
slash. The two SSH forms also answer on ``ssh.github.com``, GitHub's SSH
endpoint for a network that blocks port 22, reached as
``ssh://git@ssh.github.com:443/owner/name``. The host is compared without
regard to case, as DNS does. Any other host -- another forge, a host alias out
of the SSH config, a local path -- names no GitHub repository here, since
nothing in the URL says which one it would be.

The ``owner/name`` comes back as the URL spells it, in the characters GitHub
allows, so it passes the setup's repository validator unchanged.
"""
from __future__ import annotations

import re
from types import MappingProxyType
from urllib.parse import urlsplit

_WEB_HOSTS = frozenset(("github.com",))
_SSH_HOSTS = frozenset(("github.com", "ssh.github.com"))

# The GitHub hosts each URL scheme reaches a repository on.
_HOSTS_BY_SCHEME = MappingProxyType({
    "http": _WEB_HOSTS,
    "https": _WEB_HOSTS,
    "git": _WEB_HOSTS,
    "ssh": _SSH_HOSTS,
    "git+ssh": _SSH_HOSTS,
    "ssh+git": _SSH_HOSTS,
})
_REPOSITORY_PATH = re.compile(
    r"/?(?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9._-]+?)(?:\.git)?/?",
)


def _url_path(url: str) -> str | None:
    """The path of a ``scheme://`` URL on GitHub, else ``None``."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    hosts = _HOSTS_BY_SCHEME.get(parts.scheme.lower(), frozenset())
    return parts.path if parts.hostname in hosts else None


def _scp_path(url: str) -> str | None:
    """The path of a scp-like ``[user@]host:path`` on GitHub, else ``None``.

    Git reads that form only while no slash comes before the colon; anything
    else is a local path. It is an SSH form, so either SSH host answers.
    """
    host, colon, path = url.partition(":")
    if not colon or "/" in host:
        return None
    return path if host.rpartition("@")[2].lower() in _SSH_HOSTS else None


def repository_from_url(url: str) -> str | None:
    """The ``owner/name`` a remote URL points at on GitHub, else ``None``."""
    text = url.strip()
    path = _url_path(text) if "://" in text else _scp_path(text)
    found = None if path is None else _REPOSITORY_PATH.fullmatch(path)
    return None if found is None else f"{found['owner']}/{found['name']}"
