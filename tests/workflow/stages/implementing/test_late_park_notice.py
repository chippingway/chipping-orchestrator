# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a park nobody could measure says, and when it says it a second time.

The typed member is written for the code that branches on it, and on a thread
it is one word: `base_absent` and `diff_unpinnable` name two completely
different next moves -- a transport to wait out on one side, a checkout to
clean before any reading of it is worth taking on the other -- and a notice
that named only the member would leave a human to work out which they are
looking at. What these pin down is that it says so, and that what the step
wrote for itself travels the whole way with it -- onto the thread, and onto
both streams, where the run of readings a standing park holds silently is the
only account there is of a pair nobody can measure.

The other half is how often it is said. A park is re-read for as long as it
stands, and every one of those readings owes the thread nothing unless it has
something new to say: a retry stopping where the notice already said it stops
is a repeat nobody can answer any faster, and one stopping somewhere else is a
different next move that would otherwise never be mentioned at all.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.implementing import (
    late_park_notices as _late_park_notices,
    late_parks as _parks,
    late_records as _records,
    state as _implementing_state,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_IMPLEMENTING
from tests.workflow.stages.implementing import late_gate_test_support as support

# What the notice for a remote that would not name the base has to cover. It
# is the longest-lived of these, because it is the one step a human hears
# about only once the quiet retries behind it are spent: the sentence has to
# say what could have caused it, what has already been tried, what goes on
# happening without them, and where the invocation itself is written down.
_UNREACHABLE_BASE_TERMS = (
    "ls-remote",
    "throttling",
    "token",
    "Three retries",
    "every tick",
    "orchestrator.git_plumbing",
)

# What a transport that failed hands up for a human to read, already scrubbed
# of the credential by the layer that ran it.
_SAID = "fatal: could not read Username for 'https://github.com'"

# A step this table does not cover, for the notice that still has to be one.
_UNCOVERED_STEP = "a_step_from_a_later_vocabulary"

# How many readings one pair may lose to the transport before a human is told,
# read off the owner so a case names the bound rather than a number beside it.
_MISS_BOUND = _implementing_state._MEASUREMENT_MISSES_BEFORE_PARK

# The sentence only the road BEFORE publication writes: nothing here has ever
# been pushed, so what the park says was withheld is the publication itself.
_UNPUBLISHED = "it has not been published"

# A checkout none of this reads. The park is about the record and the thread,
# and the pair it is taken over was frozen ticks ago.
_WORKTREE = Path("/tmp")


class MeasurementNoticeTest(unittest.TestCase):
    """The line one refused reading is described to an operator by."""

    def test_every_step_says_something_of_its_own(self) -> None:
        # Distinct as well as present: a member described in another's words
        # sends somebody to the wrong thing, which is worse than the bare
        # term it replaced.
        described = {
            failure: _late_park_notices._described(failure, "")
            for failure in MeasurementFailure
        }

        self.assertTrue(all(described.values()))
        self.assertEqual(len(set(described.values())), len(MeasurementFailure))

    def test_an_unreachable_base_names_what_to_check(self) -> None:
        described = _late_park_notices._described(MeasurementFailure.BASE_UNREADABLE, "")

        for term in _UNREACHABLE_BASE_TERMS:
            with self.subTest(term=term):
                self.assertIn(term, described)

    def test_what_the_step_said_travels_with_it(self) -> None:
        # The reading is taken deep in the git layer and reported far from it,
        # so by the time this is read the process that saw that line is gone.
        # It is carried beside the explanation where there is one and stands
        # alone where the vocabulary has outgrown the table.
        described = _late_park_notices._described(MeasurementFailure.BASE_ABSENT, _SAID)

        self.assertIn(_SAID, described)
        self.assertIn("fetch", described)
        self.assertEqual(
            _late_park_notices._described(_UNCOVERED_STEP, _SAID).strip(),
            _late_park_notices._REPORTED_DETAIL.format(detail=_SAID),
        )


class StandingParkTest(unittest.TestCase):
    """A park before publication, re-read on a pair whose bound is spent.

    Driven at the owner rather than through a whole tick because the poll that
    re-enters a standing park is the reading the dispatcher takes ahead of
    every handler, and that one only re-enters a record entered PAST
    publication. Before publication the guard is the same and the sentence is
    not, and the sentence is what a human on this road is handed.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(
            support.GATE_ISSUE_NUMBER, label=LABEL_IMPLEMENTING,
        )
        self.github.add_issue(self.issue)
        self.github.seed_state(support.GATE_ISSUE_NUMBER, **{
            support.AWAITING_HUMAN: True,
            support.PARK_REASON: support.PARK_MEASUREMENT_FAILED,
            **support.recorded_generation(
                measurement_miss_count=_MISS_BOUND + 1,
                measurement_failure=MeasurementFailure.BASE_ABSENT,
            ),
        })

    def test_a_named_step_is_not_named_again(self) -> None:
        # Reported to both sinks all the same: those polls exist nowhere else,
        # and a pair nobody can measure reported by none of them looks exactly
        # like one nobody is looking at. What is spared is the thread.
        self._lost(MeasurementFailure.BASE_ABSENT, detail=_SAID)

        self.assertEqual(self.github.posted_comments, [])
        held = self._failures()
        self.assertEqual(len(held), 1)
        # And the record says as much as the notice would have: the thread is
        # what a repeat spares, so a stream that reported only
        # `measurement_failed` would leave the whole silent run unreadable.
        self.assertEqual(held[0]["failure"], "measurement_failed")
        self.assertEqual(
            held[0]["measurement_failure"], MeasurementFailure.BASE_ABSENT,
        )
        self.assertEqual(held[0]["detail"], _SAID)
        pinned = self._pinned()
        self.assertEqual(pinned[support.KEY_MISS_COUNT], _MISS_BOUND + 1)
        self.assertEqual(
            pinned[support.KEY_MEASUREMENT_FAILURE],
            MeasurementFailure.BASE_ABSENT,
        )

    def test_a_different_step_is_named_once(self) -> None:
        # A remote that stops naming the base at all is not the failure this
        # human was sent, and nothing else would ever tell them: the sentence
        # goes out once, in the wording this road owes -- and the record moves
        # to it in the write the notice rides out on, so the retry after it is
        # a repeat rather than a second announcement.
        said = support._RecordAtHandoff(self.github, support.POST_COMMENT)

        with said.held():
            self._lost(MeasurementFailure.BASE_UNREADABLE, detail=_SAID)
        self._lost(MeasurementFailure.BASE_UNREADABLE)

        self.assertEqual(len(self.github.posted_comments), 1)
        notice = self.github.posted_comments[0][1]
        self.assertIn(_UNPUBLISHED, notice)
        self.assertIn(MeasurementFailure.BASE_UNREADABLE, notice)
        self.assertIn(_SAID, notice)
        self.assertEqual(
            said.pinned[support.KEY_MEASUREMENT_FAILURE],
            MeasurementFailure.BASE_UNREADABLE,
        )
        self.assertEqual(
            self._pinned()[support.KEY_MISS_COUNT], _MISS_BOUND + 1,
        )
        # Both readings are on the stream, and both name the step that broke
        # the silence rather than only the one a human was told about. The
        # line travels with the reading that had one, so a retry the
        # transport said nothing about carries none.
        self.assertEqual(
            [
                (record["measurement_failure"], record.get("detail"))
                for record in self._failures()
            ],
            [
                (MeasurementFailure.BASE_UNREADABLE, _SAID),
                (MeasurementFailure.BASE_UNREADABLE, None),
            ],
        )

    def _lost(self, failure, detail: str = "") -> None:
        """One more reading of the parked pair, lost to the transport."""
        state = self.github.read_pinned_state(self.issue)
        gate = _records._gate(
            self.github, _TEST_SPEC, self.issue, state, _WORKTREE,
        )
        _parks._lost_reading(
            gate, _late_state.read_late_generation(state), failure, detail,
        )
        # The write every tick ends with, which is what makes a park a human
        # can read out of the flags the notice above only set in memory.
        self.github.write_pinned_state(self.issue, state)

    def _pinned(self) -> dict:
        return self.github.pinned_data(support.GATE_ISSUE_NUMBER)

    def _failures(self) -> list:
        return [
            record for record in self.github.recorded_events
            if record.get("event") == support.EVENT_LATE_FAILURE
        ]


if __name__ == "__main__":
    unittest.main()
