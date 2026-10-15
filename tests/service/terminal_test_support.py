# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A terminal typed scripted answers, a GitHub that knows tokens, and `init` run at the one with the other.

`typed_init` runs `init` with onboarding at a terminal whose lines are the
answers given, the hidden prompt reading the next of them, and reads what it
printed back as one transcript in which each answer shows as a terminal
echoes it -- a hidden one as the bare line end. Two answers stand for keys
rather than text: ``INTERRUPT`` for Ctrl+C at that question, and
``UNHIDDEN`` for a terminal whose echo the hidden prompt cannot turn off.
"""
from __future__ import annotations

import getpass
import io
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.service import token_probe
from orchestrator.service.installation import init
from orchestrator.service.onboarding import onboard

INTERRUPT = "^C"
UNHIDDEN = "^echo"

_OK = 200
_UNAUTHORIZED = 401
_REFUSED = json.dumps({"message": "Bad credentials"}).encode()


class Run(NamedTuple):
    """What one `init` answered, the transcript it printed, and what it wrote to stderr."""

    status: int
    transcript: str
    stderr: str


class _Terminal(io.StringIO):
    """A terminal typed the lines it holds, each one read echoed into the transcript."""

    def isatty(self) -> bool:
        return True

    def readline(self, *_size: object) -> str:
        line = _typed(self)
        sys.stdout.write(line)
        return line

    def hidden(self, prompt: str = "") -> str:
        """Stand in for ``getpass.getpass``: the next line, typed without an echo."""
        sys.stdout.write(prompt)
        line = _typed(self)
        if line == f"{UNHIDDEN}\n":
            raise getpass.GetPassWarning("Can not control echo on the terminal.")
        if not line:
            raise EOFError
        sys.stdout.write("\n")
        return line.removesuffix("\n")


class TokenGitHub:
    """Stands in for ``token_probe.http_get``: each token it knows reads every repository.

    ``owners`` maps each token GitHub accepts to the login it belongs to;
    any other token is refused as unauthorized. Each request is recorded as
    its API path and the token it carried.
    """

    def __init__(self, owners: Mapping[str, str]) -> None:
        self.owners = dict(owners)
        self.requests: list[tuple[str, str]] = []

    def __call__(self, url: str, token: str) -> tuple[int, bytes]:
        path = url.removeprefix(token_probe.API_ROOT)
        self.requests.append((path, token))
        owner = self.owners.get(token)
        if owner is None:
            return _UNAUTHORIZED, _REFUSED
        if path == "/user":
            return _OK, json.dumps({"login": owner}).encode()
        return _OK, json.dumps({"full_name": path.removeprefix("/repos/")}).encode()


def typed_init(shell: Mapping[str, str], package_root: Path, answers: Sequence[str]) -> Run:
    """Run ``init`` from ``shell`` at a terminal typed ``answers``, onboarding asking them."""
    terminal = _Terminal("".join(f"{answer}\n" for answer in answers))
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        patch.object(sys, "stdout", stdout),
        patch.object(sys, "stderr", stderr),
        patch.object(getpass, "getpass", side_effect=terminal.hidden),
    ):
        status = init(shell, terminal, onboard=onboard, package_root=package_root)
    return Run(status, stdout.getvalue(), stderr.getvalue())


def _typed(terminal: io.StringIO) -> str:
    """The next line typed at ``terminal``, or the Ctrl+C typed in its place."""
    line = io.StringIO.readline(terminal)
    if line == f"{INTERRUPT}\n":
        raise KeyboardInterrupt
    return line
