# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""``check``: whether the service would run, judged in the environment it runs with.

The service reads its settings from the installed ``.env`` and its tokens
from the token files, in an environment holding only what ``environment``
hands it -- ``HOME``, ``USER``, and the shell's absolute ``PATH`` entries. A
package running from its own source checkout reads the ``.env`` at that
checkout's root instead, a file no installed service reads, so the check
refuses one, with the refusal every setup command gives it, before any
setting is read. The check is held to the same environment as the service:
``problems`` starts a fresh interpreter with exactly that environment, in that
home, the way the service's own process starts, and it is there that
``settings_report`` tells a source checkout apart, resolves the settings, and
reports what keeps them from running. A token, a setting, an agent override,
a git setting, or a ``.env`` opt-out exported only in the shell therefore
cannot make a check pass where the service would fail, and the process that
asked never imports ``orchestrator.config``, so the check answers on a host
whose settings would stop it at import.

The interpreter is the one running this package, with this package's root
first on its path, so it reads the installation that asked rather than
whichever one the environment would find; and it is started without the
current directory on that path, since it runs in a home that may hold any
module name.

Local validation -- the settings, the target checkouts, the author allowlist,
a token for every ``REPOS`` entry, and every agent binary the roles run --
makes no GitHub call. The full check adds exactly one read-only call per
``REPOS`` entry, through ``token_probe``, made in that interpreter with the
token it found, which never leaves it. ``check`` answers 0 when nothing was
found, and otherwise 1 with one line on standard error per problem. The
interpreter's own standard error is captured rather than shared: a warning the
configuration prints as it loads stops nothing and is not repeated, and an
interpreter that stops before it reports is one problem too, naming its exit
status and the last line it wrote. Nothing is written anywhere: no label,
issue, agent, or workflow state is touched.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping

from orchestrator.service import paths
from orchestrator.service.environment import service_environment
from orchestrator.service.settings_report import REACH_GITHUB

# What the interpreter runs: this package's root first on the path, then the
# report on the arguments after it.
_REPORT = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "from orchestrator.service import settings_report; "
    "settings_report.report(sys.argv[2:])"
)

_READY = (
    "The service can run: its settings resolve, every repository's token "
    "reaches it, and every agent is on its PATH\n"
)
_READY_LOCALLY = (
    "The service can run as far as this host shows: its settings resolve, "
    "every repository has a token, and every agent is on its PATH; GitHub "
    "was not asked\n"
)


def problems(shell: Mapping[str, str], *, reach_github: bool) -> list[str]:
    """What keeps the service set up from ``shell`` from running, a line each.

    Only the service's environment is taken from ``shell``. With
    ``reach_github``, each repository's token is also proved to read it.
    """
    service = service_environment(shell)
    home = service.get("HOME")
    try:
        reported = subprocess.run(
            (
                sys.executable, "-P", "-c", _REPORT, str(paths.PACKAGE_ROOT),
                *((REACH_GITHUB,) if reach_github else ()),
            ),
            cwd=home,
            env=service,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        return [f"the settings cannot be checked from the service's home {home}: {error}"]
    return _read(reported)


def _read(reported: subprocess.CompletedProcess[bytes]) -> list[str]:
    """The problem lines the interpreter reported, or the one why it reported none.

    One that stopped before writing its report is named with the last line of
    its standard error, which for an uncaught error is the error itself.
    """
    try:
        lines = json.loads(reported.stdout) if reported.returncode == 0 else None
    except ValueError:
        lines = None
    if isinstance(lines, list):
        return [str(line) for line in lines]
    said = reported.stderr.decode(errors="replace").strip()
    last = said.splitlines()[-1] if said else ""
    why = f": {last}" if last else ""
    return [f"the settings check stopped before it reported (exit status {reported.returncode}){why}"]


def check(shell: Mapping[str, str], *, reach_github: bool) -> int:
    """Run ``check`` for a service set up from ``shell``, and answer with its status."""
    found = problems(shell, reach_github=reach_github)
    for problem in found:
        sys.stderr.write(f"{problem}\n")
    if found:
        return 1
    sys.stdout.write(_READY if reach_github else _READY_LOCALLY)
    return 0
