# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a human doing something while one pass is still running looks like.

Neither of the two subjects beside this one. A death is a tick that does not
live long enough to see anything fail and a refusal is a step that reported
back; here the process lives, every step reports back, and what goes stale is
a PROOF taken one round-trip ago. No ordering closes that window -- only a
reading taken again in front of the effect it licenses does -- so it is driven
from the seam a step has just finished at rather than by a death at one.

The lookup recorder is here for the same reason: what a pass may not do is
prove one pull request and act on another, and the only way to see that from
outside is to count what it asked GitHub for.
"""
from __future__ import annotations

import contextlib
from unittest.mock import patch

from tests.support.fakes import FakeGitHubClient


class _RunAndMove:
    """One step that reports back, and a world that moves before the next.

    The seam is named by what has just finished rather than by what is about
    to run, because that is where the staleness starts: a proof is worth
    exactly as much as the interval behind it, and this is the interval.
    """

    def __init__(self, ran, moved) -> None:
        self._ran = ran
        self._moved = moved

    def __call__(self, *call_args, **call_options):
        answered = self._ran(*call_args, **call_options)
        self._moved()
        return answered


class RecordedLookups:
    """Every pull request one pass asked GitHub for, in the order it asked.

    Built before the pass and held around it rather than handed back by the
    holder, so what a case asserts on is a value it named itself.
    """

    def __init__(self) -> None:
        self.numbers: list[int] = []
        self._looked_up = None

    def __call__(self, number: int):
        self.numbers.append(number)
        return self._looked_up(number)

    @contextlib.contextmanager
    def recording(self, client: FakeGitHubClient):
        """Hold the lookup seam for one pass, recording what it asked."""
        self._looked_up = client.get_pr
        with patch.object(client, "get_pr", self):
            yield


class MovedOnRead:
    """A world that moves the moment one issue has been fetched `calls` times.

    What a human does while a pass reads the same issue more than once -- a
    scan, a reading under a claim, a reading in front of a write -- named by
    which of those reads it lands behind.
    """

    def __init__(self, client: FakeGitHubClient, number: int, calls: int, moved) -> None:
        self._client = client
        self._fetch = client.get_issue
        self._number = number
        self._left = calls
        self._moved = moved

    def __call__(self, number: int):
        """Fetch the issue, and move the world behind the last counted fetch of the one this watches."""
        fetched = self._fetch(number)
        if number == self._number:
            self._left -= 1
            if not self._left:
                self._moved()
        return fetched

    def installed(self):
        """Hold the client's issue fetch for the block."""
        return patch.object(self._client, "get_issue", self)


@contextlib.contextmanager
def interleaved_after(owner, name: str, moved):
    """A human moving something the moment one step has reported back."""
    with patch.object(owner, name, _RunAndMove(getattr(owner, name), moved)):
        yield
