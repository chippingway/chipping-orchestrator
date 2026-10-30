# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a captured completion's invalidation is decided on: the whole reading its proof was taken over.

A capture is proved stale by readings of the pinned comment as much as of the
issue -- a frozen record moved, a pull request or debt its road answers gone --
and a human can put any of them back between the proof and the write that acts
on it. A guarded commit's prerequisites hold the fields a reading carries; a
field the reading lacks has no value there to hold, so a pull request or debt
restored by hand would pass them. So the retirement is held to the reading
whole (`DecidedOn`): the candidate the commit would send, read beside the
capture it rewrites, has to spell exactly what the proof was taken over, and
any field moved, restored, or added since refuses it as EVIDENCE_MOVED, for a
later tick to decide afresh.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import completion_commits as _commits, completion_records as _records


@dataclass(frozen=True)
class DecidedOn:
    """The reading an invalidation was decided on, beside the capture; asked of every candidate its commit derives."""

    reading: str

    def __call__(self, candidate: PinnedState) -> _commits.CheckpointRefusal | None:
        """None where `candidate` spells exactly the reading decided on, beside the capture; else EVIDENCE_MOVED."""
        if _beside_the_capture(candidate) == self.reading:
            return None
        return _commits.CheckpointRefusal.EVIDENCE_MOVED

    @classmethod
    def over(cls, state: PinnedState) -> DecidedOn:
        """The reading `state` is, beside its capture."""
        return cls(_beside_the_capture(state))


def _beside_the_capture(state: PinnedState) -> str:
    """`state` as the comment's JSON spells it, its capture left out."""
    beside = {
        field: held for field, held in state.state_data.items()
        if field != _records.DEVELOPER_COMPLETION
    }
    return json.dumps(beside, sort_keys=True)
