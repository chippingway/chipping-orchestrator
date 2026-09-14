# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer run guidance buys, and the candidate it comes back with.

Both halves of one tick, driven together: the resume the guidance pays for and
the prompt it carries, then the clean tree, re-frozen commit, and fresh
measurement its result is proved through. Nothing ahead of that measurement is
durable, so a run this tick does not reconcile is one the next tick pays for
again -- while a reconciliation that PARKED is re-run on its own by a later
bare continue, reading the same checkout with no second developer run.
"""
from __future__ import annotations

from orchestrator.workflow.late_split.models import LateFailure
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.workflow.stages.decomposition import (
    late_content_replies as _content_replies,
    late_content_support as _support,
    late_revision_support as _stage_support,
)
from tests.workflow.stages.decomposition.late_revision_support import PausedDuringRun, RevisionCase
from tests.workflow.stages.decomposition.late_run_support import (
    WorktreeSeed,
    agent_reply,
)
from tests.workflow.stages.decomposition.late_test_support import (
    CANDIDATE_SHA,
    EVENT_LATE_FAILURE,
    GENERATION_NUMBER,
    KEYS,
    NEXT_GENERATION,
    PLAN_PR_BODY,
    QUESTION_REPLY,
)


class DeveloperResumeTest(RevisionCase):
    """Whose session runs, under which role and stage, and on what."""

    def test_guidance_resumes_the_locked_session(self) -> None:
        self._seed_drifted()

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        spawn.assert_called_once()
        self.assertEqual(
            spawn.call_args.kwargs["resume_session_id"], _stage_support.DEV_SESSION,
        )

    def test_the_run_is_a_developer_decomposing(self) -> None:
        self._seed_drifted()

        self._revise()

        spawned = self._events_named(_support.EVENT_AGENT_SPAWN)[-1]
        self.assertEqual(spawned["agent_role"], _support.ROLE_DEVELOPER)
        self.assertEqual(spawned["stage"], _support.STAGE_DECOMPOSING)

    def test_the_guidance_is_what_the_dev_is_shown(self) -> None:
        self._seed_drifted()

        _outcome, spawn = self._revise()

        self.assertIn(_content_replies.GUIDANCE_BODY, spawn.call_args.args[1])

    def test_the_edited_issue_is_shown_beside_it(self) -> None:
        # A resume is exactly the case that cannot see an edit: the replayed
        # transcript holds the issue as it read when the work started, and the
        # commonest reason to be here is that a human changed it since.
        self._seed_drifted()
        self.issue.body = _support.EDITED_BODY

        _outcome, spawn = self._revise()

        prompt = spawn.call_args.args[1]
        self.assertIn(_support.EDITED_TITLE, prompt)
        self.assertIn(_support.EDITED_BODY, prompt)

    def test_a_landed_run_records_the_reply_as_read(self) -> None:
        # Both watermarks, because two consumers read the same thread: the
        # generation's own, so the comment does not come back as fresh
        # guidance, and the issue-wide one, so the later validating ->
        # in_review handoff does not replay it as fresh PR feedback.
        self._seed_drifted()

        self._revise()

        pinned = self._pinned()
        self.assertEqual(pinned[_support.KEY_COMMENT_WATERMARK], self.guidance.id)
        self.assertEqual(pinned[_support.KEY_LAST_ACTION_COMMENT_ID], self.guidance.id)

    def test_a_declined_run_consumes_nothing(self) -> None:
        # A pause and a shutdown sweep both mean the tick did not happen. A
        # consumption made durable by one of them would drop the human's
        # instruction with nothing on the issue left pointing at it.
        for label, declined in (
            ("paused", PausedDuringRun(self)),
            ("interrupted", agent_reply(_stage_support.DEV_ACK, interrupted=True)),
        ):
            with self.subTest(declined=label):
                self._seed_drifted()

                outcome, _spawn = self._revise(reply=declined)

                self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
                pinned = self._pinned()
                self.assertNotIn(_support.KEY_COMMENT_WATERMARK, pinned)
                self.assertTrue(pinned[KEYS.awaiting])


class RevisedCandidateTest(RevisionCase):
    """What a clean revised tree is re-frozen and re-measured as."""

    def test_a_new_commit_replaces_the_candidate(self) -> None:
        self._seed_drifted()

        outcome, _spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.candidate_sha], _support.REVISED_SHA)
        self.assertEqual(pinned[KEYS.base_sha], _support.REVISED_BASE_SHA)
        self.assertEqual(pinned[_support.KEY_ADDITIONS], _support.REVISED_ADDITIONS)
        self.assertEqual(pinned[_support.KEY_GENERATION], NEXT_GENERATION)
        self.assertFalse(pinned[KEYS.awaiting])
        self.assertEqual(len(self._events_named(_support.EVENT_LATE_MEASUREMENT)), 1)

    def test_a_tree_it_cannot_vouch_for_parks(self) -> None:
        # Uncommitted work is in the checkout a publication pushes from and
        # out of the diff a verdict is taken on, and a status read that
        # established nothing is not proof of anything either.
        for label, seed in (
            ("dirty", WorktreeSeed(head=_support.REVISED_SHA, dirty=_stage_support.DIRTY_TREE)),
            ("unreadable", WorktreeSeed(head=_support.REVISED_SHA, readable=False)),
        ):
            with self.subTest(tree=label):
                self._seed_drifted()

                outcome, _spawn = self._revise(seed=seed)

                self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
                pinned = self._pinned()
                self.assertEqual(pinned[KEYS.park_reason], _support.PARK_REVISION_DIRTY)
                self.assertEqual(pinned[KEYS.candidate_sha], CANDIDATE_SHA)
                self.assertEqual(pinned[_support.KEY_GENERATION], GENERATION_NUMBER)

    def test_an_unreadable_head_is_not_a_candidate(self) -> None:
        self._seed_drifted()

        outcome, _spawn = self._revise(seed=WorktreeSeed(head=""))

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(
            self._pinned()[KEYS.park_reason], _support.PARK_REVISION_UNMEASURED,
        )

    def test_a_candidate_nobody_measured_is_not_small(self) -> None:
        self._seed_drifted()

        outcome, _spawn = self._revise(measurement=_stage_support.UNMEASURED)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_REVISION_UNMEASURED)
        self.assertEqual(pinned[KEYS.candidate_sha], CANDIDATE_SHA)
        # The same family and typed failure the size gate writes, and the
        # same two companions: a re-measurement is taken in a checkout an
        # agent has been running in, so the step it stopped at is what tells
        # a base a fetch cannot bring from a tree something made unreadable.
        self.assertEqual(
            [
                (
                    record["failure"],
                    record["measurement_failure"],
                    record["detail"],
                )
                for record in self._events_named(EVENT_LATE_FAILURE)
            ],
            [(
                str(LateFailure.MEASUREMENT_FAILED),
                str(_stage_support.UNMEASURED.failure),
                _stage_support.UNMEASURED_DETAIL,
            )],
        )


class RolledOverHoldTest(RevisionCase):
    """A still-oversized revision leaves its plan PR a generation behind.

    The counter advances on every reconciliation that lands, so the notice the
    pull request wears names the generation before the one now running. It is
    the orchestrator's own last edit, and the next tick has to re-mark it
    rather than read it as a description somebody wrote over the hold.
    """

    def test_the_next_tick_re_marks_and_spawns(self) -> None:
        self._seed_with_plan_pr(**_stage_support.DEV_PIN)
        _content_replies.reply(self.issue)
        revised, _resumed = self._revise(measurement=_stage_support.REMEASURED_OVERSIZED)

        adjudicated, spawn = self._adjudicate_revised()

        self.assertEqual(revised.disposition, _LateDisposition.REVISED)
        spawn.assert_called_once()
        self.assertEqual(adjudicated.disposition, _LateDisposition.DECIDED)
        # Parked on what the agent asked, not on a hold read as a human's.
        self.assertEqual(self._pinned().get(KEYS.park_reason), _support.PARK_QUESTION)

    def test_the_notice_is_left_exactly_as_it_was(self) -> None:
        # The hold is the cycle's, so an advanced generation asks for the same
        # body it already wrote: one edit for the whole rollover.
        self._seed_with_plan_pr(**_stage_support.DEV_PIN)
        _content_replies.reply(self.issue)
        self._revise(measurement=_stage_support.REMEASURED_OVERSIZED)
        held = self.plan_pr.body

        self._adjudicate_revised()

        self.assertEqual(self.plan_pr.body, held)
        self.assertEqual(len(self.github.edited_pr_bodies), 1)
        # The description the first hold displaced is still the only copy of
        # what this issue owes that pull request back.
        self.assertEqual(
            self._pinned().get(KEYS.plan_pr_body), PLAN_PR_BODY,
        )

    def _adjudicate_revised(self):
        """The tick after a revision, run against the commit it left."""
        return self._run(
            QUESTION_REPLY, worktree=WorktreeSeed(head=_support.REVISED_SHA),
        )


class StalledRevisionTest(RevisionCase):
    """A bare continue re-reads a finished run rather than paying again."""

    def test_a_continue_remeasures_without_a_spawn(self) -> None:
        self._seed(**_support.REVISION_PARKED, **_stage_support.DEV_PIN)
        _content_replies.reply(self.issue, _support.BARE_CONTINUE)

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        spawn.assert_not_called()
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.candidate_sha], _support.REVISED_SHA)
        self.assertFalse(pinned[KEYS.awaiting])

    def test_a_still_dirty_tree_repeats_no_notice(self) -> None:
        self._seed(**_support.REVISION_PARKED, **_stage_support.DEV_PIN)
        _content_replies.reply(self.issue, _support.BARE_CONTINUE)
        self._revise(seed=WorktreeSeed(head=_support.REVISED_SHA, dirty=_stage_support.DIRTY_TREE))
        posted = len(self._bodies())

        outcome, spawn = self._revise(
            seed=WorktreeSeed(head=_support.REVISED_SHA, dirty=_stage_support.DIRTY_TREE),
        )

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        self.assertEqual(len(self._bodies()), posted)

    def test_nothing_new_leaves_the_park_alone(self) -> None:
        self._seed(**_support.REVISION_PARKED, **_stage_support.DEV_PIN)

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        self.assertEqual(self._pinned()[KEYS.candidate_sha], CANDIDATE_SHA)

    def test_guidance_runs_the_developer_again(self) -> None:
        self._seed(**_support.REVISION_PARKED, **_stage_support.DEV_PIN)
        _content_replies.reply(self.issue)

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        spawn.assert_called_once()

    def test_guidance_beside_a_reverted_edit_runs(self) -> None:
        # Taking the edit back does not withdraw the change the human asked
        # for. Absorbing it into the baseline would consume an instruction
        # without acting on it and then reuse a verdict nobody re-earned.
        self._seed(**_support.DRIFT_PARKED, **_stage_support.DEV_PIN)
        _content_replies.reply(self.issue)

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        spawn.assert_called_once()
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.candidate_sha], _support.REVISED_SHA)
        self.assertFalse(pinned[KEYS.awaiting])


class UnparkedGuidanceTest(RevisionCase):
    """What a reply earns when the issue is waiting on nothing."""

    def test_guidance_runs_the_developer(self) -> None:
        # Guidance means the same thing with nothing parked: the work has to
        # change. Folding it into the baseline would consume a human's
        # instruction without acting on it.
        self._seed(**_stage_support.DEV_PIN)
        _content_replies.reply(self.issue)

        revised, resumed = self._revise()

        self.assertEqual(revised.disposition, _LateDisposition.REVISED)
        resumed.assert_called_once()
        self.assertEqual(self._pinned()[KEYS.candidate_sha], _support.REVISED_SHA)

    def test_guidance_after_a_verdict_runs_too(self) -> None:
        # A verdict recorded over work the human has since asked to be
        # different is exactly the one that must not stand: the re-measured
        # candidate advances the generation, so the old answer stops applying.
        self._seed(**_support.RECORDED_SINGLE, **_stage_support.DEV_PIN)
        _content_replies.reply(self.issue)

        revised, resumed = self._revise()

        self.assertEqual(revised.disposition, _LateDisposition.REVISED)
        resumed.assert_called_once()
        pinned = self._pinned()
        self.assertEqual(pinned[_support.KEY_GENERATION], NEXT_GENERATION)
        self.assertEqual(pinned[KEYS.candidate_sha], _support.REVISED_SHA)

    def test_a_continue_with_no_park_does_nothing(self) -> None:
        # The one reply that lands here with nothing to answer: no park was
        # waiting on it and no candidate needs certifying.
        self._seed(**_support.RECORDED_SINGLE, **_stage_support.DEV_PIN)
        _content_replies.reply(self.issue, _support.BARE_CONTINUE)

        reused, resumed = self._revise()

        self.assertEqual(reused.disposition, _LateDisposition.PARKED)
        resumed.assert_not_called()
        # The recorded verdict is what the tick reaches, so nothing re-froze
        # and no second developer run was paid for.
        self.assertEqual(self._pinned()[KEYS.candidate_sha], CANDIDATE_SHA)
