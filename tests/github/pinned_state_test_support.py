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
import sys

from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import ORCHESTRATOR_COMMENT_MARKER
from orchestrator.github.pinned_state import PINNED_STATE_TEMPLATE, SCHEMA_VERSION_KEY, SUPPORTED_SCHEMA_VERSION
from tests.support.fakes import FakeComment, FakeUser

BOT = "orchestrator-bot"

# What a state may carry that the next reading would refuse: another integer
# version, every spelling Python's `==` takes for 1 and JSON does not, a value
# JSON has no spelling for at all, and nesting past the recursion limit, which
# every supported interpreter's encoder would still spell.
_NESTING_LIMIT = sys.getrecursionlimit()
REFUSED_PAYLOADS = (
    *({SCHEMA_VERSION_KEY: version} for version in (2, 0, True, 1.0, "1", None)),
    *({SCHEMA_VERSION_KEY: SUPPORTED_SCHEMA_VERSION, "usage_total": float(spelled)} for spelled in ("nan", "-inf")),
    {SCHEMA_VERSION_KEY: SUPPORTED_SCHEMA_VERSION, "nested": json.loads("[" * _NESTING_LIMIT + "]" * _NESTING_LIMIT)},
)

# A value carrying so many comment terminators that escaping each would put the
# comment past what GitHub takes, so the writer renders its record raw: what a
# preserved pull-request body carries by the thousand.
_TERMINATORS = 16384
RAW_TERMINATORS = "-->" * _TERMINATORS

# The same, opening on a quote of the marker every other comment this
# orchestrator posts carries: what a record preserving such a comment holds,
# and the one place a state comment carries that marker at all.
RAW_ORDINARY_QUOTE = f"{ORCHESTRATOR_COMMENT_MARKER}{RAW_TERMINATORS}"

# An ordinary comment's text that opens on the state marker and a brace and
# carries the marker every such comment carries in its prose, outside any JSON
# string, before the terminator it ends on: no record, closed or not, and posted
# as it stands, since it already carries that marker.
ORDINARY_PROSE = f'{{"{SCHEMA_VERSION_KEY}": 1\n{ORCHESTRATOR_COMMENT_MARKER}\nordinary explanation '


def marker(state_data: dict, *, raw: bool = False) -> str:
    """The comment body one pinned payload is carried in."""
    payload = dict(state_data)
    if not raw:
        payload.setdefault(SCHEMA_VERSION_KEY, SUPPORTED_SCHEMA_VERSION)
    return PINNED_STATE_TEMPLATE.format(
        payload=json.dumps(payload, sort_keys=True),
    )


def cut_short(state_data: dict) -> str:
    """The payload one pinned state is written as raw, cut short of its object's closing brace.

    What a truncated write or a hand edit leaves of a record. Where the record
    carries `RAW_TERMINATORS` -- written raw, since escaping them would not fit
    -- nothing but the marker it opens with says where it ends.
    """
    return json.dumps(state_data, sort_keys=True).removesuffix("}")


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
