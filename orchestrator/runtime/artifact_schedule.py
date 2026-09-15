# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When the polling process owes itself another artifact maintenance pass.

The pass, and every hold it runs under, are `artifacts`'. What this owner
answers is only whether a turn is owed between two polling passes, and whether
a turn already handed out may still start once those holds are taken. Nothing
else asks it: a `--cleanup-terminal-artifacts` run is a pass on demand, whose
schedule is having been asked, and `--once` asks for no pass at all.

Two cadences, read at every ask. `TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS`
is a duration on the monotonic clock; `TERMINAL_ARTIFACT_CLEANUP_WINDOW` is a
local time of day in `TERMINAL_ARTIFACT_CLEANUP_TIMEZONE`, and where it is set
it takes precedence. Both are held in this process's memory and nowhere else.
"""
from __future__ import annotations

import datetime
import logging
import time
from zoneinfo import ZoneInfo

from orchestrator import config

# The worktree-lifecycle channel `artifacts` reports every pass on, because a
# turn that lapsed before its pass started is a fact about the artifacts, and
# an operator filtering for what happened to them is asking about that night.
log = logging.getLogger("orchestrator.worktree_lifecycle")

# How long a window's turn that deferred before reclaiming anything waits
# before it is attempted again. Elapsed rather than read off the wall clock, so
# a clock stepped back inside the window cannot turn one deferral into a retry
# every poll. What it spaces out is the cost of an attempt rather than of a
# pass: every one closes admission and may wait out the barrier's whole bound
# on the work it is keeping out, so a busy night is asked a handful of times
# instead of once a poll.
_WINDOW_RETRY_SECONDS = 900.0

_LAPSED_LOG = (
    "artifact maintenance deferred: no unspent cleanup window was open once "
    "this host was quiet and held, so nothing was touched"
)


def _window_opened_on(
    window: tuple[datetime.time, datetime.time], zone: ZoneInfo | None,
) -> datetime.date | None:
    """The local date the window open right now opened on, or `None` outside it.

    The date is the window's name. An end earlier than its start crosses
    midnight, and the hours after midnight belong to the window that opened
    the evening before, so one night is one window on both sides of it.

    The instant is converted by the zone's own rules rather than by an offset
    held anywhere here: a wall-clock hour a spring-forward transition skips is
    never inside, and one a fall-back transition repeats is inside twice under
    the one date -- which is what keeps that hour from owing a second pass.
    """
    start, end = window
    local = datetime.datetime.fromtimestamp(time.time(), tz=zone)
    clock = local.time()
    if start < end:
        return local.date() if start <= clock < end else None
    if start <= clock:
        return local.date()
    if clock < end:
        return local.date() - datetime.timedelta(days=1)
    return None


class DueGate:
    """When this run owes another maintenance pass, and whether it may start.

    In memory and nowhere else. What a persisted record would buy is one fewer
    pass after a restart, and a pass costs nothing to repeat -- it reads the
    host as it is now, and an artifact already gone is reported as done. What
    it would cost is a file about a teardown, written by a process whose whole
    point is that it keeps no state of its own.

    With no window set, the cadence is the interval, and it is monotonic
    because an interval is a duration and not an hour of the day: a clock
    stepped by NTP, a suspend, or a timezone change would otherwise bring a
    pass forward or push it out by however far the wall clock moved. Its turn
    is spent when it is HANDED OUT rather than when the pass that took it gets
    anywhere. A pass that finds the host busy waits for the next interval
    instead of retrying on the next poll, because retrying means closing
    admission and waiting on it again: once a day that is free, and once a
    minute it is a tax on exactly the work the deferral was protecting.

    A set window takes precedence, and it IS an hour of the day, so it is read
    off the wall clock in the configured zone. A fresh gate owes nothing
    outside it: a restart outside waits for the next window, and a restart
    inside may repeat a pass the process before it already made. Its turn is
    spent only by the pass that gets past every deferral, as the last thing
    before that pass reads anything -- so a pass that then finds nothing,
    keeps or fails every candidate, raises, or runs out of budget has had its
    night, and one that deferred before that point has not. A deferred window
    is owed again, but no sooner than `_WINDOW_RETRY_SECONDS` elapsed after the
    deferral, for the same tax the interval refuses to charge. Nothing is
    caught up on: a window that closed unspent is simply gone.

    One attempt is three asks, in order: `due` between polling passes, then
    `admitted` from inside the pass once the host is quiet and held, then
    `settle` once the pass has returned, whatever it did.
    """

    def __init__(self) -> None:
        self._spent: float | None = None
        self._spent_window: datetime.date | None = None
        self._deferred_at: float | None = None
        self._admitted = False

    def due(self) -> bool:
        """Whether a pass is owed now: the window's when set, else the interval's."""
        window = config.TERMINAL_ARTIFACT_CLEANUP_WINDOW
        if window is None:
            return self._interval_due()
        if self._deferred_at is not None and (
            time.monotonic() - self._deferred_at < _WINDOW_RETRY_SECONDS
        ):
            return False
        opened = _window_opened_on(
            window, config.TERMINAL_ARTIFACT_CLEANUP_TIMEZONE,
        )
        return opened is not None and opened != self._spent_window

    def admitted(self) -> bool:
        """Whether the pass handed a turn may start now, spending a window if so.

        The interval's turn was spent when `due` handed it out, so there is
        nothing left to ask. A window is read again, because the barrier's
        wait and the handover of the host both take time the window may not
        have had left, and whichever window is open now is the one spent.
        """
        window = config.TERMINAL_ARTIFACT_CLEANUP_WINDOW
        if window is None:
            return True
        opened = _window_opened_on(
            window, config.TERMINAL_ARTIFACT_CLEANUP_TIMEZONE,
        )
        if opened is None or opened == self._spent_window:
            log.info(_LAPSED_LOG)
            return False
        self._spent_window = opened
        self._admitted = True
        return True

    def settle(self) -> None:
        """Close the attempt `due` handed out, dating it if it never started.

        Dated after the pass returns rather than when it was handed out,
        because the barrier and the handover both wait before a deferral is
        known, and the retry is owed its whole spacing after that. Only a
        window reads the date: the interval's deferral is already the rest of
        its interval.
        """
        if not self._admitted:
            self._deferred_at = time.monotonic()
        self._admitted = False

    def _interval_due(self) -> bool:
        """Whether the interval has elapsed, taking its turn if it has."""
        asked = time.monotonic()
        if self._spent is not None and (
            asked - self._spent < config.TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS
        ):
            return False
        self._spent = asked
        return True
