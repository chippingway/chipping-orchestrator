# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""``start`` and ``restart``: the installed service launched once the local check finds nothing wrong.

The check is given the environment the service runs with, layered as systemd
layers it. A user service sets no ``HOME`` or ``USER`` of its own: it inherits
the user manager's, whose own -- the shell's, for the user the command runs as
-- lie beneath what the manager's configuration hands every service,
``ManagerEnvironment=``, ``DefaultEnvironment=``, and ``environment.d``, read
by ``manager_environment``, so a ``HOME`` that configuration sets is the one
the service, and the check, reads its ``.env`` under. Over all of it lies every
variable the installed unit and its drop-ins set, read off them as systemd
applies them -- the ``PATH`` ``init`` recorded, or the one a drop-in replaced
it with, among them. So the agents are judged where the service will look for
them, not where this shell happens to, and a setting a drop-in overrides is
judged as overridden. The check's interpreter runs in
the directory the unit and its drop-ins start the service in, the home unless a
``WorkingDirectory=`` says otherwise, so a path the settings give relative to
it is judged where the service will read it. Before the check, a missing unit
is refused naming ``init``; what ``unit_environment`` cannot read as systemd
would -- a drop-in taking the environment from a file or the user manager, or
replacing the command -- is refused naming it; and so is an environment the
unit and its drop-ins leave without a ``PATH``, since the service would then
run with the user manager's own, or with one holding an empty or relative
entry: the service runs each agent in an issue's worktree, so a lookup
through such an entry would depend on that worktree -- finding nothing there,
or whatever it holds -- however the check, run in one directory, resolved it.

The check is ``check --local``: the settings, the targets, the author
allowlist, a token for every repository, and every agent, with no GitHub call,
so a GitHub outage, which the service rides out by restarting, never keeps it
from being started. Until that check passes systemd is asked nothing, not even
whether its manager answers: each problem is printed, and the command exits 1
with the service as it was, a running one still running.

Then the manager reloads its units, so that what it launches is the
definition just checked rather than one it loaded before the files changed --
which the check cannot see, and which a reload is the one way to replace --
and is asked to ``start`` or ``restart`` the unit, each bounded past
systemd's own stop deadline since a restart stops a running service first and
a start waits out a stop already under way. A ``Type=simple`` service counts as
started as soon as its process does, so the command then watches it, asking
whether it is still active at each of the 5 seconds after the job. The whole
watch, its questions included, ends within 7 seconds of the job: each
question is bounded by the time left, so a manager slow to answer cannot
stretch it. One the manager answers active throughout is reported so and
exits 0. One that leaves it -- failed, or waiting out ``RestartSec`` to be
started again -- exits 1 with what it is now and the last lines of its
journal, as does a question that gets no state in the time left and a job the
manager refuses. ``pause`` and ``clock`` are the waiting and the time the
watch is measured by, which a test fakes together.

Nothing here imports ``orchestrator.config``: the settings are read in the
interpreter the check starts.
"""
from __future__ import annotations

import getpass
import os
import time
from collections.abc import Callable, Mapping
from functools import partial

from orchestrator.service import checks, systemd
from orchestrator.service.environment import service_environment
from orchestrator.service.lifecycle import ServiceRefusal, act, answered, require_manager
from orchestrator.service.manager_environment import manager_environment
from orchestrator.service.unit_environment import UnitEnvironmentError, unit_environment, unit_working_directory
from orchestrator.service.unit_file import UNIT_NAME, unit_path

START = "start"
RESTART = "restart"

# How long a launched service is watched, in seconds, asked at each of them
# whether it is still active; and how long the whole watch may take, the last
# question's answer included.
_WATCHED_SECONDS = 5
_WATCH_BOUND_SECONDS = 7

_JOURNAL_LINES = 20

# What waits between the questions asked of a launched service, and the
# clock the watch is measured by, in seconds.
Pause = Callable[[float], None]
Clock = Callable[[], float]

_NOT_INSTALLED = (
    "{0} does not exist, so there is no service to {1}; install it with "
    "chipping-orchestrator init"
)
_UNRESOLVED = (
    "{0}; {1} checks the service's environment only as systemd would assemble "
    "it, so it asked systemd nothing: take that out -- settings belong in .env, "
    "tokens in the token files, and any other variable in an Environment= line "
    "of the unit -- or start the service with systemctl --user, which checks "
    "nothing"
)
_UNRELOADED = "; {0} launched nothing, since the manager may still hold a definition other than the one checked"
_NO_PATH = (
    "{0} and its drop-ins leave the service no PATH of their own, so it would "
    "run with the user manager's, which {1} cannot check without asking it; "
    "chipping-orchestrator init writes the unit's, and an empty Environment= "
    "in a drop-in drops it"
)
_RELATIVE_PATH = (
    "{0} and its drop-ins give the service a PATH with an empty or relative "
    "entry, through which an agent would be looked up in whichever issue "
    "worktree it is started in, not where {1} can check it; make every entry "
    "an absolute directory, as chipping-orchestrator init writes them"
)
_UNCHECKED = (
    "chipping-orchestrator {0} left the service as it was: it would not run "
    "until the problems above are repaired"
)
_LEFT = (
    f"{UNIT_NAME} was not seen active through the {_WATCHED_SECONDS} seconds "
    "after systemctl --user {0}: {1}"
)
_NO_STATE = "systemctl --user is-active gave no state ({0})"
_NO_TIME = f"no time was left in the {_WATCH_BOUND_SECONDS}-second watch to ask whether it is active"
_ACTIVE = (
    f"{UNIT_NAME} is active {_WATCHED_SECONDS} seconds after systemctl --user "
    f"{{0}}; follow its journal with: journalctl --user-unit {UNIT_NAME} -f\n"
)


def launch(
    command: str,
    shell: Mapping[str, str],
    *,
    pause: Pause = time.sleep,
    clock: Clock = time.monotonic,
) -> int:
    """Run ``command``, ``start`` or ``restart``, for the service set up from ``shell``; answer its status.

    Only ``HOME`` and ``USER`` are taken from ``shell``; the rest of the
    environment checked is what the unit and its drop-ins set.
    """
    return answered(partial(_launch, command, shell, pause, clock))


def _launch(command: str, shell: Mapping[str, str], pause: Pause, clock: Clock) -> str:
    """Check the setup, then launch the service and watch it stay active."""
    found = _problems(command, shell)
    if found:
        raise ServiceRefusal("\n".join((*found, _UNCHECKED.format(command))))
    require_manager(command)
    act("daemon-reload", advice=_UNRELOADED.format(command))
    try:
        act(command, UNIT_NAME)
    except ServiceRefusal as refused:
        raise ServiceRefusal(_journaled(str(refused))) from refused
    unseen = _unseen(pause, clock)
    if unseen is not None:
        raise ServiceRefusal(_journaled(_LEFT.format(command, unseen)))
    return _ACTIVE.format(command)


def _problems(command: str, shell: Mapping[str, str]) -> list[str]:
    """What the local check finds, run with the environment and in the directory the unit gives the service.

    A ``PATH`` that would find an agent through the directory it is started
    in -- an issue's worktree, not the one the check runs in -- is refused
    first.
    """
    environment = _service_environment(command, shell)
    # An empty entry is the working directory, as a relative one is beneath it.
    entries = environment["PATH"].split(os.pathsep)
    if not all(map(os.path.isabs, entries)):
        raise ServiceRefusal(_RELATIVE_PATH.format(unit_path(), command))
    try:
        directory = unit_working_directory(shell.get("USER") or getpass.getuser())
    except UnitEnvironmentError as unresolved:
        raise ServiceRefusal(_UNRESOLVED.format(unresolved, command)) from unresolved
    return checks.service_problems(environment, reach_github=False, working_directory=directory)


def _service_environment(command: str, shell: Mapping[str, str]) -> dict[str, str]:
    """The environment the service runs with, layered as systemd layers it.

    ``shell``'s ``HOME`` and ``USER``, the user manager's own, lie beneath
    what the manager's configuration hands every service, which a user service
    inherits as it is, and those beneath what the unit and its drop-ins set.
    """
    unit = unit_path()
    if not os.path.lexists(unit):
        raise ServiceRefusal(_NOT_INSTALLED.format(unit, command))
    user = shell.get("USER") or getpass.getuser()
    try:
        assigned, inherited = unit_environment(user), manager_environment(user)
    except UnitEnvironmentError as unresolved:
        raise ServiceRefusal(_UNRESOLVED.format(unresolved, command)) from unresolved
    if "PATH" not in assigned:
        raise ServiceRefusal(_NO_PATH.format(unit, command))
    return {**service_environment(shell), **inherited, **assigned}


def _unseen(pause: Pause, clock: Clock) -> str | None:
    """Why the launched service was not seen active through the watch, or ``None`` where it was."""
    started = clock()
    for second in range(1, _WATCHED_SECONDS + 1):
        waited = started + second - clock()
        if waited > 0:
            pause(waited)
        remaining = started + _WATCH_BOUND_SECONDS - clock()
        if remaining <= 0:
            return _NO_TIME
        active = systemd.systemctl("is-active", UNIT_NAME, timeout=remaining)
        if not active.succeeded:
            return _seen(active)
    return None


def _seen(answer: systemd.Completed) -> str:
    """What a service the manager did not answer as active is, as its answer says."""
    state = answer.stdout.strip()
    if state:
        return f"it is {state}"
    return _NO_STATE.format(answer.reason())


def _journaled(why: str) -> str:
    """``why``, followed by the last lines the service wrote to the journal."""
    journal = systemd.journalctl(
        "--user-unit", UNIT_NAME, f"--lines={_JOURNAL_LINES}", "--no-pager", "--quiet",
    )
    if not journal.succeeded:
        return f"{why}; its journal cannot be read ({journal.reason()})"
    written = journal.stdout.rstrip()
    if not written:
        return f"{why}; its journal holds no lines"
    return f"{why}; the last lines of its journal:\n{written}"
