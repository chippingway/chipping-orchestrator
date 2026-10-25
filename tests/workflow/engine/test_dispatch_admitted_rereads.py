# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Readings a dispatch takes past its gate, held to admission as the gate's own is.

The gate admits the dispatched issue's record under its claim, and two readings
come after it: the stage handler's own, which a human can edit the comment
under, and a family parent's reading of each child it would release, taken
under that child's claim. One admission refuses stops what was about to act on
it -- the handler abandoned before anything it would write, the walk releasing
no child -- and is said only in a local line. So does a record a human edits
after the handler's own reading, which the handler's next write meets: the
writer raises, and nothing that write was for is done -- or which the charge
of its next agent launch reads: no agent runs, and a handler that tears its
scratch checkout down on every exit keeps it for the human who disposes of the
record.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import issue_processing as _issue_processing, stage_targets as _stage_targets
from orchestrator.workflow.late_split import models as _late_models, phases as _late_phases, state as _late_state
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine.writer_claim_test_support import (
    DISPATCH_MODES,
    DONE_CHILD,
    FAMILY_PARENT,
    WAITING_CHILD,
    StandInHandler,
    WriterClaimDispatchCase,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    LABEL_QUESTION,
    LABEL_READY,
    _agent,
    _PatchedWorkflowMixin,
)

_WORKFLOW_LOG = "orchestrator.workflow"

_ANOTHER_VERSION = 2

_ISSUE = 41

# What the issue's record carries, before and after the human's edit: fields a
# handler reading the record as current would act on.
_RECORDED = MappingProxyType({"pickup_comment_id": 99, "agent_runs_used": 3})

# A record no pickup comment has been recorded on, which the `ready` handler
# greets before it hands the issue to implementation.
_UNGREETED = MappingProxyType({"agent_runs_used": 3})

# The two stages that tear a scratch checkout down on every exit, raising ones
# included, and the teardown each would run.
_SCRATCH_TEARDOWNS = (
    (LABEL_QUESTION, "_cleanup_question_worktree"),
    (LABEL_DECOMPOSING, "_cleanup_decompose_worktree"),
)

# The readings a dispatch takes before an agent launch's charge reads the
# record: the gate's and the handler's own.
_READINGS_BEFORE_THE_CHARGE = 2

# The readings a `ready` dispatch takes before its handoff reads the comment
# afresh to land on: the gate's and the handler's own.
_READINGS_BEFORE_THE_HANDOFF = 2

# Every label a stage handler is chosen by; the unlabeled pickup reads no record.
_HANDLED = tuple(label for label in _stage_targets._STAGE_HANDLER_TARGETS if label is not None)


class HandlerRereadTest(unittest.TestCase):
    """A handler whose own reading admission refuses is abandoned where it read it."""

    def test_a_later_edit_abandons_every_handler(self) -> None:
        # The gate reads the record current; a human edits it into another
        # version before the handler reads it again. Whichever stage the label
        # names, nothing is posted, relabelled, or pinned, and the pass ends
        # as an ordinary one rather than a failure.
        for label in _HANDLED:
            with self.subTest(label=label):
                github = FakeGitHubClient([make_issue(_ISSUE, label=label)])
                github.seed_state(_ISSUE, **_RECORDED)
                edits = _EditedAfterReadings(github, 1)

                with patch.object(github, "read_pinned_state", edits), self.assertLogs(_WORKFLOW_LOG) as logged:
                    _issue_processing._process_issue(github, _TEST_SPEC, github.get_issue(_ISSUE))
                    abandoned = _said(logged.output, "abandoning the stage handler")

                self.assertEqual(_written(github), ([], [], 0), "nothing is written past the refused reading")
                self.assertEqual(github.pinned_data(_ISSUE), dict(_RECORDED, schema_version=_ANOTHER_VERSION))
                self.assertTrue(abandoned)

    def test_a_refused_write_abandons_the_handler(self) -> None:
        # The `ready` handler reads the record current, and a human edits it
        # into another version just ahead of the handler's first write -- the
        # guarded handoff, which reads the comment afresh to land on. It is
        # refused there, so no greeting is posted, the label does not move to
        # implementation, nothing is pinned, and the pass ends as an ordinary
        # one.
        github = FakeGitHubClient([make_issue(_ISSUE, label=LABEL_READY)])
        github.seed_state(_ISSUE, **_UNGREETED)
        edits = _EditedAfterReadings(github, _READINGS_BEFORE_THE_HANDOFF)

        with patch.object(github, "read_pinned_state", edits):
            _issue_processing._process_issue(github, _TEST_SPEC, github.get_issue(_ISSUE))

        self.assertEqual(_written(github), ([], [], 0), "nothing is said or moved past the refused write")
        self.assertEqual(github.pinned_data(_ISSUE), dict(_UNGREETED, schema_version=_ANOTHER_VERSION))


class ChargeRefusalTest(_PatchedWorkflowMixin, unittest.TestCase):
    """A launch whose charge reads a record a human edited since the handler read it."""

    def test_a_refused_charge_keeps_the_checkout(self) -> None:
        # The question and decomposing handlers tear their scratch checkout
        # down on every exit. A record a human edits into another version just
        # before the launch's charge reads it is refused there: no agent runs,
        # nothing is written, and the checkout and its branch stay.
        for label, teardown in _SCRATCH_TEARDOWNS:
            with self.subTest(label=label):
                github = FakeGitHubClient([make_issue(_ISSUE, label=label, body="How does this work?")])
                github.seed_state(_ISSUE, **_UNGREETED)

                mocks = self._charged_after_an_edit(github)

                self.assertEqual(mocks["run_agent"].call_count, 0, "no agent runs")
                self.assertEqual(mocks[teardown].call_count, 0, "the checkout and its branch stay")
                self.assertEqual(github.pinned_data(_ISSUE), dict(_UNGREETED, schema_version=_ANOTHER_VERSION))

    def _charged_after_an_edit(self, github: FakeGitHubClient) -> dict:
        """One dispatch whose record is edited after the handler's own reading, answering the stood-in seams."""
        edits = _EditedAfterReadings(github, _READINGS_BEFORE_THE_CHARGE)
        with patch.object(github, "read_pinned_state", edits), patch.object(config, "DECOMPOSE", True):
            return self._run(
                lambda: _issue_processing._process_issue(github, _TEST_SPEC, github.get_issue(_ISSUE)),
                run_agent=_agent(),
            )


class RefusedChildReleaseTest(WriterClaimDispatchCase):
    """A late split's parent, dispatched as ever, releases no child whose record admission refuses."""

    def test_a_refused_child_waits_for_its_record(self) -> None:
        for mode, limit, scheduled in DISPATCH_MODES:
            with self.subTest(mode=mode):
                self._seeded_late_family()
                refused = self.github.pinned_data(WAITING_CHILD)

                self.assertTrue(self._ticked_and_reported(limit, scheduled=scheduled), "the refusal is said locally")

                self.assertEqual(self.github.pinned_data(WAITING_CHILD), refused, "nothing is written to the child")
                self.assertEqual(
                    (self.github.label_history, self.github.posted_comments), ([], []),
                    "the child is not released, and nothing parks the parent",
                )

                self.github.seed_state(WAITING_CHILD, parent_number=FAMILY_PARENT)
                self.ticked(StandInHandler(), limit=limit, scheduled=scheduled)

                self.assertEqual(self.github.label_history[0], (WAITING_CHILD, LABEL_READY), "a current one is")

    def _ticked_and_reported(self, limit: int, *, scheduled: bool) -> bool:
        """One tick, answering whether a warning named the refused child's pinned comment."""
        with self.assertLogs(_WORKFLOW_LOG, level="WARNING") as logged:
            self.ticked(StandInHandler(), limit=limit, scheduled=scheduled)
            return _said(logged.output, f"issue=#{WAITING_CHILD} pinned comment")

    def _seeded_late_family(self) -> None:
        """The blocked parent with its children on a late split's register, the waiting one's record refused."""
        self.seeded_family()
        register = PinnedState(data={"children": [DONE_CHILD, WAITING_CHILD]})
        register.set("dep_graph", {"1": [0]})
        generation = _late_models.LateGeneration(
            cycle_id=1,
            generation=1,
            root_issue=FAMILY_PARENT,
            current_issue=FAMILY_PARENT,
            lineage_depth=0,
            phase=_late_phases.LatePhase.CLEANING_UP,
            split_children=(DONE_CHILD, WAITING_CHILD),
        )
        _late_state.write_late_generation(register, generation)
        self.github.seed_state(FAMILY_PARENT, **register.data)
        self.github.seed_state(
            WAITING_CHILD, raw=True, schema_version=_ANOTHER_VERSION, parent_number=FAMILY_PARENT,
        )
        self.assertEqual(self.github.workflow_label(self.github.get_issue(WAITING_CHILD)), LABEL_BLOCKED)


class _EditedAfterReadings:
    """The client's pinned read, with a human's edit landing once `readings` readings are taken -- the gate's first."""

    def __init__(self, github: FakeGitHubClient, readings: int) -> None:
        self._github = github
        self._reads = github.read_pinned_state
        self._before_the_edit = readings

    def __call__(self, issue):
        """Read the record, and edit it into another version behind the last reading before the edit."""
        reading = self._reads(issue)
        self._before_the_edit -= 1
        if not self._before_the_edit:
            edited = dict(self._github.pinned_data(_ISSUE), schema_version=_ANOTHER_VERSION)
            self._github.seed_state(_ISSUE, raw=True, **edited)
        return reading


def _written(github: FakeGitHubClient) -> tuple:
    """The comments, relabels, and pinned writes the client was asked for."""
    return github.posted_comments, github.label_history, github.write_state_calls


def _said(output: list[str], fragment: str) -> bool:
    """Whether a logged line carries `fragment`."""
    return any(fragment in line for line in output)


if __name__ == "__main__":
    unittest.main()
