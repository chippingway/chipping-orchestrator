# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which events behind a durable word that they may be out a process still has to file.

With an audit log every absence is the log's to vouch for and the event filed; with none, only one this process owes
unpaid is, whatever its notice's id, noted by any worker of its repository's client, not another repository's, and only
for a notice saying what the owing post said: an earlier notice found said is not refiled over another's failed post.
"""
from __future__ import annotations

import unittest
from functools import partial
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import owed_events, rewrite_recovery_notices as _notices
from tests.support.fakes import FakeGitHubClient, FakeIssue, FakeLabel

_PARKED = "park_awaiting_human"

# The audit log's setting, unset where no log vouches for an absence.
_LOG = "EVENT_LOG_PATH"
_NAMED = MappingProxyType({"issue_number": 7, "reason": "auto_base_rebase_push_failed"})

# Two repositories' clients, each minting its own workers, and what they are built with.
_SLUGS = ("owner/repo", "owner/other")
_TOKEN = "tok"
_BOT = "bot"

# Two recovery park notices of one issue, parked for the same reason.
_SAID = "Reset failed; inspect the checkout."
_OTHER = "Reset succeeded; continue after repair."


def _minted(workers: int) -> tuple:
    """`workers` worker clients one repository's client mints, then another repository's client; nothing sent."""
    with patch("orchestrator.github.client.Github"), patch("orchestrator.github.client.Auth"):
        parent = GitHubClient(token=_TOKEN, repo_slug=_SLUGS[0], bot_login=_BOT)
        other = GitHubClient(token=_TOKEN, repo_slug=_SLUGS[1], bot_login=_BOT)
        minted = [parent._for_worker_thread() for _worker in range(workers)]
    return (*minted, other)


def _parks(gh: FakeGitHubClient, issue: FakeIssue, message: str) -> None:
    """A recovery park of `issue` over `message`, posted or taken in where it is already said."""
    context = SimpleNamespace(gh=gh, issue=issue, state=gh.read_pinned_state(issue))
    _notices.parks_awaiting_human(context, message, _NAMED["reason"])


class OwedEventTest(unittest.TestCase):
    """An event is still to be filed with no log only while this process owes it."""

    def test_no_log_files_only_an_owed_event(self) -> None:
        client = SimpleNamespace()
        self.enterContext(patch.object(config, _LOG, None))
        self.assertFalse(owed_events.unfiled(client, _PARKED, **_NAMED))
        owed_events.owes(client, _PARKED, **_NAMED)
        self.assertTrue(owed_events.unfiled(client, _PARKED, notice_id=9, **_NAMED))
        owed_events.pays(client, _PARKED, notice_id=9, **_NAMED)
        self.assertFalse(owed_events.unfiled(client, _PARKED, **_NAMED))

    def test_a_log_vouches_for_every_absence(self) -> None:
        self.enterContext(patch.object(config, _LOG, Path("events.jsonl")))
        self.assertTrue(owed_events.unfiled(SimpleNamespace(), _PARKED, **_NAMED))

    def test_workers_share_their_repository_debt(self) -> None:
        # A lost worker client's debt passes to the next one minted for the issue; paid there, it is paid for all.
        self.enterContext(patch.object(config, _LOG, None))
        lost, replacing, later, other = _minted(3)
        owed_events.owes(lost, _PARKED, **_NAMED)
        owing = [owed_events.unfiled(client, _PARKED, **_NAMED) for client in (replacing, other)]
        self.assertEqual(owing, [True, False])
        owed_events.pays(replacing, _PARKED, **_NAMED)
        self.assertFalse(owed_events.unfiled(later, _PARKED, **_NAMED))

    def test_another_notices_debt_files_nothing(self) -> None:
        # A restart owing a failed notice's event takes an earlier notice found saying something else as filed.
        self.enterContext(patch.object(config, _LOG, None))
        issue = FakeIssue(_NAMED["issue_number"], labels=[FakeLabel("workflow:fixing")])
        gh = FakeGitHubClient([issue])
        parks = partial(_parks, gh, issue)
        parks(_SAID)
        gh.recorded_events.clear()
        gh.owed_events.clear()
        with patch.object(gh, "comment", side_effect=RuntimeError("post failed before sending")):
            self.assertRaises(RuntimeError, parks, _OTHER)
        parks(_SAID)
        self.assertEqual(gh.recorded_events, [])


if __name__ == "__main__":
    unittest.main()
