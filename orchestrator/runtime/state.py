# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The mutable state one polling run carries.

The signal handler, the watchdog thread, the per-repo tick workers, and the
loop driving them all read and write the same few values, so they travel as
one object the composition point creates and hands out. Nothing here is a
module-level default: a caller that wants a run stopped, drained, or already
signaled builds the state that says so and passes it in.

The host claim travels the same way and for the same reason the scheduler
does: the composition point takes it, and an owner deep in a pass has to read
what THIS run holds rather than ask a module what some run once held. Its
default is the claim a run that never took one has, which is the answer that
lets nothing be reclaimed -- a caller that did not compose a run is not one
that may delete a checkout.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from orchestrator.runtime.exclusion import HostClaim, UnclaimedHost
from orchestrator.scheduler.service import IssueScheduler

# The shell convention for "stopped by signal N". `run.sh` keys on the two
# codes it produces (130 / 143) to skip its restart loop, so the base is part
# of what a signal stop means rather than a detail of one exit path.
SIGNAL_EXIT_BASE = 128


@dataclass
class RuntimeState:
    """What one polling run is stopped, drained, and exited by."""

    running: bool = True
    received_signal: int | None = None
    active_scheduler: IssueScheduler | None = None
    host_claim: HostClaim = field(default_factory=UnclaimedHost)
    shutdown_complete: threading.Event = field(default_factory=threading.Event)

    def signal_exit_code(self) -> int:
        """Return a shell-style signal exit code, or zero when none arrived."""
        if self.received_signal is None:
            return 0
        return SIGNAL_EXIT_BASE + self.received_signal
