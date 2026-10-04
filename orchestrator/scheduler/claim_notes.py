# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the holds on an issue's writer claim tell the pollers that share it.

Two questions a claim's `True` or `False` cannot answer, both about a close a
poll read before it asked for the claim.

The first is the holder's. A poll's closed reading is older than the claim a
pass takes, and the record that pass reads names the cycle it names now: if
another poller held the issue in between, it may have settled the cycle the
close ended and started a fresh one. `foreign_holds` counts the holds of
another process this one has found on the key (`writer_claims` reads the last
holder's token at every acquisition), so a pass that reads the same count it
read at the poll knows no other poller has held the issue since, and that the
record it holds is the one the close was read against.

The second is the contender's. A refusal says only that somebody holds the
issue, and for one question that is not enough. A late cycle's retirement
takes the cycle identity off the record a write before the barrier that
answers a close observed inside it, and in the process making that write the
window is advertised to its own polls -- see `retiring_cycles`. A poller on
this host that was refused the claim reads the same record from outside that
process and finds no cycle on it: a close it read there would be dropped as
ending nothing, while the hold it could not see was still retiring the cycle
that close ends.

So a hold that retires a cycle says so on the claim file it holds, for as long
as the hold lasts, and a contender asks the file. The note is the hold's own:
only a writer holding the claim writes it, and every acquisition empties the
file first, so a note a crashed holder left can never be read as the next
holder's. It is read without the lock -- a contender cannot take it -- and
anything it cannot parse is read as no note at all.

Host-local exactly as the claim is, and for the pollers that share its
namespace: a poller on another host neither writes nor reads one.
"""
from __future__ import annotations

import logging

from orchestrator.scheduler import writer_claims

log = logging.getLogger("orchestrator.scheduler")

_RETIRING = "retiring-cycle="


def note_retirement(repo_id: int, issue_number: int, cycle_id: int) -> None:
    """Say on the claim this process holds that its hold retires `cycle_id`.

    Written ahead of the retirement write and left for the rest of the hold,
    because what a contender has to know is that the close it read may have
    landed while this hold was retiring the cycle -- not whether the write is
    still in flight. Nothing is written where this process holds no writer
    claim on the issue. A note that cannot be written costs only what the
    contender would have kept, so it is logged rather than raised: the
    retirement it describes is the work, and the note is not.
    """
    path = writer_claims.claim_path(repo_id, issue_number)
    try:
        writer_claims._holdings.noted(path, f"{_RETIRING}{int(cycle_id)}\n")
    except OSError as error:
        log.warning(
            "writer claim note repo_id=%s issue=#%d could not record the "
            "retirement of cycle %d (%s at %s)",
            repo_id, issue_number, cycle_id, error, path,
        )


def noted_retirement(repo_id: int, issue_number: int) -> int | None:
    """The cycle the hold on this issue's claim noted it is retiring, if any.

    Asked by a contender, whose refusal is what says a hold is standing; a
    file nobody could read, or one carrying anything but a note, answers
    `None`.
    """
    path = writer_claims.claim_path(repo_id, issue_number)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    noted = [line.removeprefix(_RETIRING) for line in lines if line.startswith(_RETIRING)]
    if not noted or not noted[-1].isdecimal():
        return None
    return int(noted[-1])


def foreign_holds(repo_id: int, issue_number: int) -> int:
    """How many holds of this issue by another poller this process has found.

    Read at the poll and again under the claim: an equal count is no other
    poller having held the issue in between, and so no other poller having
    written its record. A count only ever grows, and grows only when this
    process takes the claim, so a hold it has not yet found is counted no
    later than the acquisition that asks.
    """
    return writer_claims._holdings.foreign_holds(writer_claims.claim_path(repo_id, issue_number))
