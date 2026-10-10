# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A changed contribution handed to a fresh adjudication, on a real repo, tick by tick.

An oversized change a human authorized is on its pull request when the base
advances under the file it edits. The refresh replays the branch cleanly, the
transfer permit refuses a contribution that is no longer the one the human
ruled on, and the size gate measures the replay past the ceiling and hands it
to an adjudication. Everything after that is the production ticks: the
attempt goes to the live generation, the dispatcher runs the adjudication
rather than holding it behind the anchor, the human authorizes the replay,
and the settlement publishes it -- leased to the head the pull request stood
on, owing the report a head this orchestrator rewrote is owed -- and hands it
to review, whichever stage it was rebased under, and on through the final docs
pass.

The pull request stays where the human left it until that authorization, a
push somebody else made in between refuses the publication, and a process
lost at any write of the handoff comes back to the same adjudication of the
same replay -- with no developer run, no reset, and no verdict reused, an
operator's retry before it included. So does a pair an earlier build stranded
under its own park, the retry that park was answered with spent with the
attempt, while a reply that says more reaches the developer as guidance; a
park somebody else left holds the adjudication instead, until a human answers
it.
"""
from __future__ import annotations

import unittest

from orchestrator.git.base_sync import persistence as _persistence
from tests.git.base_sync import journey_push_support as windows
from tests.git.base_sync.journey_adjudication_support import _authorizes, replies
from tests.git.base_sync.journey_assertions import ADJUDICATOR, KEY_REWRITE_DEBT, REVIEWER
from tests.git.base_sync.journey_handoff_support import (
    ADJUDICATED_TWICE,
    ChangedContributionJourney,
    records_a_legacy_baseline,
    spawned_roles,
)
from tests.git.base_sync.journey_push_support import crash_at
from tests.workflow.fixtures import LABEL_DECOMPOSING, LABEL_DOCUMENTING, LABEL_IN_REVIEW

# The park a settlement takes over a pull request somebody moved.
PARK_PR_UNRECONCILED = "late_pr_unreconciled"

# A park the review stage takes, which nothing on the adjudication's label answers.
PARK_REVIEW_CAP = "review_cap"

# The park an earlier build's dispatcher stranded a pair under, and what its
# notice asked for: a reply, with anything in it.
PARK_STRANDED = "auto_base_rebase_failed"
_STRANDED_NOTICE = "put the issue back on the stage the rebase was made under and reply on this issue"

# The park a recovery whose push failed leaves with the attempt kept.
PARK_PUSH_FAILED = "auto_base_rebase_push_failed"

# The operator's reply that lets a held adjudication run, one that asks for a
# parked refresh's retry and nothing else, and one that asks for more.
CONTINUE = "/orchestrator continue"
RETRY = "please retry"
GUIDED_RETRY = "Please retry. Also remove the generated table from the implementation."

# The agent a guidance reply resumes, and the one the final docs pass runs,
# which here changes nothing.
DEVELOPER = "developer"
DOCUMENTER = "developer"
DOCS_NO_CHANGE = "DOCS: NO_CHANGE"

KEY_AWAITING_HUMAN = "awaiting_human"
KEY_PARK_REASON = "park_reason"
KEY_WATERMARK = "last_action_comment_id"


class HandedOverJourneyTest(ChangedContributionJourney, unittest.TestCase):
    """The replay adjudicated afresh, authorized, published, and handed back."""

    def test_authorization_publishes_the_replay(self) -> None:
        # The tick that rebases hands the replay over, and its dispatch runs
        # the adjudication -- no relabel, no edit of the pinned comment.
        self._ticks()
        replay = self._wt_head()
        self.assertNotEqual(replay, self.accepted)
        self._assert_adjudicated_afresh(replay)

        # The human's decision on the replay is the one thing that publishes it.
        _authorizes(self, replay)
        self._assert_published(replay, self._ticks())

        # The stage the replay was taken out of carries on over it: the
        # report of the head pays the debt, the reviewer runs once, and the
        # final docs pass hands the issue to `in_review`.
        self._reviews()
        self._ticks(DOCS_NO_CHANGE)

        self._assert_documented()

    def test_a_docs_stage_replay_is_documented(self) -> None:
        # Rebased under the final docs pass, the replay is published back
        # through `validating` rather than onto the docs stage, whose handler
        # the dispatcher holds while the replay's report is owed: the report
        # pays the debt, the reviewer runs, and the docs pass hands it on.
        self._publishes_from(LABEL_DOCUMENTING)

    def test_a_ready_replay_is_documented(self) -> None:
        # The same from `in_review`, where a human was about to merge the head
        # the replay replaced.
        self._publishes_from(LABEL_IN_REVIEW)

    def test_a_foreign_push_refuses_the_publication(self) -> None:
        # Somebody pushes to the pull request while the replay is under
        # adjudication: the authorized settlement pushes nothing over them,
        # owes no report for a head it never published, moves no exemption,
        # and parks.
        self._ticks()
        replay = self._wt_head()
        foreign = self._pushes_over_the_pull_request()
        _authorizes(self, replay)

        pushed = self._ticks()

        durable = self._durable()
        parked = (durable.get("awaiting_human"), durable.get("park_reason"))
        self.assertEqual(pushed.revision, "")
        self.assertEqual(self._standing(), (replay, foreign, LABEL_DECOMPOSING))
        self.assertEqual(parked, (True, PARK_PR_UNRECONCILED))
        self.assertIsNone(durable.get(KEY_REWRITE_DEBT))
        self.assertEqual(durable.get("late_exempt_sha"), self.accepted)

    def _publishes_from(self, source: str) -> None:
        """Rebase the issue under `source`, adjudicate, authorize, and walk the published replay to `in_review`."""
        self._gh.set_workflow_label(self._issue(), source)
        self._ticks()
        replay = self._wt_head()
        self._assert_adjudicated_afresh(replay)
        _authorizes(self, replay)
        self._assert_published(replay, self._ticks())

        self._reviews()
        self._ticks(DOCS_NO_CHANGE)

        self._assert_documented()

    def _assert_documented(self) -> None:
        """Handed to `in_review` past the final docs pass, the report paid, one reviewer and one docs run spent."""
        self.assertEqual(self._gh.workflow_label(self._issue()), LABEL_IN_REVIEW)
        self.assertIsNone(self._durable().get(KEY_REWRITE_DEBT))
        self.assertEqual(spawned_roles(self), (*ADJUDICATED_TWICE, REVIEWER, DOCUMENTER))


class InterruptedHandoffTest(ChangedContributionJourney, unittest.TestCase):
    """The handoff lost at each of its writes, and the ticks that come back to it."""

    def test_a_crash_after_the_record(self) -> None:
        # The replay is recorded and nothing measured it. The recovery's retry
        # finds the permit refusing what the record names -- the changed
        # contribution -- and measures it as the lost tick would have, rather
        # than resetting it away.
        self._converges(windows.AFTER_THE_RECORD)

    def test_a_crash_before_the_relabel(self) -> None:
        # The generation is durable under the stage the rebase came from. The
        # adjudication's own guard puts its label back, and the handoff runs
        # ahead of the anchor hold on the tick after.
        self._converges(windows.AT_THE_RELABEL)

    def test_a_crash_before_the_handoff(self) -> None:
        # The adjudication has its label and the attempt is still pinned: the
        # dispatcher hands the replay over before its hold could strand it.
        self._converges(windows.BEFORE_THE_HANDOFF)

    def test_a_crash_after_the_handoff(self) -> None:
        # Everything landed and nothing after it was owed.
        self._converges(windows.AFTER_THE_HANDOFF)

    def _converges(self, window: str) -> None:
        """Lose the rebasing tick at `window`, run two more, and hold them to the unbroken handoff."""
        self._refreshes(window)
        replay = self._wt_head()
        self.assertNotEqual(replay, self.accepted)

        self._ticks()
        self._ticks()

        self._assert_adjudicated_afresh(replay)


class RetriedHandoffTest(ChangedContributionJourney, unittest.TestCase):
    """A rebase an operator's retry let go on, lost at a write of its handoff, and the ticks that come back to it.

    The retry is the attempt's, recorded read in the write that spends it --
    the anchor's on the publication, the gate's on the recovery's retry -- so
    the adjudication the lost tick left never resumes a developer over it.
    """

    def test_a_rebase_lost_after_the_record(self) -> None:
        self._converges_past_a_retry(windows.AFTER_THE_RECORD)

    def test_a_rebase_lost_at_the_relabel(self) -> None:
        self._converges_past_a_retry(windows.AT_THE_RELABEL)

    def test_a_rebase_lost_before_the_handoff(self) -> None:
        self._converges_past_a_retry(windows.BEFORE_THE_HANDOFF)

    def test_a_retry_lost_at_the_relabel(self) -> None:
        # The replay was recorded and its attempt parked; the operator's retry
        # brings the recovery back, and the gate's route is the write the tick
        # is lost behind.
        self._refreshes(windows.AFTER_THE_RECORD)
        self._converges_past_a_retry(windows.AT_THE_RELABEL, PARK_PUSH_FAILED)

    def test_a_retry_lost_before_the_handoff(self) -> None:
        self._refreshes(windows.AFTER_THE_RECORD)
        self._converges_past_a_retry(windows.BEFORE_THE_HANDOFF, PARK_PUSH_FAILED)

    def _converges_past_a_retry(self, window: str, reason: str = PARK_STRANDED) -> None:
        """Park the refresh under `reason`, retry it, lose that tick at `window`, and run two more."""
        _persistence._park_auto_rebase_failure(
            self._gh, self._issue(), self._durable(), message=_STRANDED_NOTICE, reason=reason,
        )
        retry = replies(self, RETRY)
        self._refreshes(window)
        replay = self._wt_head()

        self._ticks()
        self._ticks()

        self._assert_adjudicated_afresh(replay)
        self.assertGreaterEqual(self._durable().get(KEY_WATERMARK), retry)


class StrandedHandoffTest(ChangedContributionJourney, unittest.TestCase):
    """A pair an earlier build stranded under its own park, handed over once a human answers that park."""

    def setUp(self) -> None:
        super().setUp()
        self._refreshes(windows.BEFORE_THE_HANDOFF)
        self.replay = self._wt_head()
        _persistence._park_auto_rebase_failure(
            self._gh, self._issue(), self._durable(), message=_STRANDED_NOTICE, reason=PARK_STRANDED,
        )

    def test_the_stranded_parks_retry_is_the_attempts(self) -> None:
        # The human answered the park as it asked, with a retry. That reply
        # is the attempt's, not guidance: it goes with the park the handoff
        # retires, and the adjudication runs with no developer resumed.
        retry = replies(self, RETRY)

        self._ticks()
        self._ticks()

        self._assert_adjudicated_afresh(self.replay)
        self.assertGreaterEqual(self._durable().get(KEY_WATERMARK), retry)

    def test_a_reply_that_says_more_is_guidance(self) -> None:
        # A reply asking for more than the retry is a human's words: the
        # handoff leaves it unread, and the adjudication hands it to the
        # developer the way it hands any guidance, before adjudicating again.
        replies(self, GUIDED_RETRY)

        self._ticks()

        self.assertEqual(self._holders(), (None, None, self.replay, self.replay))
        self.assertEqual(spawned_roles(self), (ADJUDICATOR, DEVELOPER))

    def test_a_legacy_baseline_spends_the_retry(self) -> None:
        # The requirements baseline was written by the legacy algorithm, over
        # a bare continue a stage had read, before the pair was stranded. It
        # still covers the thread up to the park's notice, so the retry is the
        # attempt's, and the adjudication runs with nobody resumed.
        records_a_legacy_baseline(self)
        _persistence._park_auto_rebase_failure(
            self._gh, self._issue(), self._durable(), message=_STRANDED_NOTICE, reason=PARK_STRANDED,
        )
        retry = replies(self, RETRY)

        self._ticks()

        self._assert_adjudicated_afresh(self.replay)
        self.assertGreaterEqual(self._durable().get(KEY_WATERMARK), retry)

    def test_a_retry_past_the_handoff_is_spent(self) -> None:
        # The handoff lands and the tick is lost before the adjudication ever
        # reads the thread, with the park gone and its notice still asking for
        # a reply. The retry the human answers it with is still the attempt's:
        # the next tick records it read and adjudicates, resuming nobody.
        self._loses_the_tick_past_the_handoff()
        retry = replies(self, RETRY)

        self._ticks()

        self._assert_adjudicated_afresh(self.replay)
        self.assertGreaterEqual(self._durable().get(KEY_WATERMARK), retry)

    def test_guidance_after_the_handoff_is_guidance(self) -> None:
        # The same window with a reply that asks for more: the adjudication
        # hands it to the developer as it hands any guidance.
        self._loses_the_tick_past_the_handoff()
        replies(self, GUIDED_RETRY)

        self._ticks()

        self.assertEqual(spawned_roles(self), (ADJUDICATOR, DEVELOPER))

    def _loses_the_tick_past_the_handoff(self) -> None:
        """Run the tick whose dispatcher hands the stranded pair over, lost the moment that write has landed."""
        with crash_at(self._gh, windows.AFTER_THE_HANDOFF), self.assertRaises(RuntimeError):
            self._ticks()
        self.assertEqual(self._holders(), (None, None, self.replay, self.replay))
        self.assertEqual(spawned_roles(self), (ADJUDICATOR,))


class ForeignParkTest(ChangedContributionJourney, unittest.TestCase):
    """A park the attempt's road did not leave, beside a replay the gate hands to an adjudication."""

    def test_the_handoff_waits_behind_it(self) -> None:
        # The park is somebody else's question: the handoff leaves it and the
        # adjudication waits behind it, tick after tick, rather than replace
        # it with a verdict's park.
        self._holds_behind_it(windows.BEFORE_THE_HANDOFF)

    def test_the_gate_keeps_it_from_the_record(self) -> None:
        # Stood before the gate ever measured the replay, it survives the
        # route that creates the generation as well as the handoff.
        self._holds_behind_it(windows.AFTER_THE_RECORD)

    def test_a_reply_releases_it(self) -> None:
        # A human's reply to that park is its answer, and the adjudication runs.
        self._holds_behind_it(windows.AFTER_THE_RECORD)

        replies(self, CONTINUE)
        self._ticks()

        self._assert_adjudicated_afresh(self._wt_head())

    def _holds_behind_it(self, window: str) -> None:
        """Lose the rebasing tick at `window`, stand the review stage's park by hand, and run two ticks behind it."""
        self._refreshes(window)
        replay = self._wt_head()
        _parks_by_hand(self)

        self._ticks()
        self._ticks()

        self.assertEqual(self._holders(), (None, None, replay, replay))
        self.assertEqual(_parked(self._durable()), (True, PARK_REVIEW_CAP))
        self.assertEqual(spawned_roles(self), (ADJUDICATOR,))


def _parks_by_hand(fixture) -> None:
    """Stand the review stage's park on the pinned comment, as a human editing it would."""
    durable = fixture._durable()
    durable.set(KEY_AWAITING_HUMAN, True)
    durable.set(KEY_PARK_REASON, PARK_REVIEW_CAP)
    fixture._gh.write_pinned_state(fixture._issue(), durable)


def _parked(durable) -> tuple:
    """The park `durable` carries: whether a human is awaited, and why."""
    return durable.get(KEY_AWAITING_HUMAN), durable.get(KEY_PARK_REASON)


if __name__ == "__main__":
    unittest.main()
