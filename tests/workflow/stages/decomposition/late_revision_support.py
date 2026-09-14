# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The finished developer run the revision tests reconcile.

One description of the run, for every test that reads what it left: what a
resumed developer's worktree becomes, what an UNCHANGED commit needs before it
may become anything, and what a split that already acted outside refuses it.
They share every fixture -- the locked session, the measurement a re-freeze
answers with, and the four replies a run can end on -- so the replies and the
commit they leave behind stay one description rather than several that drift.

The four replies are the whole point of the split. All of them can leave HEAD
exactly where it was, and only one of them is an answer.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.git.measurement.models import (
    AdditionMeasurement,
    MeasurementFailure,
)
from tests.support.fakes import FakeLabel
from tests.workflow.stages.decomposition.late_content_replies import reply
from tests.workflow.stages.decomposition.late_content_support import (
    DRIFT_PARKED,
    EDITED_TITLE,
    REVISED_ADDITIONS,
    REVISED_BASE_SHA,
    REVISED_SHA,
    LateContentCase,
)
from tests.workflow.stages.decomposition.late_run_support import (
    WorktreeSeed,
    agent_reply,
)
from tests.workflow.stages.decomposition.late_test_support import (
    ADDITIONS,
    CANDIDATE_SHA,
)

DEV_AGENT = "dev_agent"
DEV_SESSION_ID = "dev_session_id"
DEV_SPEC = "claude --effort high"
DEV_SESSION = "dev-sess"

DEV_PIN = MappingProxyType(
    {DEV_AGENT: DEV_SPEC, DEV_SESSION_ID: DEV_SESSION},
)

# The marker the revision prompt asks for, and the three replies that are not
# it: prose that merely sounds like agreement, a question, and silence.
DEV_ACK = "looked again.\n\nACK: the committed work already covers that."

DEV_SOUNDS_LIKE_ACK = "the committed work already covers that, I think."

DEV_QUESTION = "should the migration keep the old column as well?"

DEV_SILENT = ""

NON_ANSWERS = (
    ("prose without the marker", DEV_SOUNDS_LIKE_ACK),
    ("a question", DEV_QUESTION),
    ("no message at all", DEV_SILENT),
)

REMEASURED = AdditionMeasurement(
    base_sha=REVISED_BASE_SHA,
    candidate_sha=REVISED_SHA,
    additions=REVISED_ADDITIONS,
)

# The same revision coming back past the ceiling instead of under it. The two
# read the same until the size gate looks, and they route the next tick
# completely differently -- one is adjudicated again, the other is not
# adjudicable at all.
REMEASURED_OVERSIZED = AdditionMeasurement(
    base_sha=REVISED_BASE_SHA,
    candidate_sha=REVISED_SHA,
    additions=ADDITIONS,
)

# What an unchanged commit measures to: the candidate that went in, re-read
# against a base that may well have moved under it.
ACKNOWLEDGED = AdditionMeasurement(
    base_sha=REVISED_BASE_SHA,
    candidate_sha=CANDIDATE_SHA,
    additions=ADDITIONS,
)

# What a checkout an agent has been running in can leave behind: a diff
# nothing here can pin, and the line the reading wrote for itself.
UNMEASURED_DETAIL = "fatal: .gitattributes: unable to read"

UNMEASURED = AdditionMeasurement(
    base_sha=REVISED_BASE_SHA,
    failure=MeasurementFailure.DIFF_UNPINNABLE,
    detail=UNMEASURED_DETAIL,
)

DIRTY_TREE = ("orchestrator/left_over.py",)

# What each of the two notices a finished revision can owe says, in the one
# phrase that tells it from every other comment on the thread. Asserted on
# rather than the whole sentence, because what these tests are about is
# whether it was said at all.
REMEASURED_NOTICE = "adjudicating it as generation"
DIRTY_NOTICE = "left changes in the"

PAUSED_LABEL = "paused"

UNCHANGED = WorktreeSeed(head=CANDIDATE_SHA)


class RevisionCase(LateContentCase):
    """A late issue whose next tick reconciles a developer's own worktree."""

    def _seed_drifted(self, *, guided: bool = True) -> None:
        self._seed(**DRIFT_PARKED, **DEV_PIN)
        self.issue.title = EDITED_TITLE
        if guided:
            self.guidance = reply(self.issue)

    def _revise(self, reply=DEV_ACK, seed=None, measurement=REMEASURED):
        return self._run(
            reply, worktree=seed or WorktreeSeed(head=REVISED_SHA),
            measurement=measurement,
        )


class PausedDuringRun:
    """An operator applying `paused` while the developer is still running."""

    def __init__(self, case: RevisionCase) -> None:
        self._case = case

    def __call__(self, *_args, **_kwargs):
        self._case.issue.labels.append(FakeLabel(PAUSED_LABEL))
        return agent_reply(DEV_ACK)
