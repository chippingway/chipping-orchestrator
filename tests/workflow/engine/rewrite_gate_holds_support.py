# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two holds a gated auto-rebase publication can end in: an adjudication, and a park.

Both the ordinary publication of a clean rebase and the retry of a replay an
interrupted tick never published reach the size gate with issue #7's replay
standing in the checkout and PR #42 on the anchor, and a hold is the whole of
what the tick does with it. One hold hands the replay to an adjudication -- a
count past the ceiling -- and the other parks it -- a count nobody can pin.
These answer the count each way, and say where each hold leaves the replay.
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git.measurement import additions as _measurement
from orchestrator.git.measurement.models import AdditionMeasurement, MeasurementFailure
from orchestrator.workflow.engine import comments as _comments, content_hash as _content_hash
from tests.git.base_sync import refresh_test_support as _base
from tests.git.base_sync.gate_reads_support import _oversized_count
from tests.workflow.engine import rewrite_publication_test_support as _world

# The attempt's anchor and the replay it recorded making, and the replay a
# live generation took over.
KEY_ANCHOR = "pending_auto_base_rebase_push_sha"
KEY_RECORDED = "pending_auto_base_rebase_rewrite_sha"
KEY_REPLAY = "late_auto_rebase_replay_sha"

# The reply watermark a park's notice moves past itself, and the requirements
# baseline the adjudication counts a thread's comments up to.
KEY_WATERMARK = "last_action_comment_id"
KEY_BASELINE = "user_content_hash"

# Two replies to a park the refresh left, and whether each is only the retry
# it asked for: the attempt's to spend, where the other is a human's words.
REPLIES = (
    ("please retry", True),
    ("branch reconciled, please retry", False),
)

# A ceiling the oversized count crosses.
_CEILING = 5


@contextlib.contextmanager
def oversized():
    """A count past the ceiling, which hands the replay to an adjudication."""
    with patch.object(config, "MAX_ADDED_LINES", _CEILING), patch.object(
        _measurement, "_count_added_lines", _oversized_count(),
    ):
        yield


@contextlib.contextmanager
def unpinnable():
    """A count whose diff nothing here can pin, which parks the replay instead."""
    failed = MagicMock(return_value=AdditionMeasurement(
        base_sha=_base.GATE_BASE_SHA,
        candidate_sha=_base.GATE_CANDIDATE_SHA,
        failure=MeasurementFailure.DIFF_UNPINNABLE,
    ))
    with patch.object(config, "MAX_ADDED_LINES", _CEILING), patch.object(
        _measurement, "_count_added_lines", failed,
    ):
        yield


# Each hold, and what it leaves: the labels written, who holds the replay --
# the attempt's anchor and record of it, then the generation's takeover -- and
# the park. Routed, the attempt is handed over with nobody parked; parked, it
# stands for its recovery with no generation owning anything.
HOLDS = (
    (
        oversized,
        ((_base.ISSUE, "workflow:decomposing"),),
        (None, None, _world.REPLAY),
        (False, None),
    ),
    (
        unpinnable,
        (),
        (_world.ANCHOR, _world.REPLAY, None),
        (True, "late_measurement_failed"),
    ),
)


def left_with(github) -> tuple:
    """Who holds issue #7's replay: the attempt's anchor and record of it, and the generation's takeover."""
    durable = github.pinned_data(_base.ISSUE)
    return durable.get(KEY_ANCHOR), durable.get(KEY_RECORDED), durable.get(KEY_REPLAY)


def covers_the_thread(github) -> None:
    """Record issue #7's requirements baseline over its thread as far as its reply watermark reaches."""
    issue = github._issues[_base.ISSUE]
    durable = github.read_pinned_state(issue)
    durable.set(KEY_BASELINE, baseline_through(github, durable.get(KEY_WATERMARK)))
    github.write_pinned_state(issue, durable)


def baseline_through(github, last: int | None) -> str:
    """Issue #7's requirements baseline over its title, its body, and its thread through comment `last`, if any."""
    issue = github._issues[_base.ISSUE]
    return _content_hash._compute_user_content_hash(
        issue,
        _comments._orchestrator_ids(github.read_pinned_state(issue)),
        comments=[seen for seen in issue.comments if seen.id <= (last or 0)],
    )


def read_through(github) -> tuple:
    """How far issue #7's thread is recorded read: its reply watermark and its requirements baseline."""
    durable = github.pinned_data(_base.ISSUE)
    return durable.get(KEY_WATERMARK), durable.get(KEY_BASELINE)


def replies(case, body: str) -> int:
    """A trusted human's reply on issue #7's thread, past everything on it; its id."""
    reply = case.gh.next_reply_id(case.gh._issues[_base.ISSUE])
    case._add_comment(reply, body, _base.HUMAN_LOGIN)
    return reply
