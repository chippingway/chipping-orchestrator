# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The variables the user manager hands every service it starts, read from its configuration as it reads them.

A user service inherits the user manager's environment as it stands, its own
``HOME`` and ``USER`` included, beneath the variables its unit sets, so what
the manager's configuration puts there reaches the service as surely as
``.env`` does. ``manager_environment`` reads the parts of it that live in
files:

- ``ManagerEnvironment=``, and over it ``DefaultEnvironment=``, in the
  ``[Manager]`` section of ``user.conf`` --
  ``~/.config/systemd/user.conf``, or ``/etc/systemd/user.conf`` where the
  home holds none -- and then of each ``user.conf.d`` drop-in in
  ``~/.config/systemd`` and under ``/etc``, ``/run``, ``/usr/local/lib``, and
  ``/usr/lib``, the home's ranking first. Each value is read as an
  ``Environment=`` one is, an empty one dropping what came before, with the
  specifiers the manager expands in its own configuration: of those, ``%%``,
  ``%h``, ``%u``, ``%U``, and ``%G`` -- the home, the user's name and ID, and
  the user's group ID -- are read, and any other is refused, the host and
  system ones systemd expands as surely as a letter it would drop the word
  for. Neither may set what moves where systemd reads its own configuration:
  ``ManagerEnvironment=`` sets the manager's own environment, so ``HOME`` or
  an ``XDG_`` directory variable there is refused, and the ``environment.d``
  generator inherits ``DefaultEnvironment=``, so ``HOME`` or
  ``XDG_CONFIG_HOME`` there is;
- then what the ``environment.d`` generator adds: each assignment of the
  ``*.conf`` files in ``~/.config/environment.d`` and in ``environment.d``
  under ``/etc``, ``/run``, ``/usr/local/lib``, and ``/usr/lib``, in the order
  systemd reads them, its value expanded against the variables set so far,
  the home, the user's name, and the user's runtime directory among them.

Files are listed by ``unit_drop_ins.manager_files``, hidden ones skipped, and
read under ``unit_environment.SYSTEM_ROOT`` outside the home. A file that
cannot be read, or that holds what ``unit_syntax`` or ``environment_syntax``
does not read as systemd would, is refused with ``UnitEnvironmentError``,
naming the file and the variable and quoting no value. What the manager is told at run time --
``systemctl --user set-environment`` or ``import-environment``, as a desktop
session does -- and its own process environment past the home and the user
can only be learned by asking it, so neither is read.

Nothing here imports from the package but the owners named above.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from functools import partial
from pathlib import Path
from types import MappingProxyType

from orchestrator.service import unit_environment as _unit
from orchestrator.service.environment_syntax import expanded, file_assignments
from orchestrator.service.unit_drop_ins import manager_files
from orchestrator.service.unit_syntax import UnitSyntaxError, environment_assignments, service_settings

_MANAGER_ENVIRONMENT = "ManagerEnvironment"
_DEFAULT_ENVIRONMENT = "DefaultEnvironment"
# What each directive may not set, since it would move where systemd reads its
# own configuration: the manager's for `ManagerEnvironment=`, which sets the
# manager's own environment, and the generator's `environment.d` for
# `DefaultEnvironment=`, which the generator inherits.
_MOVING = MappingProxyType({
    _MANAGER_ENVIRONMENT: frozenset((
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_CONFIG_DIRS",
        "XDG_DATA_HOME",
        "XDG_DATA_DIRS",
        "XDG_RUNTIME_DIR",
    )),
    _DEFAULT_ENVIRONMENT: frozenset(("HOME", "XDG_CONFIG_HOME")),
})
_UNREAD = "{0} cannot be read as systemd reads it ({1})"
_MOVED = "{0} sets {1} with {2}=, which moves where systemd reads its own configuration, so only systemd can resolve it"
_UNLISTED = "the user manager's configuration cannot be listed ({0})"

# How `user.conf` is read, and what reads the assignments of a value in it.
_manager_settings = partial(service_settings, section="[Manager]")
_Assignments = Callable[[str], list[tuple[str, str]]]
_Layers = dict[str, dict[str, str]]


def manager_environment(user: str) -> dict[str, str]:
    """Every variable the user manager's configuration hands ``user``'s services, as the manager assembles them."""
    home = Path.home()
    try:
        user_conf, environment_d = manager_files(home, _unit.SYSTEM_ROOT)
    except OSError as error:
        raise _unit.UnitEnvironmentError(_UNLISTED.format(error)) from error
    specifiers = {
        "h": str(home),
        "u": user,
        "U": str(os.getuid()),
        "G": str(os.getgid()),
    }
    layers = _manager_layers(user_conf, partial(environment_assignments, specifiers=specifiers))
    return _environment_d(environment_d, home, user, layers)


def _manager_layers(user_conf: list[Path], assignments: _Assignments) -> dict[str, str]:
    """What ``ManagerEnvironment=`` and then ``DefaultEnvironment=`` set across ``user_conf``.

    The second lies over the first. Each value is read by ``assignments``,
    with the manager's specifiers.
    """
    layers: _Layers = {_MANAGER_ENVIRONMENT: {}, _DEFAULT_ENVIRONMENT: {}}
    for path in user_conf:
        for setting in _read_file(path, _manager_settings):
            if setting[0] in layers:
                _apply(layers, path, setting, assignments)
    return {**layers[_MANAGER_ENVIRONMENT], **layers[_DEFAULT_ENVIRONMENT]}


def _apply(layers: _Layers, path: Path, setting: tuple[str, str], assignments: _Assignments) -> None:
    """Apply one ``ManagerEnvironment=`` or ``DefaultEnvironment=`` setting of the file at ``path`` to ``layers``."""
    directive, rvalue = setting
    if not rvalue:
        # An empty value drops every assignment before it.
        layers[directive] = {}
        return
    set_here = dict(_read_value(path, assignments, rvalue))
    moving = sorted(_MOVING[directive].intersection(set_here))
    if moving:
        raise _unit.UnitEnvironmentError(_MOVED.format(path, " and ".join(moving), directive))
    layers[directive] = {**layers[directive], **set_here}


def _environment_d(
    environment_d: list[Path],
    home: Path,
    user: str,
    assigned: dict[str, str],
) -> dict[str, str]:
    """``assigned`` with each assignment of the ``environment_d`` files applied, in order.

    Each value is expanded against the variables set so far, over what the
    user manager's own environment is known to hold.
    """
    known = {
        "HOME": str(home),
        "USER": user,
        "LOGNAME": user,
        "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}",
    }
    for path in environment_d:
        for key, rvalue in _read_file(path, file_assignments):
            expand = partial(expanded, environment={**known, **assigned}, name=key)
            assigned[key] = _read_value(path, expand, rvalue)
    return assigned


def _read_file[Read](path: Path, parse: Callable[[str], Read]) -> Read:
    """What ``parse`` reads in the file at ``path``, refusing it naming ``path``."""
    try:
        # Decoded as written, so the parser sees each line end systemd does.
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise _unit.UnitEnvironmentError(_UNREAD.format(path, error)) from error
    return _read_value(path, parse, text)


def _read_value[Read](path: Path, parse: Callable[[str], Read], text: str) -> Read:
    """What ``parse`` reads in ``text``, from the file at ``path``, refusing it naming ``path``."""
    try:
        return parse(text)
    except UnitSyntaxError as unread:
        raise _unit.UnitEnvironmentError(_UNREAD.format(path, unread)) from unread
