# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A change request's handoff, and the retirement of one whose developer was launched, land as guarded commits.

Another road's write right ahead of the handoff's commit -- a verdict put in
the request's place, a later report, evidence settled, a repoint, the anchor
written, a run charged, the comment unparsed or replaced -- refuses it behind
its one post, with nothing written over that road's write, relabelled, or
launched; and so does one right ahead of a retirement's commit, found
started by a later entry. The retirement behind the developer's own run is
prepared right behind it and lands with the first record of its result, so a
park it leaves keeps what another road wrote while it ran, and a verdict
another road put in this one's place, a repoint, or the anchor pointed
elsewhere stops that result altogether. A dropped request clears
the anchor only where it was this road's to drop. Whatever is
left is finished once by a later tick, made under the issue's writer claim as
every dispatch is: a handoff refused behind its post is handed over beside
that post, found by its words -- this orchestrator's own, never a copy another
author wrote -- and a commit GitHub took and lost the response to is resumed
from what the comment carries. One post, one developer, one charge.

The handoff's own requests and what moves behind them are in
`test_review_handoffs.py`, and the room it is taken with in
`test_review_handoff_room.py`.
"""
from __future__ import annotations

import operator
import unittest
from functools import partial
from itertools import product
from unittest.mock import MagicMock, patch

from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.validating import feedback_posts as _feedback_posts, review_verdicts as _verdicts
from tests.support.fakes import FakeComment, FakeUser
from tests.support.writer_claims import held_elsewhere
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING, _agent
from tests.workflow.stages.validating import (
    review_handoff_test_support as _support,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    review_write_test_support as _roads,
)

HANDED = "handed"

HANDED_BACK = ((_world.ISSUE, LABEL_FIXING), (_world.ISSUE, LABEL_VALIDATING))

# A comment of another road's the pinned feedback anchor is pointed at.
ANOTHER_COMMENT = 4_242

# Who copies the feedback post's words onto the pull request in their own name.
ANOTHER_AUTHOR = "mallory"

# The client request the relabel to `workflow:fixing` goes out through.
_SET_LABEL = "set_workflow_label"

# A field of another road's that no write of the handoff's owns, and what it
# writes there.
_NOTES = "operator_notes"

_KEPT = "keep this"

# The member of a returned verdict naming the round its reviewer ran as.
_ROUND = "round"

# How the developer a request owes ends a run that publishes nothing, and the
# park reason that leaves: timed out, or asking a question, which parks with
# no reason of its own.
_TIMED_OUT = _agent(session_id=_world.DEV_SESSION, timed_out=True)

_ASKS = _agent(session_id=_world.DEV_SESSION, last_message="Which configuration is the default?")

_UNPUBLISHED = (("a timeout", _TIMED_OUT, "agent_timeout"), ("a question", _ASKS, None))

# A checkout whose head the run leaves where the pull request stands.
_UNMOVED = (_world.HEAD,)

# Another road's write of the feedback anchor, naming a comment of its own.
_WRITES_THE_ANCHOR = _roads.Writes({_support.ANCHOR: ANOTHER_COMMENT})

# Another road's run of a launch of its own, a reviewer's say.
_CHARGES_A_RUN = partial(_support.charges_a_run, owed=False)


def _replaces_the_request(case) -> None:
    """Another road's change request of a later round in place of the one `case` has waiting, as it was handed."""
    state = case.github.read_pinned_state(case.issue)
    waiting = state.get(_world.RETURNED_VERDICT)
    state.set(_world.RETURNED_VERDICT, {**waiting, _ROUND: waiting[_ROUND] + 1})
    case.github.write_pinned_state(case.issue, state)


def _copies_the_post(case) -> int:
    """Another author posting on the pull request the very words the waiting request is posted in; the copy's id."""
    waiting = _verdicts.read_returned_verdict(case.github.read_pinned_state(case.issue))
    words = _feedback_posts.posted(waiting.round_n, waiting.feedback)
    body = _comments._with_orch_marker(_feedback_posts.receipted(words, waiting))
    author = FakeUser(ANOTHER_AUTHOR)
    copied = FakeComment(case.github.next_reply_id(case.issue), body, user=author)
    case.pull_request.issue_comments.append(copied)
    return copied.id


def _answers_while(case, answer, *roads) -> MagicMock:
    """A developer run answering `answer`, during which `roads` do another road's work on `case`, in order."""
    return MagicMock(side_effect=partial(_answering, case, answer, roads))


def _answering(case, answer, roads, *_asked, **_options):
    """`roads` doing another road's work on `case`, in order, and then `answer` as the developer's run."""
    for road in roads:
        road(case)
    return answer


def _handed_back(case) -> tuple:
    """How many feedback posts `case`'s pull request carries, every relabel, and which verdict waits."""
    waiting = case.waiting()
    return (
        len(case.feedback_posts()),
        tuple(case.github.label_history),
        None if waiting is None else waiting["verdict"],
    )


# Another road's write right ahead of the commit handing a request over,
# behind the last reading it was decided on: a verdict put in the request's
# place or written null, a later report, evidence settled, the issue pointed
# at another pull request, the feedback anchor written, a run charged, and the
# comment itself unparsed or replaced. Each refuses the handoff.
_AHEAD_OF_THE_HANDOFF = (
    ("another round's verdict", _replaces_the_request),
    ("a verdict written null", _roads.Writes({_world.RETURNED_VERDICT: None})),
    ("a later report", _read.settles_a_later_report),
    ("evidence settled", _read.settles_evidence),
    ("a repoint", _support.repoints),
    ("the anchor written", _WRITES_THE_ANCHOR),
    ("a run charged", _CHARGES_A_RUN),
    ("an unparsed comment", _roads.unparses),
    ("a replaced comment", _roads.repins),
)

# The writes ahead of a handoff that leave its request standing, for a later
# tick to hand over behind the post the refused one made.
_REFUSED_STANDING = (("a run charged", _CHARGES_A_RUN), ("the anchor written", _WRITES_THE_ANCHOR))

# Another road's write right ahead of the commit retiring a request whose
# developer was launched: a verdict put in its place, or the start that says
# it was launched written as none. Each refuses the retirement.
_AHEAD_OF_THE_RETIREMENT = (
    ("another round's verdict", _replaces_the_request),
    ("its start written as none", _roads.Writes({"agent_run_owed_started": None})),
)

# Another road's write while the developer a handed request owes runs, and the
# round of the verdict it leaves waiting: a verdict put in the request's place,
# the issue pointed at another pull request, or the feedback anchor pointed at
# a comment of its own, which a failed run's continue would replay in place of
# the feedback that run was handed. Each stops what the run's result writes.
_UNDER_THE_RUN = (
    ("another round's verdict", _replaces_the_request, 1),
    ("a repoint", _support.repoints, 0),
    ("the anchor repointed", _WRITES_THE_ANCHOR, 0),
)


class HandoffCommitTest(_support.HandoffWorld, unittest.TestCase):
    """The handoff is prepared before its post and committed behind it, or not at all; what it leaves is finished once.

    Every case's road goes ahead of the first guarded commit the tick makes,
    which on these ticks is the handoff's own.
    """

    def test_a_write_ahead_of_the_handoff_refuses_it(self) -> None:
        # Another road writes right ahead of the commit handing the request
        # over -- in the tick its reviewer returned, or on a later tick
        # handing it over from the pinned comment alone. The commit is
        # refused: the feedback is posted once, the comment stays exactly as
        # that road left it, and nothing is relabelled or launched.
        for (name, road), fresh in product(_AHEAD_OF_THE_HANDOFF, (True, False)):
            with self.subTest(name, fresh=fresh):
                self.setUp()
                decision = self.seeds()

                with _roads.AnotherRoadAhead(self, bool, partial(_roads.leaves, road)).patched():
                    ran = self.hands_over(decision if fresh else None)

                self.assertEqual(
                    (ran.call_count, self.github.label_history, self.pinned(), len(self.feedback_posts())),
                    (0, [], self.left_behind, 1),
                )

    def test_a_refused_handoff_is_finished_once(self) -> None:
        # A run another road charged, or the anchor it wrote, right ahead of
        # the commit refuses the handoff behind its feedback post. A later
        # tick, on the pinned comment alone, finds that post by its words
        # rather than posting again, hands the request over beside it, and
        # launches its one developer, whose run is the one charge it adds.
        for name, road in _REFUSED_STANDING:
            with self.subTest(name):
                self.setUp()
                decision = self.seeds()
                with _roads.AnotherRoadAhead(self, bool, road).patched():
                    self.hands_over(decision)
                charged = self.pinned()[_world.AGENT_RUNS_USED]

                ran = self.hands_over()

                self.assertEqual(
                    (
                        ran.call_count,
                        _handed_back(self),
                        self.pinned()[_world.AGENT_RUNS_USED] - charged,
                    ),
                    (1, (1, HANDED_BACK, None), 1),
                )

    def test_a_lost_handoff_is_resumed_once(self) -> None:
        # GitHub takes the commit handing the request over and loses its
        # response, so nothing is relabelled or launched behind a handoff
        # nobody confirmed. The next tick reads it handed beside its post's
        # anchor, posts nothing again, and relabels and launches the one
        # developer it owes, whose run is the one charge it adds.
        for fresh in (True, False):
            with self.subTest(fresh=fresh):
                self.setUp()
                left = self._loses_the_handoff(fresh=fresh)
                charged = self.pinned()[_world.AGENT_RUNS_USED]

                ran = self.hands_over()

                self.assertEqual(
                    (
                        left,
                        ran.call_count,
                        _handed_back(self),
                        self.pinned()[_world.AGENT_RUNS_USED] - charged,
                    ),
                    ((0, (), True), 1, (1, HANDED_BACK, None), 1),
                )

    def test_a_retry_under_the_claim_settles_once(self) -> None:
        # The retry of a handoff whose response was lost is made as every
        # dispatch makes it, under the issue's writer claim: while another
        # poller holds that claim it posts, writes, relabels, and launches
        # nothing, and once the claim is let go it relabels and launches the
        # one developer the request owes, behind the one post.
        self._loses_the_handoff(fresh=True)
        left = self.pinned()

        with held_elsewhere(self.github.repo_id, _world.ISSUE):
            contended = _roads.under_the_claim(self, self.hands_over)
        held = (contended, self.pinned() == left, tuple(self.github.label_history))
        ran = _roads.under_the_claim(self, self.hands_over)

        self.assertEqual(
            (held, ran.call_count, _handed_back(self)),
            ((None, True, ()), 1, (1, HANDED_BACK, None)),
        )

    def test_only_its_own_post_is_found(self) -> None:
        # The first post was refused, and another author copies its very
        # words, marker and all, onto the pull request. A later tick does not
        # take that copy for the feedback a failed run's continue replays as
        # this reviewer's: it posts its own, and hands the request over beside
        # that post.
        refuses = _support.RefusesOnce(self.github.pr_comment, _support.FEEDBACK_NOTICE, lands=False)
        with patch.object(self.github, "pr_comment", refuses):
            self.hands_over(self.seeds())
        copied = _copies_the_post(self)
        relabel = _world.AnotherRoadBehind(
            self, _SET_LABEL, partial(operator.eq, LABEL_FIXING), _support.HandoffWorld.remembers,
        )

        with patch.object(self.github, _SET_LABEL, relabel):
            ran = self.hands_over()

        posted = [said.id for said in self.feedback_posts() if said.id != copied]
        self.assertEqual(
            (ran.call_count, len(posted), self.remembered[_support.ANCHOR]),
            (1, 1, posted[0]),
        )

    def _loses_the_handoff(self, *, fresh: bool) -> tuple:
        """The tick handing a fresh request over whose commit GitHub takes and loses the response to.

        Through its decision where `fresh`, and from the pinned comment alone
        otherwise. What it left: the developers it launched, every relabel,
        and whether the comment carries the request handed.
        """
        decision = self.seeds()
        with _roads.AnotherRoadAhead(self, bool, _roads.loses_the_responses).patched():
            ran = self.hands_over(decision if fresh else None)
        self.github.pinned_failures.lost.discard(_world.ISSUE)
        handed = self.waiting()[HANDED] is not None
        return ran.call_count, tuple(self.github.label_history), handed


class RetirementCommitTest(_support.HandoffWorld, unittest.TestCase):
    """A request is retired, or dropped, in one guarded commit, or not at all, and only once."""

    def test_a_write_ahead_of_the_retirement_is_kept(self) -> None:
        # The developer a handed request owes was launched, and another road
        # writes right ahead of the commit retiring the request -- the first
        # the replay makes: a verdict put in its place, or that start written
        # as none, refuses it, and the comment stays exactly as that road left
        # it, nothing relabelled or launched.
        for name, road in _AHEAD_OF_THE_RETIREMENT:
            with self.subTest(name):
                self.setUp()
                self.hands_over_unlaunched()
                _support.charges_a_run(self)

                with _roads.AnotherRoadAhead(self, bool, partial(_roads.leaves, road)).patched():
                    ran = self.hands_over()

                self.assertEqual(
                    (ran.call_count, self.github.label_history, self.pinned()),
                    (0, [], self.left_behind),
                )

    def test_a_lost_retirement_settles_once(self) -> None:
        # GitHub takes the commit retiring that request and loses its
        # response: the request is retired once, and the next tick finds
        # nothing to hand over -- nothing posted, relabelled, launched, or
        # written.
        self.hands_over_unlaunched()
        _support.charges_a_run(self)
        with _roads.AnotherRoadAhead(self, bool, _roads.loses_the_responses).patched():
            self.assertEqual(self.hands_over().call_count, 0)
        self.github.pinned_failures.lost.discard(_world.ISSUE)
        left = self.pinned()

        self.assertEqual(
            (self.waiting(), self.hands_over().call_count, self.pinned(), self.github.label_history),
            (None, 0, left, []),
        )
        self.assertEqual(len(self.feedback_posts()), 1)

    def test_a_run_retires_it_over_fresh_fields(self) -> None:
        # The developer the request owes runs and publishes nothing -- it
        # times out, or asks a question -- while another road writes a field
        # of its own. The request is retired in the guarded commit landing the
        # run's park, over that write, behind its one notice, the other road's
        # field kept.
        for name, answer, reason in _UNPUBLISHED:
            with self.subTest(name):
                self.setUp()
                self.assertEqual(
                    self._runs_to(answer, _roads.Writes({_NOTES: _KEPT})),
                    (None, reason, True, _KEPT, 1),
                )

    def test_a_write_under_the_run_stops_its_result(self) -> None:
        # Another road puts its own verdict in the request's place, points the
        # issue at another pull request, or points the feedback anchor at a
        # comment of its own, and writes a field of its own, while the
        # developer runs: the retirement prepared behind the run is refused,
        # and what that run's result writes -- its park, its notice -- is
        # written and posted nowhere, the request, the anchor, and the field
        # kept exactly as that road left them.
        for unpublished, (moved, road, waiting) in product(_UNPUBLISHED, _UNDER_THE_RUN):
            with self.subTest(unpublished[0], moved=moved):
                self.setUp()
                self.assertEqual(
                    (
                        self._runs_to(unpublished[1], road, _roads.Writes({_NOTES: _KEPT})),
                        self.pinned()[_support.ANCHOR] == ANOTHER_COMMENT,
                    ),
                    ((waiting, None, False, _KEPT, 0), road is _WRITES_THE_ANCHOR),
                )

    def test_a_replacement_keeps_its_anchor(self) -> None:
        # Another road puts its own verdict in the request's place behind the
        # relabel, recording the very post this road anchored: the request is
        # not this road's to drop any more, so nobody is launched and the
        # pinned anchor is left naming that post, as the newer verdict records.
        decision = self.seeds()
        relabel = _world.AnotherRoadBehind(
            self, _SET_LABEL, partial(operator.eq, LABEL_FIXING), _replaces_the_request,
        )

        with patch.object(self.github, _SET_LABEL, relabel):
            ran = self.hands_over(decision)

        waiting = self.waiting()
        self.assertEqual(
            (ran.call_count, waiting[_ROUND], self.pinned().get(_support.ANCHOR)),
            (0, 1, waiting["anchor"]),
        )

    def _runs_to(self, answer, *roads) -> tuple:
        """Hand a fresh request to a developer answering `answer` while `roads` write; what that leaves.

        The round of the verdict waiting, or None for none; the park's reason
        and whether it waits on a human; the other road's field; and how many
        notices the issue thread gained.
        """
        posted = len(self.github.posted_comments)
        runs = _answers_while(self, answer, *roads)
        self.hands_over(self.seeds(), run_agent=runs, head_shas=_UNMOVED)
        pinned = self.pinned()
        return (
            (pinned.get(_world.RETURNED_VERDICT) or {}).get(_ROUND),
            pinned.get("park_reason"),
            bool(pinned.get("awaiting_human")),
            pinned.get(_NOTES),
            len(self.github.posted_comments) - posted,
        )


if __name__ == "__main__":
    unittest.main()
