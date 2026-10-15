# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""``remove``: the service ``init`` installed stopped, disabled, and its unit deleted, and nothing else.

With no unit at ``~/.config/systemd/user/chipping-orchestrator.service``,
``remove`` says so and exits 0 having asked systemd nothing. Otherwise, once
the user manager answers, it stops the service, disables it, deletes the unit,
and has the manager reload its units, which unloads the service. Last, where
the manager still remembers the service as failed, it forgets that with
``reset-failed``: a service stopped cleanly is gone with the reload, and
``reset-failed`` refuses a unit the manager no longer has loaded. Only a
state ``is-failed`` prints counts as its answer -- ``failed``, or an unloaded
unit's ``inactive`` among the others -- so a query the manager refuses, or one
that never finishes, is a failed step like any other rather than a no.

A step that fails exits 1 with the manager's reason, taking no step after it.
Until the stop and the disable succeed the unit is kept, so a service still
running is never left without the unit it is stopped through, and ``remove``
run again takes it up from the start; a reload or a reset that fails once the
unit is deleted names the command that finishes it.

Nothing else is touched, and ``remove`` says so: the ``.env``, the token files,
the logs, the worktrees, and linger are kept, for a later ``init`` to install
the service over again or for the operator to delete. Nothing here imports
``orchestrator.config``.
"""
from __future__ import annotations

import os

from orchestrator.service import paths, systemd
from orchestrator.service.lifecycle import STOP, ServiceRefusal, act, answered, require_manager
from orchestrator.service.unit_file import UNIT_NAME, unit_path

COMMAND = "remove"

_ABSENT = "No service is installed at {0}, so remove changed nothing\n"
_KEPT = "; {0} is kept, so run chipping-orchestrator remove again once that is repaired"
_DELETED = "; {0} is deleted, so finish with: systemctl --user {1}"
_UNANSWERED = (
    "systemctl --user is-failed {0} answered with no state ({1}), so whether "
    "the user manager still remembers the service as failed is unknown; {2} is "
    "deleted, so finish once the manager answers: where systemctl --user "
    "is-failed {0} says failed, run systemctl --user reset-failed {0}"
)
# The state `is-failed` prints for a service that is not failed, an unloaded
# one answering as inactive; anything else, or none, is no answer at all.
_NOT_FAILED = frozenset((
    "active",
    "reloading",
    "refreshing",
    "inactive",
    "activating",
    "deactivating",
    "maintenance",
))
_REMOVED = (
    "Stopped and disabled {0}, deleted {1}, and had the user manager forget it\n"
    "Kept, since remove deletes nothing else: the configuration at {2}, the "
    "token files under ~/.config, the logs in its LOG_DIR, the worktrees, and "
    "linger, which loginctl disable-linger turns off\n"
)


def remove() -> int:
    """Run ``remove``, and answer with its status."""
    return answered(_remove)


def _remove() -> str:
    """Stop, disable, and delete the installed unit, and have the manager forget it."""
    unit = unit_path()
    if not os.path.lexists(unit):
        return _ABSENT.format(unit)
    require_manager(COMMAND)
    kept = _KEPT.format(unit)
    act(STOP, UNIT_NAME, advice=kept)
    act("disable", UNIT_NAME, advice=kept)
    try:
        unit.unlink(missing_ok=True)
    except OSError as error:
        raise ServiceRefusal(f"{unit} cannot be deleted ({error}){kept}") from error
    act("daemon-reload", advice=_DELETED.format(unit, "daemon-reload"))
    failed = systemd.systemctl("is-failed", UNIT_NAME)
    if failed.succeeded:
        act("reset-failed", UNIT_NAME, advice=_DELETED.format(unit, f"reset-failed {UNIT_NAME}"))
    elif failed.stdout.strip() not in _NOT_FAILED:
        raise ServiceRefusal(_UNANSWERED.format(UNIT_NAME, failed.reason(), unit))
    return _REMOVED.format(UNIT_NAME, unit, paths.settings_file())
