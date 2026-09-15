# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The clocks a due gate reads, and the window it reads the wall one against.

Both clocks are stood in together and moved separately, because what the gate
owes is a relationship between them: a window is a wall-clock question put in
a zone, a retry is an elapsed-time question, and a test that moves one clock
without the other is how a retry is shown to be spaced by the one that cannot
jump.

The wall clock is held as an instant rather than as a local reading, so where
it lands in a zone is that zone's own rules' answer: the conversion the gate
owes is exercised rather than assumed.
"""
from __future__ import annotations

import contextlib
import datetime
import time
from collections.abc import Iterator
from unittest.mock import patch
from zoneinfo import ZoneInfo

from orchestrator import config

NIGHTLY_WINDOW = "03:00-05:00"
OVERNIGHT_WINDOW = "23:00-01:00"
NOVOSIBIRSK = "Asia/Novosibirsk"
UTC_ZONE = "UTC"
MINUTE_SECONDS = 60
HOUR_SECONDS = 3600
DAY_SECONDS = 86400

# The gate's own spacing between a deferral and the retry it is owed, spelled
# here rather than read off the owner so a test pins the contract and not
# whatever the constant happens to say.
RETRY_SECONDS = 900

_WINDOW_ATTR = "TERMINAL_ARTIFACT_CLEANUP_WINDOW"
_TIMEZONE_ATTR = "TERMINAL_ARTIFACT_CLEANUP_TIMEZONE"
_WALL_ATTR = "time"
_ELAPSED_ATTR = "monotonic"


def local(reading: str, zone: str = NOVOSIBIRSK) -> datetime.datetime:
    """The instant the wall clock in `zone` shows as `reading`."""
    return datetime.datetime.fromisoformat(reading).replace(tzinfo=ZoneInfo(zone))


class Clocks:
    """The wall clock and the monotonic one, installed over `time` together."""

    def __init__(self, instant: datetime.datetime) -> None:
        self.wall = instant.timestamp()
        self.elapsed: float = 0

    def advance(self, seconds: float) -> None:
        """Let time pass, which moves both clocks alike."""
        self.wall += seconds
        self.elapsed += seconds

    def reach(self, instant: datetime.datetime) -> None:
        """Let time pass until the wall clock shows `instant`."""
        self.advance(instant.timestamp() - self.wall)

    def step_wall(self, seconds: float) -> None:
        """Step the wall clock alone, as NTP or a suspend would."""
        self.wall += seconds

    @contextlib.contextmanager
    def installed(self) -> Iterator[Clocks]:
        """Both clocks, answering from this object for as long as it is held."""
        with (
            patch.object(time, _WALL_ATTR, side_effect=lambda: self.wall),
            patch.object(time, _ELAPSED_ATTR, side_effect=lambda: self.elapsed),
        ):
            yield self


class HeldHost:
    """A host claim whose handover takes time, and which may be refused.

    Taken, so a pass gets as far as asking for the host. The handover moves
    `clocks` on by `takes` before it answers, because what a scheduled pass
    owes its window is a reading of the clock AFTER that wait; `sole` is the
    answer, and refusing it stands in for another process holding the host.
    """

    taken = True

    def __init__(
        self, clocks: Clocks | None = None, *, takes: float = 0, sole: bool = True,
    ) -> None:
        self.handovers = 0
        self._clocks = clocks
        self._takes = takes
        self._sole = sole

    @contextlib.contextmanager
    def exclusive(self) -> Iterator[bool]:
        """Count the handover, spend its time, and give the answer."""
        self.handovers += 1
        if self._clocks is not None:
            self._clocks.advance(self._takes)
        yield self._sole


@contextlib.contextmanager
def windowed(window: str | None, zone: str = NOVOSIBIRSK) -> Iterator[None]:
    """The window settings as a started process holds them; `None` is unset."""
    if window is None:
        clock_times, resolved_zone = None, None
    else:
        start, end = window.split("-")
        clock_times = (
            datetime.time.fromisoformat(start), datetime.time.fromisoformat(end),
        )
        resolved_zone = ZoneInfo(zone)
    with (
        patch.object(config, _WINDOW_ATTR, clock_times),
        patch.object(config, _TIMEZONE_ATTR, resolved_zone),
    ):
        yield
