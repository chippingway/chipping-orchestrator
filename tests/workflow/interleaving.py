# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What happened between two of one tick's own steps, and nobody told it.

The window a fixture cannot otherwise reach. A tick posts a notice, records
how far the thread has been read some time later, and everything in between is
time a human can reply in. A case about such a window has to put its event
INSIDE the window rather than before the tick, which means hanging it on the
step that opens it.

Here rather than beside either caller because the packages that need these are
different ones, and a second copy would drift from whichever of them it was
not written for.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class _RacesTheStep:
    """One thing that happens the instant a step runs, just before it runs.

    Wraps the callable a case patches, so the step still does what it always
    did and the world it looks at is the one the race left. A class rather
    than a closure because a seam this repository patches is a value with a
    name, and one that reads back as a function of its own is the shape every
    other double here takes.
    """

    def __init__(self, wrapped: Callable, raced: Callable) -> None:
        self._wrapped = wrapped
        self._raced = raced

    def __call__(self, *called: Any, **options: Any) -> Any:
        self._raced()
        return self._wrapped(*called, **options)


class _RacesPastTheStep:
    """One thing that happens the instant a step returns, just after it runs.

    The other half of the window `_RacesTheStep` opens, for a case whose event
    has to land after the step did its work rather than before: a reply posted
    once a notice is on the thread and before the write that records how far
    the thread has been read.
    """

    def __init__(self, wrapped: Callable, raced: Callable) -> None:
        self._wrapped = wrapped
        self._raced = raced

    def __call__(self, *called: Any, **options: Any) -> Any:
        answered = self._wrapped(*called, **options)
        self._raced()
        return answered


class _RacesPastTheCall:
    """A step answering as it always does, with `raced` made once, just after its call number `nth` answers.

    For a window that only one of a step's calls opens -- the recovery's
    second reading of the checkout, or the first post of an artifact a later
    poll finds rather than posts again -- where `_RacesPastTheStep` would race
    every call.
    """

    def __init__(self, step: Callable, nth: int, raced: Callable) -> None:
        self._step = step
        self._calls = 0
        self._nth = nth
        self._raced = raced

    def __call__(self, *called: Any, **options: Any) -> Any:
        answered = self._step(*called, **options)
        self._calls += 1
        if self._calls == self._nth:
            self._raced()
        return answered
