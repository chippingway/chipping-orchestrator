# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Human replies with monotonic comment IDs for lifetime-budget scenarios."""
from __future__ import annotations

from tests.support.fakes import FakeComment, FakeUser

# The author of every comment a journey's thread carries. The allowlist is
# empty in the suite, so what this login decides is who said something rather
# than whether it was trusted.
OPERATOR = "geserdugarov"

# The floor a journey's own comment ids are minted above. The double mints its
# from 1000, so a human's comment written below that would sort under the
# receipts the orchestrator posts in answer to it.
_FIRST_COMMENT_ID = 1000


def said(issue, body: str) -> FakeComment:
    """One trusted comment, above every id the thread already carries.

    Above, because a watermark is what decides whether anybody has read it:
    a command written under the id a park's own notice ratcheted the mark to
    is one the tick that answers commands never sees.
    """
    written = FakeComment(
        id=_next_comment_id(issue), body=body, user=FakeUser(OPERATOR),
    )
    issue.comments.append(written)
    return written


def _next_comment_id(issue) -> int:
    """One id past everything the thread carries, ours and the humans'."""
    return max(
        (comment.id for comment in issue.comments), default=_FIRST_COMMENT_ID,
    ) + 1
