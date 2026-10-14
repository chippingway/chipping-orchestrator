# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The systemd user unit ``init`` installs, and where it and the unit it replaces sit.

The unit is ``~/.config/systemd/user/chipping-orchestrator.service``. It runs
``-m orchestrator run`` under the interpreter of the package that installed
it, so the service cannot pick up another installation through ``PATH``, in
the home directory, with the ``PATH`` ``environment`` captures from the shell
that installed it: a user service inherits no login shell's ``PATH``, and it is
that one which finds the agents. It restarts 30 seconds after a failure with
no limit on how often, since a GitHub outage at boot must not leave it failed
for good, and the ``128 + signum`` a graceful SIGINT or SIGTERM stop exits with
counts as a success, so ``systemctl stop`` is not recorded as a failure.

``render_unit`` writes those two values in double quotes, each backslash and
quote escaped and every ``%`` doubled: systemd unquotes and unescapes both
lines, then expands its ``%`` specifiers in what is left. A value systemd
would refuse or still read back changed is refused with ``UnitValueError``
instead: a control character, which no unit line carries, and in the
interpreter a quote or a backslash, which systemd refuses in the path it
executes, or a ``$``, which it expands in the command's ``argv[0]`` but not in
that path, so no spelling reaches both the same.

``~/.config/systemd/user/orchestrator.service`` is the hand-written unit for
the same poller that the guides of releases up to v0.13.0 describe, and
``legacy_unit_refusal`` is how ``init`` refuses to install beside it, so two
pollers never run at once. Both paths are read off the home directory at call
time.

Nothing here imports from the package.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

UNIT_NAME = "chipping-orchestrator.service"
LEGACY_UNIT_NAME = "orchestrator.service"

_UNIT_DIR = Path(".config", "systemd", "user")

_UNIT = """\
# Written by chipping-orchestrator init, which rewrites this file each time it
# runs; keep a local change in a drop-in: systemctl --user edit {name}
[Unit]
Description=chipping-orchestrator
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=%h
ExecStart={interpreter} -m orchestrator run
Environment={search_path}
Restart=on-failure
RestartSec=30
SuccessExitStatus=130 143

[Install]
WantedBy=default.target
"""

# Each character a quoted word spells otherwise: the two unquoting reads
# first, and the `%` that specifier expansion reads after them.
_ESCAPES = str.maketrans({"\\": r"\\", '"': r'\"', "%": "%%"})

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

# What systemd refuses in the path it executes, or rewrites in `argv[0]`.
_UNCARRIED_COMMAND = re.compile(r"[\"'\\$]")

_LEGACY = (
    "{0} is a hand-written unit for the same poller, and init installs no "
    "second service beside it, since the two would poll at once; stop, "
    f"disable, and delete it first -- systemctl --user stop {LEGACY_UNIT_NAME}, "
    f"systemctl --user disable {LEGACY_UNIT_NAME}, rm {{0}}, and systemctl "
    "--user daemon-reload -- and run init again"
)


class UnitValueError(ValueError):
    """A value the unit cannot carry as it is, with what to do about it."""


def unit_path() -> Path:
    """Where ``init`` installs the service's unit."""
    return Path.home() / _UNIT_DIR / UNIT_NAME


def legacy_unit_refusal() -> str | None:
    """Why ``init`` installs nothing beside the hand-written unit, or ``None`` where there is none."""
    legacy = Path.home() / _UNIT_DIR / LEGACY_UNIT_NAME
    if not os.path.lexists(legacy):
        return None
    return _LEGACY.format(legacy)


def _quoted(word: str, described: str) -> str:
    """``word`` as one double-quoted unit word systemd reads back unchanged."""
    if _CONTROL.search(word):
        raise UnitValueError(
            f"{described} holds a control character, which no line of a systemd unit can carry",
        )
    return f'"{word.translate(_ESCAPES)}"'


def render_unit(interpreter: str, search_path: str) -> str:
    """The unit running ``interpreter`` with ``search_path`` as the service's ``PATH``."""
    described = f"the interpreter {interpreter!r}"
    if not os.path.isabs(interpreter):
        raise UnitValueError(
            f"{described} running init is not an absolute path, which a unit's ExecStart needs; "
            "run init with the installed package's own interpreter",
        )
    if _UNCARRIED_COMMAND.search(interpreter):
        raise UnitValueError(
            f"{described} holds a quote, a backslash, or a '$', which systemd refuses or rewrites "
            "in the command it starts the service with; install the package under a path without one",
        )
    return _UNIT.format(
        name=UNIT_NAME,
        interpreter=_quoted(interpreter, described),
        search_path=_quoted(f"PATH={search_path}", "the captured PATH"),
    )
