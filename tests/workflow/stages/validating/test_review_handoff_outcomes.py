# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A handed change request is retired only in the write that records what its developer's run left.

Through whole ticks: a reviewer's change request handed over in the validating
tick its reviewer returned, its developer launched behind the relabel, and the
fixing tick behind that. The request stays on the pinned comment until the
record of what the run left goes down -- the park a timeout or a question
takes, or the report a round with no code in it delivers -- and is retired in
that very commit. So a commit GitHub took and whose response was lost leaves
the same record a confirmed one does, never a request retired with nothing to
answer it, and the fixing tick behind it answers that record as it would any
other: a question's park waits for its human, a timeout's is recovered as the
fixing stage recovers one, and a report is published once and hands the pull
request back for the one round it buys -- no developer launched, and no round
spent, that the confirmed commit would not have led to.

Every write that retires the request is decided on it, on the pull request
the issue points at, on the start of its developer's launch, and on the
feedback anchor as the tick read them. The start written away, a repoint, or
the anchor pointed elsewhere, right ahead of the commit recording the run's
report -- with no code in it, or ahead of a pushed fix -- refuses that record,
so nothing is retired, published, pushed, relabelled, or spent. And
the hand-back behind the relabel is one guarded commit too, so a verdict and a
field another road wrote while the label moved are kept as that road wrote
them, with nothing settled behind a hand-back that did not land.

What the handoff's own commits refuse is in `test_review_handoff_commits.py`.
"""
from __future__ import annotations

import contextlib
import operator
import unittest
from functools import partial
from itertools import product
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from tests.workflow import fix_reports as world
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING, _agent
from tests.workflow.stages.validating import (
    review_verdict_test_support as _world,
    review_write_test_support as _roads,
)

ISSUE = 1_795

PR = 17_950

VERDICT = "review_returned_verdict"

RUNS = "agent_runs_used"

ROUND = "review_round"

FIXING = (ISSUE, LABEL_FIXING)

HANDED_BACK = (FIXING, (ISSUE, LABEL_VALIDATING))

# The runs a validating tick charges: its reviewer's and its developer's.
_CHARGED = 2

# How the developer a request owes ends a run that parks -- timed out, or
# asking a question -- and what that leaves on the pinned comment -- the
# park's reason and whether it waits on a human, the request, and the round --
# what the fixing tick behind it does -- the agents it runs, every relabel,
# and the reports it publishes -- and the runs charged past the validating
# tick's own. A question's park waits for its human; a timeout's is the one
# the fixing stage recovers on its own, handing the pull request back.
_PARKING = (
    (
        "a timeout",
        _agent(session_id=world.DEV_SESSION, timed_out=True),
        (("agent_timeout", True, None, 0), (0, HANDED_BACK, 0), 0),
    ),
    (
        "a question",
        _agent(session_id=world.DEV_SESSION, last_message=world.QUESTION_REPLY),
        ((None, True, None, 0), (0, (FIXING,), 0), 0),
    ),
)


# How the developer a request owes answers with a report: alone, or beside the
# commit it pushes.
_REPORTED = (("a report alone", False), ("a pushed fix", True))

# Another road's write right ahead of the commit recording that report: the
# developer's start written away, the issue pointed at another pull request,
# or the feedback anchor pointed at a comment of its own, which a failed run's
# continue would replay.
_AHEAD_OF_THE_REPORT = (
    ("its start written away", _roads.Writes({"agent_run_owed_started": ...})),
    ("a repoint", _roads.Writes({"pr_number": PR + 1})),
    ("the anchor repointed", _roads.Writes({"pending_fix_reviewer_comment_id": 4_242})),
)

# How the developer a request owes ends a run that leaves a report owed, and
# what that run is: committed work and no report, a round that did not finish
# over committed work, or a report over a head nothing could prove. Each parks
# the debt (`report_delivery.parks_the_debt`).
_OWING = (
    ("no report over committed work", "done -- see the diff", MappingProxyType({})),
    (
        "an unfinished round",
        _agent(session_id=world.DEV_SESSION, last_message="died", exit_code=1),
        MappingProxyType({}),
    ),
    (
        "an unproved head",
        world.reported(),
        MappingProxyType({"committed": False, **dict(world.UNPROVED_HEADS)["the remote has moved on"]}),
    ),
)

# The debt park confirmed, or taken with its response lost.
_CONFIRMED_OR_LOST = (
    (False, partial(_roads.leaves, bool)),
    (True, partial(_roads.leaves, _roads.loses_the_responses)),
)

# Another road writing the developer's start away right ahead of the debt park.
_UNSTARTS = partial(_roads.leaves, _roads.Writes({"agent_run_owed_started": ...}))

_UNDELIVERABLE = "report_undeliverable"

# Another road's verdict, and a field of its own, written while the label moves.
_ANOTHER_VERDICT = MappingProxyType({"round": 5, "verdict": "changes_requested"})

_NOTES = "operator_notes"

_KEPT = "keep this"


def _records_the_report(staged) -> bool:
    """Whether a guarded commit's staged record carries the run's report: the commit recording it."""
    return "developer_report_delivery" in staged


def _parks_the_debt(staged) -> bool:
    """Whether a guarded commit's staged record parks a report owed: the park a run that left one takes."""
    return staged.get("park_reason") == _UNDELIVERABLE


def _retires_the_request(staged) -> bool:
    """Whether a guarded commit's staged record writes the request off: the first that records the run's result."""
    return staged.get(VERDICT, ...) is None


class LostResultTest(unittest.TestCase, world._FixReportMixin):
    """The commit recording a run's result, the request retired in it, is taken and its response lost."""

    def test_a_lost_park_settles_as_a_landed_one(self) -> None:
        # The commit landing the park a timeout or a question takes, with the
        # request retired beside it, loses its response. The comment carries
        # that park exactly as a commit GitHub confirmed leaves it, and the
        # fixing tick behind it does what it does there -- launching nobody,
        # and charging nothing.
        for name, answer, settled in _PARKING:
            with self.subTest(name):
                self.assertEqual(
                    (self._settles(answer, lost=True), self._settles(answer, lost=False)),
                    ((*settled, True), (*settled, False)),
                )

    def test_a_lost_report_is_handed_back_once(self) -> None:
        # The commit recording a report the developer answered with, and no
        # code, with the request retired beside it, loses its response. The
        # fixing tick behind it launches nobody, publishes that report once,
        # and hands the pull request back for the one round it buys -- where a
        # confirmed commit's own tick leaves it.
        lost = self._settles(world.reported(), lost=True)

        self.assertEqual(
            (lost, self.github.pinned_data(ISSUE)[ROUND]),
            (((None, False, None, 0), (0, HANDED_BACK, 1), 0, True), 1),
        )

    def _settles(self, answer, *, lost: bool) -> tuple:
        """The validating tick whose developer answers `answer` and the fixing tick behind it; what they leave.

        Where `lost`, the commit recording the run's result loses its
        response. What the first tick left, what the fixing tick did, and the
        runs charged, as `_PARKING` spells them, and whether a response was
        lost at all.
        """
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.left_behind = None
        losing = _roads.AnotherRoadAhead(
            self, _retires_the_request, partial(_roads.leaves, _roads.loses_the_responses),
        )
        with losing.patched() if lost else contextlib.nullcontext():
            self.requested_fix(answer, committed=False)
        self.github.pinned_failures.lost.discard(ISSUE)
        recorded = self.github.pinned_data(ISSUE)
        agents = MagicMock()
        self._ticked(self._run_fixing, agents, committed=False)
        return (
            (
                recorded.get("park_reason"),
                bool(recorded.get("awaiting_human")),
                recorded.get(VERDICT),
                recorded[ROUND],
            ),
            (agents.call_count, tuple(self.github.label_history), len(self.published_reports())),
            self.github.pinned_data(ISSUE)[RUNS] - _CHARGED,
            self.left_behind is not None,
        )


class GuardedAnswerTest(unittest.TestCase, world._FixReportMixin):
    """The writes retiring a request behind its developer's report hold the request, and keep another road's."""

    def test_a_write_ahead_of_the_report_refuses_it(self) -> None:
        # Another road writes the developer's start away, points the issue at
        # another pull request, or points the feedback anchor elsewhere, right
        # ahead of the commit recording its report: the record is refused, so
        # the request is not retired and nothing is published, pushed, or
        # spent -- the pull request still stands where it stood, and the label
        # is not moved back.
        for (name, committed), (moved, road) in product(_REPORTED, _AHEAD_OF_THE_REPORT):
            with self.subTest(name, moved=moved):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)

                with _roads.AnotherRoadAhead(self, _records_the_report, road).patched():
                    self.requested_fix(world.reported(), committed=committed)

                pinned = self.github.pinned_data(ISSUE)
                self.assertEqual(
                    (
                        pinned[VERDICT]["verdict"],
                        len(self.published_reports()),
                        pinned[ROUND],
                        self.pull_request.head.sha,
                        tuple(self.github.label_history),
                    ),
                    ("changes_requested", 0, 0, world.PUBLISHED_HEAD, (FIXING,)),
                )

    def test_a_hand_back_keeps_another_roads_write(self) -> None:
        # Another road writes a verdict of its own, and a field of its own,
        # while the label moves back to validating behind the developer's
        # report: the hand-back is refused rather than written over them, both
        # stand exactly as that road wrote them, and the report is settled
        # nowhere this tick.
        for name, committed in _REPORTED:
            with self.subTest(name):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                writes = _roads.Writes({VERDICT: dict(_ANOTHER_VERDICT), _NOTES: _KEPT})
                relabel = _world.AnotherRoadBehind(
                    self, "set_workflow_label", partial(operator.eq, LABEL_VALIDATING), writes,
                )

                with patch.object(self.github, "set_workflow_label", relabel):
                    self.requested_fix(world.reported(), committed=committed)

                pinned = self.github.pinned_data(ISSUE)
                self.assertEqual(
                    (pinned[VERDICT], pinned.get(_NOTES), len(self.published_reports())),
                    (dict(_ANOTHER_VERDICT), _KEPT, 0),
                )


class DebtParkTest(unittest.TestCase, world._FixReportMixin):
    """The park a run leaving a report owed takes retires the request in its own commit, or neither lands."""

    def test_a_debt_park_retires_the_request(self) -> None:
        # The developer a request owes leaves a report owed, and the round
        # parks the debt. Confirmed, or taken with its response lost, that one
        # commit leaves the park and the request retired together -- never a
        # park beside a request still handed -- and the fixing tick behind it
        # launches nobody over either.
        for owing, (lost, road) in product(_OWING, _CONFIRMED_OR_LOST):
            with self.subTest(owing[0], lost=lost):
                parked = self._parks(*owing[1:], road)
                agents = MagicMock()
                self._ticked(self._run_fixing, agents, committed=False)
                self.assertEqual(
                    (parked, agents.call_count),
                    (((_UNDELIVERABLE, True, None), False, (FIXING,), 0), 0),
                )

    def test_a_refused_debt_park_writes_nothing(self) -> None:
        # Another road writes the developer's start away right ahead of the
        # park's commit: the park is refused, so neither it nor the request's
        # retirement lands, the comment stays exactly as that road left it,
        # and nothing is published or relabelled.
        for name, answer, options in _OWING:
            with self.subTest(name):
                self.assertEqual(
                    self._parks(answer, options, _UNSTARTS),
                    ((None, False, "changes_requested"), True, (FIXING,), 0),
                )

    def _parks(self, answer, options, road) -> tuple:
        """The validating tick whose developer answers `answer` under `options`, `road` ahead of its debt park.

        What the comment carries after it -- the park's reason, whether it
        waits on a human, and the verdict waiting -- whether it is exactly as
        `road` left it, every relabel, and the reports published.
        """
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.left_behind = None
        with _roads.AnotherRoadAhead(self, _parks_the_debt, road).patched():
            self.requested_fix(answer, **options)
        self.github.pinned_failures.lost.discard(ISSUE)
        pinned = self.github.pinned_data(ISSUE)
        return (
            (
                pinned.get("park_reason"),
                bool(pinned.get("awaiting_human")),
                (pinned.get(VERDICT) or {}).get("verdict"),
            ),
            pinned == self.left_behind,
            tuple(self.github.label_history),
            len(self.published_reports()),
        )


if __name__ == "__main__":
    unittest.main()
