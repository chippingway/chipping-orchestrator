# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A persisted change request reaches exactly one developer, behind feedback that is posted and anchored.

Only the decision the request was persisted from is handed over, since its
words are what is posted and what the developer is resumed on. The feedback's
id is the one durable copy of it, so a post that failed, left no id, or had no
pull request of the request's own to go on hands nothing on, and the verdict
waits to post again. The subject is held to what stands behind
that post and behind the relabel ahead of the launch, and a move behind
either drops the request -- its anchor with it -- rather than paying a
developer to answer a review of work that is not there. A request already
handed resumes where its handoff stopped without posting its feedback again,
held where its anchor is gone or names another comment, and launches nobody
where the run ledger says its developer already ran -- its anchor kept even
where that developer's push moved the subject.

The preparation a request is handed over behind is in
`test_review_disposition.py`, the record it waits in in
`test_review_verdicts.py`, and what holds the launch again where the run
circuit charges and starts it in `test_review_launch_hold.py`.
"""
from __future__ import annotations

import operator
import re
import unittest
from dataclasses import replace
from functools import partial
from itertools import product
from types import MappingProxyType
from unittest.mock import patch

from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING
from tests.workflow.stages.validating import (
    review_handoff_test_support as _support,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

PR_COMMENT = "pr_comment"

SET_LABEL = "set_workflow_label"

FIXING = (_world.ISSUE, LABEL_FIXING)

HANDED_BACK = (FIXING, (_world.ISSUE, LABEL_VALIDATING))

LEDGER = "orchestrator_comment_ids"

HANDED = "handed"

# A comment id no comment carries, which `int()` would still read as one.
FRACTIONAL_ID = 1.5

# The two requests between a change request and its developer, as the client
# spells each, and which of its calls is the handoff's own.
_BEHIND_THE_POST = (PR_COMMENT, re.compile(_support.FEEDBACK_NOTICE).search)

_BEHIND_THE_RELABEL = (SET_LABEL, partial(operator.eq, LABEL_FIXING))


def _another_road(case, request: str, when, road):
    """The client's `request` patched so `road` does another road's work behind the call `when` names."""
    return patch.object(case.github, request, _world.AnotherRoadBehind(case, request, when, road))


def _refused_once(case, decision, *, lands: bool, answers: object = None):
    """Hand `decision` over through a feedback post refused once -- or, where it `lands`, answered with id `answers`."""
    refusing = _support.RefusesOnce(case.github.pr_comment, _support.FEEDBACK_NOTICE, lands=lands, answers=answers)
    with patch.object(case.github, PR_COMMENT, refusing):
        return case.hands_over(decision)


def _through(pr_number, case, decision):
    """Hand `decision` over through its run naming `pr_number` beside the subject its reviewer reviewed."""
    return case.hands_over(replace(decision, run=replace(decision.run, pr_number=pr_number)))


def _of_another_round(decision):
    """`decision`, as a later round's reviewer returned the same words about the same subject."""
    run = decision.run
    return replace(decision, run=replace(run, round_n=run.round_n + 1))


def _replaces_the_request(case, members: dict | None, *, pinned: dict | None = None) -> None:
    """Put another verdict in place of `case`'s waiting request, or none at all, and set `pinned` beside it.

    The verdict put there is the request with `members` over its own, a
    member given as `...` taken off.
    """
    state = case.github.read_pinned_state(case.issue)
    waiting = state.data.pop(_world.RETURNED_VERDICT)
    if members is not None:
        waiting.update(members)
        kept = {key: member for key, member in waiting.items() if member is not ...}
        state.set(_world.RETURNED_VERDICT, kept)
    state.data.update(pinned or {})
    case.github.write_pinned_state(case.issue, state)


# A handoff whose feedback post names no comment it can anchor on: the tick
# that meets it, and how many feedback posts are on the pull request once a
# later tick hands the request over from the pinned comment alone. An id that
# is no positive whole number -- zero, a flag, a fraction -- names none.
_UNIDENTIFIED = (
    ("a refused post", partial(_refused_once, lands=False), 1),
    ("a post that landed with no id", partial(_refused_once, lands=True), 2),
    ("a post answering id zero", partial(_refused_once, lands=True, answers=0), 2),
    ("a post answering a flag", partial(_refused_once, lands=True, answers=True), 2),
    ("a post answering a fraction", partial(_refused_once, lands=True, answers=FRACTIONAL_ID), 2),
    ("a run naming no pull request", partial(_through, None), 1),
    ("a run naming another pull request", partial(_through, _world.PR + 1), 1),
)

# A handoff whose request is not the decision handed over: the members put
# over the waiting record (none at all where None), and the decision handed --
# or, where None, a later tick handing over from the pinned comment alone.
_NOT_ITS_OWN = (
    ("no verdict waiting", None, replace),
    ("no verdict waiting, on a later tick", None, None),
    ("an approval waiting", {"verdict": "approved", "feedback": ""}, replace),
    ("an approval waiting, on a later tick", {"verdict": "approved", "feedback": ""}, None),
    ("an approval returned", {}, partial(replace, verdict="approved")),
    ("another round returned", {}, _of_another_round),
    ("other words returned", {}, partial(replace, body="1. Rename the module instead.")),
)

# The requests between a change request and its developer behind which
# another road moves what it stands on, whether the request claims evidence,
# and then how many feedback posts that leaves, the report revision the pinned
# comment records, and every relabel. A later report, a push, the issue
# pointed at another pull request, or a later evidence revision superseding
# the one the request claims each moves it.
_BEFORE_THE_LAUNCH = (
    ("a report behind the feedback post", (*_BEHIND_THE_POST, _read.settles_a_later_report), False, (1, 2, ())),
    ("a push behind the feedback post", (*_BEHIND_THE_POST, _world.pushes), False, (1, 1, ())),
    ("a repoint behind the feedback post", (*_BEHIND_THE_POST, _support.repoints), False, (1, 1, ())),
    ("evidence behind the feedback post", (*_BEHIND_THE_POST, _read.settles_evidence), True, (1, 1, ())),
    ("a report behind the relabel", (*_BEHIND_THE_RELABEL, _read.settles_a_later_report), False, (1, 2, (FIXING,))),
    ("a push behind the relabel", (*_BEHIND_THE_RELABEL, _world.pushes), False, (1, 1, (FIXING,))),
    ("a repoint behind the relabel", (*_BEHIND_THE_RELABEL, _support.repoints), False, (1, 1, (FIXING,))),
    ("evidence behind the relabel", (*_BEHIND_THE_RELABEL, _read.settles_evidence), True, (1, 1, (FIXING,))),
)

# The record a handoff wrote before it anchored its post: handed, and naming
# no post of its own.
_UNANCHORED = MappingProxyType({"anchor": ...})

# Where a handed request's handoff stopped, what another road did before the
# replay -- launched the developer it was handed to, ran something else, a
# reviewer say, cleared its feedback anchor with the round's other bookmarks as
# the fixing stage does, pointed that anchor at another comment, spelled it as
# a float the fixing stage's replay refuses, or left the record as a handoff
# wrote it before it anchored its post, beside the pinned anchor or with that
# cleared too -- and what the replay leaves: the developers it launches, every
# relabel, whether the request still waits, and whether the pinned comment is
# exactly as the replay found it.
_HANDED = (
    ("on the relabel", None, (1, HANDED_BACK, False, False)),
    ("past the launch", _support.charges_a_run, (0, (), False, False)),
    ("behind an unrelated run", partial(_support.charges_a_run, owed=False), (1, HANDED_BACK, False, False)),
    ("with its anchor cleared", partial(_support.moves_the_anchor, to="nowhere"), (0, (), True, True)),
    ("with its anchor replaced", partial(_support.moves_the_anchor, to="elsewhere"), (0, (), True, True)),
    ("with its anchor spelled as a float", partial(_support.moves_the_anchor, to="a float"), (0, (), True, True)),
    ("before handoffs anchored their post", partial(_replaces_the_request, members=_UNANCHORED), (0, (), True, True)),
    (
        "before handoffs anchored their post, the pinned anchor cleared",
        partial(_replaces_the_request, members=_UNANCHORED, pinned={_support.ANCHOR: None}),
        (0, (), True, True),
    ),
)


class ChangeRequestHandoffTest(_support.HandoffWorld, unittest.TestCase):
    """A fresh change request reaches one developer, and only over what stands."""

    def test_one_developer_answers_it(self) -> None:
        # The feedback is posted, and the request written as handed at the
        # run count it found, beside the id of that post both on the record
        # and as the pinned replay anchor, BEFORE the relabel; then the one
        # developer is resumed on the feedback, its run the one charge the
        # handoff adds, and the writes behind it retire the request.
        decision = self.seeds()
        charged = self.pinned()[_world.AGENT_RUNS_USED]

        with _another_road(self, *_BEHIND_THE_RELABEL, _support.HandoffWorld.remembers):
            ran = self.hands_over(decision)

        posted = [said.id for said in self.feedback_posts()]
        self.assertEqual(
            (
                self.remembered[_world.RETURNED_VERDICT][HANDED],
                self.remembered[_world.RETURNED_VERDICT]["anchor"],
                self.remembered[_support.ANCHOR],
                posted[0] in self.remembered[LEDGER],
            ),
            (charged, posted[0], posted[0], True),
        )
        self.assertEqual(
            (
                ran.call_count,
                ran.call_args.kwargs.get("resume_session_id"),
                _world.REQUESTED in ran.call_args.args[1],
                len(posted),
                tuple(self.github.label_history),
                self.pinned()[_world.AGENT_RUNS_USED] - charged,
                self.waiting(),
            ),
            (1, _world.DEV_SESSION, True, 1, HANDED_BACK, 1, None),
        )

    def test_a_post_it_cannot_anchor_hands_nothing(self) -> None:
        # A post GitHub refused, one it took with an answer naming no comment,
        # and a run with no pull request of the request's own to post on each
        # leave nothing to anchor the handoff on: nothing is relabelled,
        # launched, or written, and the request waits unhanded. A later tick,
        # holding no decision, hands it over from the pinned comment alone and
        # reaches one developer -- behind a second post where the first
        # landed, since a feedback post carries no receipt to find it by.
        for name, handing, posts in _UNIDENTIFIED:
            with self.subTest(name):
                self.setUp()
                decision = self.seeds()
                seeded = self.pinned()

                self.assertEqual(
                    (handing(self, decision).call_count, self.pinned(), self.github.label_history),
                    (0, seeded, []),
                )
                self.assertEqual(
                    (
                        self.hands_over().call_count,
                        len(self.feedback_posts()),
                        tuple(self.github.label_history),
                        self.waiting(),
                    ),
                    (1, posts, HANDED_BACK, None),
                )

    def test_only_its_own_request_is_handed(self) -> None:
        # The decision handed over has to be the request the comment keeps:
        # with no verdict waiting, an approval of the same subject waiting in
        # its place -- whether a decision is handed over or a later tick hands
        # over from the comment alone -- or a decision of an approval, of
        # another round, or in other words than the request says, nothing is
        # posted, written, relabelled, or launched: the post and the
        # developer's prompt would carry what the persisted request never said.
        for name, members, returning in _NOT_ITS_OWN:
            with self.subTest(name):
                self.setUp()
                decision = self.seeds()
                _replaces_the_request(self, members)
                left = self.pinned()

                self.assertEqual(
                    (
                        self.hands_over(None if returning is None else returning(decision)).call_count,
                        self.feedback_posts(),
                        self.pinned(),
                        self.github.label_history,
                    ),
                    (0, [], left, []),
                )

    def test_a_move_before_the_launch_drops_it(self) -> None:
        # Behind its feedback post, or behind the relabel ahead of the launch:
        # no developer is launched, a later report is kept rather than
        # written back over, and no anchor is left for a retry to replay.
        for name, behind, evidence, expected in _BEFORE_THE_LAUNCH:
            with self.subTest(name):
                self.setUp()
                decision = self.seeds(evidence=evidence)

                with _another_road(self, *behind):
                    self.assertEqual(self.hands_over(decision).call_count, 0)

                self.assertEqual(
                    (
                        self.waiting(),
                        self.pinned().get(_support.ANCHOR),
                        len(self.feedback_posts()),
                        _read.current_report_revision(self),
                        tuple(self.github.label_history),
                    ),
                    (None, None, *expected),
                )

    def test_a_drop_keeps_another_roads_anchor(self) -> None:
        # Behind its feedback post another road pushes and points the replay
        # anchor at a comment of its own: the request is dropped over that
        # reading, and the anchor it carries is that road's, not this road's
        # post and not cleared.
        decision = self.seeds()
        pushed = _another_road(self, *_BEHIND_THE_POST, _world.pushes)
        theirs = partial(_support.moves_the_anchor, to="elsewhere")

        # Entered in turn, so the second road wraps the post the first patched.
        with pushed, _another_road(self, *_BEHIND_THE_POST, theirs):
            self.assertEqual(self.hands_over(decision).call_count, 0)

        self.assertEqual(
            (
                self.waiting(),
                self.pinned().get(_support.ANCHOR),
                len(self.feedback_posts()),
            ),
            (None, self.pull_request.issue_comments[0].id, 1),
        )

    def test_a_moved_anchor_holds_the_relabel(self) -> None:
        # Right behind the write that hands the request over, another road
        # clears the replay anchor or points it at another comment. The launch
        # is held to the anchor before the relabel that announces it, not only
        # after: nothing is relabelled or launched, so the issue is not left on
        # `fixing` with nobody launched, and the request waits, handed.
        for to in ("nowhere", "elsewhere"):
            with self.subTest(to=to):
                self.setUp()
                decision = self.seeds()
                road = partial(_support.moves_the_anchor, to=to)

                with _another_road(self, "write_pinned_state", self._writes_the_handoff, road):
                    self.assertEqual(self.hands_over(decision).call_count, 0)

                self.assertEqual(
                    (self.github.label_history, self.waiting()[HANDED], len(self.feedback_posts())),
                    ([], self.pinned()[_world.AGENT_RUNS_USED], 1),
                )

    def _writes_the_handoff(self, state) -> bool:
        """Whether a pinned-comment write is the one that hands the waiting request over."""
        return (state.get(_world.RETURNED_VERDICT) or {}).get(HANDED) is not None


class HandedRequestTest(_support.HandoffWorld, unittest.TestCase):
    """A request already handed is finished without posting its feedback again, and by one developer."""

    def test_a_handed_request_resumes_its_handoff(self) -> None:
        # The relabel behind the write that handed the request over is
        # refused, so its feedback is posted and anchored and nobody launched.
        # The replay -- a later tick, holding no decision -- posts no feedback
        # again: it relabels and launches the one developer the request is
        # owed -- or, where the run ledger records that developer's start at
        # the count it was handed at, launches nobody and retires the request.
        # Any other run charged meanwhile, a reviewer's, is no such start.
        # Where the anchor it was handed beside is gone, no failed run could
        # replay the feedback, and where it names another comment, or is no
        # whole id, a failed run would replay another comment or none: either
        # way the handoff is held, nothing relabelled, launched, or written. A
        # record handed before handoffs anchored their post still reads as the
        # request handed, and names no post any pinned anchor -- not even none
        # -- can be vouched for as, so it is held the same way.
        for stopped, meanwhile, expected in _HANDED:
            with self.subTest(stopped):
                self.setUp()
                self.hands_over_unlaunched()
                self.assertEqual(
                    (self.waiting()[HANDED], self.waiting()["anchor"]),
                    (self.pinned()[_world.AGENT_RUNS_USED], self.pinned()[_support.ANCHOR]),
                )
                if meanwhile is not None:
                    meanwhile(self)
                left = self.pinned()

                self.assertEqual(
                    (
                        self.hands_over().call_count,
                        tuple(self.github.label_history),
                        self.waiting() is not None,
                        self.pinned() == left,
                        len(self.feedback_posts()),
                    ),
                    (*expected, 1),
                )

    def test_a_retirement_keeps_newer_records(self) -> None:
        # The developer a handed request owes was launched, and another road
        # settles a later report after this road read the comment: the request
        # is retired in a write composed over the comment read again, so that
        # report and the round it spent stay rather than being written back to
        # the ones this road read.
        self.hands_over_unlaunched()
        _support.charges_a_run(self)

        with _another_road(self, "read_pinned_state", bool, _read.settles_a_later_report):
            self.assertEqual(self.hands_over().call_count, 0)

        self.assertEqual(
            (self.waiting(), _read.current_report_revision(self), self.pinned()["review_round"]),
            (None, 2, 1),
        )

    def test_a_pushed_developer_keeps_its_anchor(self) -> None:
        # The developer a handed request owes started, recorded at the count
        # it was handed at, and pushed, and the tick died before its writes
        # retired the request. The later tick retires it as launched before it
        # asks whether the subject stands -- that push moved the head -- so the
        # anchor that developer's own replay needs is kept, not dropped as a
        # review of a subject that moved.
        self.hands_over_unlaunched()
        _support.charges_a_run(self)
        _world.pushes(self)

        self.assertEqual(self.hands_over().call_count, 0)

        self.assertEqual(
            (self.waiting(), self.pinned().get(_support.ANCHOR), self.github.label_history),
            (None, self.feedback_posts()[0].id, []),
        )

    def test_no_second_developer_behind_the_relabel(self) -> None:
        # Another road launches the developer the request is owed while the
        # relabel ahead of this road's launch is made -- on the tick that hands
        # the request over, or on a later tick's replay of that handoff -- and
        # that developer may already have pushed by the time this road reads
        # the subject again. Its start, recorded at the count the request was
        # handed at and carried by the comment read behind that subject, is
        # that launch, whatever the push did to the head: this road launches
        # nobody and retires the request, its feedback posted once and its
        # anchor left for that developer's replay rather than dropped as a
        # review of a subject that moved.
        for replayed, pushed in product((False, True), repeat=2):
            with self.subTest(replayed=replayed, pushed=pushed):
                self.setUp()
                if replayed:
                    self.hands_over_unlaunched()
                decision = None if replayed else self.seeds()
                road = partial(_support.charges_a_run, pushes=pushed)

                with _another_road(self, *_BEHIND_THE_RELABEL, road):
                    self.assertEqual(self.hands_over(decision).call_count, 0)

                self.assertEqual(
                    (
                        tuple(self.github.label_history),
                        self.waiting(),
                        [said.id for said in self.feedback_posts()],
                    ),
                    ((FIXING,), None, [self.pinned()[_support.ANCHOR]]),
                )

    def test_an_unstarted_launch_is_replayed(self) -> None:
        # The run circuit charges the developer's run and records it reserved
        # ahead of the spawn, and starts it in a write of its own; that start
        # is refused, so no developer ran. The charge past the count the
        # request was handed at is an unstarted reservation, which recorded no
        # start, so the next tick, holding no decision, replays the handoff --
        # posting nothing again -- and launches the one developer the request
        # is owed, honoring that reservation rather than charging a second run.
        decision = self.seeds()
        with patch.object(self.github, "write_pinned_state", _support.RefusesTheStart(self.github.write_pinned_state)):
            self.assertEqual(self.hands_over(decision).call_count, 0)
        handed = self.waiting()[HANDED]
        left = (
            self.pinned().get(_support.RESERVATION),
            self.pinned()[_world.AGENT_RUNS_USED] - handed,
        )

        self.assertEqual(
            (
                left,
                self.hands_over().call_count,
                self.waiting(),
                len(self.feedback_posts()),
                self.pinned()[_world.AGENT_RUNS_USED] - handed,
            ),
            (("reserved", 1), 1, None, 1, 1),
        )


if __name__ == "__main__":
    unittest.main()
