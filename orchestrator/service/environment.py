# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The environment the systemd user service runs in, taken from a shell.

A user service does not inherit the login shell's environment, so what it is
given is decided here, once, from the shell that sets it up: that shell's
``HOME`` and ``USER``, and its ``PATH`` with only the absolute entries kept.
An empty or relative ``PATH`` entry names a directory relative to wherever a
command runs, and the service runs in its home rather than in the directory
the shell was in, so such an entry would find a different executable there or
none.

Nothing else crosses. A ``GITHUB_TOKEN``, a ``REPOS``, an agent binary
override, an ``ORCHESTRATOR_SKIP_DOTENV``, or any other setting exported only
in the shell would make a process started from it work where the service does
not: the service reads its settings from the installed ``.env`` and its tokens
from the token files, and so does anything that validates for it.

``service_environment`` is that environment, built from a shell's, and
``captured_path`` the ``PATH`` it carries -- the one value both a unit file
that sets the service's ``PATH`` and a check that validates against it are
given. Applied to an environment already built here, either answers it
unchanged.

Nothing here imports from the package.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

# The shell's own values for the account the service runs as.
_CARRIED = ("HOME", "USER")


def captured_path(shell_path: str) -> str:
    """The absolute entries of ``shell_path``, in its order, as one ``PATH``."""
    return os.pathsep.join(
        entry for entry in shell_path.split(os.pathsep) if os.path.isabs(entry)
    )


def service_environment(shell: Mapping[str, str]) -> dict[str, str]:
    """``HOME``, ``USER``, and the captured ``PATH`` of ``shell``, and nothing else.

    ``HOME`` and ``USER`` are carried only when the shell sets them. ``PATH``
    is always set, empty when the shell has no absolute entry, so a ``.env``
    the service loads cannot supply one: the configuration keeps a value the
    environment already holds.
    """
    carried = {name: shell[name] for name in _CARRIED if name in shell}
    return {**carried, "PATH": captured_path(shell.get("PATH", ""))}
