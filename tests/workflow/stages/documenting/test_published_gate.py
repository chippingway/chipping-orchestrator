# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The docs commit measured before it joins a pull request that is open.

The final documentation pass is the last push before a human is asked to
merge, and what it publishes is not the docs commit's own diff -- it is
everything the pull request comes to with that commit in it. So the size gate
every other push onto an open pull request goes through stands in front of
this one too, on each road a docs commit arrives by: the fresh pass, the
commit an earlier tick stranded, and the `DOCS: NO_CHANGE` reply that still
has one waiting.

A hold is the end of the tick rather than a park: nothing is pushed, no docs
verdict is stamped, the issue goes to the adjudication instead of `in_review`,
and the head the pass produced is left as the receipt the handoff is still
owed. What the gate allows is pushed named to that commit and pinned to the
head the pass was entered on, and only then stamped, announced, and handed on.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit
from tests.support.fakes import FakeLabel
from tests.workflow import fixtures
from tests.workflow.mid_run_effects import (
    _ClosesThePullRequest,
    _MovesThePullRequest,
)
from tests.workflow.stages.documenting import (
    documenting_gate_test_support as gate,
    documenting_test_support as documenting,
)

AT_THE_CEILING = gate.AT_THE_CEILING
ENTERED_HEAD = gate.ENTERED_HEAD
MEASURED_BASE_SHA = gate.MEASURED_BASE_SHA
MEASURED_CANDIDATE_SHA = gate.MEASURED_CANDIDATE_SHA
PAST_THE_CEILING = gate.PAST_THE_CEILING
UNDER_THE_CEILING = gate.UNDER_THE_CEILING
PICKUP_COMMENT_ID = documenting.PICKUP_COMMENT_ID

# A recovered commit an earlier tick already amended: the road where the
# subject needs nothing and no head moves.
FRESH_PR_NUMBER = documenting._FreshDocumentingFixture.pr_number
RECOVERED_REFERENCED_MESSAGE = f"docs: recovered notes (#{FRESH_PR_NUMBER})\n"

# The two ways a tick ends with the record written and nothing on the remote --
# the gate holding the candidate, and a push it allowed that did not go out --
# each beside the field naming the commit it was about.
UNPUBLISHED_RECORDS = (
    ({"added_lines": PAST_THE_CEILING}, gate.KEY_SETTLED_DOCS_SHA),
    (
        {"added_lines": UNDER_THE_CEILING, "push_branch": False},
        gate.KEY_APPROVED_SHA,
    ),
)


class CumulativeDocsReadingTest(unittest.TestCase, gate._DocsGateFixtureMixin):
    """What a docs commit is counted against, and where the line falls."""

    def test_the_count_covers_the_whole_pull_request(self) -> None:
        # The pair is the base the REMOTE says the branch is cut from and the
        # commit this pass made. Counted from the head the pull request is
        # standing on instead, the reading would be the docs commit's own diff
        # -- and a pull request already at the ceiling would take a docs pass
        # of any size without the count ever noticing.
        _github, mocks = self._fresh_pass(added_lines=UNDER_THE_CEILING)

        self.assertEqual(
            mocks[gate.COUNT_ADDED_LINES].call_args.args[1:],
            (MEASURED_BASE_SHA, MEASURED_CANDIDATE_SHA),
        )

    def test_the_ceiling_is_passed_strictly(self) -> None:
        # A pull request that comes to exactly the configured value is one a
        # human may still be asked to merge; one line past it is not.
        for added in (AT_THE_CEILING, PAST_THE_CEILING):
            with self.subTest(added=added):
                github, mocks = self._fresh_pass(added_lines=added)

                if added > AT_THE_CEILING:
                    self._assert_held(github, mocks)
                    continue
                self.assertEqual(
                    mocks[documenting.PUSH_BRANCH].call_args.kwargs[
                        gate.REVISION
                    ],
                    MEASURED_CANDIDATE_SHA,
                )
                self._assert_handed_off_once(github)

    def test_the_push_replaces_the_entered_head(self) -> None:
        # The lease is the head the pull request was standing on when the pass
        # began, not one read again at the push: this is the last force-push
        # before a human is asked to merge, so what a lease taken afterwards
        # would silently drop is what that human would then not see.
        _github, mocks = self._fresh_pass(added_lines=AT_THE_CEILING)

        self.assertEqual(
            mocks[documenting.PUSH_BRANCH].call_args.kwargs[gate.LEASE],
            ENTERED_HEAD,
        )

    def test_the_hold_records_its_publication(self) -> None:
        # What the adjudication is handed: the count for the whole pull
        # request, the pair it was taken over, and the publication the reading
        # was entered on. None of them is re-derivable once the label has left
        # this stage, and the source stage is what says a settled verdict
        # hands the issue back HERE rather than to the route that opened the
        # pull request.
        github, _mocks = self._fresh_pass(added_lines=PAST_THE_CEILING)

        pinned = self._pinned(github)
        self.assertEqual(pinned[gate.KEY_ADDITIONS], PAST_THE_CEILING)
        self.assertEqual(pinned[gate.KEY_BASE_SHA], MEASURED_BASE_SHA)
        self.assertEqual(
            pinned[gate.KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertEqual(pinned[gate.KEY_SOURCE_STAGE], gate.LABEL_DOCUMENTING)
        self.assertEqual(pinned[gate.KEY_PUBLISHED_PR], self.pr_number)
        self.assertEqual(pinned[gate.KEY_PUBLISHED_SHA], ENTERED_HEAD)


class AnnouncedHandoffTest(unittest.TestCase, gate._DocsGateFixtureMixin):
    """What the pull request is told, and what the record keeps of it."""

    def test_the_notice_is_recorded_and_walked_past(self) -> None:
        # A comment this orchestrator posted has to be recognizable as its
        # own: the handoff's watermark walk seeds past it, and the in_review
        # feedback scan drops it rather than resuming a dev over an
        # informational post of ours. Both read `orchestrator_comment_ids`
        # first, and the handoff's write is the last one this tail takes --
        # posted behind it, the id would have nothing left to ride and every
        # docs notice would arrive unrecorded.
        github, issue = self._seeded(pickup_comment_id=PICKUP_COMMENT_ID)

        self._fresh_tick(github, issue, added_lines=UNDER_THE_CEILING)

        announced = github.get_pr(self.pr_number).issue_comments[-1]
        pinned = self._pinned(github)
        self.assertIn(announced.id, pinned[gate.ORCHESTRATOR_COMMENT_IDS])
        self.assertGreaterEqual(
            pinned[gate.PR_LAST_COMMENT_ID], announced.id,
        )

    def test_a_pass_drops_the_verdict_it_starts_from(self) -> None:
        # From the spawn on, a `docs_verdict` on the record means "this pass
        # finished" to both things that read one -- the merge gate, which
        # pings a head it finds a verdict beside, and the handoff, whose stamp
        # is written behind its own notice. Every shape re-anchors
        # `docs_checked_sha` to the head it is about, so an earlier round's
        # verdict left standing would name this pass's commit while it is
        # still running.
        github, _issue, _mocks = self._no_change_pass(
            seeded={documenting.DOCS_VERDICT: documenting.VERDICT_UPDATED},
            added_lines=PAST_THE_CEILING,
        )

        self.assertIsNone(self._pinned(github)[documenting.DOCS_VERDICT])

    def test_a_held_pass_still_announces_its_handoff(self) -> None:
        # The road a held pass takes to `in_review`: it announces nothing
        # itself, so the tick that finishes the handoff from the receipt is
        # the only thing that tells the pull request its docs commit arrived.
        # Driven from a record already carrying an earlier round's verdict,
        # since that is the shape this road really lands in -- the resumed dev
        # added nothing to a commit already waiting, so the pass anchors on
        # that very head.
        github, issue, _mocks = self._no_change_pass(
            seeded={documenting.DOCS_VERDICT: documenting.VERDICT_UPDATED},
            added_lines=PAST_THE_CEILING,
        )
        self.assertEqual(github.posted_pr_comments, [])

        self._settled_tick(github, issue)

        self._assert_handed_off_once(github, gate.HANDOFF_NOTICE)


class WaitingDocsCommitTest(unittest.TestCase, gate._DocsGateFixtureMixin):
    """The two roads whose commit was made before this tick began."""

    def test_a_recovered_commit_is_measured(self) -> None:
        # The recovered road pushes WITHOUT spawning, which is exactly why it
        # cannot skip the reading: the commit reaches the pull request here
        # for the first time, so an earlier tick's crash is no licence to
        # publish what a finished pass would have been held for.
        github, mocks = self._recovered_pass(added_lines=PAST_THE_CEILING)

        mocks[documenting.RUN_AGENT].assert_not_called()
        self._assert_held(github, mocks)
        self.assertEqual(
            self._pinned(github)[gate.KEY_SETTLED_DOCS_SHA],
            MEASURED_CANDIDATE_SHA,
        )

    def test_a_no_change_measures_what_waits(self) -> None:
        # A `DOCS: NO_CHANGE` verdict certifies the local tree and says
        # nothing about the remote: the commit an earlier tick left is still
        # what has to reach the pull request, so it goes through the gate
        # rather than round it on the strength of the verdict.
        github, _issue, mocks = self._no_change_pass(
            added_lines=PAST_THE_CEILING,
        )

        self._assert_held(github, mocks)
        self.assertEqual(
            self._pinned(github)[gate.KEY_SETTLED_DOCS_SHA],
            MEASURED_CANDIDATE_SHA,
        )

    def test_a_no_change_refuses_a_moved_head(self) -> None:
        # The same road with the pull request moved while the resumed dev was
        # out. The head the pass was entered on is what the push is pinned to,
        # so somebody else's commit is refused rather than adopted as the
        # lease and force-overwritten by a candidate the gate allowed.
        github, issue = self._seeded_resume()

        mocks = self._no_change_tick(
            github, issue,
            run_agent=_MovesThePullRequest(
                github.get_pr(self.pr_number),
                gate.MOVED_PR_HEAD,
                fixtures._agent(
                    session_id=documenting.DEV_SESSION,
                    last_message=gate.NO_CHANGE_REPLY,
                ),
            ),
            added_lines=UNDER_THE_CEILING,
        )

        self._assert_held(github, mocks)
        self.assertEqual(
            github.get_pr(self.pr_number).head.sha, gate.MOVED_PR_HEAD,
        )


class ClosedPublicationTest(unittest.TestCase, gate._DocsGateFixtureMixin):
    """A pull request the docs commit has nowhere left to land on."""

    def test_a_pull_request_closed_mid_run_refuses(self) -> None:
        # A count against a closed or merged pull request would adjudicate a
        # question nobody can act on, and the preflight drains one before the
        # pass begins -- so the only way to reach this state is a human
        # closing the pull request while the docs agent is out.
        github, issue = self._seeded()

        mocks = self._fresh_tick(
            github, issue,
            run_agent=_ClosesThePullRequest(
                github.get_pr(self.pr_number),
                fixtures._agent(
                    session_id=documenting.DEV_SESSION,
                    last_message=gate.DOCS_REPLY,
                ),
            ),
            added_lines=UNDER_THE_CEILING,
        )

        self._assert_held(github, mocks)
        pinned = self._pinned(github)
        self.assertTrue(pinned[documenting.AWAITING_HUMAN])
        self.assertEqual(
            pinned[documenting.PARK_REASON], gate.PARK_MEASUREMENT_FAILED,
        )


class DocsPushCrashTest(unittest.TestCase, gate._DocsGateFixtureMixin):
    """The window between the push going out and this stage writing it down."""

    def test_a_failed_push_keeps_what_a_retry_pins_to(self) -> None:
        # The approval goes down BEFORE the push, so a tick that dies over it
        # leaves both the commit owed a publication and the head to pin it
        # against. Read afresh on the retry instead, the lease would be
        # whatever the pull request has moved to since.
        github, _mocks = self._fresh_pass(
            added_lines=UNDER_THE_CEILING, push_branch=False,
        )

        self._assert_unstamped(github)
        pinned = self._pinned(github)
        self.assertEqual(pinned[gate.KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[gate.KEY_APPROVED_LEASE], ENTERED_HEAD)
        self.assertEqual(
            pinned[documenting.PARK_REASON], documenting.PARK_PUSH_FAILED,
        )

    def test_a_landed_push_pays_its_debt_durably(self) -> None:
        # The branch is on the remote and this stage still has a relabel and a
        # release to make. A process that died in that window would leave a
        # paid debt pinned for good -- nothing revisits it, and the pre-tick
        # base refresh reads it as a branch frozen out of the sync -- so the
        # debt and the receipt ride one write, taken inside the gate.
        github, _issue = self._crashed_pass(added_lines=UNDER_THE_CEILING)

        pinned = self._pinned(github)
        self.assertIsNone(pinned.get(gate.KEY_APPROVED_SHA))
        self.assertIsNone(pinned.get(gate.KEY_APPROVED_LEASE))
        # And the commit that landed is named twice over: by the receipt that
        # says what reached the remote, and by the one this stage is owed a
        # handoff for.
        self.assertEqual(pinned[gate.KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(
            pinned[gate.KEY_SETTLED_DOCS_SHA], MEASURED_CANDIDATE_SHA,
        )

    def test_the_crash_leaves_the_pass_on_this_stage(self) -> None:
        # `in_review` repairs nothing it is handed: relabelled ahead of the
        # write, the merge gate would read a `docs_checked_sha` naming the
        # commit the pass BEGAN on and a verdict nobody wrote, and no later
        # tick of any stage goes back for it.
        github, _issue = self._crashed_pass(added_lines=UNDER_THE_CEILING)

        self.assertEqual(github.label_history, [])
        self._assert_unstamped(github)

    def test_a_checkout_that_moved_holds_the_handoff(self) -> None:
        # The worktree is writable while the push runs. What went out is the
        # commit that was named, so the pull request is right; what is wrong
        # is the CHECKOUT the reviewer, the squash, and the next docs pass all
        # work from -- so the publication stands and the handoff stops.
        github, mocks = self._fresh_pass(
            added_lines=UNDER_THE_CEILING,
            candidate_commit=(
                FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
                FrozenCommit(sha=gate.MOVED_AFTER_PUSH),
            ),
        )

        mocks[documenting.PUSH_BRANCH].assert_called_once()
        self._assert_unstamped(github)
        self.assertEqual(
            self._pinned(github)[documenting.PARK_REASON],
            gate.PARK_CANDIDATE_MOVED,
        )


class DocsHandoffCrashTest(unittest.TestCase, gate._DocsGateFixtureMixin):
    """The three effects of the tail, and what a tick dying on each leaves."""

    def test_the_tick_after_the_crash_hands_it_on(self) -> None:
        # What the receipt buys: the pull request is standing on the commit
        # the dead tick pushed, so the tick that follows finishes the handoff
        # from the record rather than spawning a second agent over published
        # work. This is the one window the tail cannot close -- the notice
        # went out and the write that would have recorded it did not -- so the
        # finishing tick says it again rather than leaving the pull request
        # with a stamp nothing announced.
        github, issue = self._crashed_pass(added_lines=UNDER_THE_CEILING)

        mocks = self._settled_tick(github, issue)

        mocks[documenting.RUN_AGENT].assert_not_called()
        mocks[documenting.PUSH_BRANCH].assert_not_called()
        self._assert_handed_off_once(github, gate.HANDOFF_NOTICE, notices=2)

    def test_a_settled_crash_hands_on_next_tick(self) -> None:
        # The adjudicated-single road through the same window. The commit was
        # published from the adjudication and the label handed back here, so
        # the receipt is all this stage has -- and a crash over its write must
        # leave that receipt exactly where it stands rather than consume it.
        github, issue = self._seeded(**{
            gate.KEY_SETTLED_DOCS_SHA: MEASURED_CANDIDATE_SHA,
        })
        self._crashed(github, issue, self._settled_tick)
        self.assertEqual(github.label_history, [])
        self.assertEqual(
            self._pinned(github)[gate.KEY_SETTLED_DOCS_SHA],
            MEASURED_CANDIDATE_SHA,
        )

        mocks = self._settled_tick(github, issue)

        mocks[documenting.RUN_AGENT].assert_not_called()
        self._assert_handed_off_once(github, gate.HANDOFF_NOTICE, notices=2)

    def test_a_failed_relabel_reruns_the_pass(self) -> None:
        # The record this window leaves -- a pass already called finished,
        # with the receipt that write dropped -- is the very record a
        # `validating` approval handing the same head back leaves. Nothing
        # tells them apart, so the tick that follows runs the pass rather than
        # handing off on evidence that could belong to either: skipping a docs
        # pass an approval just bought is the failure that cannot be undone,
        # and re-running one over an already-documented tree is not.
        github, issue = self._crashed_pass(
            dies=gate.DIES_ON_THE_RELABEL, added_lines=UNDER_THE_CEILING,
        )
        crashed = self._pinned(github)
        self.assertIsNone(crashed[gate.KEY_SETTLED_DOCS_SHA])
        self.assertEqual(github.label_history, [])

        mocks = self._rerun(github, issue)

        mocks[documenting.RUN_AGENT].assert_called_once()
        self.assertEqual(
            github.label_history, [(self.issue_number, documenting.IN_REVIEW)],
        )

    def test_a_finished_handoff_frees_the_next_pass(self) -> None:
        # The receipt may not outlive the handoff it was written for. Left
        # standing by a write behind the relabel that did not land, a later
        # `validating` approval at the same head -- a body edit acknowledged
        # without a commit -- would read it as that pass still pending, skip
        # the docs pass the approval just bought, and hand the issue to
        # `in_review` a second time with no agent having run.
        github, issue = self._seeded()
        self._fresh_tick(github, issue, added_lines=UNDER_THE_CEILING)
        self.assertIsNone(self._pinned(github)[gate.KEY_SETTLED_DOCS_SHA])

        issue.labels = [FakeLabel(documenting.DOCUMENTING)]
        mocks = self._rerun(github, issue)

        mocks[documenting.RUN_AGENT].assert_called_once()

    def _rerun(self, github, issue):
        """The docs pass a tick takes when it finds nothing left owed.

        Its agent has an already-documented tree in front of it, so it
        confirms the diff and writes nothing.
        """
        return self._fresh_tick(
            github, issue,
            run_agent=fixtures._agent(
                session_id=documenting.DEV_SESSION,
                last_message=gate.NO_CHANGE_REPLY,
            ),
            head_shas=[MEASURED_CANDIDATE_SHA, MEASURED_CANDIDATE_SHA],
        )


class AmendedCandidateTest(unittest.TestCase, gate._DocsGateFixtureMixin):
    """The docs commit the gate is entered on is the one its subject became."""

    def test_the_gate_names_only_the_amended_commit(self) -> None:
        # An amendment is a new commit, so it comes before anything names one.
        # Held, the candidate the adjudication is handed and the receipt the
        # handoff is owed are the amended commit; allowed, so are the push and
        # the receipt saying what reached the remote. The commit the agent made
        # is never measured, recorded, or published -- handed to the gate
        # instead, it would be refused as a checkout standing somewhere else.
        for added in (UNDER_THE_CEILING, PAST_THE_CEILING):
            with self.subTest(added=added):
                github, mocks = self._fresh_pass(
                    added_lines=added,
                    head_shas=[
                        ENTERED_HEAD,
                        documenting.SHA_UNREFERENCED,
                        MEASURED_CANDIDATE_SHA,
                    ],
                )

                self.assertEqual(
                    mocks[documenting.AMEND_COMMIT_MESSAGE].call_args.args[1],
                    documenting.SHA_UNREFERENCED,
                )
                self.assertEqual(
                    mocks[gate.COUNT_ADDED_LINES].call_args.args[1:],
                    (MEASURED_BASE_SHA, MEASURED_CANDIDATE_SHA),
                )
                pinned = self._pinned(github)
                if added > AT_THE_CEILING:
                    self.assertEqual(
                        pinned[gate.KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA,
                    )
                    self.assertEqual(
                        pinned[gate.KEY_SETTLED_DOCS_SHA], MEASURED_CANDIDATE_SHA,
                    )
                    self.assertEqual(
                        pinned[documenting.DOCS_CHECKED_SHA],
                        MEASURED_CANDIDATE_SHA,
                    )
                    continue
                self.assertEqual(
                    mocks[documenting.PUSH_BRANCH].call_args.kwargs[gate.REVISION],
                    MEASURED_CANDIDATE_SHA,
                )
                self.assertEqual(
                    pinned[gate.KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA,
                )
                self._assert_handed_off_once(github)

    def test_a_failed_push_pins_the_amended_head(self) -> None:
        # The approval goes down before the push and the park behind it writes
        # the record as it stands, so a retry reading either back finds the
        # commit that was measured rather than the head the pass began at.
        github, _mocks = self._fresh_pass(
            added_lines=UNDER_THE_CEILING,
            push_branch=False,
            head_shas=[
                ENTERED_HEAD,
                documenting.SHA_UNREFERENCED,
                MEASURED_CANDIDATE_SHA,
            ],
        )

        pinned = self._pinned(github)
        self.assertEqual(pinned[gate.KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(
            pinned[documenting.DOCS_CHECKED_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertEqual(
            pinned[documenting.PARK_REASON], documenting.PARK_PUSH_FAILED,
        )

    def test_recovered_referenced_records_its_head(self) -> None:
        # The idempotent road: a commit an earlier tick already amended needs
        # no replacement, and this one anchors no head of its own -- no agent
        # ran for it to be anchored against. The record still has to name what
        # the tick publishes, so `docs_checked_sha` is that recovered commit
        # wherever the tick ends with the record written and nothing pushed.
        for run_options, named in UNPUBLISHED_RECORDS:
            with self.subTest(**run_options):
                github, mocks = self._recovered_pass(
                    commit_message=RECOVERED_REFERENCED_MESSAGE, **run_options,
                )

                mocks[documenting.AMEND_COMMIT_MESSAGE].assert_not_called()
                pinned = self._pinned(github)
                self.assertEqual(pinned[named], MEASURED_CANDIDATE_SHA)
                self.assertEqual(
                    pinned[documenting.DOCS_CHECKED_SHA], MEASURED_CANDIDATE_SHA,
                )

    def test_switched_off_leaves_the_head_it_began_at(self) -> None:
        # With the switch off no reference is added and no commit is replaced,
        # so the pass publishes the commit it made and a hold records the head
        # the pass anchored on before its spawn.
        with patch.object(config, documenting.PR_REF_IN_SUBJECT, False):
            github, mocks = self._fresh_pass(
                added_lines=PAST_THE_CEILING,
                head_shas=[ENTERED_HEAD, MEASURED_CANDIDATE_SHA],
            )

        mocks[documenting.AMEND_COMMIT_MESSAGE].assert_not_called()
        pinned = self._pinned(github)
        self.assertEqual(pinned[documenting.DOCS_CHECKED_SHA], ENTERED_HEAD)
        self.assertEqual(
            pinned[gate.KEY_SETTLED_DOCS_SHA], MEASURED_CANDIDATE_SHA,
        )


if __name__ == "__main__":
    unittest.main()
