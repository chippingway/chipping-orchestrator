# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Every barrier between work that ended and a push onto it.

The reconciliation that runs ahead of every stage ends in a PUSH -- the reading
it takes does, and the debt road beside it exists to make one -- while the
terminal that drains finished work runs inside the stage handler behind both.
So an ending reaching the orchestrator between the crash and the recovery is
the way work would otherwise land on a pull request nobody can merge.

Three facts answer it, and they are answered differently. The issue OBJECT and
the PULL REQUEST the record names are read at the reconciliation's door and the
tick is handed back: the handler's own terminal is next, and it marks the issue
`done` or `rejected` with the record, the branch and the debt left exactly as
they are. A pull request is the half the issue's flag cannot show -- a merge
leaves the issue open until a terminal reads it -- and it is read fail-OPEN
there, so a remote that would not answer costs a poll rather than stranding an
issue.

Everything the tick spends past that door -- a stage check, a checkout probe, a
remote read, a diff -- is time a poll on another worker can find the world
changing in. So the last barrier is inside the publication, immediately before
the push and nowhere else in it, and there the same pull-request reading fails
CLOSED: what falling through costs is a branch nothing can put back.
"""

from __future__ import annotations

import unittest
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.stages.implementing import (
    late_overflow as _overflow,
    late_publication as _publication,
    late_push as _late_push,
    late_records as _late_records,
)
from tests.support.fakes import FakeGitHubClient, FakePRRef, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    MEASURED_CANDIDATE_SHA,
    _issue_branch,
    _open_pr_for,
)
from tests.workflow.interleaving import _RacesPastTheStep, _RacesTheStep
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.fixing import (
    fixing_test_support as fixing,
    published_gate_support as support,
)
from tests.workflow.stages.fixing.test_late_dispatch import (
    ISSUE,
    PR_NUMBER,
    PUSH_BRANCH,
    _FrozenPairMixin,
)

_REPO_SLUG = _TEST_SPEC.slug

# What a pull request reads as once it is over, whichever way it ended, and
# the two labels an issue behind one lands on.
_CLOSED = "closed"
_MERGED = "merged"
_UNREADABLE = "unreadable"
_REJECTED = "rejected"
_DONE = "done"

# The fourth thing that can end in the barrier's window, beside the three a
# pull request can be in. Named here because it is raced the same way and
# refused the same way, and differs only in which reading can answer for it.
_A_LATCHED_CLOSE = "a latched close"

# The stage the fixing support does not name, since its own fixtures never
# sit on it.
_IMPLEMENTING = "workflow:implementing"

# The three stages that carry no PR-state arc of their own, and so reach a
# pull request somebody closed as an ordinary tick unless a terminal says
# otherwise. `in_review` and `fixing` drain one inline and are not here.
_SWEPT_STAGES = (_IMPLEMENTING, fixing.VALIDATING, fixing.DOCUMENTING)

# The debt a tick that died between the retirement and the push leaves: one
# commit owed a publication, and the head the pull request was standing on
# when it was approved. No generation beside it, which is what makes this the
# window the frozen pair cannot cover.
_OWED_PUBLICATION = MappingProxyType({
    support.KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
    support.KEY_APPROVED_LEASE: fixing.PR_HEAD_SHA,
    support.KEY_APPROVED_BASIS: support.GATE_READING,
})

# The step the gated publication takes last before its barrier, which is the
# window a pull request can end in without the gate above ever seeing it.
_REPINNED = "_repinned"

# The barrier's own terminal reading, which is a request and so a window of
# its own: a close landing while it is in flight is one only a latch read
# AFTER it can still answer.
_STILL_OPEN = "still_open"

# Every way a record can leave this barrier with no pull request to hold the
# push to. The payload is JSON, so a hand edit or an older write can leave any
# of these, and each reads absent through the fail-closed reader every
# identity here goes through -- which is what a barrier standing in front of a
# force-push may not mistake for having nothing to check. What such a record
# does to a whole run is `tests/git/publication/test_squash_switched_off.py`'s,
# on the one road that reaches this push holding its own pull request.
_UNUSABLE_RECORDS = MappingProxyType({
    "absent": None,
    "not positive": 0,
    "a flag": True,
    "not whole": 2.5,
    "no number at all": [],
})


def _owing(case, label: str = fixing.FIXING):
    """An issue whose only late record is a push an approval still owes.

    Seeded rather than reached through the frozen pair beside it, because the
    two are different windows: this one opens past the write that retired the
    generation, so there is no record left for the reading to be re-entered
    from and the approval is the whole of what says a push is owed.
    """
    github = FakeGitHubClient()
    issue = make_issue(ISSUE, label=label)
    github.add_issue(issue)
    github.seed_state(
        ISSUE,
        branch=_issue_branch(ISSUE),
        pr_number=PR_NUMBER,
        **_OWED_PUBLICATION,
    )
    _open_pr_for(
        github,
        issue_number=ISSUE,
        pr_number=PR_NUMBER,
        head=FakePRRef(sha=fixing.PR_HEAD_SHA),
    )
    return github, issue


# The two records this owner goes back for, which are the two windows a crash
# between the gate and the push can leave.
_RECOVERABLE = MappingProxyType({
    "a frozen pair": lambda case: case._frozen(),
    "a debt a crash left": _owing,
})


def _ended(github, *, merged: bool = False, unreadable: bool = False) -> None:
    """End this issue's pull request, which leaves the ISSUE itself open.

    Three shapes with two flags between them, and both matter: a merge and a
    plain close are different endings to a reader, and a pull request this
    host cannot read at all is the third state a push may not land on -- the
    one that says whether the reading behind the barrier fails open or closed.
    """
    if unreadable:
        github.pulls.pop(PR_NUMBER, None)
        return
    pull_request = github.get_pr(PR_NUMBER)
    pull_request.merged = merged
    pull_request.state = _CLOSED


# The two endings a pull request has, plus the reading that cannot say which:
# every state a push immediately behind it may not land on.
_ENDINGS = MappingProxyType({
    _MERGED: partial(_ended, merged=True),
    _CLOSED: _ended,
    _UNREADABLE: partial(_ended, unreadable=True),
})


def _closed_issue(github) -> None:
    """What a human closing the issue leaves on the tick's own snapshot."""
    github.add_issue(make_issue(ISSUE, label=fixing.FIXING, closed=True))


# Every way work can be over before the reconciliation opens, against every
# record it goes back for: one answer on all of them.
_FINISHED = MappingProxyType({
    f"{ended} over {record}": (over, owed)
    for ended, over in (
        ("the issue", _closed_issue),
        ("its pull request", _ENDINGS[_CLOSED]),
        ("a merge of it", _ENDINGS[_MERGED]),
    )
    for record, owed in _RECOVERABLE.items()
})


class TerminalWorkReconciliationTest(
    ObservedCloseCase, unittest.TestCase, _FrozenPairMixin,
):
    """What the reconciliation's door hands back, and what it hands back TO.

    Both roads out of that owner publish: a frozen pair is measured and
    pushed, and a debt is paid by a push of its own. Neither may happen on an
    issue somebody closed -- nor on a pull request somebody merged or closed,
    which the issue's own flag cannot show and which leaves the push nowhere
    to land. The gate below refuses to freeze an entry against one, so without
    the guard the road ends in `late_measurement_failed`: a human parked over
    a publication that is finished.

    Handing back is only half an answer, so the stages it hands back to are
    run here too. The terminal that drains finished work lives inside the
    handler, and a stage with no arc for a pull request somebody closed
    without merging simply carries on: on `implementing` the size gate
    measures the committed candidate again and pushes it -- opening a SECOND
    pull request, since the first is gone -- and on `validating` and
    `documenting` a reviewer or a docs agent is spawned over work a human has
    already rejected.
    """

    def setUp(self) -> None:
        self._fresh_process()

    def test_work_that_ended_publishes_nothing(self) -> None:
        # Every ending against both records, and one answer on all of them:
        # nothing pushed, and no park invented for a question no human has to
        # answer -- a `late_measurement_failed` mention is the wrong reply to
        # a publication that is simply finished.
        for described, (over, owed) in _FINISHED.items():
            with self.subTest(finished=described):
                github = owed(self)[0]
                over(github)

                mocks = self._route(github, github.get_issue(ISSUE))[1]

                mocks[PUSH_BRANCH].assert_not_called()
                self.assertIsNone(
                    github.pinned_data(ISSUE).get(fixing.PARK_REASON),
                )

    def test_polls_hold_each_record_for_the_terminal(self) -> None:
        # Handing the tick back costs nothing here, and it is the whole reason
        # the door reads rather than parks. But a poll is never the last one:
        # nothing here writes, so what the first hands back is exactly what
        # the second reads, and the generation, the receipt and the debt have
        # to survive however many fall between the ending and the cleanup.
        # Nothing is spent on the way either -- no park, no mention, no push
        # -- because a publication that is simply finished is not a question
        # a human has been asked twice. Behind them the stage's own terminal
        # drains the issue, with no agent rerun, off the record those polls
        # preserved.
        for described, owed in _RECOVERABLE.items():
            with self.subTest(record=described):
                github = owed(self)[0]
                _ended(github)
                recorded = dict(github.pinned_data(ISSUE))

                self._route(github, github.get_issue(ISSUE))
                mocks = self._route(github, github.get_issue(ISSUE))[1]

                mocks[PUSH_BRANCH].assert_not_called()
                self.assertEqual(dict(github.pinned_data(ISSUE)), recorded)
                self.assertEqual(github.posted_comments, [])

                mocks = self._route_to_the_stage(
                    github, github.get_issue(ISSUE),
                )

                mocks[fixing.RUN_AGENT].assert_not_called()
                self.assertIn((ISSUE, _REJECTED), github.label_history)

    def test_each_stage_finalizes_rather_than_running(self) -> None:
        for stage in _SWEPT_STAGES:
            with self.subTest(stage=stage):
                github, issue = _owing(self, stage)
                _ended(github)

                mocks = self._route_to_the_stage(github, issue)

                mocks[PUSH_BRANCH].assert_not_called()
                mocks[fixing.RUN_AGENT].assert_not_called()
                self.assertIn((ISSUE, _REJECTED), github.label_history)

    def test_a_merged_one_still_finalizes_as_done(self) -> None:
        # The other ending, so the arc added beside it is about the CLOSE
        # rather than about terminal pull requests having stopped working.
        github, issue = _owing(self, fixing.VALIDATING)
        _ended(github, merged=True)

        mocks = self._route_to_the_stage(github, issue)

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertIn((ISSUE, _DONE), github.label_history)

    def test_an_unreadable_one_is_still_reconciled(self) -> None:
        # The fail-OPEN half: a reading that did not come back says nothing
        # about whether the work is over, so the tick goes to the road that
        # takes its own reading and parks with the reason it fails for.
        # Answered the other way, every briefly unreachable issue would strand.
        github, issue = self._frozen()
        _ended(github, unreadable=True)

        mocks = self._route(github, issue)[1]

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(
            github.pinned_data(ISSUE)[fixing.PARK_REASON],
            support.PARK_MEASUREMENT_FAILED,
        )

    def test_an_open_one_is_still_reconciled(self) -> None:
        # The other side, so the guard is about the ending rather than about
        # pull requests: the same record over work that can still be joined is
        # measured and published before the stage runs.
        dispatched, mocks = self._route(*self._frozen())

        mocks[PUSH_BRANCH].assert_called_once()
        dispatched.assert_called_once()


class LatchedCloseReconciliationTest(
    ObservedCloseCase, unittest.TestCase, _FrozenPairMixin,
):
    """A close a later poll saw, answered against the latch instead.

    The object this tick holds still reads open, so handing the tick back
    would reach a terminal with nothing to finalize and a handler that spawns
    an agent. The push is refused instead, and what advances the issue is the
    cleanup pass every latched close is owed.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self._latch_close(_REPO_SLUG, ISSUE)

    def test_a_latched_close_pushes_nothing(self) -> None:
        for described, owed in _RECOVERABLE.items():
            with self.subTest(record=described):
                mocks = self._route(*owed(self))[1]

                mocks[PUSH_BRANCH].assert_not_called()

    def test_the_record_is_left_for_the_cleanup(self) -> None:
        # Nothing is relabelled, announced or dropped: the debt and the pair
        # the recovery would have spent are what the cleanup pass reads.
        github, issue = _owing(self)

        self._route(github, issue)

        self.assertEqual(
            github.pinned_data(ISSUE)[support.KEY_APPROVED_SHA],
            MEASURED_CANDIDATE_SHA,
        )
        self.assertEqual(github.label_history, [])


class EndedBeforeThePushTest(
    ObservedCloseCase, unittest.TestCase, support._SizeGateFixtureMixin,
):
    """The last barrier of all, immediately before the push itself.

    The gate refuses to ENTER a call on a pull request that is already over,
    so the only way one reaches the push is by ending in the window behind
    that reading -- the freeze, the whole gated measurement, and the repin.
    Its branch is still at the head this tick froze there, so the lease
    SUCCEEDS: the force-push lands and moves a merged pull request's branch
    back onto the commits it merged, which is the one effect nothing can undo.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.scenario = self._seed_fix_round()

    def test_everything_that_ended_refuses_the_push(self) -> None:
        # Every state a push may not land on, raced into the window the
        # barrier exists for -- the unreadable pull request included, since
        # this reading fails CLOSED where the same one at the reconciliation's
        # door falls through: there it costs a poll, and here a branch whose
        # pull request may already be merged. A close a poll LATCHED is the
        # same answer one field over and the only reading that can give it,
        # since the issue object this tick holds still reads open. All of
        # them are held the same way: nothing pushed, nothing relabelled,
        # nothing announced, and the record left for the cleanup it is owed.
        raced = dict(_ENDINGS)
        raced[_A_LATCHED_CLOSE] = lambda _github: self._latch_close(
            _REPO_SLUG, fixing.ISSUE,
        )

        for ending, over in raced.items():
            with self.subTest(ended=ending):
                self.setUp()

                self._assert_refused(self._raced(over))

    def test_one_still_open_publishes_as_ever(self) -> None:
        # The other side, so the barrier is about the ending rather than
        # about spending a request: nothing raced, and the push lands.
        self._assert_pushed_once(self._run_fix_round(self.scenario))

    def test_a_second_poll_holds_the_debt(self) -> None:
        # What a refusal here leaves is a DEBT -- the approval and its lease,
        # with the generation already retired by the write that approved the
        # candidate -- so the poll behind it comes in by the reconciliation's
        # road rather than the gate's. That road publishes too, and the
        # ending is still there, so it hands the tick straight back with the
        # debt exactly as it stands and spends no mention on the way. What
        # drains such an issue is the stage terminal the reconciliation cases
        # above hand back to, off this same record.
        self._raced(_ENDINGS[_CLOSED])
        owed = dict(self.scenario.github.pinned_data(fixing.ISSUE))

        mocks = self._poll(self.scenario)[1]

        self._assert_refused(mocks)
        self.assertEqual(
            dict(self.scenario.github.pinned_data(fixing.ISSUE)), owed,
        )

    def test_a_remote_that_answers_publishes(self) -> None:
        # The unreadable half over two polls, which is the one that says the
        # fail-CLOSED reading costs a poll rather than the work. Poll one
        # refuses and writes nothing about what it could not read; poll two
        # pays the debt it left with a leased push of the very commit that
        # was measured, and no developer is rerun for it -- nothing about the
        # candidate changed while the remote was away.
        self._raced(_ENDINGS[_UNREADABLE])
        _open_pr_for(
            self.scenario.github,
            issue_number=ISSUE,
            pr_number=PR_NUMBER,
            head=FakePRRef(sha=fixing.PR_HEAD_SHA),
        )

        mocks = self._poll(self.scenario)[1]

        self._assert_pushed_once(mocks)
        mocks[fixing.RUN_AGENT].assert_not_called()

    def _assert_refused(self, mocks) -> None:
        """Nothing pushed, and nothing handed on behind it."""
        self._assert_unpushed(mocks)
        self.assertEqual(self.scenario.github.label_history, [])

    def _raced(self, ending):
        """Run one fix round, ending the pull request just past the repin.

        Hung on the repin because that is the last step before the barrier:
        the gate has read the pull request by then and the push has not run,
        which is exactly the window a poll on another worker can end it in.
        """
        with patch.object(
            _late_push,
            _REPINNED,
            _RacesPastTheStep(
                _late_push._repinned,
                lambda: ending(self.scenario.github),
            ),
        ):
            return self._run_fix_round(self.scenario)


class BarrierReadingsTest(
    ObservedCloseCase, unittest.TestCase, support._SizeGateFixtureMixin,
):
    """What the barrier reads, and which of its readings gets the final word.

    Asked of the barrier itself as well as through a tick, because part of
    what it pins is an ORDER: both readings answer the same question on a
    whole run, so a case that only watched the push could not say which of
    them did.

    The record it reads them off is the other part. Every road that reaches
    this barrier publishes onto a pull request the remote already carries, so
    one that cannot NAME one -- a field that is gone, or one the comment
    carries and this build cannot read back -- is the record disagreeing with
    itself, and the fail-closed readers every identity here goes through turn
    the second into the first.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.scenario = self._seed_fix_round()

    def test_a_close_landing_in_the_read_is_answered(self) -> None:
        # The terminal reading is a REQUEST, so it is a window of its own: a
        # poll finding the issue closed while it is in flight is one a latch
        # read BEFORE it has already answered "no" to. The reading that costs
        # nothing is the one that gets the last word for exactly that reason.
        with patch.object(
            _overflow._PublicationReading,
            _STILL_OPEN,
            _RacesTheStep(
                _overflow._PublicationReading.still_open,
                lambda: self._latch_close(_REPO_SLUG, fixing.ISSUE),
            ),
        ):
            self.assertTrue(_publication._publication_ended(self._gate()))

    def test_a_live_publication_is_not(self) -> None:
        # The other side of the same call, so the order above is about the
        # window rather than about the barrier refusing everything it is asked.
        self.assertFalse(_publication._publication_ended(self._gate()))

    def test_an_unusable_record_refuses(self) -> None:
        # Neither shape leaves anything for the reading below to be about, so
        # both refuse. Read as "nothing to check" instead, the barrier skips
        # its reading and the force-push lands on whatever the branch's pull
        # request has become -- one somebody merged included, since its branch
        # is still exactly where this tick froze it and the lease succeeds.
        for described, recorded in _UNUSABLE_RECORDS.items():
            with self.subTest(pr_number=described):
                self.scenario = self._seed_fix_round(pr_number=recorded)

                self.assertTrue(_publication._publication_ended(self._gate()))

    def _gate(self):
        """The subject the barrier is asked about, as the push owner has it."""
        github = self.scenario.github
        return _late_records._gate(
            github, _TEST_SPEC, self.scenario.issue,
            github.read_pinned_state(self.scenario.issue),
            fixing.TEMP_ROOT,
        )


if __name__ == "__main__":
    unittest.main()
