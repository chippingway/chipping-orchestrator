# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""GitHub double that records or refuses agent-run circuit checkpoints."""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from tests.support.fakes import FakeGitHubClient, FakeIssue

_WRITE_REFUSED = "pinned write refused"

_READ_REFUSED = "pinned read refused"


class CircuitGitHubClient(FakeGitHubClient):
    """A client that remembers its pinned writes and can refuse them.

    The refusals are what the circuit's own promises are read against: a
    launch may not reach a process on a state nobody could read or a charge
    nobody could record, and neither failure is one a stage above could see
    from the result alone.
    """

    def __init__(self, **client_fields) -> None:
        super().__init__(**client_fields)
        self.writes: list[dict] = []
        self.unreadable = False
        self.unparsed = False
        self._writes_allowed: int | None = None

    def refuse_write(self, *, after: int = 0) -> None:
        """Refuse the pinned write that follows `after` further ones."""
        self._writes_allowed = after

    def read_pinned_state(self, issue: FakeIssue) -> PinnedState:
        if self.unreadable:
            raise RuntimeError(_READ_REFUSED)
        if self.unparsed:
            return PinnedState(comment_id=1, data={}, parsed=False)
        return super().read_pinned_state(issue)

    def write_pinned_state(
        self, issue: FakeIssue, state: PinnedState,
    ) -> PinnedState:
        self.writes.append(dict(state.data))
        if self._writes_allowed is not None:
            if self._writes_allowed <= 0:
                raise RuntimeError(_WRITE_REFUSED)
            self._writes_allowed -= 1
        return super().write_pinned_state(issue, state)
