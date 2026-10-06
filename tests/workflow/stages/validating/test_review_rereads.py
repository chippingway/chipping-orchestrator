# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a guarded reread of the pinned comment keeps where another road wrote beside this tick.

The tick reads the comment, resolves its reviewer's subject over that reading,
and stages its own moves; another road's write lands on the comment before
the reread. Wherever the reread carries anything -- a persisted verdict's
recheck over records that stand, the return's own reading over records that
moved -- a field both roads moved keeps both moves where they add up or only
advance: the runs each folded into the usage totals, the cost tags beside
them, each thread read as far as either read it. The ledger of the
orchestrator's own comments is merged, within its bound, and an entry naming
no comment -- or a ledger that is no list -- is dropped from either side
rather than read as one or left for the next scan of the ledger to fail on. Every other field both moved
-- and one a hand edit spelled as no writer does -- is one road's to say. The
reread hands back the comment as it found it, which is what a later reading
of the same run is measured against.

The reading a subject is bound to is laid over the state in hand the same way,
measured from the comment as the tick read it, save for a field the comment
already holds as the tick does, which is not counted a second time.

The return's own write behind a reread is a guarded commit over a fresh
reading, so another road writing between the two is never written back over:
its folds, its reading of either thread, and its posts are kept beside the
return's own, while a record the return was decided on -- a later report, a
repoint, another round's verdict, or any of them spelled anew, `null` for none
or `true` for `1` -- a field the tick moved too, a comment that no longer reads
as the one read, or one with no room left refuses it with nothing written. A
commit GitHub took and never confirmed keeps the tick's state out of every
whole-state write behind it.
"""
from __future__ import annotations

import itertools
import unittest
from types import MappingProxyType, SimpleNamespace
from typing import NamedTuple

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_records as _records,
    review_subjects as _review_subjects,
)
from orchestrator.workflow.stages.implementing import resume_batch as _resume_batch
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_comment as _review_comment,
    review_verdicts as _verdicts,
    review_writes as _review_writes,
)
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.stages.validating import (
    review_park_test_support as _parked,
    review_write_test_support as _roads,
)

# The issue a race is run on, over the in-memory client.
RACED_ISSUE = 1_818

# The revision of the report the reviewer was handed, and of the one another
# road settled over it.
HANDED = 1

SETTLED = 2

# The member a report record names its revision by.
REVISION = "revision"

# The fields both roads move, as the comment spells them.
AGENT_RUNS = "issue_agent_runs"

TOKENS = "issue_total_tokens"

COST = "issue_total_cost_usd"

COST_SOURCES = "issue_cost_sources"

ISSUE_THREAD_MARK = "last_action_comment_id"

PR_THREAD_MARK = "pr_last_comment_id"

LEDGER = "orchestrator_comment_ids"

REVIEW_ROUND = "review_round"

# The cost tags a folded run can carry.
REPORTED = "reported"

ESTIMATED = "estimated"

UNPRICED = "unknown-price"

# What the comment carried when the subject was resolved over it: the report
# handed over, the issue's usage totals and cost tags, both threads read
# through, the ledger of the orchestrator's own comments, and the round.
_RESOLVED = MappingProxyType({
    _records.CURRENT_REPORT: {REVISION: HANDED},
    AGENT_RUNS: 3,
    TOKENS: 300,
    COST: 3.0,
    COST_SOURCES: [REPORTED],
    ISSUE_THREAD_MARK: 100,
    PR_THREAD_MARK: 200,
    LEDGER: [100],
    REVIEW_ROUND: 1,
})

# Each road's moves over that reading, and the comment it posted: this tick's
# run folded, the pull-request thread read furthest, and the round moved on;
# another road's run folded with a cost nobody priced, the issue thread read
# furthest, and a round of its own.
_OURS = (
    MappingProxyType({
        AGENT_RUNS: 4,
        TOKENS: 320,
        COST: 3.5,
        COST_SOURCES: [ESTIMATED, REPORTED],
        ISSUE_THREAD_MARK: 110,
        PR_THREAD_MARK: 215,
        REVIEW_ROUND: 2,
    }),
    110,
)

_THEIRS = (
    MappingProxyType({
        AGENT_RUNS: 4,
        TOKENS: 350,
        COST: 3.25,
        COST_SOURCES: [REPORTED, UNPRICED],
        ISSUE_THREAD_MARK: 120,
        PR_THREAD_MARK: 205,
        REVIEW_ROUND: 3,
    }),
    120,
)

# Every move both roads made that is kept whole: the runs each folded added
# up, the cost tags joined, each thread read as far as either read it, and
# both roads' comments on the ledger.
_BOTH_KEPT = MappingProxyType({
    AGENT_RUNS: 5,
    TOKENS: 370,
    COST: 3.75,
    COST_SOURCES: [ESTIMATED, REPORTED, UNPRICED],
    ISSUE_THREAD_MARK: 120,
    PR_THREAD_MARK: 215,
    LEDGER: [100, 110, 120],
})


# The ledger's bound, and the comment each road posted once it was full.
_CAP = _comments._ORCH_COMMENT_ID_CAP

_OUR_POST_AT_THE_CAP = (MappingProxyType({}), _CAP + 1)

_THEIR_POST_AT_THE_CAP = _CAP + 2


class _Ledger(NamedTuple):
    """A ledger the comment carries, the comment each road posts to it, and the newest ids a merge of both leaves."""

    name: str
    carried: tuple
    ours: tuple
    theirs: int | None
    newest: range


# A full ledger each road's own post evicted the oldest id from; and one
# already past its bound, with an id twice -- an older binary's, a hand edit --
# that neither road posts to, so the other reading adds no id.
_LEDGERS = (
    _Ledger(
        "a full ledger",
        tuple(range(1, _CAP + 1)),
        _OUR_POST_AT_THE_CAP,
        _THEIR_POST_AT_THE_CAP,
        range(3, _CAP + 3),
    ),
    _Ledger(
        "a ledger past its bound",
        (*range(1, _CAP + 2), _CAP),
        (MappingProxyType({}), None),
        None,
        range(2, _CAP + 2),
    ),
)


class _Reading(NamedTuple):
    """One reread that carries anything, what the other road wrote beside its moves, and what it answers."""

    name: str
    persisted: bool
    # The report records the other road left: none of its own, or a later
    # settlement.
    theirs: MappingProxyType
    stood: bool
    # Whose round the reread keeps: this tick's, or the other road's.
    kept_round: int


# A persisted verdict's recheck, or the return's own reading, over records
# that stand keeps this tick's round; the return's own reading over a later
# report the other road settled keeps that road's with the report.
_READINGS = (
    _Reading("a persisted verdict's standing records", True, MappingProxyType({}), True, 2),
    _Reading("the return's standing records", False, MappingProxyType({}), True, 2),
    _Reading(
        "the return over a later settlement",
        False,
        MappingProxyType({_records.CURRENT_REPORT: {REVISION: SETTLED}}),
        False,
        3,
    ),
)


# Values another road's write left spelled as no writer spells them -- hand
# edits: a word, or a flag, for a total; a fraction for a count of runs; a
# word for the list of cost tags; a flag for a comment-id watermark.
_HAND_EDITS = (
    (TOKENS, "lots"),
    (TOKENS, True),
    (AGENT_RUNS, 4.5),
    (COST_SOURCES, UNPRICED),
    (PR_THREAD_MARK, True),
)

# Entries on the comment's ledger that name no comment: one it already
# carried, and one another road's write adds beside the comment it posted.
_NAMES_NO_COMMENT = ("bad-id", True)

_CARRIED_LEDGER = (_NAMES_NO_COMMENT[0], 100)

_THEIR_LEDGER = (*_CARRIED_LEDGER, _NAMES_NO_COMMENT[1])

# What the merge leaves: the comment this tick's own reading held, its own
# post, and the one the other road posted -- no entry naming no comment, from
# either side.
_MERGED_LEDGER = (100, 110, 120)


# What this tick wrote earlier in the tick than the reading a subject is bound
# to, what it staged behind that write, and what another road moved and posted
# after it: a run folded with a cost nobody priced, the issue thread read
# furthest, and a round of its own.
_WRITTEN_EARLIER = MappingProxyType({TOKENS: 320, PR_THREAD_MARK: 215})

_STAGED = MappingProxyType({ISSUE_THREAD_MARK: 110, REVIEW_ROUND: 2})

_THEIRS_BEFORE_THE_BINDING = (
    MappingProxyType({
        AGENT_RUNS: 4,
        COST: 3.25,
        COST_SOURCES: [REPORTED, UNPRICED],
        ISSUE_THREAD_MARK: 120,
        REVIEW_ROUND: 3,
    }),
    120,
)

# What the binding leaves: the other road's run and its cost tag, the issue
# thread read as far as either read it, and its notice as the orchestrator's;
# the total and the mark this tick wrote once each; and the round this tick's.
_BOUND = MappingProxyType({
    AGENT_RUNS: 4,
    TOKENS: 320,
    COST: 3.25,
    COST_SOURCES: [REPORTED, UNPRICED],
    ISSUE_THREAD_MARK: 120,
    PR_THREAD_MARK: 215,
    LEDGER: [100, 120],
    REVIEW_ROUND: 2,
    _records.CURRENT_REPORT: _RESOLVED[_records.CURRENT_REPORT],
})

# The subject a binding is resolved for, which the binding itself never reads.
_SUBJECT = _review_subjects.ReviewSubject(
    pr_number=None, commit="c0ffee", requirements_revision="baseline", report=None,
)


def _moves(state: PinnedState, fields: MappingProxyType, posted: int | None) -> None:
    """One road's moves on `state`: `fields` written, and any comment `posted` recorded as the orchestrator's."""
    state.data.update(fields)
    if posted is not None:
        _comments._track_orchestrator_comment(state, posted)


class ConcurrentWritesTest(unittest.TestCase):
    """What a guarded reread keeps where this tick and another road both moved a field."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(RACED_ISSUE)
        self.github.add_issue(self.issue)

    def test_both_moves_are_kept_either_way(self) -> None:
        # Kept whole, neither road's fold of a run is written away by the
        # other's, no comment either read is handed to the next reader as new,
        # and no comment either posted is read back as a human's. A field that
        # neither adds up nor advances -- the round -- is one road's to say.
        # The reread hands back the comment exactly as the other road left it.
        for reading in _READINGS:
            with self.subTest(reading.name):
                theirs = ({**_THEIRS[0], **reading.theirs}, _THEIRS[1])

                reread, carried = self._raced(_RESOLVED, theirs, persisted=reading.persisted)

                self.assertEqual(
                    (reread.stood, reread.read), (reading.stood, self.github.pinned_data(RACED_ISSUE)),
                )
                self.assertEqual(
                    {field: carried.get(field) for field in (*_BOTH_KEPT, REVIEW_ROUND)},
                    {**_BOTH_KEPT, REVIEW_ROUND: reading.kept_round},
                )
                self.assertEqual(
                    carried[_records.CURRENT_REPORT], {**_RESOLVED, **reading.theirs}[_records.CURRENT_REPORT],
                )

    def test_a_value_no_writer_records_is_one_roads(self) -> None:
        # A value another road left as no writer spells it -- a hand edit --
        # cannot be added to, joined, or advanced past: like any other field
        # both moved, it is this tick's over records that stand, and the other
        # road's where they moved.
        for reading, (field, edited) in itertools.product(_READINGS, _HAND_EDITS):
            with self.subTest(reading.name, field=field, edited=edited):
                self.setUp()

                carried = self._raced(
                    _RESOLVED,
                    ({**_THEIRS[0], **reading.theirs, field: edited}, _THEIRS[1]),
                    persisted=reading.persisted,
                )[1]

                kept = _OURS[0][field] if reading.stood else edited
                self.assertEqual(carried[field], kept)

    def test_a_ledger_merges_to_the_newest_ids(self) -> None:
        # Each road's own post evicted the oldest id from a full ledger: the
        # merge keeps the newest the bound holds from both, and does not put
        # back the id both evicted. A ledger already past its bound is cut to
        # the newest the bound holds, each once, even where the other reading
        # adds no id, so the write behind the reread is bounded.
        for ledger, reading in itertools.product(_LEDGERS, _READINGS):
            with self.subTest(ledger.name, reading=reading.name):
                self.setUp()
                resolved = {**_RESOLVED, LEDGER: list(ledger.carried)}
                theirs = (reading.theirs, ledger.theirs)

                carried = self._raced(
                    resolved, theirs, persisted=reading.persisted, ours=ledger.ours,
                )[1]

                self.assertEqual(carried[LEDGER], list(ledger.newest))

    def test_an_entry_naming_no_comment_is_left_out(self) -> None:
        # The comment already carries an entry naming no comment, and another
        # road's write adds another beside the one it posted: the reread still
        # answers, merges only the comment that road posted, and drops the
        # entry this tick's own reading held too -- so the next scan of the
        # ledger reads it rather than failing on it.
        carrying = {**_RESOLVED, LEDGER: list(_CARRIED_LEDGER)}
        for reading in _READINGS:
            with self.subTest(reading.name):
                self.setUp()
                theirs = (
                    {**_THEIRS[0], **reading.theirs, LEDGER: list(_THEIR_LEDGER)},
                    _THEIRS[1],
                )

                reread, carried = self._raced(carrying, theirs, persisted=reading.persisted)

                self.assertIs(reread.stood, reading.stood)
                self.assertEqual(carried[LEDGER], list(_MERGED_LEDGER))
                self.assertEqual(_comments._orchestrator_ids(PinnedState(state_data=carried)), set(_MERGED_LEDGER))

    def test_a_ledger_that_is_no_list_is_dropped(self) -> None:
        # The comment carries a ledger no writer spells -- a hand edit that is
        # no list at all -- and neither road posts: the reread drops it rather
        # than leave it for the next scan of the ledger to fail on.
        spoiled = {**_RESOLVED, LEDGER: "not a ledger"}
        for reading in _READINGS:
            with self.subTest(reading.name):
                self.setUp()

                theirs = ({**_THEIRS[0], **reading.theirs}, None)

                carried = self._raced(
                    spoiled, theirs, persisted=reading.persisted, ours=(_OURS[0], None),
                )[1]

                self.assertNotIn(LEDGER, carried)
                self.assertEqual(_comments._orchestrator_ids(PinnedState(state_data=carried)), set())

    def _raced(self, resolved, theirs, *, persisted: bool, ours=_OURS):
        """The reread's answer (`review_comment._Reread`, or None), and the state it leaves, once both moved."""
        self.github.seed_state(self.issue, **resolved)
        state = self.github.read_pinned_state(self.issue)
        resolved_over = dict(state.data)
        _moves(state, *ours)
        other = self.github.read_pinned_state(self.issue)
        _moves(other, *theirs)
        self.github.write_pinned_state(self.issue, other)
        reread = _review_comment._records_stand(self.github, self.issue, state, resolved_over, persisted=persisted)
        return reread, state.data


class BindingTest(unittest.TestCase):
    """What the reading a subject is bound to lays over the state in hand, measured from the tick's own read."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(RACED_ISSUE)
        self.github.add_issue(self.issue)

    def test_each_move_is_kept_once(self) -> None:
        # This tick wrote a total and the pull-request thread mark earlier in
        # the tick and staged its round and the issue thread read through
        # behind that write; another road then folded a run, moved the round,
        # and read the issue thread through a notice it posted. The binding
        # carries that road's moves and keeps the thread read as far as either
        # read it, while the round stays this tick's to say and what the
        # comment already holds as this tick does is not counted again.
        state, read = self._written_earlier()
        other = self.github.read_pinned_state(self.issue)
        _moves(other, *_THEIRS_BEFORE_THE_BINDING)
        self.github.write_pinned_state(self.issue, other)

        resolved_over = _review_comment._resolved_over(self.github, self.issue, state)
        _review_comment._ResolvedSubject(_SUBJECT, resolved_over).lays_over(state, read)

        kept = {field: state.get(field) for field in _BOUND}
        self.assertEqual(kept, dict(_BOUND))

    def _written_earlier(self) -> tuple[PinnedState, dict]:
        """The state this tick holds once it wrote `_WRITTEN_EARLIER` and staged `_STAGED`; and the comment it read."""
        self.github.seed_state(self.issue, **_RESOLVED)
        state = self.github.read_pinned_state(self.issue)
        read = dict(state.data)
        _moves(state, _WRITTEN_EARLIER, None)
        self.github.write_pinned_state(self.issue, state)
        _moves(state, _STAGED, None)
        return state, read


# The pull request the return was resolved on, and one another road points the
# issue at instead.
PR = 1_819

OTHER_PR = PR + 1

# What the comment carried when the return's reread read it.
_RETURNED_OVER = MappingProxyType({**_RESOLVED, "pr_number": PR})

# This tick's own moves of the return -- its run folded, the pull-request
# thread read furthest, the round moved on -- and another road's behind its
# reread that the return's commit keeps beside them: a run folded with a cost
# nobody priced, the issue thread read furthest, and a notice it posted.
_RETURN_MOVES = (MappingProxyType({**_OURS[0], LEDGER: [100]}), None)

_INDEPENDENT = _roads.Writes({
    **{field: written for field, written in _THEIRS[0].items() if field != REVIEW_ROUND},
    LEDGER: [100, _THEIRS[1]],
})

# A reviewer run handed `_SUBJECT` that left no verdict, as far as its return
# records it: no usage, and the session it ran as.
_LEFT_NO_VERDICT = _models._ReviewerRun(
    wt=None,
    round_n=1,
    pr_number=PR,
    agent_result=SimpleNamespace(usage=None, session_id="rev-sess"),
    delivery=None,
    subject=_SUBJECT,
    resolved_over={},
)

# What the return's commit leaves of both: every move kept whole, as a reread
# keeps them, and the round this tick's.
_COMMITTED = MappingProxyType({**_BOTH_KEPT, LEDGER: [100, 120], REVIEW_ROUND: 2})


# Another road's write behind the return's reread that its commit may not land
# over: a record the return was decided on moved -- a later report settled,
# the issue pointed at another pull request, another round's verdict persisted
# -- or spelled anew, a verdict `null` where none was and the report's revision
# `true` where it was `1`; the round, which this tick moved too; and the comment
# itself unparsed, replaced, or filled to its limit.
_REFUSING = (
    ("a later report", _roads.Writes({_records.CURRENT_REPORT: {REVISION: SETTLED}})),
    ("a repointed pull request", _roads.Writes({"pr_number": OTHER_PR})),
    ("another round's verdict", _roads.Writes({_verdicts.RETURNED_VERDICT: {"round": 3}})),
    ("a verdict written null", _roads.Writes({_verdicts.RETURNED_VERDICT: None})),
    ("the report's revision spelled true", _roads.Writes({_records.CURRENT_REPORT: {REVISION: True}})),
    ("the round this tick moved", _roads.Writes({REVIEW_ROUND: 3})),
    ("an unparsed comment", _roads.unparses),
    ("a replaced comment", _roads.repins),
    ("a full comment", lambda case: _parked.fills_to(case, 0)),
)


class ReturnCommitTest(unittest.TestCase):
    """What the return's commit lands where another road wrote behind the reread it was decided on."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(RACED_ISSUE)
        self.github.add_issue(self.issue)

    def test_independent_moves_are_kept(self) -> None:
        # Another road folds a run, reads the issue thread further, and posts
        # a notice once the reread is taken: the commit lays the return over
        # that, adding up both runs, joining both cost tags, keeping each
        # thread read as far as either read it and both roads' comments, and
        # the state then reads as the comment does.
        state = self._reread()
        _INDEPENDENT(self)

        landed = _review_writes.lands(self.github, self.issue, state, _review_writes.RETURN)

        pinned = self.github.pinned_data(RACED_ISSUE)
        self.assertTrue(landed)
        self.assertEqual(
            {field: pinned.get(field) for field in _COMMITTED}, dict(_COMMITTED),
        )
        self.assertEqual((state.data, state.withheld), (pinned, False))

    def test_a_move_it_decided_on_refuses_it(self) -> None:
        # Nothing is written over what the other road left, and the state is
        # kept out of every whole-state write behind the refusal.
        for name, road in _REFUSING:
            with self.subTest(name):
                self.setUp()
                state = self._reread()
                road(self)
                left = self._written()

                landed = _review_writes.lands(self.github, self.issue, state, _review_writes.RETURN)
                self.github.write_pinned_state(self.issue, state)

                self.assertEqual(
                    (landed, state.withheld, self._written()), (False, True, left),
                )

    def test_a_lost_response_withholds_the_state(self) -> None:
        # The commit lands and its response is lost: the comment carries the
        # return, but nothing behind the commit may act on it, and no
        # whole-state write puts the tick's state back over the comment.
        state = self._reread()
        self.github.pinned_failures.lost.add(RACED_ISSUE)

        landed = _review_writes.lands(self.github, self.issue, state, _review_writes.RETURN)
        written = self._written()
        self.github.write_pinned_state(self.issue, state)

        self.assertEqual(
            (landed, state.withheld, self._written()), (False, True, written),
        )
        self.assertEqual(written[0][TOKENS], _OURS[0][TOKENS])

    def test_a_full_comment_posts_no_park(self) -> None:
        # A reviewer that left no verdict parks, and the comment has no room
        # for the park beside the run's records: the park's record is
        # prepared before its notice, so no notice is posted and nothing is
        # written over the comment.
        state = self._reread()
        _parked.fills_to(self, 0)
        left = self._written()
        posted = []

        _review_writes.parks_the_return(
            self.github, self.issue, state, _LEFT_NO_VERDICT, ("reviewer_timeout", lambda: posted.append(True)),
        )

        self.assertEqual((posted, self._written()), ([], left))

    def _written(self) -> tuple:
        """What the pinned comment carries, and how many writes it has taken."""
        return self.github.pinned_data(RACED_ISSUE), self.github.write_state_calls

    def _reread(self) -> PinnedState:
        """The state this tick holds once it staged the return's moves and read the comment again behind them."""
        self.github.seed_state(self.issue, **_RETURNED_OVER)
        state = self.github.read_pinned_state(issue=self.issue)
        resolved_over = dict(state.data)
        _moves(state, *_RETURN_MOVES)
        _review_comment._records_stand(self.github, self.issue, state, resolved_over, persisted=True)
        return state


class UnreadReplyTest(unittest.TestCase):
    """A human reply nobody read yet is still delivered by the scan behind a reread's write.

    Over a real thread: this tick's reading delivered a reply and marks the
    thread read through it; another road, meanwhile, read the thread through a
    notice of its own and posted a second one after that reply, recorded as
    the orchestrator's without moving any mark; and a human replies after
    both. The reread's write keeps the mark that went further -- this tick's
    -- and both roads' posts as the orchestrator's, so the reply batch a later
    tick freezes over the pinned comment delivers the unread reply, and
    neither the one this tick delivered nor either road's notice.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(RACED_ISSUE)
        self.github.add_issue(self.issue)

    def test_the_unread_reply_is_delivered(self) -> None:
        for reading in _READINGS:
            with self.subTest(reading.name):
                self.setUp()
                unread = self._raced_on_the_thread(reading)

                batch = _resume_batch._freeze(
                    self.github, self.issue, self.github.read_pinned_state(self.issue),
                )

                self.assertEqual([reply.id for reply in batch.comments], [unread])

    def _raced_on_the_thread(self, reading: _Reading) -> int:
        """Both roads' moves on the thread, then the reread under `reading` and its write; the unread reply's id."""
        self.github.seed_state(self.issue, **{
            **_RESOLVED, ISSUE_THREAD_MARK: self._replied("A question this issue already answered."), LEDGER: [],
        })
        state = self.github.read_pinned_state(self.issue)
        resolved_over = dict(state.data)
        read_through = self.github.comment(self.issue, "Another road's notice, read through.").id
        state.set(ISSUE_THREAD_MARK, self._replied("A reply this tick delivered."))
        other = self.github.read_pinned_state(self.issue)
        _moves(
            other,
            {**reading.theirs, ISSUE_THREAD_MARK: read_through, LEDGER: [read_through]},
            self.github.comment(self.issue, "Another road's later notice.").id,
        )
        self.github.write_pinned_state(self.issue, other)
        unread = self._replied("A reply nobody has read yet.")
        _review_comment._records_stand(self.github, self.issue, state, resolved_over, persisted=reading.persisted)
        self.github.write_pinned_state(self.issue, state)
        return unread

    def _replied(self, body: str) -> int:
        """One trusted human reply, above everything the thread holds; its id."""
        reply = FakeComment(
            id=self.github._next_comment_id(self.issue), body=body, user=FakeUser("alice"),
        )
        self.issue.comments.append(reply)
        return reply.id


if __name__ == "__main__":
    unittest.main()
