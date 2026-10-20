# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The events this process is filing behind a durable word that they may be out, for a caller with no log to ask.

A caller that leaves such a word on GitHub -- a landed rewrite's `base_rebased` record -- asks the stream before filing
the event again (`events.filed`); with no audit log that stream is this process's tail alone, so the word counts as the
event filed, at most once, unless this process noted it owing (`owes`) and never filed it (`pays`). The note lives on
the repository's client, shared with its worker clients (`github/client.GitHubClient._for_worker_thread`), so a worker
taking over from one lost mid-filing still owes it, and another repository's never mixes in.
"""
from __future__ import annotations

from typing import Any

from orchestrator.github import events as _events

# Where a client keeps the events its process noted owing, shared with every worker client it mints.
_NOTED = "owed_events"


def owes(client: Any, event: str, *, issue_number: int, **identity: Any) -> bool:
    """Note that `client`'s process is about to file `event` for `issue_number`, as `identity` names it; noted anew.

    False where the debt was owed already, for a caller whose write behind the note was refused to drop only a debt
    that write introduced (`pays`).
    """
    owing = _owing(event, issue_number, identity)
    noted = _noted(client)
    anew = owing not in noted
    noted.add(owing)
    return anew


def pays(client: Any, event: str, *, issue_number: int, **identity: Any) -> None:
    """Drop the note `owes` made: the event is filed, or the write saying it may be out was refused outright."""
    _noted(client).discard(_owing(event, issue_number, identity))


def unfiled(client: Any, event: str, *, issue_number: int, **identity: Any) -> bool:
    """Whether an event the stream does not carry, a durable word saying it may be out, is still to be filed.

    Always where the audit log is configured, which vouches for the absence; with none, only an event `client`'s process
    noted owing and never paid.
    """
    return _events.durable() or _owing(event, issue_number, identity) in _noted(client)


def _noted(client: Any) -> set:
    """The events `client`'s process noted owing, kept on the client -- a test double's own where it carries none."""
    if getattr(client, _NOTED, None) is None:
        setattr(client, _NOTED, set())
    return getattr(client, _NOTED)


def _owing(event: str, issue_number: int, identity: dict[str, Any]) -> tuple:
    """The event `owes` notes: its kind, its issue, and every member of `identity`."""
    return (event, int(issue_number), tuple(sorted(identity.items())))
