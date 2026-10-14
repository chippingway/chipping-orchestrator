# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The systemd user manager and logind, asked through ``systemctl`` and ``loginctl``.

Every call is one command run to completion with its output captured and
standard input closed, so nothing waits on the operator, and bounded: one
that has not finished in 30 seconds is killed and answered as a failure, the
same as one whose binary cannot be run at all. ``run_command`` is where a call
leaves the process, and the seam a test stands a fake systemd in for; it never
raises, so every caller reads one ``Completed`` whatever happened.

``systemctl`` asks the calling user's own manager, through ``--user``, and
``loginctl`` asks logind. Two answers are read here rather than by each
caller: ``manager_problem``, why the user manager cannot be reached, if it
cannot -- no systemd, no manager for this login, or no bus to reach it
through -- and ``linger_enabled``, whether logind starts the user's manager
at boot and keeps it after the last login ends, which is what lets a user
service run unattended.

Nothing here imports from the package.
"""
from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import NamedTuple

_TIMEOUT_SECONDS = 30

_SYSTEMCTL = ("systemctl", "--user")

_LINGERING = "Linger=yes"


class Completed(NamedTuple):
    """How one command ended: its exit status, or ``None`` where it never ran to one."""

    status: int | None
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        """Whether the command ran and exited 0."""
        return self.status == 0

    def reason(self) -> str:
        """What the command said about how it ended: its last line of stderr, else its status."""
        said = self.stderr.strip()
        if said:
            return said.splitlines()[-1]
        return f"exit status {self.status}"


def run_command(argv: Sequence[str], timeout: float = _TIMEOUT_SECONDS) -> Completed:
    """Run ``argv`` to completion within ``timeout`` seconds, and say how it ended."""
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Completed(None, "", f"{argv[0]} did not finish within {timeout} seconds")
    except OSError as error:
        return Completed(None, "", f"{argv[0]} cannot be run ({error})")
    return Completed(completed.returncode, completed.stdout, completed.stderr)


def systemctl(*arguments: str) -> Completed:
    """Run ``systemctl --user`` with ``arguments``."""
    return run_command((*_SYSTEMCTL, *arguments))


def loginctl(*arguments: str) -> Completed:
    """Run ``loginctl`` with ``arguments``."""
    return run_command(("loginctl", *arguments))


def manager_problem() -> str | None:
    """Why ``systemctl --user`` cannot reach the user's manager, or ``None`` where it can.

    The manager's own version is the property asked for: answering for it
    takes nothing but a manager to answer.
    """
    probe = systemctl("show", "--property=Version")
    if probe.succeeded:
        return None
    return probe.reason()


def linger_enabled(user: str) -> bool:
    """Whether logind keeps ``user``'s manager running with nobody logged in.

    An answer that cannot be read counts as no, so a caller that enables
    linger on a no asks logind rather than assuming.
    """
    shown = loginctl("show-user", user, "--property=Linger")
    return shown.succeeded and shown.stdout.strip() == _LINGERING
