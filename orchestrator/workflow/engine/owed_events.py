# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The events this process is filing behind a durable word that they may be out, for a caller with no log to ask.

A caller that leaves such a word on GitHub -- a landed rewrite's record of its `base_rebased` event, a park's notice
naming its `park_awaiting_human` -- and then files the event asks the stream before filing it again (`events.filed`).
With no audit log configured that stream is this process's tail alone, which says nothing of an event an earlier process
filed, so the word is taken as the event filed: once at most, never twice -- an event a process was lost ahead of goes
unfiled. Only an event this process noted it was filing (`owes`) and never filed since (`pays`) -- the step ahead of it
raised, or its finish was cut short -- is still its own to file (`unfiled`). The note is kept on the repository's
client, which shares it with every worker client it mints (`github/client.GitHubClient._for_worker_thread`), so a worker
taking an issue up behind one lost mid-filing files what that one still owed, and one repository's debt never answers
for another's. A notice the event names (`notice_id`) is no part of what is owed: the event is owed before its notice is
posted. What that notice says (`said`) is: a park posts a notice only where none saying the same stands past the
watermark, so one found saying it later is that post's own, and a debt a failed post of one notice left never files the
event of another notice found said.
"""
from __future__ import annotations

from typing import Any

from orchestrator.github import events as _events

# Where a client keeps the events its process noted owing, shared with every worker client it mints.
_NOTED = "owed_events"

# The notice an event names, which is posted after the event is owed.
_NOTICE = "notice_id"


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
