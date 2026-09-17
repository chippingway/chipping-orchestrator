# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What each field of a recorded report transaction may be.

The pinned comment is JSON a human can edit and an older binary may have
written, so nothing here trusts the type it finds. Every reader answers with an
absence rather than raising, for the reason the late readers do: a transaction
is recorded on an issue that already has committed work, and a `TypeError` out
of a state read would strand that work behind a crash on every poll instead of
behind something somebody can act on.

Fail-closed is the rule, and each field is read for what it IS rather than for
its Python type. A receipt has to be spelled the way the report header carries
it, because a receipt the header could not carry is one no retry could ever
find its own comment by. A slug has to be one repository name, a branch one
ref-shaped line, and the report text something that would still fit in a
comment -- a record holding more than a comment can hold describes a
publication that could never be made, and acting on it would mean publishing an
excerpt under a header that claims to be the whole report.

Text is held to what UTF-8 can carry, which is not the same as what `str` can
hold: the pinned comment is JSON, and JSON spells a lone surrogate as an escape
any decoder reads back into a string Python will not encode. Recorded, that
value survives every read here and raises at the far end -- where the report is
hashed for its content revision, or handed to a request -- so it is refused at
the point it is read instead.

Every number is bounded too, and for a reason the text fields do not have: the
identities and the revision a transaction records are COPIED into the records
its settlement adds, so a number wider than anything the far side ever issued
is a record that fits the comment now and settles into one GitHub refuses --
after the report is already on the thread, where nothing can still be repaired.

The report bound reserves headroom below what a comment holds, because the
record shares the pinned comment with everything else the issue has recorded.
What the ceiling protects is the write: a transaction accepted at the very
limit is one whose own pinned write GitHub then refuses, which would lose the
record the publication depends on at exactly the moment it is needed.
"""
from __future__ import annotations

import re

from orchestrator.github import comments as _trust
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.workflow.late_split import payloads as _payloads

# What the rest of a pinned comment is left when a report is recorded in it.
# The record shares the comment with the late generation, the watermarks, the
# bookmarks, and the comment-id ledger, and a report accepted at the ceiling is
# one whose own write is refused.
_RECORD_HEADROOM = 8192

# How long a recorded report may be. A report past it is refused where it is
# declared rather than cut, because an excerpt published under a header saying
# it is the complete report is indistinguishable from the report itself.
MAX_REPORT_TEXT = MAX_PINNED_BODY - _RECORD_HEADROOM

# How long a branch name this domain will carry may be. Published, like the
# slug halves below, because a record written BEFORE the publication it will be
# bound to has to reserve the room that publication's subject will take -- and
# a reservation narrower than what the field admits would accept a report whose
# own transaction the binding then refuses, after the code is already pushed.
MAX_BRANCH = 256

# How long each half of one repository slug may be.
MAX_SLUG_HALF = 100

# The range GitHub issues its identities out of, which the revision counted
# beside them is a small ordinal inside.
_RECORDED_NUMBER_BITS = 63

# The widest number this domain will record. Anything past this ceiling is a
# value nothing on the far side ever wrote -- and, unbounded, one the
# settlement's own write could not be measured against.
MAX_RECORDED_NUMBER = 2 ** _RECORDED_NUMBER_BITS - 1

# How a receipt has to be spelled for the report header to carry it verbatim,
# which is the same spelling `github/developer_reports.py` holds one to: a
# receipt the header cannot carry names a comment no retry could find.
_RECEIPT = re.compile("[A-Za-z0-9_.-]{1,128}")

# One repository, spelled as GitHub spells it, with both halves bounded: an
# owner is one of the values a settlement copies, so an unbounded one would be
# a record whose settling write cannot be measured. Anything else is not a
# repository this transaction could be held against.
_SLUG = re.compile(
    f"[A-Za-z0-9-]{{1,{MAX_SLUG_HALF}}}/[A-Za-z0-9._-]{{1,{MAX_SLUG_HALF}}}",
)

# One ref line: no whitespace, no control characters, nothing that would make
# a recorded branch two lines when something reads it back.
_BRANCH = re.compile(r"[^\s\x00-\x1f]+")


def as_receipt(raw: object) -> str | None:
    """Return the transaction receipt recorded, or None unless it is one.

    The bound is the report header's own, so a receipt that reads back here is
    one a published comment could actually be found by. Read any looser, a
    retry would search the thread for a scope no comment can carry and post a
    second report believing the first never landed.
    """
    if not isinstance(raw, str) or _RECEIPT.fullmatch(raw) is None:
        return None
    return raw


def as_slug(raw: object) -> str | None:
    """Return the repository a transaction is bound to, or None unless it is one.

    What keeps a recovered transaction on the repository it was recorded for.
    A value that is not one repository name is not a binding at all, and a
    reader that took it as one would compare it against the client's own slug
    and refuse every tick, or -- worse, if it happened to match loosely --
    publish a report onto somebody else's pull request.
    """
    if not isinstance(raw, str) or _SLUG.fullmatch(raw) is None:
        return None
    return raw


def carries_utf8(written: str) -> bool:
    """Whether recorded text is text UTF-8 can carry.

    The pinned comment is JSON, and JSON spells a lone surrogate as an escape
    every decoder reads back into a `str` Python refuses to encode. Nothing
    between here and the far end notices: it round trips through the comment,
    matches every pattern below, and raises at the digest that hashes a report
    or the request that carries it -- on a tick nobody is watching, with the
    transaction already recorded.
    """
    try:
        written.encode()
    except UnicodeEncodeError:
        return False
    return True


def as_branch(raw: object) -> str | None:
    """Return the branch a transaction is bound to, or None unless it is one.

    The other half of naming a publication: a pull request standing on the
    recorded commit says nothing about where that work would have been pushed,
    so the branch is proved beside it. Bounded and single-line, because what is
    compared against it is a ref the git layer resolved -- and encodable, since
    the pattern below admits every surrogate a JSON escape can spell.
    """
    if not isinstance(raw, str) or len(raw) > MAX_BRANCH:
        return None
    if not carries_utf8(raw):
        return None
    return raw if _BRANCH.fullmatch(raw) else None


def as_recorded_number(raw: object) -> int | None:
    """Return one recorded identity or revision, or None unless it is one.

    Positive, whole, and inside the ceiling above. The bound is what the
    settlement depends on rather than anything the pull request or the comment
    itself needs: every number here is written again into the records a
    settlement adds, so a reader that accepted an arbitrarily wide one would
    accept a transaction whose settling write is larger than any measurement
    taken before it.
    """
    number = _payloads.as_identity(raw)
    if number is None or number > MAX_RECORDED_NUMBER:
        return None
    return number


def as_report_text(raw: object) -> str | None:
    """Return the complete report recorded, or None unless one is.

    A report has to SAY something, has to be text UTF-8 can carry, has to be
    small enough that publishing it is still possible, and may not carry a
    receipt marker of this orchestrator's. Every refusal is the same answer:
    the record describes a publication this build cannot make. Whitespace alone
    is no report -- it renders to a
    comment with a header and nothing under it -- and a text past the ceiling
    is one the pinned write that recorded it should never have accepted, so
    reading it back is already evidence the comment was edited.

    The marker refusal is the one that matters on a thread rather than in a
    comment. Receipts are found by substring, so a report quoting one would
    read to the search that looks for it as the step it names -- and the
    published-report format refuses such a text at construction anyway, which
    would strand a transaction that had already been recorded. Refused here, it
    is caught where the record is still being read rather than where it can no
    longer be repaired.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    if _trust.carries_reserved_marker(raw) or not carries_utf8(raw):
        return None
    return raw if len(raw) <= MAX_REPORT_TEXT else None
