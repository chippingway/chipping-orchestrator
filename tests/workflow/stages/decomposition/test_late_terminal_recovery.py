# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The terminal an umbrella earned, finished by whichever pass gets there.

`done` takes the issue off both labels the closed-owner sweep queries, so it
is the one write in this mode that nothing could ever come back to. What makes
it safe is the write AHEAD of it: one pinned write that stamps the resolution
and retires the cycle together, and past which there is no live cycle under
the terminal for anything to have to find.

Everything before that write is ordinary: the owner is on `umbrella` with a
live cycle, which the sweep and the umbrella poll both already own. Everything
after it is a label and a close, asked of a record that already says the
terminal is due -- so a pass that dies in between leaves an owner this sweep
keeps yielding until one of them lands.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import dispatch_closure as _dispatch_closure
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import _TEST_SPEC, _PatchedWorkflowMixin
from tests.workflow.observation_support import (
    ObservedCloseCase,
    receipt_for,
)
from tests.workflow.stages.decomposition.late_cancel_support import (
    settled_umbrella,
)
from tests.workflow.stages.decomposition.late_cleanup_support import (
    PARENT_NUMBER,
    SUPERSEDED_BRANCH,
    resource_states,
    walk_owner,
)
from tests.workflow.stages.decomposition.late_observation_seams import (
    CHILD_RELABEL as LABEL_WRITE,
    ISSUE_COMMENT,
    latches_on_call,
    latches_on_retirement,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CYCLE_ID,
    KEYS,
)

_WORKFLOW_LOG = "orchestrator.workflow"

_TEST_SLUG = _TEST_SPEC.slug

_SET_LABEL = "set_workflow_label"

_RECONCILED = "reconciled"

_RESOLVED_AT = "umbrella_resolved_at"

_RETIRED = "late_retired_cycle_id"

_CYCLE_ID = "late_cycle_id"

_PINNED_WRITE = "write_pinned_state"

# What a process that does not come back from the terminal looks like here.
_DIED = RuntimeError("the process holding this issue is gone")


class _TerminalCase(ObservedCloseCase, _PatchedWorkflowMixin):
    """One settled umbrella, walked into the terminal it earned."""

    def setUp(self) -> None:
        self._fresh_process()
        self.seeded = settled_umbrella()

    def _record(self) -> dict:
        return self.seeded.github.pinned_data(PARENT_NUMBER)

    def _label(self):
        return self.seeded.github.workflow_label(self.seeded.parent)

    def _died_before_the_label(self) -> None:
        """Resolve the umbrella, ending the process before its label write."""
        with patch.object(
            self.seeded.github, _SET_LABEL, side_effect=_DIED,
        ), self.assertRaises(RuntimeError):
            walk_owner(self, self.seeded)
        self.seeded.parent.closed = True


class RetiredBeforeTheTerminalTest(_TerminalCase, unittest.TestCase):
    """The write that makes the terminal durable retires the cycle with it.

    Which is what leaves nothing under `done` to be found: a close arriving
    after it is a human closing an issue this orchestrator had already
    finished, not a cancellation of a cycle still running.
    """

    def test_the_record_keeps_no_cycle(self) -> None:
        walk_owner(self, self.seeded)

        record = self._record()
        self.assertIsNone(record.get(_CYCLE_ID))
        self.assertIsNotNone(record[_RESOLVED_AT])
        self.assertEqual(self._label(), WorkflowLabel.DONE)

    def test_the_ledger_it_recorded_stands(self) -> None:
        # An obligation does not stop being owed because the identity written
        # beside it was cleared, so the two ledgers travel across the write.
        walk_owner(self, self.seeded)

        self.assertEqual(
            resource_states(self.seeded.github),
            {SUPERSEDED_BRANCH: _RECONCILED},
        )

    def test_a_close_at_the_label_leaves_it_finished(self) -> None:
        # Past the record there is no live cycle, so the reading has nothing
        # to end -- and nothing is stranded by it either.
        with latches_on_call(
            self.seeded.github, _TEST_SLUG, PARENT_NUMBER, LABEL_WRITE,
        ):
            walk_owner(self, self.seeded)

        self.assertEqual(self._label(), WorkflowLabel.DONE)
        self.assertIsNone(self._record().get(_CYCLE_ID))


class ClosedInsideTheRetirementTest(_TerminalCase, unittest.TestCase):
    """The write that retires the cycle is a request, and the poll runs beside it.

    A close observed inside it leaves a durable receipt on the thread while
    the record has just stopped naming the cycle that receipt is scoped to.
    So the latch is asked once more BEHIND the write, and the answer there is
    a reinstatement rather than a refusal: the generation is still in the
    call's own memory, and it goes back cancelled.
    """

    def test_the_cycle_is_put_back_and_cancelled(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._closed_inside_the_retirement()

        record = self._record()
        self.assertTrue(record[KEYS.cancelled])
        self.assertEqual(record[_CYCLE_ID], CYCLE_ID)

    def test_no_terminal_is_written(self) -> None:
        # The owner keeps `umbrella`, which is the label the closed-owner
        # sweep asks for -- so the ending is reached from where it stands.
        with self.assertLogs(_WORKFLOW_LOG):
            self._closed_inside_the_retirement()

        self.assertEqual(self.seeded.github.label_history, [])
        self.assertFalse(self.seeded.parent.closed)

    def test_the_ending_retires_it(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._closed_inside_the_retirement()
        self.seeded.parent.closed = True

        self.seeded.swept(self)

        self.assertEqual(self._label(), WorkflowLabel.REJECTED)

    def test_a_close_at_the_window_exit_is_caught(self) -> None:
        # The interval a barrier taken before the exit would step over: the
        # write has landed, the cycle is still advertised, and a poll can
        # still latch a close and receipt it against that cycle.
        with self.assertLogs(_WORKFLOW_LOG):
            self._closed_inside_the_retirement(after=True)

        record = self._record()
        self.assertTrue(record[KEYS.cancelled])
        self.assertEqual(record[_CYCLE_ID], CYCLE_ID)
        self.assertEqual(self.seeded.github.label_history, [])

    def test_a_racing_poll_keeps_the_reading(self) -> None:
        # The window that makes the barrier answerable at all: a poll reading
        # the record between the write and the barrier is told nothing about
        # a cycle, and without the window it would call the reading spent.
        with self.assertLogs(_WORKFLOW_LOG):
            self._closed_inside_the_retirement(polling=True)

        self.assertTrue(self._record()[KEYS.cancelled])

    def _closed_inside_the_retirement(
        self, *, polling: bool = False, after: bool = False,
    ) -> None:
        """Walk this umbrella, closing it inside the write that retires."""
        github = self.seeded.github
        held = (
            _PollsAfterTheRetirement(github).answering()
            if polling
            else latches_on_retirement(
                github, _TEST_SLUG, PARENT_NUMBER, after=after,
            )
        )
        with held:
            walk_owner(self, self.seeded)


class DiedInsideTheRetirementTest(_TerminalCase, unittest.TestCase):
    """The barrier behind the retirement write is THIS process's.

    A process that does not reach it leaves only what is on the remote: a
    record naming the cycle it dropped, and a receipt on the thread naming the
    same one. The two together are what the next process reads instead of the
    barrier -- without them the sweep would find a record with no cycle and
    write `done` over a close the thread says was observed.
    """

    def test_a_process_that_dies_leaves_it_adoptable(self) -> None:
        # The barrier is THIS process's, so a process that does not reach it
        # leaves only what is on the remote: a record naming the cycle it
        # dropped, and a receipt on the thread naming the same one.
        self._died_inside_the_retirement()

        record = self._record()
        self.assertIsNone(record.get(_CYCLE_ID))
        self.assertEqual(record[_RETIRED], CYCLE_ID)
        self.assertEqual(len(self._receipts()), 1)

    def test_the_next_process_ends_that_cycle(self) -> None:
        # The regression: nothing in memory survives, and the sweep would
        # otherwise read a record with no cycle and finish the terminal --
        # writing `done` over a close the thread says was observed.
        self._died_inside_the_retirement()
        self.seeded.parent.closed = True
        self._fresh_process()

        with self.assertLogs(_WORKFLOW_LOG):
            self.seeded.swept(self)

        self.assertTrue(self._record()[KEYS.cancelled])
        self.assertEqual(self._label(), WorkflowLabel.REJECTED)

    def _died_inside_the_retirement(self) -> None:
        """Retire the cycle, poll behind the write, and end the process."""
        github = self.seeded.github
        with self.assertRaises(RuntimeError), _PollsAfterTheRetirement(github, dying=True).answering():
            walk_owner(self, self.seeded)

    def _receipts(self) -> list:
        """Every close receipt on this owner's thread for its own cycle."""
        marker = receipt_for(PARENT_NUMBER, CYCLE_ID)
        return [
            body for number, body in self.seeded.github.posted_comments
            if number == PARENT_NUMBER and marker in body
        ]


class DiedBeforeTheTerminalTest(_TerminalCase, unittest.TestCase):
    """The label never landed, and the owner is still where a sweep finds it.

    That is the whole of the recovery: the resolution is on the record and
    the label is the one the closed-owner sweep asks for, so the terminal is
    written by whichever pass gets there -- however long after, and however
    many times the write has to be retried.
    """

    def test_it_is_left_on_the_swept_label(self) -> None:
        self._died_before_the_label()

        self.assertEqual(self._label(), WorkflowLabel.UMBRELLA)
        self.assertIsNotNone(self._record()[_RESOLVED_AT])

    def test_a_later_sweep_finishes_it(self) -> None:
        # No relabel, no operator, and nothing this process remembers.
        self._died_before_the_label()
        self._fresh_process()

        with self.assertLogs(_WORKFLOW_LOG):
            self.seeded.swept(self)

        self.assertEqual(self._label(), WorkflowLabel.DONE)

    def test_a_refused_terminal_is_asked_again(self) -> None:
        # The retry, and what makes it possible: a write GitHub declines
        # leaves the owner on the label the sweep queries, so the pass after
        # it writes what this one could not.
        self._died_before_the_label()
        self._fresh_process()
        with patch.object(
            self.seeded.github, _SET_LABEL, side_effect=_DIED,
        ), self.assertLogs(_WORKFLOW_LOG):
            self.seeded.swept(self)
        self.assertEqual(self._label(), WorkflowLabel.UMBRELLA)

        with self.assertLogs(_WORKFLOW_LOG):
            self.seeded.swept(self)

        self.assertEqual(self._label(), WorkflowLabel.DONE)

    def test_an_owner_it_never_resolved_is_left_alone(self) -> None:
        # The bound that keeps the recovery narrow: every umbrella the
        # initial decomposer made carries no cycle and no stamp, and a closed
        # one is a hard human stop with nothing to finalize.
        seeded = settled_umbrella()
        seeded.parent.closed = True
        seeded.github.seed_state(PARENT_NUMBER, umbrella=True)

        seeded.swept(self)

        self.assertEqual(seeded.github.label_history, [])


class ClosedBeforeTheRecordTest(_TerminalCase, unittest.TestCase):
    """A close observed before the resolution is recorded ends the cycle.

    The latch is asked with no request standing between the answer and the
    write, so the owner keeps `umbrella` with the mark down -- and the ending
    retires it to `rejected` from a label the sweep still queries.
    """

    def test_no_terminal_is_written(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._closed_inside_the_notice()

        self.assertEqual(self.seeded.github.label_history, [])
        self.assertTrue(self._record()[KEYS.cancelled])

    def test_the_ending_retires_it(self) -> None:
        with self.assertLogs(_WORKFLOW_LOG):
            self._closed_inside_the_notice()
        self.seeded.parent.closed = True

        self.seeded.swept(self)

        self.assertEqual(self._label(), WorkflowLabel.REJECTED)

    def _closed_inside_the_notice(self) -> None:
        """Walk this umbrella, closing it inside its own closing comment."""
        with latches_on_call(
            self.seeded.github, _TEST_SLUG, PARENT_NUMBER, ISSUE_COMMENT,
        ):
            walk_owner(self, self.seeded)


class _PollsAfterTheRetirement:
    """Run the dispatcher's whole deferral behind that same write.

    The other half of the race: the poll does not merely latch, it asks the
    record what the reading is worth and settles it where the answer is that
    there is nothing to end. What it reads there is a record with no cycle.

    `dying` ends the walk where the write left it, which is the other half of
    the same window: the barrier behind that write is this process's, and a
    process that does not reach it leaves only what is on the remote.
    """

    def __init__(self, github, *, dying: bool = False) -> None:
        self._github = github
        self._writing = github.write_pinned_state
        self._polled = False
        self._dying = dying

    def __call__(self, issue, state):
        """Answer this write, and poll behind the one that retires."""
        answered = self._writing(issue, state)
        if self._polled or state.data.get(_CYCLE_ID) is not None:
            return answered
        self._polled = True
        _dispatch_closure._kept_closed_reading(
            self._github, _TEST_SPEC, PARENT_NUMBER,
        )
        if self._dying:
            raise _DIED
        return answered

    def answering(self):
        """Put this in front of every pinned write the walk makes."""
        return patch.object(
            self._github, _PINNED_WRITE, side_effect=self,
        )


if __name__ == "__main__":
    unittest.main()
