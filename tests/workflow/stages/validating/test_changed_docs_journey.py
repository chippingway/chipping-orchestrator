# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A final-docs pass that changes the pull request, reported, reviewed, and documented again with no human.

Walked whole by the dispatcher from an approval its squash published: the docs
pass commits on top of the squash and its push lands, and the pass hands the
pull request back to `validating` rather than on to `in_review` -- owing a
report of the docs commit, its evidence and approval retired. The developer
is asked for that report alone, which settles as REPORT: READY without a reply
or a commit, and leaves the approved report standing as it was written; the
fresh reviewer is handed the new report and has to bring evidence of its own
on the docs commit, and only then does the next final-docs pass run, finding
nothing left to write, and hand the issue to `in_review`. No stale-report park
is taken, and one run of each role is charged.

The same holds through a crash in every window the hand-back and the report
behind it open: a push whose answer was lost, a hand-back write that never
landed or landed with its answer lost, a relabel that failed behind it, and
each place the report's publication can stop short. With no configured
`VERIFY_COMMANDS` the reviewer's own run on the docs commit is the evidence,
and a reviewer reusing the evidence the hand-back retired is refused.

The report debt keeps the head the docs commit replaced through a recovery
that republishes the commit over itself, and the hand-back never lands with
the evidence it outdated still current: measured whole, with its approval
cleared first, and held where the comment has no room to retire it.
"""
from __future__ import annotations

import contextlib
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.repo_values import SHA_LENGTH
from tests.workflow.stages.validating import (
    changed_docs_journey_support as _docs,
    changed_docs_room_support as _room,
    evidence_round_test_support as _round,
    report_refresh_crashes as _crashes,
    review_verdict_readings as _read,
    squash_rebase_journey_support as _journey,
)

DOCS_HEAD = _docs.DOCS_HEAD

SQUASHED = _docs.SQUASHED

# What the hand-back leaves on the pinned comment, as `handed_back` reads it:
# the debt from the squash it replaced onto the docs commit beside the mark
# naming that commit, the commit stamped with no verdict, no current evidence
# -- the approval's run superseded by the squash's carry, and the carry
# invalidated -- and no approval.
HANDED_BACK = (
    ((SQUASHED, DOCS_HEAD), DOCS_HEAD), (DOCS_HEAD, None), None, ("superseded", "invalidated"), False,
)

# The parked reviewer that reuses retired evidence leaves, as the label, the
# park, and the runs spawned.
REUSE_REFUSED = (WorkflowLabel.VALIDATING, "reviewer_unverified", _docs.ONE_OF_EACH[:3])

# The run a reviewer's declared run on the docs commit publishes, under an
# empty configuration: the reviewer's own, on the docs commit.
REVIEWERS_RUN = (EvidenceSource.REVIEWER_REPORTED, DOCS_HEAD, DOCS_HEAD)

# The labels the issue moves through where a base refresh rebases the docs
# commit once it is handed back: that refresh's own route back to
# `workflow:validating` sits beside the hand-back's.
REBASED_ON_THE_WAY = (WorkflowLabel.DOCUMENTING, WorkflowLabel.VALIDATING, *_docs.DOCUMENTED_AGAIN[1:])

# A docs receipt's lease as no gate writes it, and the field it is written to.
DAMAGED_LEASE = "not-a-commit"

SETTLED_DOCS_LEASE = "docs_settled_lease"

# A commit the checkout went to while the docs push was out, which leaves the
# push landed and its handoff parked for the checkout's recovery.
MOVED_AFTER_PUSH = "de" * (SHA_LENGTH // 2)

# Every window a crash can cut the walk short in, as the context the docs
# dispatch runs under -- None where it runs through -- and the context the
# refresh's does. The push's answer lost leaves the gate's approval for the
# next tick to settle; the hand-back write dying leaves the gate's receipt,
# which the next tick finishes from; the write landing with its answer lost,
# or the relabel behind it failing, leaves the debt and mark the dispatcher
# finishes the relabel from; and every place the report's publication stops
# short is finished by a later tick.
CRASHES = (
    ("the push's answer lost", "push", contextlib.nullcontext),
    ("the hand-back's write dying", _docs.dying_on_the_hand_back, contextlib.nullcontext),
    ("the hand-back's answer lost", _docs.losing_the_hand_back, contextlib.nullcontext),
    ("the relabel failing", _docs.dying_on_the_relabel, contextlib.nullcontext),
    ("the report's post refused", None, _crashes.refusing_the_post),
    ("the report's answer lost", None, _crashes.losing_the_response),
    ("a crash before the report's binding", None, _crashes.dying_before_the_binding),
    ("a crash on the report's settlement", None, _crashes.dying_on_the_settlement),
)


class ChangedDocsJourneyTest(_docs._ChangedDocsWalk, unittest.TestCase):
    """A content-changing docs pass earns a fresh report and review before the next final-docs pass."""

    def test_changed_docs_are_reported_and_reviewed(self) -> None:
        # The docs commit retires what the approval rested on and owes a
        # report of itself; the developer writes it with nobody asked, the
        # approved report left as it was; the reviewer is handed it and
        # approves the docs commit on a run of its own; and the next docs pass
        # changes nothing and hands the issue to `in_review`. Later ticks
        # spawn, charge, and post nothing more.
        self.walks_into_documenting()
        approved = self.pull_request.issue_comments[0].body

        self.changes_the_docs()

        self.assertEqual(self.handed_back(), HANDED_BACK)
        self.refreshes()
        self.assert_refreshed_over(approved)
        self.approved_into_review(DOCS_HEAD)
        self.assert_reviewer_handed_the_report()
        self.assert_quiet_after()
        self.assert_one_of_each()

    def test_a_crash_anywhere_ends_in_one_of_each(self) -> None:
        # Whichever window a process dies in, the next dispatch finishes what
        # landed -- the gate's settlement, the hand-back from its receipt, the
        # relabel from its debt, the report from its record -- and the walk
        # ends with one run of each role and nothing parked for a human.
        for name, docs_window, report_window in CRASHES:
            with self.subTest(name):
                self.setUp()
                self.walks_into_documenting()
                self.changes_the_docs_under(docs_window)
                with report_window(self):
                    self.refreshes()

                self.approved_into_review(DOCS_HEAD)

                self.assert_one_of_each()

    def test_a_held_base_refresh_keeps_the_lineage(self) -> None:
        # A base refresh behind a hand-back that never landed holds the
        # branch still: the receipt is the docs pass's, and a rebase first
        # would leave a debt naming the docs commit as the head replaced,
        # which no settled report is about. The next dispatch hands the docs
        # commit back, and a rebase behind that carries the debt onto the head
        # it publishes, still from the squash -- so the report of the approved
        # commit is refreshed for the rebased head, once, with no human.
        self.walks_into_a_lost_hand_back()
        self.base_refresh(_journey.ADVANCED)
        self.assert_held_still()
        self.dispatched()
        self.base_refresh(_journey.ADVANCED)
        self.refreshes()

        self.approved_into_review(_journey.ADVANCED)

        self.assertIn(_docs.APPROVED_REPORT, self.spawned(_journey.REFRESHER)[0])
        self.assert_one_of_each(_journey.ADVANCED, rounds=0, walked=REBASED_ON_THE_WAY)

    def test_a_moved_context_still_hands_back(self) -> None:
        # The approval's evidence stops standing once the verification context
        # moves, which is no question for a pass the receipts prove published:
        # its hand-back is finished first, retiring that evidence and recording
        # the report debt, rather than the issue going back with none.
        self.walks_into_a_lost_hand_back()
        self.moves_the_context()

        self.dispatched()

        self.assertEqual(self.handed_back(), HANDED_BACK)
        self.refreshes()
        self.approved_into_review(DOCS_HEAD)
        self.assert_one_of_each()

    def test_the_review_it_buys_counts_once(self) -> None:
        # The hand-back spends one review round in the write that records it,
        # so where the approval left none to spare the review it buys parks on
        # the cap rather than running -- the report refreshed all the same, and
        # nothing spawned or spent past that park.
        self.enterContext(patch.object(config, "MAX_REVIEW_ROUNDS", 1))
        self.walks_into_documenting()
        self.changes_the_docs()
        self.refreshes()

        for _ in range(3):
            self.dispatched()

        pinned = self.pinned()
        capped = (self.roles(), pinned["park_reason"], pinned["review_round"])
        self.assertEqual(capped, (_docs.ONE_OF_EACH[:2], "review_cap", 1))
        self.assertEqual(self.spent_since(self.charged)[0], 2)

    def test_empty_config_takes_the_reviewers_run(self) -> None:
        # With no configured command the orchestrator runs nothing on the
        # docs commit, so the evidence the approval of it rests on is the
        # reviewer's own run there, published as the reviewer reported it.
        self.enterContext(patch.object(config, "VERIFY_COMMANDS", ()))
        self.walks_into_documenting()
        self.changes_the_docs()
        self.refreshes()

        self.approved_into_review(DOCS_HEAD)

        latest = _read.artifacts(self)[-1]
        self.assertEqual((latest.source, latest.tested_sha, latest.target_head), REVIEWERS_RUN)
        self.assert_one_of_each()

    def test_retired_evidence_is_not_reused(self) -> None:
        # The squash's carry was the evidence the approval of the squash rested
        # on, and the hand-back retired it: a reviewer approving the docs
        # commit by reusing it is refused, and the docs pass does not run.
        self.walks_into_documenting()
        reuse = _round.declared_reuse(self.current_evidence().content_revision)
        self.changes_the_docs()
        self.refreshes()

        self.dispatched((_journey.REVIEWER, _round.reviewer(reuse)))

        label = self.labels()[-1]
        park = self.pinned()["park_reason"]
        self.assertEqual((label, park, self.roles()), REUSE_REFUSED)


class ChangedDocsProvenanceTest(_docs._ChangedDocsWalk, unittest.TestCase):
    """What the hand-back records survives the roads around it, and lands whole or not at all."""

    def test_a_moved_checkout_keeps_the_lease(self) -> None:
        # The push lands while the checkout moves under it, so the handoff
        # parks and the recovery republishes the docs commit over itself,
        # which leaves the code-publication receipt leased to the docs commit.
        # The lease the gate recorded beside the docs receipt is the head the
        # docs commit replaced, so the debt still names the squash and the
        # report of the approved commit is refreshed with no human.
        self.walks_into_documenting()
        self.changes_the_docs(
            candidate_commit=(FrozenCommit(sha=DOCS_HEAD), FrozenCommit(sha=MOVED_AFTER_PUSH)),
        )
        self.dispatched()

        self.assertEqual(self.handed_back(), HANDED_BACK)
        self.refreshes()
        self.approved_into_review(DOCS_HEAD)
        self.assert_one_of_each()

    def test_a_damaged_lease_holds_the_hand_back(self) -> None:
        # A docs receipt whose lease is no commit names no head the report
        # debt could be owed from, so nothing is handed back on it: no debt,
        # no relabel, no developer asked for a report, and the record left
        # exactly as it stands for a human to repair.
        self.walks_into_a_lost_hand_back()
        state = self.github.read_pinned_state(self.issue)
        state.set(SETTLED_DOCS_LEASE, DAMAGED_LEASE)
        self.github.write_pinned_state(self.issue, state)

        self.dispatched()
        self.refreshes()

        self.assert_held_still()
        pinned = self.pinned()
        held = (self.roles(), pinned[SETTLED_DOCS_LEASE], pinned["docs_settled_sha"])
        self.assertEqual(held, ((_journey.DOCUMENTER,), DAMAGED_LEASE, DOCS_HEAD))

    def test_the_retirement_is_measured_whole(self) -> None:
        # A comment with room for the hand-back only once its approval is
        # written null: measured with that approval cleared first, the
        # evidence's retirement fits, and the hand-back lands with it retired
        # rather than leaving it current behind the approval's removal.
        self.walks_into_a_lost_hand_back()
        _room.fills_with_the_approval_kept(self)

        self.dispatched()

        self.assertEqual(self.labels()[-1], WorkflowLabel.VALIDATING)
        self.assertEqual(self.handed_back(), HANDED_BACK)

    def test_no_room_to_retire_holds_the_hand_back(self) -> None:
        # One byte too few to retire the evidence holds the whole hand-back:
        # nothing is announced, recorded, or relabelled, and the receipt the
        # gate left stands -- so the tick after a human makes room hands the
        # docs commit back with its evidence retired, announcing it once.
        self.walks_into_a_lost_hand_back()
        _room.fills_up_to_the_retirement(self)
        told = len(self.pull_request.issue_comments)

        self.dispatched()

        self.assert_held_still()
        held = len(self.pull_request.issue_comments)
        _room.makes_room(self)
        self.dispatched()
        self.assertEqual(self.handed_back(), HANDED_BACK)
        announced = len(self.pull_request.issue_comments)
        self.assertEqual((held, announced), (told, told + 1))


if __name__ == "__main__":
    unittest.main()
