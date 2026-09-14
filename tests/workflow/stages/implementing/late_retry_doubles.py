# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pinned writes observed during a retry and a continuation arriving inside its reads."""
from __future__ import annotations

from unittest.mock import patch

from tests.workflow.stages.implementing import late_gate_test_support as support


class _WritesDuringTheTick:
    """Every durable write one tick made, as the client was handed it.

    A crash window is only visible in the writes themselves: what it leaves is
    a pinned comment some later tick reads as ordinary, so an assertion on the
    state a whole tick ends at cannot see it at all.
    """

    def __init__(self, github) -> None:
        self.writes: list[dict] = []
        self._github = github
        self._wrapped = github.write_pinned_state

    def __call__(self, issue, state):
        self.writes.append(dict(state.data))
        return self._wrapped(issue, state)

    def held(self):
        """Record the pinned writes of one tick."""
        return patch.object(self._github, "write_pinned_state", self)


class _LandsTheRetry:
    """One operator writing the retry command, the instant a step has run.

    A class rather than a closure because a seam this repository patches is a
    value with a name, and because it has to fire ONCE: hung on a read and
    fired on every one of them, each later reading would answer against a
    thread the one before it never saw.
    """

    def __init__(self, case) -> None:
        self._case = case
        self.landed = False

    def __call__(self) -> None:
        if not self.landed:
            self.landed = True
            self._case._reply(support.BARE_CONTINUE)
