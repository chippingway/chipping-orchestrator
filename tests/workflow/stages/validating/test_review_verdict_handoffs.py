# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned change request reaches exactly one developer, behind feedback that is posted and anchored.

The feedback's id is the one durable copy of it, so a post that failed or left
no id hands nothing on and the verdict waits to post again. The subject is
held to what stands behind that post and behind the relabel ahead of the
launch, and a move behind either drops the request -- its anchor with it --
rather than paying a developer to answer a review of work that is not there.
A request already handed resumes where its handoff stopped without posting
its feedback again, and launches nobody where the run ledger says its
developer already ran.

The preparation the request is handed over behind is in
`test_review_disposition.py`.
"""
from __future__ import annotations

import itertools
import operator
import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS
from tests.workflow.value_helpers import _open_pr_for

PR_COMMENT = "pr_comment"

SET_LABEL = "set_workflow_label"

FIXING = (_world.ISSUE, LABEL_FIXING)

HANDED_BACK = (FIXING, (_world.ISSUE, LABEL_VALIDATING))

ANCHOR = "pending_fix_reviewer_comment_id"

HANDED = "handed"

REQUESTED = "changes_requested"

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# A reviewer asking for that change beside its declared run, which failed.
REQUESTING = _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED")

# What one developer answering a change request adds to what the issue spent:
# its run charged and folded, and the one round its pushed fix spends -- the
# reviewer's tokens are not folded again.
_ONE_DEVELOPER = (1, 1, 0, 1)

_CARRIES_THE_VERDICT = operator.methodcaller("get", _world.RETURNED_VERDICT)

_THE_FEEDBACK = _disposed.saying(_disposed.FEEDBACK_NOTICE)

_TO_FIXING = partial(operator.eq, LABEL_FIXING)

def _repoints(case) -> None:
    """Another road pointing `case`'s issue at another pull request than the one its reviewer reviewed."""
    _open_pr_for(case.github, issue_number=_world.ISSUE, pr_number=_world.PR + 1)
    state = case.github.read_pinned_state(case.issue)
    state.set("pr_number", _world.PR + 1)
    case.github.write_pinned_state(case.issue, state)


# The requests between a change request's verdict and its developer behind
# which another road moves what it stands on, the reply that earned it -- one
# declaring nothing, or one whose failed run it relies on as evidence -- how
# many feedback posts that leaves, the report revision the pinned comment
# records then, and every relabel. A later report, a push, the issue pointed at
# another pull request, or a later evidence revision superseding the one the
# request claims each moves it.
_BEFORE_THE_LAUNCH = (
    (
        "a report behind the verdict's write",
        UNDECLARED_REQUEST,
        ("write_pinned_state", _CARRIES_THE_VERDICT, _read.settles_a_later_report),
        (0, 2, ()),
    ),
    (
        "a report behind the feedback post",
        UNDECLARED_REQUEST,
        (PR_COMMENT, _THE_FEEDBACK, _read.settles_a_later_report),
        (1, 2, ()),
    ),
    ("a push behind the feedback post", UNDECLARED_REQUEST, (PR_COMMENT, _THE_FEEDBACK, _world.pushes), (1, 1, ())),
    ("a repoint behind the feedback post", UNDECLARED_REQUEST, (PR_COMMENT, _THE_FEEDBACK, _repoints), (1, 1, ())),
    ("evidence behind the feedback post", REQUESTING, (PR_COMMENT, _THE_FEEDBACK, _read.settles_evidence), (1, 1, ())),
    (
        "a report behind the relabel",
        UNDECLARED_REQUEST,
        (SET_LABEL, _TO_FIXING, _read.settles_a_later_report),
        (1, 2, (FIXING,)),
    ),
    ("a repoint behind the relabel", UNDECLARED_REQUEST, (SET_LABEL, _TO_FIXING, _repoints), (1, 1, (FIXING,))),
    ("evidence behind the relabel", REQUESTING, (SET_LABEL, _TO_FIXING, _read.settles_evidence), (1, 1, (FIXING,))),
)

def _fixing() -> dict:
    """How a tick runs in which one developer answers the request and pushes."""
    return {
        _world.RUN_AGENT: [_disposed.developer()],
        "dirty_files": (),
        "push_branch": True,
        "head_shas": FIX_HEAD_SHAS,
    }


def _charges_a_run(case) -> None:
    """The launch of the developer a handed request was owed, as its charge of the run ledger records it."""
    state = case.github.read_pinned_state(case.issue)
    state.set(_world.AGENT_RUNS_USED, state.get(_world.AGENT_RUNS_USED) + 1)
    case.github.write_pinned_state(case.issue, state)


def _clears_the_anchor(case) -> None:
    """The fixing stage's clear of the round's bookmarks, the reviewer-feedback anchor among them."""
    state = case.github.read_pinned_state(case.issue)
    state.set(ANCHOR, None)
    case.github.write_pinned_state(case.issue, state)


def _on_pull_request(numbers, returned_run, *read):
    """The run `returned_run` builds from `read`, naming the pull requests `numbers` gives it and its subject."""
    run = returned_run(*read)
    subject = replace(run.subject, pr_number=numbers[1])
    return replace(run, pr_number=numbers[0], subject=subject)


# The pull requests a run names beside the one its subject names that no
# verdict is acted on through: another, none beside one, and none beside none.
_ELSEWHERE = (
    (_world.PR + 1, _world.PR),
    (None, _world.PR),
    (None, None),
)

# The verdicts a returned run can carry: a change request declaring nothing,
# and an approval over its own passing run.
_RETURNED = (UNDECLARED_REQUEST, _world.declared_run())


# Where a handed request's handoff stopped, what another road did before the
# replay -- launched the developer it was handed to, or cleared its feedback
# anchor with the round's other bookmarks as the fixing stage does -- and what
# the replay leaves: the developers it launches, every relabel, and the verdict
# waiting.
_HANDED = (
    ("on the relabel", None, (1, HANDED_BACK, None)),
    ("past the launch", _charges_a_run, (0, (), None)),
    ("with its anchor cleared", _clears_the_anchor, (0, (), REQUESTED)),
)


class DisposedChangeRequestTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A change request reaches one developer, and only over what stands."""

    def test_a_held_request_reaches_one_developer(self) -> None:
        # Its evidence's publication is held, so nothing is posted or
        # relabelled; the next tick hands it to the developer it owes, over
        # the verdict the first tick wrote, with no reviewer run again.
        self.github.report_failures.lost.add(_world.PR)
        self.returns(REQUESTING)
        self.github.report_failures.lost.discard(_world.PR)
        charged = tuple(map(
            operator.add, _read.spent(self), _ONE_DEVELOPER,
        ))
        self.assertEqual(
            (_disposed.feedback_posts(self), self.github.label_history), ([], []),
        )

        run = self.finishes(**_fixing())[_world.RUN_AGENT]

        self.assertEqual(
            (
                run.call_count,
                run.call_args.kwargs.get("resume_session_id"),
                _world.REQUESTED in run.call_args.args[1],
                len(_disposed.feedback_posts(self)),
                _read.artifacts(self)[0].commands[0].exit_status,
                tuple(self.github.label_history),
                _read.spent(self),
                self.waiting(),
            ),
            (1, _world.DEV_SESSION, True, 1, 1, HANDED_BACK, charged, None),
        )

    def test_a_move_before_the_launch_drops_it(self) -> None:
        # Behind the verdict's write, its feedback post, or the relabel ahead
        # of the launch: no developer is launched, a later report is kept
        # rather than written back over, and no anchor is left for a retry to
        # replay.
        for name, message, behind, expected in _BEFORE_THE_LAUNCH:
            with self.subTest(name):
                self.setUp()

                ran = _world.AnotherRoadBehind(self, *behind).returning(message, **_fixing())

                self.assertEqual(
                    (
                        ran[_world.RUN_AGENT].call_count,
                        self.waiting(),
                        self.pinned().get(ANCHOR),
                        len(_disposed.feedback_posts(self)),
                        _read.current_report_revision(self),
                        tuple(self.github.label_history),
                    ),
                    (0, None, None, *expected),
                )

    def test_a_feedback_post_with_no_id_holds_it(self) -> None:
        # Whether GitHub refused the post or took it with an answer naming no
        # comment, nothing is relabelled or launched without the anchor. The
        # verdict, never handed, posts again on the next tick and reaches one
        # developer: twice over on the pull request where the first post
        # landed, since a feedback post carries no receipt to find it by.
        for name, lands, posts in (("refused", False, 1), ("landed with no id", True, 2)):
            with self.subTest(name):
                self.setUp()
                with patch.object(
                    self.github, PR_COMMENT,
                    _disposed.RefusesOnce(self.github.pr_comment, _disposed.FEEDBACK_NOTICE, lands=lands),
                ):
                    held = self.returns(UNDECLARED_REQUEST)
                self.assertEqual(
                    (
                        held[_world.RUN_AGENT].call_count,
                        self.pinned()[_world.RETURNED_VERDICT][HANDED],
                        self.pinned().get(ANCHOR),
                        self.github.label_history,
                    ),
                    (0, None, None, []),
                )

                fixed = self.finishes(**_fixing())

                self.assertEqual(
                    (
                        fixed[_world.RUN_AGENT].call_count,
                        len(_disposed.feedback_posts(self)),
                        tuple(self.github.label_history),
                        self.waiting(),
                    ),
                    (1, posts, HANDED_BACK, None),
                )

    def test_a_handed_request_resumes_its_handoff(self) -> None:
        # The relabel behind the write that handed the request over is
        # refused, so its feedback is posted and anchored and nobody launched.
        # The replay posts no feedback again: it relabels and launches the one
        # developer the request is owed -- or, where the run ledger was charged
        # past the count it was handed at, launches nobody and retires the
        # verdict, that developer already having run. Where the feedback
        # anchor it was handed beside is gone, no failed run could replay the
        # feedback, so the handoff is held: nothing relabelled or launched, and
        # the verdict waits as it was.
        for stopped, meanwhile, expected in _HANDED:
            with self.subTest(stopped):
                self.setUp()
                self._hands_over_unlaunched()
                handed = self.pinned()
                self.assertEqual(
                    (handed[_world.RETURNED_VERDICT][HANDED], handed[ANCHOR] is not None),
                    (handed[_world.AGENT_RUNS_USED], True),
                )
                if meanwhile is not None:
                    meanwhile(self)

                ran = self.finishes(**_fixing())

                self.assertEqual(
                    (
                        ran[_world.RUN_AGENT].call_count,
                        tuple(self.github.label_history),
                        self.waiting(),
                        len(_disposed.feedback_posts(self)),
                    ),
                    (*expected, 1),
                )

    def test_no_second_launch_behind_the_relabel(self) -> None:
        # Another road launches the developer the request is owed while the
        # relabel ahead of this road's launch is made -- on the tick that hands
        # the request over, or on a replay of that handoff. Its charge of the
        # run ledger past the count the request was handed at is that launch,
        # so this road launches nobody and retires the verdict, its feedback
        # posted once and its anchor left for that developer's replay.
        for replayed in (False, True):
            with self.subTest(replayed=replayed):
                self.setUp()
                behind = _world.AnotherRoadBehind(self, SET_LABEL, _TO_FIXING, _charges_a_run)
                tick = partial(self.returns, UNDECLARED_REQUEST, **_fixing())
                if replayed:
                    self._hands_over_unlaunched()
                    tick = partial(self.finishes, **_fixing())

                with patch.object(self.github, SET_LABEL, behind):
                    ran = tick()

                self.assertEqual(
                    (
                        ran[_world.RUN_AGENT].call_count,
                        tuple(self.github.label_history),
                        self.waiting(),
                        self.pinned().get(ANCHOR) is not None,
                        len(_disposed.feedback_posts(self)),
                    ),
                    (0, (FIXING,), None, True, 1),
                )

    def test_an_unstarted_launch_is_replayed(self) -> None:
        # The run circuit charges the developer's run and records it reserved
        # ahead of the spawn, and starts it in a write of its own; that start
        # is refused, so no developer ran. The charge past the count the
        # request was handed at is an unstarted reservation rather than a
        # launch, so the next tick replays the handoff -- posting nothing again
        # -- and launches the one developer the request is owed, honoring that
        # reservation rather than charging the issue a second run.
        with patch.object(self.github, "write_pinned_state", _disposed.RefusesTheStart(self.github.write_pinned_state)):
            unstarted = self.returns(UNDECLARED_REQUEST, **_fixing())
        left = (
            self.waiting(),
            self.pinned().get("agent_run_reservation"),
            self.pinned()[_world.AGENT_RUNS_USED],
        )

        ran = self.finishes(**_fixing())

        self.assertEqual(
            (
                unstarted[_world.RUN_AGENT].call_count,
                left,
                ran[_world.RUN_AGENT].call_count,
                self.waiting(),
                [pr for pr, body in self.github.posted_pr_comments if _disposed.FEEDBACK_NOTICE in body],
                self.pinned()[_world.AGENT_RUNS_USED] - left[2],
            ),
            (0, (REQUESTED, "reserved", left[2]), 1, None, [_world.PR], 0),
        )

    def _hands_over_unlaunched(self) -> None:
        """The tick that hands the request over, whose relabel ahead of the launch GitHub refuses."""
        refused = patch.object(self.github, SET_LABEL, side_effect=RuntimeError("refused"))
        with refused, self.assertRaises(RuntimeError):
            self.returns(UNDECLARED_REQUEST)


class ForeignRunTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A verdict is acted on only through a run naming the pull request its subject is on."""

    def test_another_pull_request_hands_nothing(self) -> None:
        # A later tick's rebuilt run naming another pull request than the one
        # the waiting verdict's subject is on -- or none -- would post the
        # feedback and push the fix there: nothing is posted, handed,
        # relabelled, or launched, and the verdict waits as it was.
        for pr_number in (_world.PR + 1, None):
            with self.subTest(pr_number=pr_number):
                self.setUp()
                _read.seeds_a_verdict(self, _read.settles_evidence(self), REQUESTED)
                self.run = replace(self.run, pr_number=pr_number)

                ran = self.finishes(**_fixing())

                self.assertEqual(self._handed(ran), (0, [], None, REQUESTED, []))

    def test_a_returned_run_elsewhere_is_refused(self) -> None:
        # A returned run naming another pull request than the one its subject
        # is on -- or none, beside a subject naming one or naming none either --
        # would post a change request's feedback and push its fix there, or
        # post an approval and squash there: whichever the verdict, it is
        # refused outright, nothing persisted, published, posted, relabelled,
        # or launched, and the pinned comment left as it was.
        for numbers, message in itertools.product(_ELSEWHERE, _RETURNED):
            with self.subTest(pr_numbers=numbers, verdict=message.splitlines()[-1]):
                self.setUp()
                before = (self.pinned(), len(self.github.posted_pr_comments))

                with patch.object(_world, "returned_run", partial(_on_pull_request, numbers, _world.returned_run)):
                    ran = self.returns(message, **_fixing())

                self.assertEqual(
                    (
                        self._handed(ran),
                        self.pinned(),
                        self.github.posted_pr_comments[before[1]:],
                    ),
                    ((0, [], None, None, []), before[0], []),
                )

    def _handed(self, ran) -> tuple:
        """The developers launched, the feedback posted, the verdict's handed count, the verdict, every relabel."""
        waiting = self.pinned().get(_world.RETURNED_VERDICT) or {}
        return (
            ran[_world.RUN_AGENT].call_count,
            _disposed.feedback_posts(self),
            waiting.get(HANDED),
            self.waiting(),
            self.github.label_history,
        )


if __name__ == "__main__":
    unittest.main()
