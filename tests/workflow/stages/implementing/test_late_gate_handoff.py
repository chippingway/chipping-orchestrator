# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The commit an approval owes a publication, and the checkout that carries it.

Between the write that approves a candidate and the push that publishes it,
`late_approved_sha` is the only thing on the issue naming the work: the
retirement a small candidate earns and the exemption a `single` verdict
records both drop the generation that used to name it. So the commit is proved
before anything runs, and the two ways it can fail to be there -- a checkout
that moved off it, and a host that never had it -- reach the same park and the
same wordless recovery.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit, MeasurementFailure
from orchestrator.workflow.stages.implementing import (
    late_parks as _parks,
)
from tests.support.fakes import FakePRRef
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    LABEL_VALIDATING,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
    _agent,
    _authorized_exemption,
)
from tests.workflow.stages.implementing import late_gate_test_support as support

_DECOMPOSING = (support.GATE_ISSUE_NUMBER, LABEL_DECOMPOSING)
_CANDIDATE_MOVED = "late_candidate_moved"
_KEY_APPROVED_SHA = "late_approved_sha"
_KEY_APPROVED_BASIS = "late_approved_basis"
_MOVED_SHA = "e" * SHA_LENGTH
# The session a resume continues, seeded so a resumed run is the pinned one
# rather than a fresh spawn.
_DEV_SESSION = "sess-1"
_DECOMPOSE = "DECOMPOSE"
_KEY_PR_NUMBER = "pr_number"
_KEY_PUBLISHED_SHA = "implementing_published_sha"
# What the fake opens when a publication reaches it.
_OPENED_PR_NUMBER = 1
# The reply a human writes to make the developer change the work, and what a
# resumed run says when it has.
_GUIDANCE = "drop the generated fixtures from this"
_FINISHED = "done"
# What a resumed run says when it answered instead of building.
_ASKED = "which half of this did you mean?"

# A host the approved commit never reached: the object is not in the store,
# and the checkout the rebuild left is standing on the base it was restored
# from.
_MISSING_OBJECT = MappingProxyType({
    "candidate_commit": FrozenCommit(sha=_MOVED_SHA),
    "recorded_commit": FrozenCommit(
        failure=MeasurementFailure.CANDIDATE_ABSENT,
    ),
})

# The same host, whose checkout was reset rather than rebuilt: the object is
# still in the store the worktree shares, and the branch is standing somewhere
# else entirely.
_CHECKOUT_ELSEWHERE = MappingProxyType({
    "candidate_commit": FrozenCommit(sha=_MOVED_SHA),
})

# Both ways the approved commit can fail to be what the checkout is on, named
# as the park has to tell them apart.
_WITHOUT_THE_COMMIT = (
    ("the object is gone", _MISSING_OBJECT),
    ("the object is here", _CHECKOUT_ELSEWHERE),
)


class UnpublishedCommitTest(support._GateCase, unittest.TestCase):
    """A commit an approval owes a publication is proved before anything runs.

    Every approval opens the same window. The write that lets a candidate
    through drops the record that named it -- the retirement a small candidate
    earns, and the exemption a `single` verdict is settled by -- and the push
    it licenses comes after that write. A tick that dies in between leaves
    committed work on the branch and nothing on the issue waiting for
    anything, so the next one runs as an ordinary tick: on a replacement host
    the checkout is rebuilt from the base or the plan pull request, and the
    head it lands on is what would be published or handed to a second
    developer.
    """

    def test_a_retirement_names_the_commit_it_owes(self) -> None:
        # Durable in the same write that ends the generation, because that
        # write is what takes the last other name for the commit off the
        # issue. Read one step past the PUSH, which is the effect the record
        # is protecting: a tick that dies there has to come back to a comment
        # that still says which commit is owed one.
        recorded = support._RecordAtHandoff(self.github, support.FIND_OPEN_PR)

        with recorded.held():
            self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self.assertEqual(
            recorded.pinned[_KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertNotIn(support.KEY_CANDIDATE_SHA, recorded.pinned)

    def test_it_says_the_reading_is_behind_it(self) -> None:
        # The count came back at or below the ceiling, so nobody's permission
        # was involved -- which is what makes the tick after a crash spending
        # this approval a repeat of a decision rather than a bypass of one.
        recorded = support._RecordAtHandoff(self.github, support.FIND_OPEN_PR)

        with recorded.held():
            self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self.assertEqual(
            recorded.pinned[_KEY_APPROVED_BASIS],
            str(_parks.LateApprovalBasis.READING),
        )

    def test_the_publication_spends_it(self) -> None:
        self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self.assertIsNone(self._pinned()[_KEY_APPROVED_SHA])

    def test_it_is_spent_before_the_relabel(self) -> None:
        # The crash boundary the debt cannot outlive. Past the label the issue
        # belongs to `validating` and implementing never runs on it again, so
        # an approval still standing there is one nothing will ever spend --
        # and it goes on freezing the branch out of the base refresh for the
        # rest of the issue's life.
        recorded = support._RecordAtHandoff(self.github)

        with recorded.held():
            self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self.assertIsNone(recorded.pinned[_KEY_APPROVED_SHA])
        self.assertEqual(recorded.pinned[_KEY_PR_NUMBER], _OPENED_PR_NUMBER)

    def test_a_checkout_without_it_parks(self) -> None:
        # With no commits ahead of base there is nothing for the shortcut to
        # publish, so what the proof stops here is the SPAWN -- a second
        # developer over an implementation that is already written. Holding
        # the object proves only that the store was never pruned, and the
        # store outlives the branch: a checkout reset on the very host that
        # made the commit still has it sitting there.
        for checkout, seeded in _WITHOUT_THE_COMMIT:
            with self.subTest(checkout=checkout):
                self.setUp()
                self._seed(**{_KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA})

                mocks = self._run_gate(has_new_commits=False, **seeded)

                self._assert_no_agent(mocks)
                self._assert_unmeasured(mocks)
                self._assert_held(mocks)
                self._assert_waiting_for_the_checkout()

    def test_a_new_host_parks_for_an_accepted_commit(self) -> None:
        # After a `single` verdict the generation is gone, so the exemption
        # and the commit it owes a publication for are the only records left.
        # Without the second one nothing here would tell the accepted
        # implementation from whatever the rebuild put on the branch.
        self._seed(**{
            **_authorized_exemption(),
            _KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
        })

        mocks = self._run_gate(**_MISSING_OBJECT)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_waiting_for_the_checkout()

    def _assert_waiting_for_the_checkout(self) -> None:
        """Parked on the one refusal a human answers with a worktree."""
        pinned = self._pinned()
        self.assertTrue(pinned[support.AWAITING_HUMAN])
        self.assertEqual(pinned[support.PARK_REASON], _CANDIDATE_MOVED)
        self.assertIn(
            MEASURED_CANDIDATE_SHA, self.github.posted_comments[-1][1],
        )


class ApprovedCommitPublicationTest(support._GateCase, unittest.TestCase):
    """What a checkout standing on the approved commit buys: that commit.

    The approval is this gate's own verdict about one object id, and the
    write that made it dropped the record naming that commit. So the tick it
    comes back on owns exactly one job -- publish it -- and every question the
    ordinary flow would ask instead is a question about something else: the
    ceiling against a base that has moved since, whether the branch reads as
    ahead of that base, and what a fresh developer would write.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**{_KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA})

    def test_it_publishes_without_measuring_again(self) -> None:
        # A count seeded well past the ceiling is never taken: re-deciding a
        # settled question is how work a human already adjudicated is routed
        # back into adjudication.
        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_published(mocks)
        self.assertNotIn(_DECOMPOSING, self.github.label_history)

    def test_the_switch_off_still_names_it(self) -> None:
        # `DECOMPOSE=off` keeps NEW candidates out of the gate, and an issue
        # that owes a push is not one. Bypassing there would hand the
        # publication a candidate this gate never looked at while the record
        # beside it names a different commit as the one owed a push.
        with patch.object(config, _DECOMPOSE, False):
            mocks = self._run_gate()

        self._assert_unmeasured(mocks)
        self.assertEqual(
            mocks[support.PUSH_BRANCH].call_args.kwargs["revision"],
            MEASURED_CANDIDATE_SHA,
        )

    def test_a_branch_reading_empty_still_publishes(self) -> None:
        # "Is there work to publish" is answered downstream by asking whether
        # the branch is ahead of base, and a base that has since absorbed the
        # commit -- or a probe that could not answer -- reads as an issue with
        # nothing on it. The record names the commit outright, so no heuristic
        # is consulted and no second developer is bought.
        mocks = self._run_gate(has_new_commits=False)

        self._assert_no_agent(mocks)
        self._assert_published(mocks)
        self.assertIn(
            (support.GATE_ISSUE_NUMBER, LABEL_VALIDATING),
            self.github.label_history,
        )

    def test_an_accepted_commit_goes_the_same_way(self) -> None:
        # The `single` verdict's own window: the exemption and the approval
        # are written together, and either is enough for the commit to be the
        # one this tick publishes.
        self._seed(**{
            **_authorized_exemption(),
            _KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
        })

        mocks = self._run_gate()

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_published(mocks)


class _RelabelRefused(RuntimeError):
    """What a `set_workflow_label` GitHub would not accept raises."""


class _RefusedRelabel:
    """A client whose handoff to `validating` does not land.

    Everything else about the publication happens: the branch is pushed, the
    pull request is opened, and the pinned write ahead of the label lands. The
    label is the one effect that does not, which is the whole of the window
    this stands in for.
    """

    def __init__(self, github) -> None:
        self._github = github
        self._set_label = github.set_workflow_label

    def __call__(self, issue, label, **options):
        if str(label) == LABEL_VALIDATING:
            raise _RelabelRefused(str(label))
        return self._set_label(issue, label, **options)


class RefusedRelabelRecoveryTest(support._GateCase, unittest.TestCase):
    """A publication whose relabel did not land, and the tick after it.

    The narrowest window on this road and the one with the effects already
    out. The pinned write goes ahead of the label so nothing this line spends
    is stranded on an issue that has moved on -- but where the label itself is
    refused the issue has NOT moved on: it is still implementing, its branch
    is pushed, a pull request carries it, and every record the gate decided by
    is spent. Read as work nobody has ruled on, that branch is measured again
    against a base that has moved and a ceiling that may have been retuned
    since.
    """

    def test_the_pushed_commit_is_recorded(self) -> None:
        # The one record that outlives the window, written in the same breath
        # as the ones it spends.
        self._published_without_the_relabel()

        pinned = self._pinned()
        self.assertEqual(pinned[_KEY_PUBLISHED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertIsNone(pinned[_KEY_APPROVED_SHA])
        self.assertEqual(pinned[_KEY_PR_NUMBER], _OPENED_PR_NUMBER)

    def test_the_next_tick_does_not_re_decide_it(self) -> None:
        # A ceiling retuned or a base that moved between the two ticks makes
        # this a different question from the one the gate already answered,
        # and an oversized answer would route a branch that is already pushed
        # and already on a pull request to adjudication -- with nothing left
        # to hold back, which is the one outcome the gate exists to prevent.
        self._published_without_the_relabel()

        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self.assertNotIn(_DECOMPOSING, self.github.label_history)

    def test_the_next_tick_finishes_the_handoff(self) -> None:
        # And what it does instead is the rest of the publication: the pull
        # request that already carries the commit is reused rather than a
        # second one opened over it, and the label the first tick could not
        # write lands.
        self._published_without_the_relabel()

        self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self.assertEqual(len(self.github.opened_prs), 1)
        self.assertIn(
            (support.GATE_ISSUE_NUMBER, LABEL_VALIDATING),
            self.github.label_history,
        )

    def test_a_switched_off_push_is_recorded_too(self) -> None:
        # `DECOMPOSE=off` decides nothing about the candidate, so the commit
        # the push carries is one the checkout named rather than one the gate
        # did -- and the branch is just as published either way. The switch is
        # an operator's to turn back on: flipped between the two ticks, the
        # gate would read an already published branch as work nobody has ruled
        # on and could route it to adjudication with the pull request open.
        self._published_without_the_relabel(decomposing=False)

        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self.assertNotIn(_DECOMPOSING, self.github.label_history)
        self.assertIn(
            (support.GATE_ISSUE_NUMBER, LABEL_VALIDATING),
            self.github.label_history,
        )

    def _published_without_the_relabel(self, decomposing: bool = True) -> None:
        """Tick one: pushed, its pull request opened, and the label refused."""
        refused = _RefusedRelabel(self.github)
        with patch.object(config, _DECOMPOSE, decomposing), patch.object(
            self.github, support.SET_LABEL, refused,
        ), self.assertRaises(_RelabelRefused):
            self._run_gate(added_lines=support.SMALL_ADDITIONS)
        opened = self.github.opened_prs[-1]
        # The head GitHub answers with once a push has opened a pull request,
        # which the double cannot derive: the poll after reads this to tell a
        # publication that landed from a receipt naming a branch that moved.
        opened.head = FakePRRef(
            sha=MEASURED_CANDIDATE_SHA, ref=opened.head_branch,
        )
        self.github.add_pr(opened)
        self.github.existing_open_pr[opened.head_branch] = opened


class GuidedPastTheApprovalTest(support._GateCase, unittest.TestCase):
    """What a human's guidance to a refused handoff buys, and what it costs.

    The other way out of `late_candidate_moved`: rather than putting the
    checkout back, the operator asks for the work to change. That resumes the
    developer on a branch already carrying the approved commit, which is what
    makes every reading here about telling the run's own output from what it
    started on -- and the approval, which named a commit this branch is now
    moving past.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**{
            support.AWAITING_HUMAN: True,
            support.PARK_REASON: _CANDIDATE_MOVED,
            _KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
            "dev_agent": "codex",
            "dev_session_id": _DEV_SESSION,
        })
        self._reply(_GUIDANCE)

    def test_an_adjudication_takes_the_approval_back(self) -> None:
        # A human who leaves the checkout on the descendant and asks for a
        # change gets what they asked for: the developer is resumed, and what
        # it leaves is measured as the fresh candidate it is. Past the ceiling
        # the approval it was committed on top of is owed no push any more --
        # left standing it would freeze the branch out of the base refresh for
        # the whole adjudication and park every later tick on a host that no
        # longer has that commit.
        mocks = self._run_gate(
            added_lines=support.OVERSIZED_ADDITIONS,
            run_agent=_agent(
                session_id=_DEV_SESSION, last_message=_FINISHED,
            ),
            head_shas=(MEASURED_CANDIDATE_SHA, _MOVED_SHA),
            candidate_commit=FrozenCommit(sha=_MOVED_SHA),
        )

        self._assert_resumed(mocks)
        self._assert_measured(mocks)
        self._assert_held(mocks)
        self.assertIn(_DECOMPOSING, self.github.label_history)
        self.assertIsNone(self._pinned()[_KEY_APPROVED_SHA])

    def test_the_switch_off_bypasses_the_new_commit(self) -> None:
        # The approval keeps the switch from bypassing because a commit this
        # gate decided has to be published under the id it decided about --
        # and that is a claim about ONE commit. A resumed developer's new work
        # is not it: it is new work, which is exactly what the switch keeps
        # out of the gate, so measuring it and routing an oversized one to
        # adjudication is the switch failing CLOSED on a stale record.
        with patch.object(config, _DECOMPOSE, False):
            mocks = self._resumed_past_the_approval()

        self._assert_resumed(mocks)
        self._assert_unmeasured(mocks)
        self._assert_published(mocks)
        self.assertNotIn(_DECOMPOSING, self.github.label_history)

    def test_a_refused_push_supersedes_the_approval(self) -> None:
        # And the debt follows the commit, whether or not the push lands. Read
        # on the one road that does not reach the handoff which spends it: the
        # push failed, so the tick parks -- and a record still naming the
        # commit this branch has moved past would freeze it out of the base
        # refresh for the rest of the issue's life and park every later tick
        # asking for a checkout back for work nobody will push. What it names
        # instead is the commit that was about to go out, which is the one
        # still owed one.
        with patch.object(config, _DECOMPOSE, False):
            mocks = self._resumed_past_the_approval(push_branch=False)

        self._assert_resumed(mocks)
        self.assertEqual(self.github.opened_prs, [])
        self.assertEqual(self._pinned()[_KEY_APPROVED_SHA], _MOVED_SHA)

    def test_a_question_does_not_publish_the_approval(self) -> None:
        # The commit the guidance was asked ABOUT is already on the branch, so
        # ahead-of-base says "this run committed" for a run that committed
        # nothing. Published on that reading, the developer's question is
        # dropped and the very commit a human was still deciding about is sent
        # to review.
        mocks = self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            run_agent=_agent(session_id=_DEV_SESSION, last_message=_ASKED),
            head_shas=(_MOVED_SHA, _MOVED_SHA),
            candidate_commit=FrozenCommit(sha=_MOVED_SHA),
        )

        self._assert_resumed(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self.assertIn(_ASKED, self.github.posted_comments[-1][1])
        self.assertTrue(self._pinned()[support.AWAITING_HUMAN])

    def _resumed_past_the_approval(self, **run_options):
        """One guidance resume whose developer committed a different SHA."""
        return self._run_gate(
            added_lines=support.OVERSIZED_ADDITIONS,
            run_agent=_agent(
                session_id=_DEV_SESSION, last_message=_FINISHED,
            ),
            head_shas=(MEASURED_CANDIDATE_SHA, _MOVED_SHA),
            candidate_commit=FrozenCommit(sha=_MOVED_SHA),
            **run_options,
        )


class MovedCheckoutRecoveryTest(support._GateCase, unittest.TestCase):
    """The park a checkout answers, and the publication it costs nothing.

    Publication refuses to hand review a worktree that has left the commit the
    gate approved. Everything else about that reading is gone by then -- the
    generation is retired ahead of the effects it licenses, on purpose -- so
    the park writes the commit down, and putting the checkout back on it is
    the whole of the answer: no reply, no guidance, and no second developer
    run over work the first one already committed and the gate already
    measured.
    """

    def test_the_park_records_the_approved_commit(self) -> None:
        # Without it the refusal names a commit in prose and nothing durable,
        # and the operator who does exactly the right thing gets no
        # acknowledgement for it.
        self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            candidate_commit=(
                FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
                FrozenCommit(sha=_MOVED_SHA),
            ),
        )

        pinned = self._pinned()
        self.assertEqual(pinned[support.PARK_REASON], _CANDIDATE_MOVED)
        self.assertEqual(pinned[_KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)

    def test_a_restored_checkout_publishes_itself(self) -> None:
        # The recovery is an ordinary tick rather than a command: the operator
        # moved the checkout back and the next poll publishes it. What goes
        # out is named against the commit the gate approved.
        self._park()

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_no_agent(mocks)
        self.assertEqual(
            mocks[support.PUSH_BRANCH].call_args.kwargs["revision"],
            MEASURED_CANDIDATE_SHA,
        )
        self.assertIn(
            (support.GATE_ISSUE_NUMBER, LABEL_VALIDATING),
            self.github.label_history,
        )

    def test_the_recovered_park_is_spent(self) -> None:
        # Both halves of it: the park that was refusing the handoff, and the
        # commit it was waiting to see. A record left behind would have the
        # next tick answering a question this one settled.
        self._park()

        self._run_gate(added_lines=support.SMALL_ADDITIONS)

        pinned = self._pinned()
        self.assertFalse(pinned[support.AWAITING_HUMAN])
        self.assertIsNone(pinned[support.PARK_REASON])
        self.assertIsNone(pinned[_KEY_APPROVED_SHA])

    def test_a_checkout_still_elsewhere_stays_parked(self) -> None:
        # And says nothing while it does. The question is asked every tick,
        # which is what lets the checkout coming back be enough on its own --
        # so an operator who leaves it where it is must not be told the same
        # thing once a poll.
        self._park()

        mocks = self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            candidate_commit=FrozenCommit(sha=_MOVED_SHA),
        )

        self._assert_no_agent(mocks)
        self._assert_held(mocks)
        self.assertTrue(self._pinned()[support.AWAITING_HUMAN])
        self.assertEqual(self.github.posted_comments, [])

    def test_an_unreadable_checkout_stays_parked(self) -> None:
        # A head that cannot be peeled proves nothing, and "not the approved
        # commit" is what nothing proves here: the recovery publishes on the
        # strength of the comparison rather than on the absence of an answer.
        self._park()

        mocks = self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            candidate_commit=FrozenCommit(
                sha="", failure=MeasurementFailure.CANDIDATE_UNREADABLE,
            ),
        )

        self._assert_held(mocks)
        self.assertTrue(self._pinned()[support.AWAITING_HUMAN])

    def _park(self) -> None:
        """Seed the park publication takes on a checkout that moved off."""
        self._seed(**{
            support.AWAITING_HUMAN: True,
            support.PARK_REASON: _CANDIDATE_MOVED,
            _KEY_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
            "dev_agent": "codex",
            "dev_session_id": _DEV_SESSION,
        })

if __name__ == "__main__":
    unittest.main()
