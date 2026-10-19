# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The events this process is filing behind a durable word that they may be out, for a caller with no log to ask.

A caller that leaves such a word on GitHub -- a landed rewrite's `base_rebased` record, a park's notice -- asks the
stream before filing the event again (`events.filed`); with no audit log that stream is this process's tail alone, so
the word counts as the event filed, at most once, unless this process noted it owing (`owes`) and never filed it
(`pays`). The note lives on the repository's client, shared with its worker clients
(`github/client.GitHubClient._for_worker_thread`), keyed by what the notice says (`said`), not its id, so one notice's
failed post never files another's event. A checkout loss no write recorded is owed the same way (`owes_a_loss`).
"""
from __future__ import annotations

from typing import Any

from orchestrator.github import events as _events

# Where a client keeps the events its process noted owing, shared with every worker client it mints.
_NOTED = "owed_events"

# The notice an event names, which is posted after the event is owed; and the record a checkout loss is owed.
_NOTICE = "notice_id"
_LOST = "checkout_lost"


def owes(client: Any, event: str, *, issue_number: int, said: str = "", **identity: Any) -> bool:
    """Note that `client`'s process is about to file `event` for `issue_number`, as `identity` names it; noted anew.

    `said` is the text of the notice the event rides, where it rides one. False where the debt was owed already, for a
    caller whose write behind the note was refused to drop only a debt that write introduced (`pays`).
    """
    owing = _owing(event, issue_number, said, identity)
    noted = _noted(client)
    anew = owing not in noted
    noted.add(owing)
    return anew


def pays(client: Any, event: str, *, issue_number: int, said: str = "", **identity: Any) -> None:
    """Drop the note `owes` made: the event is filed, or the write saying it may be out was refused outright."""
    owing = _owing(event, issue_number, said, identity)
    _noted(client).discard(owing)


def unfiled(client: Any, event: str, *, issue_number: int, said: str = "", **identity: Any) -> bool:
    """Whether an event the stream does not carry, a durable word saying it may be out, is still to be filed.

    Always where the audit log is configured, which vouches for the absence; with none, only an event `client`'s process
    noted owing and never paid, over a notice saying `said`.
    """
    owing = _owing(event, issue_number, said, identity)
    return _events.durable() or owing in _noted(client)


def _noted(client: Any) -> set:
    """The events `client`'s process noted owing, kept on the client -- a test double's own where it carries none."""
    if getattr(client, _NOTED, None) is None:
        setattr(client, _NOTED, set())
    return getattr(client, _NOTED)


def _owing(event: str, issue_number: int, said: str, identity: dict[str, Any]) -> tuple:
    """The event `owes` notes, the text its notice says kept and the notice's id left out."""
    named = {field: field_value for field, field_value in identity.items() if field != _NOTICE}
    return (event, int(issue_number), said, tuple(sorted(named.items())))


def owes_a_loss(context: Any, recorded: bool) -> bool:
    """`recorded`, a checkout loss `context`'s recovery read noted owed for its attempt where it was not."""
    owing = (_LOST, int(context.issue.number), context.pending_pre_rebase_sha)
    if not recorded:
        _noted(context.gh).add(owing)
    return recorded


def pays_a_loss(context: Any) -> bool:
    """Whether `context`'s attempt owed a checkout loss no write recorded, dropped for the asker to record."""
    owing = (_LOST, int(context.issue.number), context.pending_pre_rebase_sha)
    owed = owing in _noted(context.gh)
    _noted(context.gh).discard(owing)
    return owed
