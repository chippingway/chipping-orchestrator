# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the holds on an issue's writer claim tell the pollers that share it.

Two questions a claim's `True` or `False` cannot answer, both about a close a
poll read before it asked for the claim.

The first is the holder's. A poll's closed reading is older than the claim a
pass takes, and the record that pass reads names the cycle it names now: if
another poller held the issue in between, it may have settled the cycle the
close ended and started a fresh one. So a poll reads `moment` before it reads
anything off GitHub, and its closed reading carries that moment to the pass;
`writer_claims` learns, at every acquisition, when another poller's hold it
finds on the key ended. A pass under the claim for which every such hold had
ended before the poll's moment (`undisturbed_since`) knows no other poller has
held the issue since the close was read, and that the record it holds is the
one the close was read against. A hold that ended before the poll -- a
restarted poller's own predecessor's included -- is no reason to doubt it.

The second is the contender's. A refusal says only that somebody holds the
issue, and for one question that is not enough. A late cycle's retirement
takes the cycle identity off the record a write before the barrier that
answers a close observed inside it, and in the process making that write the
window is advertised to its own polls -- see `retiring_cycles`. A poller on
this host that was refused the claim reads the same record from outside that
process and finds no cycle on it: a close it read there would be dropped as
ending nothing, while the hold it could not see was still retiring the cycle
that close ends.

So a hold that retires a cycle says so on the claim file it holds
(`note_retirement`), for as long as the hold lasts, and a contender asks the
file (`noted_retirement`). The note is the hold's own: only a writer holding
the claim writes it, and it is read only off a file that hold signed and has
not stamped as released. The next holder takes the lock a moment before it
empties the file, so the stamp is what keeps a note from reaching past a hold
that let go. A hold killed holding the claim stamps nothing, and its note is
read until the next holder empties the file, the first thing that holder
does: until then it was the last hold to write the issue, and a close kept
over the cycle it noted is reconciled under the claim later, where one
dropped would be lost. It is read without the lock -- a contender cannot take
it -- and anything it cannot parse is read as no note at all.

Host-local exactly as the claim is, and for the pollers that share its
namespace: a poller on another host neither writes nor reads one.
"""
from __future__ import annotations

import logging

from orchestrator.scheduler import writer_claims

log = logging.getLogger("orchestrator.scheduler")

_RETIRING_KEY = "retiring-cycle"
_RETIRING = f"{_RETIRING_KEY}="


def note_retirement(repo_id: int, issue_number: int, cycle_id: int) -> None:
    """Say on the claim this process holds that its hold retires `cycle_id`.

    Written ahead of the retirement write and left for the rest of the hold,
    because what a contender has to know is that the close it read may have
    landed while this hold was retiring the cycle -- not whether the write is
    still in flight. Nothing is written where this process holds no writer
    claim on the issue. A note that cannot be written, or is cut short and
    taken back, costs only what the contender would have kept, so it is
    logged rather than raised: the retirement it describes is the work, and
    the note is not.
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
    `None`. Only a whole line is a note: the last piece of a file read while
    its holder writes, or one a write left cut short, has no line end, and a
    cut `retiring-cycle=43` would otherwise name cycle 4. And only a standing
    hold's line is one: a file no hold signed is nobody's note, and one whose
    hold stamped its release is a note of a hold that is over, still on the
    file only because the next holder has not emptied it yet.
    """
    path = writer_claims.claim_path(repo_id, issue_number)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    left = writer_claims._Left.read(text)
    noted = left.fields.get(_RETIRING_KEY, "")
    return int(noted) if left.standing and noted.isdecimal() else None


def moment() -> int:
    """Now, on the clock every hold on this host stamps its release with.

    Read by a poll BEFORE it lists anything, so the moment a closed reading
    carries is no later than the read it describes: a hold another poller
    made while the poll was reading counts as one made after it, never before.
    """
    return writer_claims._holdings.moment()


def undisturbed_since(repo_id: int, issue_number: int, read_at: int) -> bool:
    """Whether no other poller has held this issue since `read_at`, as far as this process has found.

    Asked under the issue's claim, where it is the whole answer: every hold of
    another poller before this one has been found by then, with when it
    ended. One that ended before `read_at` was over when the reading was
    taken; one that had not -- or one whose holder died without saying when
    -- may have written the record since.
    """
    return writer_claims._holdings.undisturbed_since(writer_claims.claim_path(repo_id, issue_number), read_at)
