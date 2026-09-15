# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a cycle's ending leaves behind, past the write that clears it.

Two records, kept together because they answer the same question from the two
ends a generation can stop at, and kept OUTSIDE `LATE_STATE_KEYS` for the one
reason both exist: clearing late mode is defined as dropping exactly the
generation's own group, and each of these is a fact about that generation
which has to outlive the drop. A key inside the group would be taken by the
same write it is written in.

The retirement correlation names the cycle a clear dropped. A close observed
INSIDE that write leaves a receipt scoped to a cycle the record no longer
names, and without the correlation there is nothing left to adopt it against.
It names ONE such window and outlives no other: the receipt it correlates to
is a comment, comments are append-only, and a correlation left standing past
its window would let a cycle-scoped receipt be adopted against a record whose
cycle is two generations newer.

The terminal record says a `rejected` was owed and then that it landed. Two
fields because it is a two-phase record, exactly as an external obligation is:
the identity says which cycle the terminal is about and goes down BEFORE the
label write, so a tick that died in between has something durable to come back
to; the flag says the label was PROVED to be on the issue and goes down after.
Only the pair authorizes a restart. An attempt is not a terminal -- a write
GitHub refused leaves an owner that is unlabeled for the reason it always was,
and treating the intent as proof would start a fresh cycle on a gesture nobody
made.

The proof is that the label IS on the issue, and it is reached three ways. The
pass that made the write takes it returning, and has to: reading the issue
back proves no more than what that write left on the object it went through,
and on any other object answers with the label it wore a moment ago -- and a
closed owner leaves the sweep on that write with no second visit to correct
it. Any later pass takes it by SEEING `rejected` on the issue, which is what
backfills a cancellation that ended before this record existed. And where the
decision stands with neither -- a process that died between the label and
the flag -- the remote's own label history is asked, because that window is
the one thing no local record can answer for and an operator's removal would
otherwise be spent re-applying a terminal that had already landed.

Every field here is read through the domain's own readers, so a hand-edited
identity or a `"true"` string reads back as no ending at all -- which refuses
a restart rather than authorizing one on a value anybody could have typed.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import payloads as _payloads

LATE_RETIRED_CYCLE_ID = "late_retired_cycle_id"

LATE_TERMINAL_CYCLE_ID = "late_terminal_cycle_id"

LATE_TERMINAL_CONFIRMED = "late_terminal_confirmed"


def read_retired_cycle(state: PinnedState) -> int | None:
    """The cycle a retirement dropped off this record, if one did.

    Read through the domain's own identity reader, so a hand-edited value
    reads back as no retirement at all rather than as a cycle nothing can be
    correlated with.
    """
    return _payloads.as_identity(state.get(LATE_RETIRED_CYCLE_ID))


def record_retired_cycle(state: PinnedState, cycle_id: int) -> None:
    """Say which cycle the write that clears late mode is dropping.

    Written in the SAME pinned write as the clear, because what it exists for
    is the window between that write and the barrier behind it: a poll
    observing the close in there receipts a cycle the record has stopped
    naming, and a process that dies before the barrier runs leaves the receipt
    with nothing to be adopted against.

    What ends the window is `clear_retired_cycle` and the generation write
    that asks for it, between them.
    """
    state.set(LATE_RETIRED_CYCLE_ID, int(cycle_id))


def clear_retired_cycle(state: PinnedState) -> None:
    """Drop the retirement correlation, leaving every other field alone.

    Asked by the write that records a generation with an IDENTITY, which is
    the one state that says the window a correlation names is over: either
    the adoption itself put the cycle back, or an operator authorized a fresh
    one. Left standing past that, a cycle-scoped receipt could be adopted
    against a record whose cycle is generations newer -- moving a completed
    owner to `rejected` on a close that ended something else entirely.

    Every retirement that DROPS a cycle records one instead, the umbrella's
    terminal included: the barrier that answers a close observed inside such
    a write belongs to the process that made it, so a process that dies first
    leaves the correlation and the receipt as the only pair a later one can
    read the ending back from.
    """
    state.data.pop(LATE_RETIRED_CYCLE_ID, None)


def terminal_confirmed(state: PinnedState, cycle_id: int) -> bool:
    """Whether THIS cycle's terminal is recorded as proved on the issue.

    Both halves, and the identity first: a flag left by an earlier cycle says
    nothing about this one, and an issue reaches a terminal more than once.

    The absence of it is the whole question a caller asks. Whether the
    decision half is there beside it separates a terminal this binary
    attempted from one an older one wrote, and neither is proof -- so nothing
    reads the decision on its own.
    """
    if _payloads.as_identity(state.get(LATE_TERMINAL_CYCLE_ID)) != cycle_id:
        return False
    return _payloads.as_flag(state.get(LATE_TERMINAL_CONFIRMED))


def record_terminal(
    state: PinnedState, cycle_id: int, *, confirmed: bool,
) -> None:
    """Record which cycle the terminal is about, and whether it is proved.

    The unconfirmed write is the decision, made durable before the label it
    carries out; the confirmed one is the receipt. An unconfirmed record
    DROPS the flag rather than leaving it, because the same field is reused by
    every cycle this issue ends: a confirmation left standing from the cycle
    before would authorize a restart over an attempt that has not landed yet.
    """
    state.set(LATE_TERMINAL_CYCLE_ID, int(cycle_id))
    if confirmed:
        state.set(LATE_TERMINAL_CONFIRMED, True)
    else:
        state.data.pop(LATE_TERMINAL_CONFIRMED, None)
