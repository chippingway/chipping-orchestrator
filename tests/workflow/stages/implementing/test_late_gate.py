# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The size gate between a committed candidate and the branch it publishes on.

Every clean committed candidate goes through one seam, so what these pin down
is what that seam decides once it has a number: a candidate at or below the
ceiling publishes and goes to review, one past it is held unpublished under the
adjudication label, and two are never measured at all -- the commit an
adjudication accepted, and every candidate while the switch is off. What a
reading nobody could take costs, and the evidence rules a retry re-reads it
under, are in the recovery module beside this one.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
)
from tests.support.fakes import FakePR, FakePRRef
from tests.workflow import fixtures as _fixtures
from tests.workflow.stages.implementing import late_gate_test_support as support

_OTHER_SHA = "d" * _fixtures.SHA_LENGTH
_KEY_APPROVED_SHA = "late_approved_sha"
# The stage's own receipt, which admits a commit the remote already carries
# without a reading -- and which leaves this seam's debt to the publication.
_KEY_RECEIPT_SHA = "implementing_published_sha"
_KEY_APPROVED_BASIS = "late_approved_basis"
_KEY_PR_NUMBER = "pr_number"
# The pull request the receipt names, written with it by the push that landed
# rather than by the relabel behind it.
_KEY_RECEIPT_PR = "implementing_published_pr"
# The head that push replaced, `null` for an initial publication that froze
# none. Written with the two beside it, so a group missing the key is one no
# tick produced.
_KEY_RECEIPT_LEASE = "implementing_published_lease"
_KEY_BRANCH = "branch"
# The pull request this stage's own push opened, which the receipt beside it
# is only evidence for while the remote still agrees.
_DELIVERED_PR_NUMBER = 812
_DECOMPOSING = (support.GATE_ISSUE_NUMBER, _fixtures.LABEL_DECOMPOSING)
_STAGE_IMPLEMENTING = "implementing"
_DECOMPOSE = "DECOMPOSE"
_CANDIDATE_MOVED = "late_candidate_moved"
_POST_PUBLICATION = "late_post_publication"
_SOURCE_STAGE = "late_source_stage"
_PUBLISHED_PR = "late_published_pr_number"
_PUBLISHED_SHA = "late_published_sha"

# A checkout that answers the gate with the measured commit and the
# publication with a descendant: the race the handoff refuses.
_MOVING_HEAD = (
    FrozenCommit(sha=_fixtures.MEASURED_CANDIDATE_SHA),
    FrozenCommit(sha=_OTHER_SHA),
)

# The same race one reading further in, for an issue whose record already
# names a commit: the reconciliation ahead of the spawn proves it before the
# gate sees the issue at all, so the descendant is the third answer rather
# than the second.
_RECONCILED_THEN_MOVING = (
    FrozenCommit(sha=_fixtures.MEASURED_CANDIDATE_SHA),
    *_MOVING_HEAD,
)

class LateGateVerdictTest(support._GateCase, unittest.TestCase):
    """What a measured candidate earns: the ordinary push, or adjudication."""

    def test_a_small_candidate_publishes(self) -> None:
        # The ordinary world: measured, under the ceiling, and published: the
        # branch is pushed, a pull request opened, and the issue handed to
        # review. The generation is dropped with it --
        # a frozen candidate freezes this branch out of the base refresh, and a
        # record carried into the stages that close the issue reads as a live
        # cycle a close should end. What outlives it is the cycle it was, so
        # the next candidate on this issue cannot answer to the same number.
        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_published(mocks)
        self.assertEqual(len(self.github.opened_prs), 1)
        self.assertIn(
            (support.GATE_ISSUE_NUMBER, _fixtures.LABEL_VALIDATING),
            self.github.label_history,
        )
        pinned = self._pinned()
        self.assertNotIn(support.KEY_CANDIDATE_SHA, pinned)
        self.assertEqual(pinned[support.KEY_RETIRED_CYCLE], 1)

    def test_an_oversized_candidate_is_held(self) -> None:
        # Nothing published: no push, no pull request, and the label handed to
        # the adjudication rather than to review.
        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_held(mocks)
        self.assertEqual(self.github.label_history, [_DECOMPOSING])

    def test_the_hold_records_what_it_measured(self) -> None:
        # The record the coordinator is handed names both commits, the ceiling
        # they were measured under, the boundary they stand at, and the
        # identities every later record is correlated by -- because that record
        # is the whole of what the adjudication reconciles from.
        self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_frozen(additions=support.OVERSIZED_ADDITIONS)
        pinned = self._pinned()
        self.assertEqual(pinned[support.KEY_THRESHOLD], config.MAX_ADDED_LINES)
        self.assertEqual(pinned[support.KEY_CYCLE_ID], 1)
        self.assertEqual(pinned[support.KEY_GENERATION], 1)
        self.assertEqual(
            pinned[support.KEY_CURRENT_ISSUE], support.GATE_ISSUE_NUMBER,
        )
        self.assertEqual(
            pinned[support.KEY_ROOT_ISSUE], support.GATE_ISSUE_NUMBER,
        )
        self.assertEqual(pinned[support.KEY_LINEAGE_DEPTH], 0)

    def test_the_hold_records_no_publication(self) -> None:
        # An initial publication is the side of the gate that has no pull
        # request behind it, and the record says so by carrying none of the
        # publication group -- which is what lets a live pinned comment answer
        # the question with no migration having reached it.
        self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        pinned = self._pinned()
        for absent in (
            _POST_PUBLICATION, _SOURCE_STAGE, _PUBLISHED_PR, _PUBLISHED_SHA,
        ):
            self.assertNotIn(absent, pinned)

    def test_the_hold_says_what_it_waits_for(self) -> None:
        self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        notice = self.github.posted_comments[-1][1]
        self.assertIn(str(support.OVERSIZED_ADDITIONS), notice)
        self.assertIn(str(config.MAX_ADDED_LINES), notice)
        self.assertIn(_fixtures.MEASURED_CANDIDATE_SHA, notice)

    def test_a_candidate_at_the_ceiling_publishes(self) -> None:
        # Strictly past, so the trigger cannot move by one line when the
        # threshold is retuned.
        mocks = self._run_gate(added_lines=config.MAX_ADDED_LINES)

        self._assert_published(mocks)


class LateGateRetirementTest(support._GateCase, unittest.TestCase):
    """A retirement is durable before the publication it licenses.

    What follows one is a push, a pull request, and the label that hands the
    issue to review -- and the tick's own pinned write comes after all of it.
    A crash in that window would leave a published pull request under
    `workflow:validating` over a record that still says `measuring`: the
    branch frozen out of the base refresh for good, and a close on that issue
    read by the cancellation guard as a live cycle to end.
    """

    def test_a_small_candidate_retires_first(self) -> None:
        recorded = support._RecordAtHandoff(self.github)

        with recorded.held():
            self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self.assertNotIn(support.KEY_CANDIDATE_SHA, recorded.pinned)
        self.assertEqual(recorded.pinned[support.KEY_RETIRED_CYCLE], 1)


class LateGatePushTest(support._GateCase, unittest.TestCase):
    """The push is named against the commit that passed, not against HEAD.

    The gate reads the checkout and the publication writes it, and `HEAD`
    between those two moments is not necessarily the commit that passed:
    another tick, an operator, or a descendant the timeout cleanup raced can
    move it. A push that named nothing would publish whatever it had become
    while the record named the commit that was measured.
    """

    def test_the_measured_commit_is_pushed(self) -> None:
        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self.assertEqual(
            mocks[support.PUSH_BRANCH].call_args.kwargs["revision"],
            _fixtures.MEASURED_CANDIDATE_SHA,
        )

    def test_the_exempt_commit_is_pushed(self) -> None:
        self._seed(**_fixtures._authorized_exemption())

        mocks = self._run_gate()

        self.assertEqual(
            mocks[support.PUSH_BRANCH].call_args.kwargs["revision"],
            _fixtures.MEASURED_CANDIDATE_SHA,
        )

    def test_a_moved_checkout_publishes_nothing(self) -> None:
        # The push would be safe on its own -- it names the approved commit --
        # but the CHECKOUT is what every stage past this one works from: the
        # reviewer reads a head ahead of the pushed branch as unpushed work to
        # publish, the squash rewrites what is on it, and the docs pass commits
        # on top. A worktree left on a descendant would carry an implementation
        # the gate never saw into review, a merge later.
        mocks = self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            candidate_commit=_MOVING_HEAD,
        )

        self._assert_held(mocks)
        self.assertEqual(self.github.label_history, [])
        pinned = self._pinned()
        self.assertTrue(pinned[support.AWAITING_HUMAN])
        self.assertEqual(pinned[support.PARK_REASON], _CANDIDATE_MOVED)

    def test_an_approved_commit_is_not_re_decided(self) -> None:
        # The recovery proves the checkout is on the commit an approval owes a
        # push for, and the gate reads that head again for itself with the
        # worktree writable in between. Measured there, the replacement is
        # approved in the original's place and pushed -- and the checkout
        # guard below finds a head matching what the gate just decided, so
        # nothing downstream catches it. The approval a reading or a human
        # stood behind would be gone, for a commit neither ever saw.
        self._seed(**{_KEY_APPROVED_SHA: _fixtures.MEASURED_CANDIDATE_SHA})

        mocks = self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            candidate_commit=_MOVING_HEAD,
        )

        self._assert_held(mocks)
        self.assertEqual(self.github.label_history, [])
        pinned = self._pinned()
        self.assertTrue(pinned[support.AWAITING_HUMAN])
        self.assertEqual(pinned[_KEY_APPROVED_SHA], _fixtures.MEASURED_CANDIDATE_SHA)

    def test_a_moved_checkout_says_both_commits(self) -> None:
        self._run_gate(
            added_lines=support.SMALL_ADDITIONS,
            candidate_commit=_MOVING_HEAD,
        )

        notice = self.github.posted_comments[-1][1]
        self.assertIn(_fixtures.MEASURED_CANDIDATE_SHA, notice)
        self.assertIn(_OTHER_SHA, notice)

    def test_an_unmeasured_branch_is_named_too(self) -> None:
        # The switch keeps a candidate out of the MEASUREMENT; it does not
        # make it unnameable. A push named against nothing publishes whatever
        # the branch has become by the time git runs it, and leaves nothing on
        # the issue afterwards saying which commit that was -- so the checkout
        # names it where the gate did not.
        with patch.object(config, _DECOMPOSE, False):
            mocks = self._run_gate()

        self._assert_unmeasured(mocks)
        self.assertEqual(
            mocks[support.PUSH_BRANCH].call_args.kwargs["revision"],
            _fixtures.MEASURED_CANDIDATE_SHA,
        )


class MovedCheckoutDebtTest(support._GateCase, unittest.TestCase):
    """What the park a moved checkout takes records about the push it owes.

    The refusal stands exactly where the publication would have minted that
    debt, so the group it writes is the only account a later tick has of what
    the push it is about to make rests on -- and the one thing it may not do
    is invent one the record never carried.
    """

    def test_a_moved_checkout_says_what_it_rests_on(self) -> None:
        # The refusal stands exactly where the publication would have minted
        # the debt this seam owes: a candidate the RECEIPT admitted skipped
        # the reading, the gate's own debt writer declines here because no
        # publication was frozen to lease a push against, and the intent that
        # would have recorded one is never reached. Written as the commit
        # alone, the tick that comes back to this park would have to infer
        # whose decision the push it is about to make rests on.
        self._delivered_by_this_stage()

        mocks = self._run_gate(
            added_lines=support.OVERSIZED_ADDITIONS,
            candidate_commit=_MOVING_HEAD,
        )

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        pinned = self._pinned()
        self.assertEqual(pinned[support.PARK_REASON], _CANDIDATE_MOVED)
        self.assertEqual(pinned[_KEY_APPROVED_SHA], _fixtures.MEASURED_CANDIDATE_SHA)
        self.assertEqual(
            pinned[_KEY_APPROVED_BASIS],
            str(_late_approval_reading.LateApprovalBasis.UNMEASURED),
        )

    def test_a_legacy_debt_is_not_upgraded(self) -> None:
        # The shape an older build left: the exempt commit named as owed a
        # push, with no account of what that debt rests on. Stamped
        # `unmeasured` as the park goes up, it would stop reading as unknown
        # and become debt this workflow owns -- so the checkout coming back
        # would publish an adjudicated commit without anything revalidating
        # the operator authorization behind it.
        self._seed(**{
            **_fixtures._authorized_exemption(),
            _KEY_APPROVED_SHA: _fixtures.MEASURED_CANDIDATE_SHA,
        })

        self._run_gate(
            added_lines=support.OVERSIZED_ADDITIONS,
            candidate_commit=_RECONCILED_THEN_MOVING,
        )

        pinned = self._pinned()
        self.assertEqual(pinned[support.PARK_REASON], _CANDIDATE_MOVED)
        self.assertEqual(pinned[_KEY_APPROVED_SHA], _fixtures.MEASURED_CANDIDATE_SHA)
        self.assertIsNone(pinned[_KEY_APPROVED_BASIS])

    def test_a_restored_checkout_publishes_on_it(self) -> None:
        # And what the complete record buys: the poll after an operator puts
        # the worktree back reads one commit owed a push and the grounds it is
        # owed on, and publishes without asking the size question again.
        self._delivered_by_this_stage()
        self._run_gate(
            added_lines=support.OVERSIZED_ADDITIONS,
            candidate_commit=_MOVING_HEAD,
        )

        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_published(mocks)

    def _delivered_by_this_stage(self) -> None:
        """The receipt this stage's own push left, and the publication it is.

        All of them, because the receipt is only evidence beside them: the
        note naming the commit, the pull request that push opened -- recorded
        with the note, since the relabel that records `pr_number` is the write
        this window is missing -- and the branch both are about. Read on its
        own the note says what was PUSHED and nothing about where it went or
        whether it is still there.
        """
        branch = _fixtures._issue_branch(support.GATE_ISSUE_NUMBER)
        opened = FakePR(
            number=_DELIVERED_PR_NUMBER,
            head_branch=branch,
            head=FakePRRef(sha=_fixtures.MEASURED_CANDIDATE_SHA, ref=branch),
        )
        self.github.add_pr(opened)
        self.github.existing_open_pr[branch] = opened
        self._seed(**{
            _KEY_RECEIPT_SHA: _fixtures.MEASURED_CANDIDATE_SHA,
            # Written with it and `null`, as an initial publication records
            # it: that push froze no head to be pinned to, and the key still
            # goes down -- the three are one write.
            _KEY_RECEIPT_LEASE: None,
            _KEY_RECEIPT_PR: _DELIVERED_PR_NUMBER,
            _KEY_PR_NUMBER: _DELIVERED_PR_NUMBER,
            _KEY_BRANCH: branch,
        })


class LateGateTelemetryTest(support._GateCase, unittest.TestCase):
    """One call, two streams, and a record that joins without pinned state."""

    def test_the_audit_stream_carries_it(self) -> None:
        self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        measured = self._records(support.EVENT_LATE_MEASUREMENT)
        self.assertEqual(len(measured), 1)
        self._assert_record(measured[0], support.OVERSIZED_ADDITIONS)

    def test_the_analytics_stream_carries_it(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            log_path = Path(scratch) / "analytics.jsonl"
            self._run_gate(
                added_lines=support.SMALL_ADDITIONS,
                analytics_log_path=log_path,
            )
            recorded = [
                record for record in _fixtures._analytics_records(log_path)
                if record.get("event") == support.EVENT_LATE_MEASUREMENT
            ]

        self.assertEqual(len(recorded), 1)
        self._assert_record(recorded[0], support.SMALL_ADDITIONS)

    def _assert_record(self, record: dict, additions: int) -> None:
        self.assertEqual(record["stage"], _STAGE_IMPLEMENTING)
        self.assertEqual(record["issue"], support.GATE_ISSUE_NUMBER)
        self.assertEqual(record["source_sha"], _fixtures.MEASURED_CANDIDATE_SHA)
        self.assertEqual(record["base_sha"], _fixtures.MEASURED_BASE_SHA)
        self.assertEqual(record["additions"], additions)
        self.assertEqual(record["threshold"], config.MAX_ADDED_LINES)
        self.assertEqual(record["cycle_id"], 1)
        self.assertEqual(record["root_issue"], support.GATE_ISSUE_NUMBER)


class LateGateExemptionTest(support._ParkedRetryCase, unittest.TestCase):
    """The one commit an adjudication accepted, and nothing beside it.

    The two cases that decide by commit id are asked of an issue with agent
    runs to spare and of one with none left, because the ledger beside this
    gate must not move either answer: a spent lifetime is not a way past the
    ceiling, and it is not a reason to re-adjudicate a commit somebody already
    accepted. Nothing here spawns, so neither reading charges a run.
    """

    def test_an_exemption_retires_the_record(self) -> None:
        # A guidance resume can put the checkout back on a commit an
        # adjudication already accepted, while the record still names the
        # candidate that resume was about. Publishing the exemption without
        # dropping that record would leave a generation pinned at `measuring`
        # over work nothing is going to publish -- freezing the branch out of
        # the base refresh and carrying a live-looking cycle into the stages
        # that close the issue.
        mocks = self._resumed_onto_the_exemption()

        self._assert_unmeasured(mocks)
        self._assert_published(mocks)
        pinned = self._pinned()
        self.assertNotIn(support.KEY_CANDIDATE_SHA, pinned)
        self.assertEqual(pinned[support.KEY_RETIRED_CYCLE], 1)

    def test_an_exemption_retires_before_the_push(self) -> None:
        recorded = support._RecordAtHandoff(self.github)

        with recorded.held():
            self._resumed_onto_the_exemption()

        self.assertNotIn(support.KEY_CANDIDATE_SHA, recorded.pinned)
        self.assertEqual(recorded.pinned[support.KEY_RETIRED_CYCLE], 1)

    def test_an_accepted_commit_is_not_measured(self) -> None:
        # Without this the gate would measure the accepted candidate past the
        # same ceiling and adjudicate it again, forever.
        for runs_left, ledger in support.LEDGERS.items():
            with self.subTest(runs_left=runs_left):
                self._seed(**{**_fixtures._authorized_exemption(), **ledger})

                mocks = self._run_gate()

                self._assert_unmeasured(mocks)
                self._assert_published(mocks)
                self._assert_charged_nothing(ledger)

    def test_work_past_it_is_a_fresh_candidate(self) -> None:
        for runs_left, ledger in support.LEDGERS.items():
            with self.subTest(runs_left=runs_left):
                self._seed(**{
                    **_fixtures._authorized_exemption(_OTHER_SHA), **ledger,
                })

                mocks = self._run_gate(
                    added_lines=support.OVERSIZED_ADDITIONS,
                )

                self._assert_measured(mocks)
                self._assert_held(mocks)
                self._assert_charged_nothing(ledger)

    def _resumed_onto_the_exemption(self):
        """A resume that put the checkout back on an accepted commit.

        The record names the candidate the guidance was about; the checkout
        ends on the commit an earlier adjudication accepted. Both are true at
        once, which is the coexistence this subject is about.
        """
        self._seed(**{
            support.AWAITING_HUMAN: True,
            support.PARK_REASON: support.PARK_MEASUREMENT_FAILED,
            support.LAST_ACTION_COMMENT_ID: support.PRIOR_ACTION_COMMENT_ID,
            "dev_agent": "codex",
            "dev_session_id": support.DEV_SESSION,
            **_fixtures._authorized_exemption(),
            **support.recorded_generation(candidate_sha=_OTHER_SHA),
        })
        self._reply("put it back on the commit we already agreed")
        return self._run_gate(
            run_agent=_fixtures._agent(
                session_id=support.DEV_SESSION,
                last_message=_fixtures._reported("reset"),
            ),
            head_shas=(_OTHER_SHA, _fixtures.MEASURED_CANDIDATE_SHA),
        )


class LateGateSwitchTest(support._GateCase, unittest.TestCase):
    """`DECOMPOSE=off` keeps new work out, and decides nothing already in."""

    def test_a_new_candidate_is_not_measured(self) -> None:
        # Nothing is decided about it and nothing is recorded for it: the
        # switch keeps a candidate out of the gate rather than answering the
        # gate's question cheaply, so the issue leaves carrying no generation
        # at all.
        with patch.object(config, _DECOMPOSE, False):
            mocks = self._run_gate()

        self._assert_unmeasured(mocks)
        self._assert_published(mocks)
        self.assertNotIn(support.KEY_CYCLE_ID, self._pinned())

    def test_a_recorded_one_is_reconciled(self) -> None:
        # The switch decides whether work ENTERS the gate. A candidate this
        # issue already froze is in it, and turning the switch off must not
        # publish it as though a verdict had been recorded for it.
        self._seed(**support.recorded_generation())

        with patch.object(config, _DECOMPOSE, False):
            mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_measured(mocks)
        self._assert_held(mocks)
        self.assertIn(_DECOMPOSING, self.github.label_history)

    def test_the_debt_it_mints_says_what_it_rests_on(self) -> None:
        # The switch is the one road that proves no candidate at all, so the
        # commit the debt names comes off the CHECKOUT rather than off a gate
        # verdict -- and the publication mints the approval itself. Read where
        # a crash leaves one standing: the push failed, so nothing spent it,
        # and the tick that comes back to it would otherwise have to guess
        # whether a human's gesture stands behind a debt it spends without
        # asking anybody.
        with patch.object(config, _DECOMPOSE, False):
            self._run_gate(push_branch=False)

        pinned = self._pinned()
        self.assertEqual(pinned[_KEY_APPROVED_SHA], _fixtures.MEASURED_CANDIDATE_SHA)
        self.assertEqual(
            pinned[_KEY_APPROVED_BASIS],
            str(_late_approval_reading.LateApprovalBasis.UNMEASURED),
        )

    def test_a_restart_publishes_it_without_measuring(self) -> None:
        # And what the record buys, end to end. A fresh process reads the
        # comment that crash left -- the park answered, the switch since
        # turned back on, a count seeded well past the ceiling -- and finds
        # one commit named as owed a push. Read as work nobody has ruled on
        # instead, the branch the first tick was publishing would be routed
        # to adjudication.
        with patch.object(config, _DECOMPOSE, False):
            self._run_gate(push_branch=False)
        self._seed(**{
            key: written for key, written in self._pinned().items()
            if key not in (support.AWAITING_HUMAN, support.PARK_REASON)
        })

        mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_published(mocks)
        self.assertNotIn(_DECOMPOSING, self.github.label_history)
        pinned = self._pinned()
        self.assertIsNone(pinned[_KEY_APPROVED_SHA])
        self.assertIsNone(pinned[_KEY_APPROVED_BASIS])


if __name__ == "__main__":
    unittest.main()
