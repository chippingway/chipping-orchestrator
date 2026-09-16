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

# What the rest of a pinned comment is left when a report is recorded in it.
# The record shares the comment with the late generation, the watermarks, the
# bookmarks, and the comment-id ledger, and a report accepted at the ceiling is
# one whose own write is refused.
_RECORD_HEADROOM = 8192

# How long a recorded report may be. A report past it is refused where it is
# declared rather than cut, because an excerpt published under a header saying
# it is the complete report is indistinguishable from the report itself.
MAX_REPORT_TEXT = MAX_PINNED_BODY - _RECORD_HEADROOM

# How long a branch name this domain will carry may be.
_BRANCH_LIMIT = 256

# How a receipt has to be spelled for the report header to carry it verbatim,
# which is the same spelling `github/developer_reports.py` holds one to: a
# receipt the header cannot carry names a comment no retry could find.
_RECEIPT = re.compile("[A-Za-z0-9_.-]{1,128}")

# One repository, spelled as GitHub spells it. Anything else is not a
# repository this transaction could be held against.
_SLUG = re.compile("[A-Za-z0-9-]+/[A-Za-z0-9._-]{1,100}")

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


def as_branch(raw: object) -> str | None:
    """Return the branch a transaction is bound to, or None unless it is one.

    The other half of naming a publication: a pull request standing on the
    recorded commit says nothing about where that work would have been pushed,
    so the branch is proved beside it. Bounded and single-line, because what is
    compared against it is a ref the git layer resolved.
    """
    if not isinstance(raw, str) or len(raw) > _BRANCH_LIMIT:
        return None
    return raw if _BRANCH.fullmatch(raw) else None


def as_report_text(raw: object) -> str | None:
    """Return the complete report recorded, or None unless one is.

    A report has to SAY something, has to be small enough that publishing it is
    still possible, and may not carry a receipt marker of this orchestrator's.
    All three refusals are the same answer: the record describes a publication
    this build cannot make. Whitespace alone is no report -- it renders to a
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
    if _trust.carries_reserved_marker(raw):
        return None
    return raw if len(raw) <= MAX_REPORT_TEXT else None
