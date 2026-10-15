# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The environment and directory the installed unit starts the service in, read as systemd assembles them.

The service's own settings come from the unit ``init`` writes and from every
drop-in ``unit_drop_ins`` finds for it, applied after the unit in the order
systemd applies them. ``unit_environment`` answers the variables they set:
each ``Environment=`` assignment sets its variable, replacing what an earlier
one set, and an empty ``Environment=`` drops every assignment before it.
``unit_working_directory`` answers the directory the service starts in: the
last ``WorkingDirectory=`` read, the home where none is.

What cannot be resolved here is refused with ``UnitEnvironmentError`` rather
than guessed: ``EnvironmentFile=``, ``PassEnvironment=``, and
``UnsetEnvironment=``, which take the service's environment from a file or
from the user manager's own; ``ExecStart=`` in a drop-in, after which the
service no longer runs the package that installed it; an ``Environment=`` or
``WorkingDirectory=`` value ``unit_syntax`` does not read as systemd would;
and a unit, drop-in, or drop-in directory that cannot be read. ``%h`` and
``%u`` expand to the home and the user's name, as the user manager expands
them.

``SYSTEM_ROOT`` is the root the drop-in directories outside the home are read
under: ``/``, but for a test. Nothing here imports from the package but
``unit_drop_ins``, ``unit_file``, and ``unit_syntax``.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from types import MappingProxyType

from orchestrator.service.unit_drop_ins import drop_ins
from orchestrator.service.unit_file import unit_path
from orchestrator.service.unit_syntax import (
    UnitSyntaxError,
    environment_assignments,
    service_settings,
    working_directory,
)

SYSTEM_ROOT = Path("/")

_ENVIRONMENT = "Environment"
_WORKING_DIRECTORY = "WorkingDirectory"
_UNRESOLVED = "{0} sets {1}=, which only systemd can resolve"
# The reason quotes no value, which may hold a token.
_UNREAD = "{0} sets {1}= in a way not read here as systemd reads it: {2}"
# What the unit may not set, since it takes the service's environment from a
# file or from the user manager's own, and what a drop-in may not set besides,
# each with the reason it is refused.
_Refusals = Mapping[str, str]
_UNIT_REFUSALS = MappingProxyType({
    "EnvironmentFile": _UNRESOLVED,
    "PassEnvironment": _UNRESOLVED,
    "UnsetEnvironment": _UNRESOLVED,
})
_DROP_IN_REFUSALS = MappingProxyType({
    **_UNIT_REFUSALS,
    "ExecStart": "{0} sets {1}=, so the service would not run the package that installed it",
})

class UnitEnvironmentError(Exception):
    """Why the service's environment cannot be read without asking systemd, the whole reason as its text."""


def unit_environment(user: str) -> dict[str, str]:
    """Every variable the installed unit and its drop-ins set for ``user``'s service, as systemd applies them."""
    specifiers = {"h": str(Path.home()), "u": user}
    assigned: dict[str, str] = {}
    for path, key, rvalue in _settings():
        if key == _ENVIRONMENT:
            assigned = _assigned(assigned, path, rvalue, specifiers)
    return assigned


def unit_working_directory(user: str) -> str:
    """The directory the installed unit and its drop-ins start ``user``'s service in."""
    specifiers = {"h": str(Path.home()), "u": user}
    directory = specifiers["h"]
    for path, key, rvalue in _settings():
        if key != _WORKING_DIRECTORY:
            continue
        try:
            directory = working_directory(rvalue, specifiers)
        except UnitSyntaxError as unread:
            raise UnitEnvironmentError(_UNREAD.format(path, key, unread)) from unread
    return directory


def _settings() -> Iterator[tuple[Path, str, str]]:
    """Each ``[Service]`` setting of the unit, then of its drop-ins, with the file it is in, as systemd applies them.

    What only systemd can resolve is refused as it is reached.
    """
    for path, refusals in _unit_files():
        for key, rvalue in _file_settings(path):
            refusal = refusals.get(key)
            if refusal is not None:
                raise UnitEnvironmentError(refusal.format(path, key))
            yield path, key, rvalue


def _unit_files() -> list[tuple[Path, _Refusals]]:
    """The unit and each of its drop-ins, in the order systemd applies them, with what each may not set."""
    try:
        found = drop_ins(Path.home(), SYSTEM_ROOT)
    except OSError as error:
        raise UnitEnvironmentError(f"the unit's drop-ins cannot be listed ({error})") from error
    return [(unit_path(), _UNIT_REFUSALS), *((drop_in, _DROP_IN_REFUSALS) for drop_in in found)]


def _file_settings(path: Path) -> list[tuple[str, str]]:
    """The ``[Service]`` settings of the unit file at ``path``."""
    try:
        # Decoded as written: Python's newline translation would make two
        # line ends of a newline and a carriage return, which systemd reads as one.
        return service_settings(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, UnitSyntaxError) as error:
        raise UnitEnvironmentError(f"{path} cannot be read ({error})") from error


def _assigned(
    assigned: dict[str, str],
    path: Path,
    rvalue: str,
    specifiers: Mapping[str, str],
) -> dict[str, str]:
    """``assigned`` with the ``Environment=`` value ``rvalue`` of the unit file at ``path`` applied.

    An empty value drops every assignment before it.
    """
    if not rvalue:
        return {}
    try:
        assignments = environment_assignments(rvalue, specifiers)
    except UnitSyntaxError as unread:
        raise UnitEnvironmentError(_UNREAD.format(path, _ENVIRONMENT, unread)) from unread
    return {**assigned, **dict(assignments)}
