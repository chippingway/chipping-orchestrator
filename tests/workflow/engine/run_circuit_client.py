# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""GitHub double that records or refuses agent-run circuit checkpoints."""
from __future__ import annotations

from orchestrator.github.pinned_state import SCHEMA_VERSION_KEY, PinnedState
from tests.support.fakes import FakeGitHubClient, FakeIssue

_WRITE_REFUSED = "pinned write refused"

_READ_REFUSED = "pinned read refused"

# The version a human's edit leaves the record under: one admission refuses.
_EDITED_VERSION = 2


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
        self.unsupported = False
        self._writes_allowed: int | None = None
        self._edited_before: int | None = None

    def refuse_write(self, *, after: int = 0) -> None:
        """Refuse the pinned write that follows `after` further ones."""
        self._writes_allowed = after

    def edit_before_write(self, *, after: int = 0) -> None:
        """Have a human edit the record into a version admission refuses, just ahead of the write after `after` more.

        The writer then refuses that write by raising `RecordRefused` with
        nothing written, as it refuses every write over such a record.
        """
        self._edited_before = after

    def read_pinned_state(self, issue: FakeIssue) -> PinnedState:
        if self.unreadable:
            raise RuntimeError(_READ_REFUSED)
        if self.unparsed:
            return PinnedState(comment_id=1, data={}, parsed=False)
        if self.unsupported:
            return PinnedState(comment_id=1, data={}, supported=False)
        return super().read_pinned_state(issue)

    def write_pinned_state(
        self, issue: FakeIssue, state: PinnedState,
    ) -> PinnedState:
        self.writes.append(dict(state.data))
        self._edit_when_due(issue)
        if self._writes_allowed is not None:
            if self._writes_allowed <= 0:
                raise RuntimeError(_WRITE_REFUSED)
            self._writes_allowed -= 1
        return super().write_pinned_state(issue, state)

    def _edit_when_due(self, issue: FakeIssue) -> None:
        """Make the edit `edit_before_write` asked for, if this is the write it is due ahead of."""
        if self._edited_before is None:
            return
        if self._edited_before:
            self._edited_before -= 1
            return
        self._edited_before = None
        edited = {**self.pinned_data(issue.number), SCHEMA_VERSION_KEY: _EDITED_VERSION}
        self.seed_state(issue, raw=True, **edited)
