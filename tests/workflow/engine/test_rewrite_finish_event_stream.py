# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite's `base_rebased` event, found on the audit log by a fresh process however much the log grew.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
reviewed rebase finished with the audit log configured, the process killed
behind the event and before the checkpoint that marks the head announced. The
next process starts with no event in memory, and the log has grown by more
than a mebibyte of other issues' events since: the recovery asks the whole
log for the event before it files one, finds it, and files nothing again --
one `base_rebased` on the log for one rewrite, the head routed once. So does
an attempt a finish from before the attempt recorded its events left, which
filed the event and died behind it with no record of it on the comment. A
log that would not read is no answer: the finish is held with
nothing filed, relabelled, or retired, and the next tick, the log readable
again, finds the event the same way. Nothing is run again, pushed, or
launched.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.github import events as _events
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)

_REBASED = "base_rebased"

# Another issue's event, enough of which grow the log past a mebibyte.
_LATER_EVENT = json.dumps({"event": "agent_spawn", "issue": 8, "repo": "chippingway/chipping-orchestrator"})

_LATER = f"{_LATER_EVENT}\n"

_GROWN_LINES = 20_000

_MEBIBYTE = 1_048_576


def _unreadable(*_called, **_options):
    """The audit log's lines, answering as a log the process may not read."""
    raise PermissionError("the event log may not be read")


class EventStreamRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """A fresh process finds the event a lost one filed anywhere on the audit log, and files it once."""

    def setUp(self) -> None:
        support.CapturedRunCase.setUp(self)
        work_dir = self.enterContext(tempfile.TemporaryDirectory())
        self.event_log = Path(work_dir) / "events.jsonl"
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", self.event_log))

    def test_a_fresh_process_finds_the_event(self) -> None:
        head = self._dies_behind_the_event()

        self.recovers()

        self._assert_filed_once(head)

    def test_an_unrecorded_event_is_found_too(self) -> None:
        # A finish from before the record existed filed the event and died
        # behind it, leaving no record of it on the attempt.
        head = self._dies_behind_the_event()
        legacy = self.gh.read_pinned_state(self.issue)
        legacy.data.pop(readings.KEY_ANNOUNCED_EVENT)
        self.gh.write_pinned_state(self.issue, legacy)

        self.recovers()

        self._assert_filed_once(head)

    def test_an_unread_log_holds_the_finish(self) -> None:
        head = self._dies_behind_the_event()
        with patch.object(_events, "_named_lines", side_effect=_unreadable):
            self.recovers()
        announced = readings.pinned(self).get(readings.KEY_ANNOUNCED)
        held = (self._logged(), readings.relabels(self), announced)
        self.assertEqual(held, ([head], (), None))

        self.recovers()

        self._assert_filed_once(head)

    def _dies_behind_the_event(self) -> str:
        """Land and review a rebase, kill its finish behind the event, and restart; the landed head.

        The restart leaves the client with no event in memory, as a fresh
        process has, and the log grown past a mebibyte by another issue's
        events.
        """
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_CHECKPOINT, partial(self.finishes, head))
        self.gh.recorded_events.clear()
        with self.event_log.open("a", encoding="utf-8") as grown:
            grown.write(_LATER * _GROWN_LINES)
        self.assertGreater(self.event_log.stat().st_size, _MEBIBYTE)
        return head

    def _logged(self) -> list[str]:
        """The head every `base_rebased` the audit log carries for issue #7 names, oldest first."""
        logged = (json.loads(line) for line in self.event_log.read_text().splitlines())
        return [
            event["sha"] for event in logged
            if event.get("event") == _REBASED and event.get("issue") == git_support.ISSUE
        ]

    def _assert_filed_once(self, head: str) -> None:
        """`head` filed once on the log, nothing filed again in memory, and the head routed with the attempt retired."""
        filed = (self._logged(), support.announced(self))
        self.assertEqual(filed, ([head], []))
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
