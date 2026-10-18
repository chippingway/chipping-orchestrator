# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which events behind a durable word that they may be out a process still has to file.

With an audit log configured every absence the stream reads is the log's to
vouch for, so the event is filed; with none, only one this process noted
owing and never paid is, whatever notice the event names.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import owed_events

_PARKED = "park_awaiting_human"

_NAMED = MappingProxyType({"issue_number": 7, "reason": "auto_base_rebase_push_failed"})


class OwedEventTest(unittest.TestCase):
    """An event is still to be filed with no log only while this process owes it."""

    def test_no_log_files_only_an_owed_event(self) -> None:
        client = SimpleNamespace()
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", None))
        self.assertFalse(owed_events.unfiled(client, _PARKED, **_NAMED))

        owed_events.owes(client, _PARKED, **_NAMED)
        self.assertTrue(owed_events.unfiled(client, _PARKED, notice_id=9, **_NAMED))

        owed_events.pays(client, _PARKED, notice_id=9, **_NAMED)
        self.assertFalse(owed_events.unfiled(client, _PARKED, **_NAMED))

    def test_a_log_vouches_for_every_absence(self) -> None:
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", Path("events.jsonl")))
        self.assertTrue(owed_events.unfiled(SimpleNamespace(), _PARKED, **_NAMED))


if __name__ == "__main__":
    unittest.main()
