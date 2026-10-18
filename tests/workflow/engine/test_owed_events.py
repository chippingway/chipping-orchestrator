# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which events behind a durable word that they may be out a process still has to file.

With an audit log configured every absence the stream reads is the log's to
vouch for, so the event is filed; with none, only one this process noted
owing and never paid is, whatever notice the event names -- noted by any
worker client the repository's client minted, and by none of another
repository's.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import owed_events

_PARKED = "park_awaiting_human"

_NAMED = MappingProxyType({"issue_number": 7, "reason": "auto_base_rebase_push_failed"})

# Two repositories' clients, each minting its own workers, and what they are built with.
_SLUGS = ("owner/repo", "owner/other")

_TOKEN = "tok"

_BOT = "bot"


def _minted(workers: int) -> tuple:
    """`workers` worker clients one repository's client mints, then another repository's client; nothing sent."""
    with patch("orchestrator.github.client.Github"), patch("orchestrator.github.client.Auth"):
        parent = GitHubClient(token=_TOKEN, repo_slug=_SLUGS[0], bot_login=_BOT)
        other = GitHubClient(token=_TOKEN, repo_slug=_SLUGS[1], bot_login=_BOT)
        minted = [parent._for_worker_thread() for _worker in range(workers)]
    return (*minted, other)


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

    def test_workers_share_their_repository_debt(self) -> None:
        # A scheduled handler's worker client is lost behind its notice, and
        # the next one minted for the issue still owes the event; paid there,
        # it is paid for every worker, and another repository's owes nothing.
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", None))
        lost, replacing, later, other = _minted(3)
        owed_events.owes(lost, _PARKED, **_NAMED)
        owing = [owed_events.unfiled(client, _PARKED, **_NAMED) for client in (replacing, other)]
        self.assertEqual(owing, [True, False])

        owed_events.pays(replacing, _PARKED, **_NAMED)
        self.assertFalse(owed_events.unfiled(later, _PARKED, **_NAMED))


if __name__ == "__main__":
    unittest.main()
