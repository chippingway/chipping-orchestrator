# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The client and the comments the pinned-state contract is held against.

The client is the real one, built past its constructor so no connection is
opened: every pinned-state read and write under test is the adapter's own, and
the only thing the tests supply is the login the token stands for. The comments
are the PyGithub-shaped doubles, written as the account that login names, since
a record the orchestrator did not author is one the read is meant to refuse.
"""
from __future__ import annotations

import json

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PINNED_STATE_TEMPLATE
from tests.support.fakes import FakeComment, FakeUser

BOT = "orchestrator-bot"


def marker(state_data: dict) -> str:
    """The comment body one pinned payload is carried in."""
    return PINNED_STATE_TEMPLATE.format(
        payload=json.dumps(state_data, sort_keys=True),
    )


def bot_comment(comment_id: int, body: str) -> FakeComment:
    """One comment the account backing the token wrote."""
    return FakeComment(id=comment_id, body=body, user=FakeUser(BOT))


def state_client(bot_login: str = BOT) -> GitHubClient:
    """The real client, with nothing built but the trust boundary.

    `__new__` rather than the constructor, which would open a connection to
    GitHub; the pinned-state surface reads nothing off the client but the
    login it authenticates records against.
    """
    client = GitHubClient.__new__(GitHubClient)
    client._bot_login = bot_login
    return client
