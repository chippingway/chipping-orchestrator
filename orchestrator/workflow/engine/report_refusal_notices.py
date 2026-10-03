# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a human and the log are told about a report this build would not record.

A finished run's report that cannot be recorded holds the tick, and the notice
announcing the hold is the whole of what the human who answers it is told: the
report was published nowhere, and the session that wrote it is resumed only by
their reply. So the notice names WHICH refusal it was and what clears that one,
because the four are cleared by different things. A report quoting a receipt
marker is written again without the literal text. One past the ceiling a
recorded report is held to is written shorter. One the pinned comment has no
room for is refused for room the issue's other records share with it. And a
record this build's own reader refuses for anything else is a record to
inspect, since nothing says its length or its words are the cause.

Room is the one refusal whose cure depends on what was recorded. A rewrite of
the report gives room back only where the measured write carries the report's
TEXT: the delivered record and the transaction it becomes do, for a report
written out in full. A verification carries where the report stands and the
digest read there, and the settlement carries where the report landed, so no
rewrite moves either and only freeing room on the comment does. And what a
rewrite has to save is counted in the comment's own characters rather than the
report's: the text is stored escaped for JSON, where a line break, a quote, or
anything outside ASCII costs more than one, so a report's length says little
about the room it takes. The notice gives both counts, the second in the very
rendering the refused write was measured in, and asks for the saving in it.

Size is named only where a size was measured and failed. A notice guessing at
length over a refusal no length decided sends the developer to shorten a report
refused for something else, and the reply buys a run that is refused again.

The refused text is never quoted back. A notice is a comment of this
orchestrator's own, and receipts are found by searching raw comment text, so a
marker quoted there would read as the step it names; it is described in prose
instead, which is exactly what the report is asked to do.

The log line carries the same cause beside its code -- the `RecordRefusal`
value, or `comment_overflow` with the write measured and the later writes it
was measured beside -- so an operator reading the log reads what the notice
says rather than a second guess at it.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from types import MappingProxyType

from orchestrator import config
from orchestrator.workflow.engine import (
    report_record_room as _room,
    report_record_values as _record_values,
    report_records as _records,
)

log = logging.getLogger("orchestrator.workflow")

_UNRECORDABLE_PARK = (
    "{mentions} this issue's developer run finished with a completion report "
    "this orchestrator cannot record on its pinned comment: {why}. Nothing was "
    "published: {withheld}. The report is recorded before any code goes out, "
    "because that record is the only thing a later tick could publish it "
    "from, and publishing the code anyway would hand review an implementation "
    "with no report and no record of what the run said. {recovery}"
)

# How every recovery ends, because every one is the same resume: the reply is
# what the session is resumed on, and a report alone is what it owes.
_RESUMED = (
    "the orchestrator resumes the session, which needs no new commit to "
    "deliver the report, and the report it writes then is the one that gets "
    "published"
)

_LOGGED = "issue=#%d %s; publishing nothing and holding for a human"


@dataclass(frozen=True)
class _Reading:
    """One refusal, as the notice and the log put it.

    `why` completes the notice's sentence about what refused the report,
    `recovery` is the notice's closing instruction, and `logged` is the log
    line's account of the same cause.
    """

    why: str
    recovery: str
    logged: str


_RESERVED_RECEIPT = _Reading(
    why=(
        "it contains the literal text that opens every hidden receipt this "
        "orchestrator records its own steps with, which no developer report "
        "may carry anywhere -- inline code, a fenced block, and a quotation "
        "included, since receipts are found by searching raw comment text and "
        "Markdown does not hide one from that search"
    ),
    recovery=(
        "Reply asking for the report again with every receipt or marker it "
        f"discusses described in prose rather than quoted, and {_RESUMED}."
    ),
    logged=(
        "wrote a developer report carrying the literal text that opens this "
        "orchestrator's hidden receipts (reserved_receipt)"
    ),
)

_INVALID_RECORD = _Reading(
    why=(
        "the record it would be written as is one this orchestrator's own "
        "reader would not hand back as written, so a member that record "
        "carries -- the requirements revision the run was handed, the "
        "report's text, or its bookkeeping -- will not read"
    ),
    recovery=(
        "Inspect this issue's pinned comment, whose requirements baseline the "
        "record is stamped with, and the orchestrator's log for this refusal, "
        f"then reply, and {_RESUMED}."
    ),
    logged=(
        "wrote a developer report whose record this build's own reader "
        "refuses (invalid_record; route {route}, requirements revision "
        "{requirements})"
    ),
)

_TOO_LONG = (
    "the report is {length} characters long, past the {ceiling} a recorded "
    "report may be"
)

_TOO_LONG_RECOVERY = "Reply asking for a report of at most {ceiling} characters, and {resumed}."

_TOO_LONG_LOGGED = (
    "wrote a developer report of {length} characters, past the {ceiling} a "
    "recorded report may be (report_too_long)"
)

_OVERFLOW = (
    "{write} would leave the pinned comment {size} characters long{later}, "
    "{over} past the {limit} GitHub accepts in one comment"
)

# What frees room for a report written out in full, measured where the write
# carries its text: the saving it needs is in the comment's characters, which is
# the escaped text rather than the report's own length.
_TEXT_ROOM = (
    "That comment stores the report's {length} characters of text as {stored} "
    "once escaped for JSON -- one for most plain ASCII characters, and two to "
    "twelve for a line break, a quote, a backslash, a control character, or "
    "anything outside ASCII. "
    "Reply asking for a report whose escaped text is at least {over} "
    "characters smaller -- the least this write needs, since the writes "
    "measured after it are reached only once it fits -- or free room on the "
    "pinned comment first, and {resumed}."
)

# What frees room where the measured write carries no report text at all.
_NO_TEXT_ROOM = (
    "{carried}, so no rewrite of the report makes room there: free room on "
    "the pinned comment, then reply, and {resumed}."
)

_VERIFIED_CARRIES = (
    "A verified report is recorded as where it stands and the digest read "
    "there, never as its text"
)

_SETTLED_CARRIES = "That write carries where the report landed rather than its text"

_OVERFLOW_LOGGED = (
    "cannot record its developer report ({mode}): the {write} write leaves "
    "the pinned comment {size} characters long (receipt reserved: {receipt}, "
    "hand-back reserved: {hand_back}), past the {limit} GitHub accepts "
    "(comment_overflow)"
)

_WRITES = MappingProxyType({
    _room.MeasuredWrite.RECORD: "the record of it",
    _room.MeasuredWrite.BINDING: (
        "the publication transaction it becomes once its code reaches a pull "
        "request"
    ),
    _room.MeasuredWrite.SETTLEMENT: (
        "the write that settles that transaction once the report is out"
    ),
})

_LATER = MappingProxyType({
    _room.LaterWrites(): "",
    _room.LaterWrites(receipt=True): (
        ", counting the code-publication receipt the push writes"
    ),
    _room.LaterWrites(hand_back=True): (
        ", counting the stale-approval hand-back"
    ),
    _room.LaterWrites(receipt=True, hand_back=True): (
        ", counting the code-publication receipt the push writes and the "
        "stale-approval hand-back"
    ),
})


def explains_the_refusal(
    issue_number: int,
    delivered: _records.DeliveredReport,
    refusal: _room.RecordingRefusal,
    withheld: str,
) -> str:
    """Log why this report was refused, and return the notice that tells a human.

    `withheld` is what the road that recorded it held back, which the caller
    knows and this owner does not: a pull request never opened, or one still
    standing on the commit it carried.
    """
    reading = _reading_of(delivered, refusal)
    log.error(_LOGGED, issue_number, reading.logged)
    return _UNRECORDABLE_PARK.format(
        mentions=config.HITL_MENTIONS,
        why=reading.why,
        withheld=withheld,
        recovery=reading.recovery,
    )


def _reading_of(
    delivered: _records.DeliveredReport, refusal: _room.RecordingRefusal,
) -> _Reading:
    """The reading one refusal earns, each measured one with its own numbers.

    A refusal this owner has no words for reads as the invalid record, the
    one reading that claims nothing about length or room, and its log line
    names what the record was stamped with so an operator can look for it.
    """
    if isinstance(refusal, _room.CommentOverflow):
        return _overflowed(delivered, refusal)
    if refusal is _record_values.RecordRefusal.RESERVED_RECEIPT:
        return _RESERVED_RECEIPT
    if refusal is not _record_values.RecordRefusal.REPORT_TOO_LONG:
        return replace(_INVALID_RECORD, logged=_INVALID_RECORD.logged.format(
            route=delivered.route,
            requirements=delivered.requirements_revision or "none",
        ))
    measured = {
        "length": len(delivered.report or ""),
        "ceiling": _record_values.MAX_REPORT_TEXT,
    }
    return _Reading(
        why=_TOO_LONG.format(**measured),
        recovery=_TOO_LONG_RECOVERY.format(**measured, resumed=_RESUMED),
        logged=_TOO_LONG_LOGGED.format(**measured),
    )


def _overflowed(
    delivered: _records.DeliveredReport, overflow: _room.CommentOverflow,
) -> _Reading:
    """The reading of one measured comment past the ceiling GitHub holds it to."""
    over = overflow.size - overflow.limit
    return _Reading(
        why=_OVERFLOW.format(
            write=_WRITES[overflow.write],
            size=overflow.size,
            later=_LATER[overflow.later],
            over=over,
            limit=overflow.limit,
        ),
        recovery=_room_recovery(delivered, overflow.write, over),
        logged=_OVERFLOW_LOGGED.format(
            mode=delivered.mode,
            write=overflow.write.value,
            size=overflow.size,
            receipt=overflow.later.receipt,
            hand_back=overflow.later.hand_back,
            limit=overflow.limit,
        ),
    )


def _room_recovery(
    delivered: _records.DeliveredReport, write: _room.MeasuredWrite, over: int,
) -> str:
    """What gives back the room one write lacked, and how much of it.

    Only a report written out in full, measured where the write carries its
    text, can be rewritten into less room. A verification has no text
    recorded anywhere, so it is asked about before the write is.
    """
    if delivered.mode is _records.ReportMode.VERIFY:
        return _NO_TEXT_ROOM.format(carried=_VERIFIED_CARRIES, resumed=_RESUMED)
    if write is _room.MeasuredWrite.SETTLEMENT:
        return _NO_TEXT_ROOM.format(carried=_SETTLED_CARRIES, resumed=_RESUMED)
    text = delivered.report or ""
    return _TEXT_ROOM.format(
        length=len(text), stored=_stored_length(text), over=over, resumed=_RESUMED,
    )


def _stored_length(text: str) -> int:
    """How many characters of an overflowing pinned comment this text takes.

    Counted in the rendering the refused write was measured in, which is the
    only one a saving can be counted in too. A comment past the ceiling is
    rendered with the HTML-comment terminators in its payload left unescaped
    -- escaping them only adds, so `pinned_state_body` falls back to the plain
    payload -- and a comment fits exactly when that plain rendering does. So
    what the text costs there, and what rewriting it saves, is its JSON escape
    alone: twelve characters for one outside the BMP, six for any other outside
    ASCII or a control character, two for a line break, a quote or a
    backslash. Rendered through `pinned_state_body` on its own, a short payload
    would take the terminator escape too and count five characters for every
    one in the text that the refused write never spent.
    """
    return len(json.dumps(text)) - len(json.dumps(""))
