# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The installed unit's drop-ins, and any ``*.conf`` set, found and ordered as systemd finds and applies them.

A drop-in is a ``*.conf`` file in a ``chipping-orchestrator.service.d``
directory, in a ``chipping-.service.d`` one -- the unit's name cut after its
dash -- or in a ``service.d`` one for every service, under each directory
systemd reads user units from by default: the user's own configuration and
data directories under the home, and the system-wide ones under ``/etc``,
``/run``, and ``/usr``, in systemd's order. The directories named for the
unit rank above ``service.d`` ones. Generated and transient units' directories
are not read, since nothing generates this unit.

``conf_files`` answers the files systemd reads from a list of such
directories, as its own lister does for drop-ins and for ``environment.d`` and
``user.conf.d``: each ``*.conf`` file but a hidden one, whose name starts with
a dot -- the one systemd skips, so ``.disabled.conf`` applies nowhere -- the
one in the directory ranked first masking any of its name further down, and
those left in the order of their names. ``manager_files`` answers the user
manager's own: ``~/.config/systemd/user.conf``, or ``/etc/systemd/user.conf``
where the home holds none, then each ``user.conf.d`` drop-in in
``~/.config/systemd`` and under ``/etc``, ``/run``, ``/usr/local/lib``, and
``/usr/lib``, the home's ranking first; and the generator's ``environment.d``
files in ``~/.config`` and under the same four. ``drop_ins`` and
``manager_files`` are given the home and the root the system-wide directories
are read under, so a caller can point the second at a scratch directory; a
directory that cannot be listed raises its ``OSError``. Nothing here imports
from the package but ``unit_file``.
"""
from __future__ import annotations

import os
from pathlib import Path

from orchestrator.service.unit_file import UNIT_NAME

# The drop-in directories named for the unit and for its name cut after each
# dash, then the one for every service, as systemd ranks them.
_NAMED_DROP_INS = (f"{UNIT_NAME}.d", "chipping-.service.d")
_TYPE_DROP_INS = "service.d"
_CONF = ".conf"

# The user manager's `user.conf` in the home and on the system, and the system
# directories its `user.conf.d` and the generator's `environment.d` sit in, in
# the order they rank, each below the home's.
_USER_CONF = Path(".config", "systemd", "user.conf")
_SYSTEM_USER_CONF = Path("etc", "systemd", "user.conf")
_USER_CONF_D = "systemd/user.conf.d"
_ENVIRONMENT_D = "environment.d"
_SYSTEM_CONF_DIRS = ("etc", "run", "usr/local/lib", "usr/lib")
_HIDDEN = "."

# Where systemd reads user units from by default, in its order, each under
# the home or the root, `_RUNTIME` being the user's runtime directory there.
# Generated and transient units' directories are left out, since nothing
# generates this unit.
_HOME = "home"
_ROOT = "root"
_RUNTIME = f"run/user/{os.getuid()}"
_SEARCH_PATH = (
    (_HOME, ".config/systemd/user.control"),
    (_ROOT, f"{_RUNTIME}/systemd/user.control"),
    (_HOME, ".config/systemd/user"),
    (_ROOT, "etc/xdg/systemd/user"),
    (_ROOT, "etc/systemd/user"),
    (_ROOT, f"{_RUNTIME}/systemd/user"),
    (_ROOT, "run/systemd/user"),
    (_HOME, ".local/share/systemd/user"),
    (_ROOT, "usr/local/share/systemd/user"),
    (_ROOT, "usr/share/systemd/user"),
    (_ROOT, "usr/local/lib/systemd/user"),
    (_ROOT, "usr/lib/systemd/user"),
)


def drop_ins(home: Path, root: Path) -> list[Path]:
    """Each drop-in systemd applies to the unit, in the order it applies them."""
    return conf_files(_directories(home, root))


def manager_files(home: Path, root: Path) -> tuple[list[Path], list[Path]]:
    """The user manager's ``user.conf`` files, and the generator's ``environment.d`` ones, each in the order read."""
    main = home / _USER_CONF
    if not os.path.lexists(main):
        main = root / _SYSTEM_USER_CONF
    mains = [main] if os.path.lexists(main) else []
    drop_ins = conf_files(_ranked(home, root, _USER_CONF_D))
    return [*mains, *drop_ins], conf_files(_ranked(home, root, _ENVIRONMENT_D))


def _ranked(home: Path, root: Path, below: str) -> list[Path]:
    """``below`` in the home's configuration directory, then under each system one, as they rank."""
    system = [root / base / below for base in _SYSTEM_CONF_DIRS]
    return [home / ".config" / below, *system]


def conf_files(directories: list[Path]) -> list[Path]:
    """Each ``*.conf`` file systemd reads from ``directories``, ranked first first, in the order it reads them."""
    found: dict[str, Path] = {}
    for directory in directories:
        for name in _conf_names(directory):
            found.setdefault(name, directory / name)
    return [found[applied] for applied in sorted(found)]


def _directories(home: Path, root: Path) -> list[Path]:
    """Every directory systemd reads the unit's drop-ins from, the ones that rank first first."""
    anchors = {_HOME: home, _ROOT: root}
    bases = [anchors[anchor] / below for anchor, below in _SEARCH_PATH]
    named = [base / name for base in bases for name in _NAMED_DROP_INS]
    return [*named, *(base / _TYPE_DROP_INS for base in bases)]


def _conf_names(directory: Path) -> list[str]:
    """The name of each drop-in in ``directory``, none where there is no such directory."""
    try:
        names = os.listdir(directory)
    except (FileNotFoundError, NotADirectoryError):
        return []
    shown = (name for name in names if not name.startswith(_HIDDEN))
    return [name for name in shown if name.endswith(_CONF)]
