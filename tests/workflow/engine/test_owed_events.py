# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which events behind a durable word that they may be out a process still has to file.

With an audit log every absence is the log's to vouch for and the event filed; with none, only one this process owes
unpaid is, noted by any worker of its repository's client and not another repository's, and only for the very head the
owing record named.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import owed_events

_REBASED = "base_rebased"

# The audit log's setting, unset where no log vouches for an absence.
_LOG = "EVENT_LOG_PATH"

# The landed head a finish's `base_rebased` record names, and another one.
_HEAD = "b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2"
_OTHER_HEAD = "c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3"
_NAMED = MappingProxyType({"issue_number": 7, "sha": _HEAD})

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
        self.enterContext(patch.object(config, _LOG, None))
        self.assertFalse(owed_events.unfiled(client, _REBASED, **_NAMED))
        owed_events.owes(client, _REBASED, **_NAMED)
        other_head = {**_NAMED, "sha": _OTHER_HEAD}
        owing = [owed_events.unfiled(client, _REBASED, **named) for named in (_NAMED, other_head)]
        self.assertEqual(owing, [True, False])
        owed_events.pays(client, _REBASED, **_NAMED)
        self.assertFalse(owed_events.unfiled(client, _REBASED, **_NAMED))

    def test_a_log_vouches_for_every_absence(self) -> None:
        self.enterContext(patch.object(config, _LOG, Path("events.jsonl")))
        self.assertTrue(owed_events.unfiled(SimpleNamespace(), _REBASED, **_NAMED))

    def test_workers_share_their_repository_debt(self) -> None:
        # A lost worker client's debt passes to the next one minted for the issue; paid there, it is paid for all.
        self.enterContext(patch.object(config, _LOG, None))
        lost, replacing, later, other = _minted(3)
        owed_events.owes(lost, _REBASED, **_NAMED)
        owing = [owed_events.unfiled(client, _REBASED, **_NAMED) for client in (replacing, other)]
        self.assertEqual(owing, [True, False])
        owed_events.pays(replacing, _REBASED, **_NAMED)
        self.assertFalse(owed_events.unfiled(later, _REBASED, **_NAMED))


if __name__ == "__main__":
    unittest.main()
