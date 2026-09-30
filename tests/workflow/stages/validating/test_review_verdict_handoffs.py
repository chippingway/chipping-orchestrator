# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A disposed change request reaches exactly one developer, behind feedback that is posted and anchored.

Through `review_disposition`: a request ready in the tick its reviewer
returned is handed over there, and one held on its evidence is handed over
from the record by the later tick that finishes it, with no reviewer again. A
feedback post that failed or left no id hands nothing on, and the next tick
posts it again. A request a tick already handed -- its relabel refused, or its
developer's start -- is replayed from where that handoff stopped: its
feedback never posted twice, and its developer launched once and charged once.

The handoff's own races -- the subject, the evidence, the run ledger, and the
anchor moving behind each of its requests -- are covered beside
`review_handoffs`; this is what the disposition composes of it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    review_handoff_test_support as _handoff,
    review_verdict_test_support as _world,
)

PR_COMMENT = "pr_comment"

SET_LABEL = "set_workflow_label"

# The issue's folded token total, which holds the reviewer's usage once.
TOKENS = "issue_total_tokens"

HANDED_BACK = ((_world.ISSUE, LABEL_FIXING), (_world.ISSUE, LABEL_VALIDATING))

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# A reviewer asking for that change beside its declared run, which failed.
REQUESTING = _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED")


def _refuses_the_relabel(case) -> None:
    """The tick handing `case`'s request over, dying on the relabel GitHub refuses ahead of its developer."""
    refused = patch.object(case.github, SET_LABEL, side_effect=RuntimeError("refused"))
    with refused, case.assertRaises(RuntimeError):
        case.returns(UNDECLARED_REQUEST, **_disposed.fixing())


def _refuses_the_start(case) -> None:
    """The tick handing `case`'s request over, whose developer's charge lands and whose start GitHub refuses."""
    with patch.object(case.github, "write_pinned_state", _handoff.RefusesTheStart(case.github.write_pinned_state)):
        case.returns(UNDECLARED_REQUEST, **_disposed.fixing())


class DisposedRequestTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A change request reaches its one developer, from the tick it returned in or a later one."""

    def test_a_request_reaches_one_developer(self) -> None:
        # Handed over in the tick its reviewer returned, or -- its evidence's
        # publication held -- by the next tick, over the verdict the first
        # wrote: either way one developer, resumed on the reviewer's words,
        # one feedback post, and the reviewer's usage folded once.
        for held in (False, True):
            with self.subTest(held=held):
                self.setUp()
                if held:
                    self.github.report_failures.lost.add(_world.PR)
                first = self.returns(REQUESTING, **_disposed.fixing())
                self.github.report_failures.lost.discard(_world.PR)
                posted = len(self.feedback_posts())

                later = self.finishes(**_disposed.fixing())

                ran = later[_world.RUN_AGENT] if held else first[_world.RUN_AGENT]
                self.assertEqual(
                    (
                        posted,
                        first[_world.RUN_AGENT].call_count + later[_world.RUN_AGENT].call_count,
                        ran.call_args.kwargs.get("resume_session_id"),
                        _world.REQUESTED in ran.call_args.args[1],
                        len(self.feedback_posts()),
                        tuple(self.github.label_history),
                        self.pinned()[TOKENS],
                        self.waiting(),
                    ),
                    (int(not held), 1, _world.DEV_SESSION, True, 1, HANDED_BACK, _world.REVIEWER_TOKENS, None),
                )

    def test_a_post_it_cannot_anchor_holds_it(self) -> None:
        # Refused outright, or taken with an answer naming no comment: nothing
        # is handed, relabelled, or launched without the anchor. The next tick
        # posts again and reaches one developer -- twice over on the pull
        # request where the first post landed, since a feedback post carries
        # no receipt to find it by.
        for name, lands, posts in (("refused", False, 1), ("landed with no id", True, 2)):
            with self.subTest(name):
                self.setUp()
                left = self._held_on_the_post(lands=lands)

                fixed = self.finishes(**_disposed.fixing())

                self.assertEqual(
                    (
                        left,
                        fixed[_world.RUN_AGENT].call_count,
                        len(self.feedback_posts()),
                        tuple(self.github.label_history),
                        self.waiting(),
                    ),
                    ((0, None, ()), 1, posts, HANDED_BACK, None),
                )

    def _held_on_the_post(self, *, lands: bool) -> tuple:
        """The tick whose feedback post GitHub refuses, or takes naming no comment where it `lands`.

        What it left: the developers it launched, the run count the request
        was handed at, and every relabel.
        """
        refuses = _handoff.RefusesOnce(self.github.pr_comment, _handoff.FEEDBACK_NOTICE, lands=lands)
        with patch.object(self.github, PR_COMMENT, refuses):
            held = self.returns(UNDECLARED_REQUEST, **_disposed.fixing())
        handed = self.pinned()[_world.RETURNED_VERDICT][_disposed.HANDED]
        return (held[_world.RUN_AGENT].call_count, handed, tuple(self.github.label_history))


class HandedReplayTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A handed request is finished from where its handoff stopped, launching and charging one developer."""

    def test_a_handed_request_is_replayed(self) -> None:
        # The handoff is written, its feedback posted and anchored, and the
        # tick stops short of the developer: on the relabel, or on the start
        # of the run it charged. The next tick posts nothing again, and
        # launches the one developer the request owes -- the charge that
        # never started honored rather than a second one taken.
        for name, stops in (("on the relabel", _refuses_the_relabel), ("on the start", _refuses_the_start)):
            with self.subTest(name):
                self.setUp()
                stops(self)
                handed = self.pinned()[_world.RETURNED_VERDICT][_disposed.HANDED]
                anchored = self.pinned()[_disposed.ANCHOR]

                ran = self.finishes(**_disposed.fixing())

                self.assertEqual(
                    (
                        anchored in {said.id for said in self.pull_request.issue_comments},
                        ran[_world.RUN_AGENT].call_count,
                        len(self.feedback_posts()),
                        self.pinned()[_world.AGENT_RUNS_USED] - handed,
                        self.waiting(),
                    ),
                    (True, 1, 1, 1, None),
                )


if __name__ == "__main__":
    unittest.main()
