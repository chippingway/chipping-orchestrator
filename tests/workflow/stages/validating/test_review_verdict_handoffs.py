# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A disposed change request reaches exactly one developer, behind feedback that is posted and anchored.

Through `review_disposition`: a request ready in the tick its reviewer
returned is handed over there, and one held on its evidence is handed over
from the record by the later tick that finishes it, with no reviewer again. A
feedback post that failed or left no id hands nothing on, and the next tick
posts it again -- or finds the one that landed by its words, whatever its
findings quote. A request a tick already handed -- its relabel refused, or its
developer's start -- is replayed from where that handoff stopped: its
feedback never posted twice, and its developer launched once and charged once. A request persisted before findings
were formatted, its verification declaration raw beside whatever claim it
earned, is posted and handed on concise by the tick finishing it, from its
record as persisted.

The handoff's own races -- the subject, the evidence, the run ledger, and the
anchor moving behind each of its requests -- are covered beside
`review_handoffs`; this is what the disposition composes of it.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.pinned_state import PINNED_STATE_MARKER
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    raw_feedback_test_support as _raw,
    resumed_verdict_test_support as _resumed,
    review_handoff_test_support as _handoff,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    review_write_test_support as _roads,
)

PR_COMMENT = "pr_comment"

SET_LABEL = "set_workflow_label"

# The issue's folded token total, which holds the reviewer's usage once.
TOKENS = "issue_total_tokens"

HANDED_BACK = ((_world.ISSUE, LABEL_FIXING), (_world.ISSUE, LABEL_VALIDATING))

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# A reviewer requesting a change whose findings quote the pinned state's
# marker, which the readers of unread pull-request feedback leave out.
QUOTING_REQUEST = (
    f"{_world.REQUESTED}\n2. Never read a body quoting `{PINNED_STATE_MARKER}` as the state."
    "\n\nVERDICT: CHANGES_REQUESTED"
)

# A reviewer asking for that change beside its declared run, which failed.
REQUESTING = _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED")

# The member of a handed verdict's record naming the post it was handed over with.
HANDED_WITH = "anchor"

# A park as a human's reply leaves it: cleared.
_ANSWERED = MappingProxyType({"awaiting_human": False, "park_reason": None})

# How a tick's feedback post leaves nothing to anchor on, and the request it
# was posted for: refused outright, taken with an answer naming no comment, or
# taken with its response lost over findings quoting the pinned state's marker.
_UNANCHORED = (
    ("refused", MappingProxyType({"lands": False}), UNDECLARED_REQUEST),
    ("landed with no id", MappingProxyType({"lands": True}), UNDECLARED_REQUEST),
    (
        "lost, quoting the state marker",
        MappingProxyType({"lands": True, "answers": RuntimeError("response lost")}),
        QUOTING_REQUEST,
    ),
)

# Each request a tick persisted before findings were formatted: the reply its
# reviewer returned, where that tick stopped, and the findings the tick
# finishing it posts and hands its developer. A fresh run's evidence still
# owed; a reuse, and a run declared and nothing else, whose feedback post was
# refused -- the last handed on as no findings rather than as the declaration
# it was persisted as.
_HISTORICAL = (
    ("a fresh run, its evidence owed", lambda _case: _world.PASSED_REQUEST, _raw.owes_its_evidence, _world.REQUESTED),
    (
        "a reuse, its post refused",
        lambda case: _world.REQUEST_REUSING.format(digest=_read.settles_evidence(case).content_revision),
        _resumed.refuses_the_post,
        _world.REQUESTED,
    ),
    (
        "a run declared alone, its post refused",
        lambda _case: _world.DECLARED_ALONE,
        _resumed.refuses_the_post,
        _world.NO_FINDINGS,
    ),
)


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
        # Refused outright, taken with an answer naming no comment, or taken
        # with its response lost: nothing is handed, relabelled, or launched
        # without the anchor. The next tick reaches one developer behind one
        # feedback post: it posts again where the first was refused, and finds
        # the one that landed, in the very words it would post -- reading the
        # thread whole, so findings quoting the pinned state's marker are no
        # exception -- rather than posting it twice.
        for name, fails, reply in _UNANCHORED:
            with self.subTest(name):
                self.setUp()
                left = self._held_on_the_post(reply, **fails)

                fixed = self.finishes(**_disposed.fixing())

                self.assertEqual(
                    (
                        left,
                        fixed[_world.RUN_AGENT].call_count,
                        len(self.feedback_posts()),
                        tuple(self.github.label_history),
                        self.waiting(),
                    ),
                    ((0, None, ()), 1, 1, HANDED_BACK, None),
                )

    def test_a_park_behind_its_subject_posts_nothing(self) -> None:
        # Another road parks the issue over a report it cannot deliver while
        # the request is proved ready -- in the tick its reviewer returned,
        # or on a later tick finishing it waiting -- and the reading that
        # proves it carries the park onto the tick's state. Nothing is posted,
        # relabelled, or launched under that park, which stays as that road
        # wrote it with the request waiting; once a reply clears it, a later
        # tick hands the request to its one developer behind one post.
        for fresh in (True, False):
            with self.subTest(fresh=fresh):
                self.setUp()
                held = self._parked_while_proved(fresh=fresh)
                _roads.Writes(_ANSWERED)(self)

                fixed = self.finishes(**_disposed.fixing())

                self.assertEqual(
                    (
                        held,
                        fixed[_world.RUN_AGENT].call_count,
                        len(self.feedback_posts()),
                        tuple(self.github.label_history[-2:]),
                    ),
                    ((0, 0, ((_disposed.UNDELIVERABLE, True), "changes_requested")), 1, 1, HANDED_BACK),
                )

    def _parked_while_proved(self, *, fresh: bool) -> tuple:
        """Another road's park landing while the request is proved ready; what the tick it lands in leaves.

        In the tick its reviewer returned where `fresh`, right behind the issue
        read that resolves its subject; otherwise on a later tick finishing it,
        its first post refused, once that tick read the comment. The developers
        launched, the feedback posts, and the park with the verdict waiting.
        """
        if fresh:
            parks = _world.AnotherRoadBehind(self, "get_issue", self._before_its_post, _disposed.parks_over_its_report)
            with parks.patched():
                ran = self.returns(UNDECLARED_REQUEST, **_disposed.fixing())
        else:
            self._held_on_the_post(UNDECLARED_REQUEST, lands=False)
            ran = self.finishes(meanwhile=_disposed.parks_over_its_report, **_disposed.fixing())
        launched = ran[_world.RUN_AGENT].call_count
        return launched, len(self.feedback_posts()), self.parked()[:2]

    def _before_its_post(self, _issue_number) -> bool:
        """Whether the request is persisted and its feedback not yet posted."""
        return self.waiting() is not None and not self.feedback_posts()

    def _held_on_the_post(self, reply: str, **fails) -> tuple:
        """The tick whose reviewer returns `reply` and whose feedback post fails once as `fails` says.

        `fails` is as `RefusesOnce` takes it. What the tick left: the
        developers it launched, the run count the request was handed at, and
        every relabel.
        """
        refuses = _handoff.RefusesOnce(self.github.pr_comment, _handoff.FEEDBACK_NOTICE, **fails)
        with patch.object(self.github, PR_COMMENT, refuses):
            held = self.returns(reply, **_disposed.fixing())
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


class HistoricalRequestTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A request persisted with its declaration raw is posted and handed on concise, its record kept as persisted."""

    def test_a_raw_request_is_handed_on_concise(self) -> None:
        # Persisted raw beside the claim its declaration earned -- a fresh
        # run's or a reuse's -- and left waiting on its evidence or on its
        # feedback post: the tick finishing it posts the concise findings
        # once and resumes the one developer on exactly them.
        for name, reply, leaves, concise in _HISTORICAL:
            with self.subTest(name):
                self.setUp()

                finished = self._finishes_raw(reply, leaves, concise)

                self.assertEqual(
                    (finished, self.waiting()),
                    ((True, 1, ((concise,), True)), None),
                )

    def test_a_recovered_handoff_keeps_the_record(self) -> None:
        # A failed run's request persisted raw, its post refused, and the tick
        # recovering it dying on the relabel behind its concise post: the
        # record handed is the one persisted -- round, subject, raw feedback,
        # and the claim with its receipt -- beside that post as its anchor,
        # and the next tick launches the one developer on the concise
        # findings, posting nothing again.
        _raw.leaves_raw(self, _resumed.refuses_the_post)
        persisted = self.pinned()[_world.RETURNED_VERDICT]
        refused = patch.object(self.github, SET_LABEL, side_effect=RuntimeError("refused"))
        with refused, self.assertRaises(RuntimeError):
            self.finishes(**_disposed.fixing())
        handed = self.pinned()[_world.RETURNED_VERDICT]

        ran = self.finishes(**_disposed.fixing())[_world.RUN_AGENT]

        self.assertEqual(
            (
                persisted["feedback"],
                handed,
                self._feedback_ids(),
                ran.call_count,
                _raw.handed(self, ran.call_args.args[1], _world.CONCISE_FAILURE),
                self.waiting(),
            ),
            (
                _raw.RAW_FAILURE,
                {**persisted, _disposed.HANDED: handed[_disposed.HANDED], HANDED_WITH: handed.get(HANDED_WITH)},
                [handed.get(HANDED_WITH)],
                1,
                ((_world.CONCISE_FAILURE,), True),
                None,
            ),
        )

    def _finishes_raw(self, reply, leaves, concise: str) -> tuple:
        """Leave the request `reply(self)` waiting unformatted, as `leaves` does, then finish it in a later tick.

        Whether its record was persisted with the reply's feedback raw, the
        developers the later tick launched, and what it posted and handed on
        of `concise` (`raw_feedback_test_support.handed`).
        """
        replied = reply(self)
        _raw.leaves_raw(self, leaves, replied)
        persisted = self.pinned()[_world.RETURNED_VERDICT]["feedback"]
        ran = self.finishes(**_disposed.fixing())[_world.RUN_AGENT]
        handed = _raw.handed(self, ran.call_args.args[1], concise)
        return persisted == _raw.as_persisted(replied), ran.call_count, handed

    def _feedback_ids(self) -> list:
        """The id of every reviewer-feedback comment on the pull request, oldest first."""
        return [said.id for said in self.pull_request.issue_comments if _handoff.FEEDBACK_NOTICE in said.body]


if __name__ == "__main__":
    unittest.main()
