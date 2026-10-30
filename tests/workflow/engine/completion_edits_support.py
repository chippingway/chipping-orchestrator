# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a human or another road does to a capture's pinned comment while a write over it is out.

A hand edit leaves the comment unparseable, under another version, or gone;
another road writes the comment whole right behind the reading a write was
decided on. Neither is a second orchestrator writer: the caller holds the
issue's claim, so a move here is somebody editing the comment by hand.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import patch

from orchestrator.github.pinned_state import SCHEMA_VERSION_KEY, AdmissionStatus, PinnedState
from tests.support.fakes import FakeGitHubClient, FakeIssue
from tests.workflow.engine.completion_test_support import ISSUE, CompletionWorld

_UNSUPPORTED_VERSION = 2


def unpinned(world: CompletionWorld, *, malformed: bool = False, unsupported: bool = False) -> None:
    """A hand edit leaves the comment unparseable or under version 2, or deletes it."""
    if not (malformed or unsupported):
        world.github._pinned.pop(ISSUE)
        return
    world.github._pinned[ISSUE] = PinnedState(
        comment_id=world.state.comment_id,
        state_data={} if malformed else {**world.record(), SCHEMA_VERSION_KEY: _UNSUPPORTED_VERSION},
        parsed=not malformed,
        supported=False,
        admission_status=AdmissionStatus.MALFORMED if malformed else AdmissionStatus.UNSUPPORTED,
    )


def interfering(world: CompletionWorld, **fields) -> AbstractContextManager:
    """Let another road write `fields` once, right behind the next reading and before the commit reads again."""
    reader = _ReadThenMove(world.github, world.github.read_pinned_state, dict(fields))
    return patch.object(world.github, "read_pinned_state", side_effect=reader.read)


@dataclasses.dataclass
class _ReadThenMove:
    """A reading another road writes right behind, once: a whole-record write over the record as it stands."""

    github: FakeGitHubClient
    reader: Callable[[FakeIssue], PinnedState]
    fields: dict = dataclasses.field(default_factory=dict)

    def read(self, issue: FakeIssue) -> PinnedState:
        """The reading, with the move landed behind it."""
        fresh = self.reader(issue)
        if self.fields:
            landed = self.reader(issue)
            landed.state_data.update(self.fields)
            self.fields = {}
            self.github.write_pinned_state(issue, landed)
        return fresh
