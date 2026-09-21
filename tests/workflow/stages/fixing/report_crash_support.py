# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a crash between a report's record and its publication leaves behind.

A report is written to the pinned comment before the size gate and before the
push, so every window past that write is one a tick can die in and come back to
an issue that still says what its developer reported. These are the shapes those
windows leave -- a delivery nothing bound, with or without a receipt beside it --
and the reading a case about such a window actually needs: not what the comment
says once the dust settles, but what the FIRST write that mattered already said.
"""

from __future__ import annotations

from datetime import UTC, datetime as _datetime, timedelta as _timedelta
from unittest import mock

from orchestrator.github.pinned_state import PinnedState as _PinnedState
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.stages.fixing import (
    feedback as _feedback,
    models as _models,
)
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _publication_state,
)
from tests.support.fakes import FakeComment as _FakeComment, FakeUser as _FakeUser

# The pinned field a recorded, unbound report stands on.
_DELIVERED_REPORT = "developer_report_delivery"

# The pinned field naming the pull request a receipt is recorded against.
_PR_NUMBER = "pr_number"

# How a report this issue delivered is named, as the engine spells it.
_RECEIPT = "issue-{issue}-report-1"

# The author every reply these fixtures put on a thread is written by.
_HUMAN = "alice"


class _RecordsTheWrite:
    """One durable write, remembered as it goes by rather than read back."""

    def __init__(self, durable, written):
        self.durable = durable
        self.written = written

    def __call__(self, issue, state):
        self.written.append(dict(state.data))
        return self.durable(issue, state)


def recorded_writes(github, written):
    """Capture every pinned state this tick writes, in order, into `written`.

    What a case about a crash window asks is not what the comment says at the
    end but what the first write that mattered already said, so the states are
    captured as they go by rather than read back afterwards.
    """
    return mock.patch.object(
        github, "write_pinned_state",
        _RecordsTheWrite(github.write_pinned_state, written),
    )


def consumed_pairs(issue, readers, comment_id: int) -> tuple:
    """What one issue-thread reply comes to, off the owner that derives it.

    Built from the reply itself through the stage's own delivery owner rather
    than spelled out, so a case is about the pairs a round recorded being the
    pairs this stage derives -- not about a tuple a fixture chose that both
    sides happen to match.
    """
    seeded = _PinnedState(state_data=dict(readers))
    batch = _models._FixingFeedback(
        issue_thread=[
            seen for seen in issue.comments if seen.id == comment_id
        ],
        pr_conversation=[],
        review_comments=[],
        review_summaries=[],
    )
    return _feedback._consumed_delivery(seeded, batch).consumed_pairs(seeded)


def _now():
    """The tz-aware clock a settled comment's age is measured from."""
    return _datetime.now(UTC)


def recorded_delivery(
    seeded, readers, comment_id: int, *, landed: str = "", spends=(),
) -> None:
    """A report an earlier tick recorded and a crash left unbound.

    Spelled the way that tick would have written it: the report, and the input
    its run consumed riding the same record. `landed` is the code-publication
    receipt a crash AFTER the push leaves behind, and its absence is the crash
    before one. `spends` is the route bookkeeping that round froze -- the fix
    bookmarks it clears and the reviewer round it lands on -- which only the
    write that completes the publication may apply.
    """
    state = seeded.github.read_pinned_state(seeded.issue)
    state.set(_DELIVERED_REPORT, {
        "receipt": _RECEIPT.format(issue=seeded.issue.number),
        "revision": 1,
        "requirements": _content_hash._compute_user_content_hash(
            seeded.issue, (),
        ),
        "mode": "publish",
        "route": "workflow:fixing",
        "watermarks": [
            list(pair) for pair in consumed_pairs(
                seeded.issue, readers, comment_id,
            )
        ],
        "spends": [list(pair) for pair in spends],
        "report": "the run that answered this feedback reported it.",
    })
    if landed:
        _publication_state._record_publication(
            state, landed, "", state.get(_PR_NUMBER),
        )
    seeded.github.write_pinned_state(seeded.issue, state)


def later_pr_comment(pull_request, comment_id: int, body: str) -> None:
    """A reply on the pull request's own conversation, after the snapshot.

    Feedback the fixing scan reads and the requirements baseline does not: that
    hash covers the issue thread alone, so a comment here is unread input a
    publication can still settle around.
    """
    pull_request.issue_comments.append(_FakeComment(
        id=comment_id,
        body=body,
        user=_FakeUser(_HUMAN),
        created_at=_now() - _timedelta(hours=1),
    ))


def later_comment(issue, comment_id: int, body: str) -> None:
    """Put a human's reply on the thread after the crash that stalled it.

    What turns a stalled issue back into an ordinary fix round: the recovery
    has consumed everything the dead tick read, so only a reply that landed
    AFTER it gives the next round anything to answer.
    """
    issue.comments.append(_FakeComment(
        id=comment_id,
        body=body,
        user=_FakeUser(_HUMAN),
        created_at=_now() - _timedelta(hours=1),
    ))
