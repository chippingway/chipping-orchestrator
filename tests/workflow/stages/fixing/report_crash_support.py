# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What happens inside the windows a report round leaves open.

A report is written to the pinned comment before the size gate and before the
push, so every window past that write is one a tick can die in and come back to
an issue that still says what its developer reported. These are the shapes those
windows leave -- a delivery nothing bound, with or without a receipt beside it --
and the readings a case about one actually needs: the checkout every report road
re-proves, and the route bookkeeping such a record is still holding.

The minutes a developer is OUT are a window of the same kind, and what arrives
in them is here too, on each of the two surfaces a fixing scan reads: the issue
thread the requirements baseline covers, and the pull request conversation it
does not.
"""

from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path
from unittest import mock

from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.github.pinned_state import PinnedState as _PinnedState
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    report_delivery_state as _delivery_state,
)
from orchestrator.workflow.stages.fixing import (
    feedback as _feedback,
    models as _models,
)
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _publication_state,
)
from tests.support import fakes
from tests.workflow.stages.fixing import fixing_test_support as _support

# The pinned field a recorded, unbound report stands on.
_DELIVERED_REPORT = "developer_report_delivery"

# How a report this issue delivered is named, as the engine spells it.
_RECEIPT = "issue-{issue}-report-1"

# The author every reply these fixtures put on a thread is written by.
_HUMAN = "alice"


@contextlib.contextmanager
def on_a_real_checkout():
    """A tick whose worktree probe answers a directory that is really there.

    Every report road re-proves the checkout rather than remembering a
    receipt, so a case about one surviving that proof has to have one: the
    shared probe names a path no host holds, which is the answer the
    missing-checkout park is about rather than a backdrop for anything else.
    """
    with tempfile.TemporaryDirectory() as checkout, mock.patch.object(
        _support.worktree_paths, _support.WORKTREE_PATH,
        return_value=Path(checkout),
    ):
        yield


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
            state, landed, "", state.get("pr_number"),
        )
    seeded.github.write_pinned_state(seeded.issue, state)


def later_pr_comment(pull_request, comment_id: int, body: str) -> None:
    """A reply on the pull request's own conversation, after the snapshot.

    Feedback the fixing scan reads and the requirements baseline does not:
    that hash covers the issue thread alone, so a comment here is unread input
    an outstanding publication can still settle around.
    """
    pull_request.issue_comments.append(fakes.FakeComment(
        id=comment_id,
        body=body,
        user=fakes.FakeUser(_HUMAN),
        created_at=_support.now_utc() - _support.timedelta(hours=1),
    ))


def later_comment(issue, comment_id: int, body: str) -> None:
    """Put a human's reply on the thread after the crash that stalled it.

    What turns a stalled issue back into an ordinary fix round: the recovery
    has consumed everything the dead tick read, so only a reply that landed
    AFTER it gives the next round anything to answer.
    """
    issue.comments.append(fakes.FakeComment(
        id=comment_id,
        body=body,
        user=fakes.FakeUser(_HUMAN),
        created_at=_support.now_utc() - _support.timedelta(hours=1),
    ))


def a_tree(*, readable: bool = True, paths=()):
    """One worktree status probe answer, spelled by the case that wants it.

    The two refusals a report road tells apart live here rather than in a
    case: a tree this host PROVED dirty is one no later poll takes back, and a
    status nobody could read is not that at all.
    """
    return _WorktreeStatus(readable=readable, paths=tuple(paths))


def frozen_record(pinned_data):
    """The unbound report record this comment is still holding, or None.

    Read off the record rather than off the comment, because that is the whole
    difference a reported round makes: the readers it consumed and the round
    its route spends both exist and neither has been applied, and only the
    write that publishes the report may apply either.
    """
    return _delivery_state.read_delivered_report(
        _PinnedState(state_data=dict(pinned_data)),
    )
