# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A final-docs pass that changes the pull request, completed straight into review with no second review.

Walked whole by the dispatcher from an approval, squashed or not: the docs
pass commits on top of the head it was entered on, its push lands, the
configured suite is run on exactly the docs commit, and the pass completes
into `in_review` -- the approved subject, the settled report and the commit it
was written about, and the review rounds spent left exactly as the approval
left them, and the docs commit recorded beside them, verified by that run.
The next tick's reconciliation publishes the run, the pull request is told it
is ready once, and later ticks do nothing. No reviewer and no report refresh
is launched behind the approval: the docs pass is the one run charged.

The same holds through a crash in every window the completion opens -- a push
whose answer was lost, a completion write that never landed or landed with
its answer lost, and a relabel that failed behind it -- each finished by the
next dispatch from what landed, with no second agent run, and a pause applied
while the docs commit's run is out holds it, receipt intact, until the label
comes off. Under an empty
`VERIFY_COMMANDS` nothing is run or published on the docs commit, and the
completion says so. A run that fails on the docs commit, one that passes and
binds no evidence, and one that tests another head offer nothing for merge;
the docs pass a bare continue resumes over a failed commit has what it leaves
verified again, a fix over the head the pass was first entered on. A later
approval retires an earlier pass's unfinished receipt and runs its own pass,
and a base rebase of the completed docs commit is a genuine rewrite: the
approved report is refreshed for the rebased head, through the docs pass's
lineage, before the review that rebase owes.

The reported sequence of an approval bought by an operator's grant past a
spent review cap ends the same way, whether the approval squashed or not and
whether the docs pass changed anything.
"""
from __future__ import annotations

import unittest
from itertools import product
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.workflow.engine import final_docs_records as _final_docs
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeLabel
from tests.workflow import (
    drift_reports as _drift_world,
    published_reports as _published_reports,
    review_world as _world,
)
from tests.workflow.fixtures import _agent
from tests.workflow.stages.validating import (
    changed_docs_journey_support as _docs,
    changed_docs_readings as _readings,
    readiness_journey_support as _readiness,
    squash_rebase_journey_support as _journey,
)

DOCS_HEAD = _docs.DOCS_HEAD

UNCONFIGURED = _final_docs.FinalVerification.UNCONFIGURED

# Every window a crash can cut the completion short in, as the context the docs
# dispatch runs under -- None where it runs through. The push's answer lost
# leaves the gate's approval for the next tick to settle and the receipt
# beside it; the completion's write dying leaves the gate's receipt, which the
# next tick finishes from; and the write landing with its answer lost, or the
# relabel behind it failing, leaves the completion, which the next tick
# relabels from.
CRASHES = (
    ("the push's answer lost", "push"),
    ("the completion's write dying", _readings.dying_on_the_completion),
    ("the completion's answer lost", _readings.losing_the_completion),
    ("the relabel failing", _readings.dying_on_the_relabel),
)

# How a report refresh behind a rebase of the docs commit names the report the
# pull request carries: the approved commit, squashed and then documented into
# the docs commit that rebase replaced.
DOCUMENTED_INTO = (
    f"describes `{_docs.HEAD}`, the approved commit this orchestrator documented, in a final docs pass, into "
    f"`{DOCS_HEAD}`"
)

# The control label an operator pauses an issue with, and what a pass held
# over it leaves: the label, the docs receipt, and no completion recorded.
PAUSED = "paused"

UNCOMPLETED = (WorkflowLabel.DOCUMENTING, DOCS_HEAD, (None, None, None))

# The report a later round settles about the published docs commit.
LATER_REPORT = "Reports on the published docs commit; the approved change reads as before."

# The operator's grant of one more reviewer round past a spent cap.
GRANT = "/orchestrator add-review-rounds 1"

# What a docs pass that changed nothing tells from its spawn on, the ready ping
# last, and the completion it records: the head it was entered and completed
# on, the evidence the approval rests on retained.
PINGED = (_readiness.READY,)

DOCUMENTED_UNCHANGED = ((_readiness.SPAWN, _journey.DOCUMENTER), PINGED)

RETAINED = _final_docs.FinalVerification.RETAINED.value

EXECUTED = _final_docs.FinalVerification.EXECUTED.value

# The operator's answer to a failed run's park, and the fix the docs pass it
# resumes commits on top of the docs commit it published.
CONTINUE = "/orchestrator continue"

FIX_HEAD = "f1" * (len(DOCS_HEAD) // 2)


class _PausesWhileVerifying:
    """The verify runner of a run an operator pauses the issue during, the run itself passing on the docs commit."""

    def __init__(self, case) -> None:
        self._case = case

    def __call__(self, *_called, **_options):
        self._case.issue.labels.append(FakeLabel(PAUSED))
        return _readings.docs_run()


class ChangedDocsJourneyTest(_docs._ChangedDocsWalk, unittest.TestCase):
    """A content-changing docs pass completes into review over a run of its own commit, and nothing more runs."""

    def test_changed_docs_complete_into_review(self) -> None:
        # Squashed or not, the docs commit is completed into `in_review` over
        # a run of exactly that commit, the approval's records untouched; the
        # next tick publishes that run and pings once, and later ticks spawn,
        # verify, charge, write, and post nothing more.
        for squashes in (True, False):
            with self.subTest(squashes=squashes):
                self.setUp()
                self.enterContext(patch.object(config, "SQUASH_ON_APPROVAL", squashes))
                self.walks_into_documenting()

                self.changes_the_docs()
                self.dispatched()

                self.assert_documented_into_review()
                self.assert_quiet_into_review()

    def test_a_crash_anywhere_completes_once(self) -> None:
        # Whichever window a process dies in, the next dispatch finishes what
        # landed -- the gate's settlement and the completion from its receipt,
        # or the relabel from the completion -- and the walk ends in review,
        # told once, with the docs pass the one run.
        for name, window in CRASHES:
            with self.subTest(name):
                self.setUp()
                self.walks_into_documenting()
                self.changes_the_docs_under(window)

                self.dispatched()

                self.assert_documented_into_review()
                self.assert_quiet_into_review()

    def test_a_docs_rebase_refreshes_the_report(self) -> None:
        # A base rebase of the completed docs commit is a genuine rewrite: its
        # debt names the docs commit as the head replaced, and the approved
        # report -- about the approved commit, squashed and then documented
        # into that docs commit -- is refreshed for the rebased head with no
        # human, its prompt naming that lineage, and the walk goes on through
        # a fresh review and docs pass to one ready ping on the rebased head.
        self.walks_into_documenting()
        self.changes_the_docs()
        self.dispatched()

        self.base_refresh(_journey.ADVANCED)
        self.dispatched(_journey.refresh())
        self.approved_into_review(_journey.ADVANCED)

        rebased = (_journey.REFRESHER, _journey.REVIEWER, _journey.DOCUMENTER)
        self.assertEqual(self.roles()[-len(rebased):], rebased)
        self.assertIn(DOCUMENTED_INTO, self.spawned(_journey.REFRESHER)[0])
        self.assert_ready_on(_journey.ADVANCED, self.refreshed)

    def test_a_later_approval_runs_its_own_pass(self) -> None:
        # The completion of a published pass never landed, so its receipt
        # stands when a human sends the issue back and a later approval is
        # given over a report of the published docs commit: that approval
        # retires the receipt, and its own docs pass runs and completes,
        # rather than the earlier pass being finished from a receipt entered
        # on the head the earlier approval was of.
        self.enterContext(patch.object(config, "SQUASH_ON_APPROVAL", False))
        self._sent_back_over_an_unfinished_pass()

        self.dispatched(
            _journey.approval_on(DOCS_HEAD),
            squash_result=_readings.leaves_the_branch,
            verify_result=_readings.docs_run(),
        )
        self.dispatched(_journey.DOCS)
        self.dispatched()

        self.assertEqual(self.roles(), (_journey.DOCUMENTER, _journey.REVIEWER, _journey.DOCUMENTER))
        retained = ((RETAINED, DOCS_HEAD, DOCS_HEAD), (DOCS_HEAD, "no_change"), None)
        self.assertEqual(self.completed(), retained)
        self.assert_told_once((PINGED,), DOCS_HEAD)

    def test_empty_config_runs_nothing(self) -> None:
        # With no configured command nothing runs on the docs commit and
        # nothing is published as passing: the completion records that the
        # head is verified by nothing, and the ping rests on that alone.
        self.enterContext(patch.object(config, "VERIFY_COMMANDS", ()))
        self.walks_into_documenting()

        self.changes_the_docs()
        self.dispatched()

        self.assert_documented_into_review(UNCONFIGURED, _docs.DOCUMENTED_UNVERIFIED)
        self.assertEqual(self.verifications, 0)



    def test_a_pause_during_verification_holds(self) -> None:
        # An operator pauses the issue while the docs commit's run is out:
        # nothing is recorded, announced, or relabelled, and the receipt
        # stands. Once the label comes off, the next dispatch verifies the
        # commit again and completes it, with no second agent run.
        self.walks_into_documenting()
        told = len(self.pull_request.issue_comments)

        self.changes_the_docs(verified=MagicMock(side_effect=_PausesWhileVerifying(self)))

        receipt = self.pinned()["docs_settled_sha"]
        recorded = self.completed()[0]
        self.assertEqual((self.labels()[-1], receipt, recorded), UNCOMPLETED)
        self.assertEqual(len(self.pull_request.issue_comments), told)
        unpaused = self.issue.labels.pop()
        self.assertEqual(unpaused.name, PAUSED)
        self.dispatched(verify_result=_readings.docs_run())
        self.dispatched()
        self.assert_documented_into_review()

    def _sent_back_over_an_unfinished_pass(self) -> None:
        """A docs commit published and its completion's write dying, the issue sent back and a later report settled."""
        self.walks_into_documenting()
        with _readings.dying_on_the_completion(self):
            self.changes_the_docs()
        self.github.set_workflow_label(self.issue, WorkflowLabel.VALIDATING)
        _published_reports.republishes_the_report(self.github, self.issue, LATER_REPORT)

class FailedDocsRunTest(_docs._ChangedDocsWalk, unittest.TestCase):
    """A docs commit whose own run does not pass, or tests another head, is offered to nobody until one does."""

    def test_a_failed_run_offers_nothing(self) -> None:
        # The configured suite fails on the docs commit, or passes with an
        # output no artifact can carry, so it binds no evidence: the pass parks
        # with the commit published and no completion recorded, later ticks
        # leave it parked, nothing reaches review, and the receipt stands --
        # holding the base refresh off the branch -- for the pass a continue
        # resumes.
        for verified, reason in (
            (_readings.failed_docs_run(), "verify_failed"),
            (_readings.unrecordable_docs_run(), "verify_unrecorded"),
        ):
            with self.subTest(reason):
                self.setUp()
                self.walks_into_documenting()

                self.changes_the_docs(verified=verified)
                self.dispatched(verify_result=_readings.docs_run())

                self.assertEqual(self._held_on_the_receipt(), (WorkflowLabel.DOCUMENTING, reason, None))
                self.assertEqual(self.pull_request.head.sha, DOCS_HEAD)
                self.assertNotIn(PINGED, self.told(self.walked))

    def test_a_continue_reruns_a_failed_pass(self) -> None:
        # A bare continue answers the failed run's park by resuming the docs
        # pass over the commit it published, the failure on the thread it is
        # handed: a fix it commits is pushed and verified over the head the
        # pass was first entered on, and a `DOCS: NO_CHANGE` has the commit
        # already published verified again -- either way completed into
        # review once its run passes, the approval untouched.
        for name, rerun, final in (
            ("a fix committed", self.commits_a_fix, FIX_HEAD),
            ("nothing to add", self.adds_nothing, DOCS_HEAD),
        ):
            with self.subTest(name):
                self.setUp()
                self.walks_into_documenting()
                self.changes_the_docs(verified=_readings.failed_docs_run())
                _drift_world.human_reply(self, CONTINUE)

                rerun()
                self.dispatched()

                self._assert_rerun_into_review(final)

    def commits_a_fix(self) -> None:
        """The resumed docs pass committing a fix over the published docs commit, its own run passing."""
        self.dispatched(
            (_journey.DOCUMENTER, _agent(last_message="docs: fix the failing check")),
            head_shas=(DOCS_HEAD, FIX_HEAD),
            commit_message=f"docs: fix the failing check (#{_world.PR})\n",
            candidate_commit=FrozenCommit(sha=FIX_HEAD),
            push_branch=_drift_world._LandingPush(self.pull_request),
            verify_result=_readings.docs_run(FIX_HEAD),
        )

    def adds_nothing(self) -> None:
        """The resumed docs pass finding nothing to add, the published commit's run passing this time."""
        self.dispatched(_journey.DOCS, verify_result=_readings.docs_run())

    def test_a_run_of_another_head_holds(self) -> None:
        # A run that tested another commit says nothing of the docs commit:
        # nothing is recorded, parked, announced, or relabelled, and the
        # receipt stands, so the next dispatch verifies the docs commit
        # itself and completes the pass with no second agent run.
        self.walks_into_documenting()

        self.changes_the_docs(verified=_readings.docs_run(commit=_world.OTHER_HEAD))

        self.assertEqual(self._held_on_the_receipt(), (WorkflowLabel.DOCUMENTING, None, None))
        self.dispatched(verify_result=_readings.docs_run())
        self.dispatched()
        self.assert_documented_into_review()


    def _held_on_the_receipt(self) -> tuple:
        """The label, the park, and the completion where the docs receipt still stands on the docs commit."""
        pinned = self.pinned()
        self.assertEqual(pinned["docs_settled_sha"], DOCS_HEAD)
        completion = pinned.get(_final_docs.FINAL_DOCS)
        return self.labels()[-1], pinned.get("park_reason"), completion


    def _assert_rerun_into_review(self, final: str) -> None:
        """Completed on `final`, verified by its own run, the approval untouched, and the docs pass the two runs."""
        completion = ((EXECUTED, self.entered_on(), final), (final, "updated"), None)
        self.assertEqual(self.completed(), completion)
        self.assertEqual(self.approved(), self.approval)
        self.assertEqual(self.roles(), (_journey.DOCUMENTER, _journey.DOCUMENTER))
        self.assert_told_once((PINGED,), final)

class GrantedRoundJourneyTest(_docs._ChangedDocsWalk, unittest.TestCase):
    """The review-cap park an operator's grant answers, approved and documented, ends once in review."""

    def test_a_granted_approval_documents_into_review(self) -> None:
        # The review cap parks the round; a trusted grant of one more round
        # buys the review, which approves. Whether the approval squashed and
        # whether the docs pass changed anything, the pass completes into
        # `in_review` with the round count the approval left, the approved
        # subject and report as the approval left them, and no reviewer or
        # report refresh launched past it -- and the pull request is told it
        # is ready once, and nothing after.
        for squashes, changes in product((True, False), (True, False)):
            with self.subTest(squashes=squashes, changes=changes):
                self.setUp()
                self.enterContext(patch.object(config, "SQUASH_ON_APPROVAL", squashes))
                self.granted_and_approved()

                self.documents(changes=changes)

                self.assert_granted_into_review(changes)
                self.assert_quiet_into_review()

    def test_a_granted_completion_recovers(self) -> None:
        # The same walk with the completion cut short in each window it opens:
        # the next dispatch finishes it from what landed, and the walk ends in
        # review as it would have.
        for name, window in CRASHES:
            with self.subTest(name):
                self.setUp()
                self.granted_and_approved()

                self.changes_the_docs_under(window)
                self.dispatched()

                self.assert_granted_into_review(changes=True)
                self.assert_quiet_into_review()

    def granted_and_approved(self) -> None:
        """Park the round on its spent review cap, grant one more round, and approve on it."""
        self.enterContext(patch.object(config, "MAX_REVIEW_ROUNDS", 2))
        state = self.github.read_pinned_state(self.issue)
        # The cap's park walks the reply boundary over our own posts, and the
        # delivered stretch, reaching it, moves with it.
        for record, recorded in (
            ("awaiting_human", True),
            ("park_reason", "review_cap"),
            (_docs.REVIEW_ROUND, config.MAX_REVIEW_ROUNDS),
            ("last_action_comment_id", _readiness.high_water(self)),
            ("delivered_through_comment_id", _readiness.high_water(self)),
        ):
            state.set(record, recorded)
        self.github.write_pinned_state(self.issue, state)
        _drift_world.human_reply(self, GRANT)
        self.walks_into_documenting()

    def documents(self, *, changes: bool) -> None:
        """The docs pass, committing a docs change where `changes`, and the dispatch behind it."""
        if changes:
            self.changes_the_docs()
        else:
            self.dispatched(_journey.DOCS)
        self.dispatched()

    def assert_granted_into_review(self, changes: bool) -> None:
        """The walk ended in review over the granted round, told once, the round count the approval's.

        The grant reopened one round below the cap, which the approval spent
        none of; nothing past it spends any either.
        """
        self.assertEqual(self.approval[2], config.MAX_REVIEW_ROUNDS - 1)
        if changes:
            self.assert_documented_into_review()
            return
        head = self.entered_on()
        retained = ((RETAINED, head, head), (head, "no_change"), None)
        self.assertEqual(self.completed(), retained)
        self.assert_only_documented()
        self.assert_told_once(DOCUMENTED_UNCHANGED, head)


if __name__ == "__main__":
    unittest.main()
