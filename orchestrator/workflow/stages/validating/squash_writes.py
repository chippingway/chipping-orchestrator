# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The client an approval's squash is handed, and the pinned writes it guards and follows.

The squash writes the state in hand wherever it writes -- the collapse record
ahead of its rewrite, the size gate's own records -- and what it hands back
does not say whether it wrote at all: a branch with nothing to rewrite, or an
install that makes no new collapse, writes nothing. Every write the approval
tail makes behind it is laid over the comment measured from the comment as the
tail last read or wrote it (`handoff._Held`), so that last write has to be
known rather than guessed. Measured from the comment read before a squash that
wrote, a move the squash's write already carried -- a usage total -- reads as
another road's and is added a second time. Taken whole
over the comment behind a squash that wrote nothing, a field another road
wrote while it ran -- a round a reply spent -- is written back over.

Nor may a write of the squash's own put back what another road wrote ahead of
it. Its first write comes a request or more after the tail last read the
comment, and a report settled, a round spent, or a verdict replaced in that
time would be written over by the older state in hand -- and then read back
by the tail as the records its approval stands on. So each write is held
first to the report, pull-request, verdict, and evidence records the state in
hand carries, and laid over the comment as read then (`handoff._Held.follows`),
exactly as the tail's own writes are. One whose records moved is refused the
way GitHub refusing it would be: the squash already answers that by not
rewriting where the write is the record ahead of its rewrite, and past the
rewrite by leaving the collapse it recorded for the next tick's recovery, which
holds the relabel to an approval that no longer covers the report.

So the squash is handed its gate with a client that passes every call through,
and guards each write of the issue's own pinned comment and hands it on, once
it lands, as the one the tail last wrote. A write of another issue's -- a
child the size gate files -- is not this comment, and is neither.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState


class _RecordsMoved(RuntimeError):
    """A squash's write refused: the comment no longer carries the records the squash was taken under."""


class _FollowsItsWrites:
    """`gh` for one squash of `issue`'s branch: every call passed through, each write of its comment guarded."""

    def __init__(
        self,
        gh: GitHubClient,
        issue: Issue,
        holds: Callable[[PinnedState], bool],
        wrote: Callable[[PinnedState], None],
    ) -> None:
        self._gh = gh
        self._issue_number = issue.number
        self._holds = holds
        self._wrote = wrote

    def __getattr__(self, name: str):
        return getattr(self._gh, name)

    def write_pinned_state(self, issue: Issue, state: PinnedState) -> PinnedState:
        """Write `state` through `gh` where `holds` lets it, and hand it to `wrote` once it has landed.

        Only a write of this issue's comment is asked or handed on; one
        `holds` refuses raises rather than landing.
        """
        if issue.number != self._issue_number:
            return self._gh.write_pinned_state(issue, state)
        if not self._holds(state):
            raise _RecordsMoved(
                f"issue #{issue.number}'s pinned comment no longer carries the report, "
                "pull-request, verdict, or evidence records its squash was taken under",
            )
        written = self._gh.write_pinned_state(issue, state)
        self._wrote(state)
        return written


def followed(
    gate,
    holds: Callable[[PinnedState], bool],
    wrote: Callable[[PinnedState], None],
):
    """`gate` with a client asking `holds` before each write of its issue's comment, and handing it to `wrote` after."""
    return replace(gate, gh=_FollowsItsWrites(gate.gh, gate.issue, holds, wrote))
