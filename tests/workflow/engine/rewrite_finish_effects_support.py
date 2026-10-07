# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a landed rewrite's finish says, and what it meets on issue #7 while it runs.

The notice and the `base_rebased` event as a case reads them back -- spelled
literally, since the pull requests and the sinks already carry them -- a
relabel that remembers what the pinned comment durably said when it came, a
comment filled to a chosen room and the room a write takes on it, and a
human's reply on the thread.
"""
from __future__ import annotations

from orchestrator.github import comments as _trust
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.engine.rewrite_finish_test_support import (
    ISSUE,
    KEY_REWRITE_DEBT,
    LANDED,
    PR_NUMBER,
    FinishWorld,
    owed,
)

# A pinned key nothing reads, standing in for whatever else fills the comment.
FILLER = "room_filler"

_HUMAN_LOGIN = "human"


def posted(notice: str) -> str:
    """`notice` as the pull request carries it, stamped as this orchestrator's own comment."""
    return f"{notice}\n\n{_trust.ORCHESTRATOR_COMMENT_MARKER}"


def rebased(method: str) -> dict:
    """The `base_rebased` payload a finish of PR #42 onto `LANDED` files through `method`, without its timestamp."""
    return {
        "repo": "chippingway/chipping-orchestrator",
        "issue": ISSUE,
        "event": "base_rebased",
        "stage": "fixing",
        "pr_number": PR_NUMBER,
        "sha": LANDED,
        "method": method,
        "review_round": 0,
    }


class DurableAtTheRelabel:
    """A relabel that remembers what the pinned comment durably said when it came.

    What a finish has made durable by then is what a process lost in the
    relabel comes back to, so it is the record the route is held to.
    """

    def __init__(self, world: FinishWorld) -> None:
        self._github = world.github
        self._relabel = world.github.set_workflow_label
        self.seen: list[dict] = []
        world.github.set_workflow_label = self

    def __call__(self, issue, label) -> None:
        """Read the durable record, then apply the label."""
        self.seen.append(self._github.pinned_data(issue.number))
        self._relabel(issue, label)


def leaves(world: FinishWorld, room: int) -> None:
    """Fill issue #7's pinned comment until `room` characters are left under the limit."""
    pinned = world.github._pinned[ISSUE].data
    pinned[FILLER] = ""
    filled = MAX_PINNED_BODY - room - len(pinned_state_body(pinned))
    pinned[FILLER] = "x" * filled


def makes_room(world: FinishWorld) -> None:
    """Take the filler back off issue #7's pinned comment, as a human making room does."""
    pinned = world.github._pinned[ISSUE]
    pinned.data.pop(FILLER)


def room_for(world: FinishWorld, **added: object) -> int:
    """The room `added` takes on issue #7's pinned comment as it stands; the debt alone by default."""
    durable = world.pinned()
    grown = {**durable, **(added or {KEY_REWRITE_DEBT: owed()})}
    return len(pinned_state_body(grown)) - len(pinned_state_body(durable))


def replies(world: FinishWorld) -> int:
    """A human's reply on issue #7's thread; its id."""
    reply = FakeComment(
        id=world.github.next_reply_id(world.issue),
        body="made room, please retry",
        user=FakeUser(_HUMAN_LOGIN),
    )
    world.issue.comments.append(reply)
    return reply.id
