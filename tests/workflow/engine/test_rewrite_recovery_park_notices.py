# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A guarded recovery park made again by a restarted process, taking in its notice and asking the log.

The guarded recovery case (`guarded_recovery_support`): issue #7's rebased
head reviewed, its run settled under the anchor, and the finish killed before
its announcement. The next tick's recovery cannot fetch the branch, so it
takes the git owner's fail-closed abort, handed the workflow's guarded
operations as every recovery is: the park behind the reset
posts its notice and files its `park_awaiting_human` event, and GitHub refuses
its record, so the attempt stands for the next tick's recovery to park again.

The process restarts in between, with no event in memory. The park made
again takes in the notice the conversation carries past the watermark rather
than saying it twice -- the issue marked awaiting a human, the watermark moved
to it, and the notice entered behind the comment-id ledger as it stood -- and
asks the audit log for the event naming that notice: it files nothing where
the log carries it or will not read, and files it once more where the log
lost it; with none configured, the notice said is taken as its event filed. The run is invalidated whole beside the
park. With no log, a notice that went out with its answer lost leaves its event owed: the park made again in that
process files it, and one a restarted process makes files none.
"""
from __future__ import annotations

import tempfile
import unittest
from functools import partial
from pathlib import Path
from typing import NamedTuple
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import branch_transport
from orchestrator.github import event_log as _event_log
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
)
from tests.workflow.interleaving import _RacesPastTheCall

_FETCHES = "_authed_fetch"

# The audit log's reader, which a log the process may not read refuses.
_LINES = "_named_lines"

# The event every park files.
_PARKED = "park_awaiting_human"

# The watermark and the comment-id ledger, as the pinned comment spells them.
_WATERMARK = "last_action_comment_id"
_LEDGER = "orchestrator_comment_ids"


def _unreadable(*_called, **_options):
    """The audit log's lines, answering as a log the process may not read."""
    raise PermissionError("the event log may not be read")


def _posted(case) -> list[str]:
    """What `case`'s client posted on its issue."""
    return [body for number, body in case.gh.posted_comments if number == git_support.ISSUE]


def _named(case) -> list:
    """The notice each `park_awaiting_human` event on `case`'s client's tail names."""
    parks = [event for event in case.gh.recorded_events if event["event"] == _PARKED]
    return [event.get("notice_id") for event in parks]


def _loses_the_answer() -> None:
    """Lose the answer of the post the notice just went out in."""
    raise RuntimeError("the answer was lost")


def _kept(recorded: list, ours: list) -> list:
    """The entries of `recorded` among `ours`, in the order `recorded` keeps them."""
    return [entry for entry in recorded if entry in ours]


class _Stream(NamedTuple):
    """How the audit log stands when the restarted process parks again, and how many events that park files.

    `logged` configures a log, `lost` empties it at the restart, and `unread`
    has it refuse every read behind the restart.
    """

    name: str
    logged: bool
    lost: bool
    unread: bool
    files: int


_STREAMS = (
    _Stream("a log carrying the event", logged=True, lost=False, unread=False, files=0),
    _Stream("a log that lost the event", logged=True, lost=True, unread=False, files=1),
    _Stream("a log that will not read", logged=True, lost=False, unread=True, files=0),
    _Stream("no log", logged=False, lost=False, unread=False, files=0),
)


class RestartedParkNoticeTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A park made again after a restart says its notice once, and files its event only where the log lacks it."""

    def test_the_notice_is_taken_in(self) -> None:
        # The first park's record is refused behind its notice and event, and
        # the process restarts: the next park takes in the notice, and files
        # the event again only where the log lost it.
        for stream in _STREAMS:
            with self.subTest(stream=stream.name):
                self.setUp()
                settled = self.settles_then_dies()[1]
                ledger = self.pinned_fields(_LEDGER)[0] or []
                self._parks_across_a_restart(stream)

                self.assert_released()
                self.assert_invalidated(settled)
                self._assert_taken_in(ledger, stream.files)

    def test_a_lost_post_still_owes_its_event(self) -> None:
        # With no log, the first park's notice goes out with its answer lost, nothing filed or recorded; the next park
        # takes it in: this process still owes the event and files it once, a restarted one takes the notice as filed.
        for restarted, filed in ((False, 1), (True, 0)):
            with self.subTest(restarted=restarted):
                self.setUp()
                settled = self.settles_then_dies()[1]
                ledger = self.pinned_fields(_LEDGER)[0] or []
                self._parks_over_a_lost_post(restarted=restarted)
                self.assert_released()
                self.assert_invalidated(settled)
                self._assert_taken_in(ledger, filed)

    def _parks_over_a_lost_post(self, *, restarted: bool) -> None:
        """Poll over an unfetched branch with no log, the notice's answer lost, then poll again -- `restarted` first."""
        with (
            patch.object(config, "EVENT_LOG_PATH", None),
            patch.object(branch_transport, _FETCHES, guarded.unfetched),
        ):
            with patch.object(self.gh, "comment", _RacesPastTheCall(self.gh.comment, 1, _loses_the_answer)):
                self.recovers()
            if restarted:
                self.gh.recorded_events.clear()
                self.gh.owed_events = set()
            self.recovers()

    def _parks_across_a_restart(self, stream: _Stream) -> None:
        """Poll over an unfetched branch, the park's record refused, then restart over `stream` and poll again."""
        event_log = None
        if stream.logged:
            event_log = Path(self.enterContext(tempfile.TemporaryDirectory())) / "events.jsonl"
        refused = self.gh.pinned_failures.refused
        races = _RacesPastTheCall(self.gh.comment, 1, partial(refused.add, git_support.ISSUE))
        with (
            patch.object(config, "EVENT_LOG_PATH", event_log),
            patch.object(branch_transport, _FETCHES, guarded.unfetched),
        ):
            with patch.object(self.gh, "comment", races):
                self.recovers()
            refused.discard(git_support.ISSUE)
            self.gh.recorded_events.clear()
            if stream.lost:
                event_log.write_text("", encoding="utf-8")
            with patch.object(_event_log, _LINES, _unreadable if stream.unread else _event_log._named_lines):
                self.recovers()

    def _assert_taken_in(self, ledger: list, filed: int) -> None:
        """The one notice posted at the watermark and entered behind `ledger`, `filed` events on the tail naming it.

        `ledger` is the comment-id ledger as it stood before the first park;
        whatever another road entered beside it may stand there too.
        """
        watermark, recorded = self.pinned_fields(_WATERMARK, _LEDGER)
        said = [comment.body for comment in self.issue.comments if comment.id == watermark]
        self.assertEqual(said, _posted(self))
        self.assertEqual(_named(self), [watermark][:filed])
        ours = [*ledger, watermark]
        self.assertEqual(_kept(recorded, ours), ours)


if __name__ == "__main__":
    unittest.main()
