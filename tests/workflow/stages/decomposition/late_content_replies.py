# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Human guidance, authorization, and comment builders for late-content tests."""
from __future__ import annotations

from tests.support.fakes import (
    FakeComment,
    FakeIssue,
    FakeUser,
)
from tests.workflow.stages.decomposition import late_test_support as _support

HUMAN = "geserdugarov"

GUIDANCE_BODY = "the migration is a separate change; take it out of this one"
AUTHORIZE_COMMAND = "/orchestrator authorize-oversized"

GUIDANCE_ID = 11

# The id a park's own notice took. A park that announced itself ratcheted the
# shared consumed watermark past it, so a seeded park carries that too -- it is
# what makes a REPLY tell itself apart from conversation the issue was already
# carrying when the park fired, and what `reply` lands above.
PARK_NOTICE_ID = 100


def human_comment(
    comment_id: int,
    body: str,
    *,
    login: str = HUMAN,
    user_type: str = "User",
) -> FakeComment:
    """One comment on the issue thread, authored by whoever is named."""
    return FakeComment(
        id=comment_id, body=body, user=FakeUser(login, user_type),
    )


def authorization(named: str = _support.CANDIDATE_SHA) -> str:
    """The whole comment that authorizes one candidate to publish unsplit.

    Built against a commit rather than fixed, because half of what these tests
    are about is which commit was named: the parked candidate, one it has been
    replaced by, and an argument that is no commit at all all arrive as the
    same command.
    """
    return f"{AUTHORIZE_COMMAND} {named}"


def guidance_comment(comment_id: int = GUIDANCE_ID) -> FakeComment:
    """The trusted comment that says the work itself has to change."""
    return human_comment(comment_id, GUIDANCE_BODY)


def reply(issue: FakeIssue, body: str = GUIDANCE_BODY) -> FakeComment:
    """Append one trusted human reply after everything already on the thread.

    What a real reply to a park is: written once the human has read the notice,
    and therefore carrying an id above it. That means above everything the
    thread carries AND above `PARK_NOTICE_ID`, since a seeded park records the
    id its notice took rather than the comment itself. A test that seeds a
    comment by a fixed id is describing conversation the issue was already
    carrying when the park fired; this is the answer to what the workflow just
    said.
    """
    posted = human_comment(
        1 + max([
            PARK_NOTICE_ID,
            *(issue_comment.id for issue_comment in issue.comments),
        ]),
        body,
    )
    issue.comments.append(posted)
    return posted
