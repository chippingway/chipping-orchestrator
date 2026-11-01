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

from functools import partial

from orchestrator.workflow.engine import (
    completion_routes as _routes,
    run_ledger_values as _run_ledger_values,
    run_limit_values as _run_limit_values,
)
from orchestrator.workflow.late_split.models import LateFailure
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.stages.decomposition import (
    captured_revision_support as _captured,
    late_content_replies as _content_replies,
    late_content_support as _support,
    late_revision_support as _stage_support,
)
from tests.workflow.stages.decomposition.late_requirements_support import KEY_USER_CONTENT_HASH, requirements
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
    LATE_ISSUE_NUMBER,
    NEXT_GENERATION,
    PLAN_PR_BODY,
    QUESTION_REPLY,
)

# An allowance the issue has already spent to its last run.
_SPENT = 4

# The room a comment leaves that neither a revision's capture nor the delivery
# its report would otherwise be recorded as fits in, and the debt and park a
# report nothing could record leaves.
_ROOM_FOR_NEITHER = 1800
_OWED_REPORT = "developer_report_owed"
_UNDELIVERABLE = "report_undeliverable"

# Every way a developer's CLI stops before it reads its prompt, each as the
# reply it hands back: on its quota, with the notice or without it, on a
# refusal its provider answered the turn with -- an auth refusal on a failed
# exit, a rate limit on a clean one -- and an Antigravity run whose failure
# record names the quota, which stopped it even though its timeout fired too.
_STOPPED_RUNS = (
    ("a silent quota stop", partial(agent_reply, _stage_support.DEV_SILENT, exit_code=_stage_support.QUOTA_EXIT)),
    ("a quota notice", partial(agent_reply, _stage_support.QUOTA_NOTICE, exit_code=_stage_support.QUOTA_EXIT)),
    ("an auth refusal", partial(agent_reply, "API Error: 401 Unauthorized", exit_code=1)),
    ("a rate limit", partial(agent_reply, "API Error: 429 Too Many Requests", exit_code=0)),
    ("an AGY quota stop past its timeout", _stage_support.agy_quota_past_timeout),
)


class DeveloperResumeTest(RevisionCase):
    """Whose session runs, under which role and stage, and on what."""

    def test_guidance_resumes_the_locked_session(self) -> None:
        self._seed_drifted()

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        spawn.assert_called_once()
        self.assertEqual(
            spawn.call_args.kwargs["options"].resume_session_id, _stage_support.DEV_SESSION,
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
                self.assertNotIn(KEY_USER_CONTENT_HASH, pinned)
                self.assertTrue(pinned[KEYS.awaiting])

    def test_a_refused_launch_consumes_nothing(self) -> None:
        # The run circuit writes its own park before refusing, and that write
        # is taken off a fresh read: nothing this tick staged rides it, so the
        # guidance is still unread behind a park that says why.
        self._seed_drifted()
        self.github.seed_state(LATE_ISSUE_NUMBER, **{
            **self._pinned(),
            _run_ledger_values.AGENT_RUN_ALLOWANCE: _SPENT,
            _run_ledger_values.AGENT_RUNS_USED: _SPENT,
        })

        outcome, spawn = self._revise()

        spawn.assert_not_called()
        self.assertEqual(outcome.disposition, _LateDisposition.DEFERRED)
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.park_reason], _run_limit_values.PARK_AGENT_RUN_LIMIT)
        self.assertNotIn(_support.KEY_COMMENT_WATERMARK, pinned)
        self.assertNotIn(KEY_USER_CONTENT_HASH, pinned)


class StoppedRunTest(RevisionCase):
    """A developer run whose CLI stopped before it worked consumes nothing."""

    def test_the_continue_hands_the_guidance_on(self) -> None:
        # The retry the park waits for is a human's continue once the quota
        # resets or the provider serves again, and the guidance nobody read
        # is what it resumes on.
        for shape, stopped_reply in _STOPPED_RUNS:
            with self.subTest(run=shape):
                self._seed(**_stage_support.DEV_PIN)
                _content_replies.reply(self.issue)
                self._stopped(stopped_reply())
                _content_replies.reply(self.issue, _support.BARE_CONTINUE)

                revised, resumed = self._revise()

                self.assertEqual(revised.disposition, _LateDisposition.REVISED)
                self.assertIn(_content_replies.GUIDANCE_BODY, resumed.call_args.args[1])
                self.assertEqual(self._pinned()[KEY_USER_CONTENT_HASH], requirements(self.issue))

    def test_an_unread_edit_is_asked_about_again(self) -> None:
        # The edit the guidance answered reached no agent either, so the
        # continue meets it as the drift it still is, and the answer to that
        # park is what resumes the developer with the guidance whole.
        self._seed_drifted()
        self._stopped(agent_reply(_stage_support.DEV_SILENT, exit_code=_stage_support.QUOTA_EXIT))
        _content_replies.reply(self.issue, _support.BARE_CONTINUE)
        _asked, unspawned = self._revise()
        unspawned.assert_not_called()
        self.assertEqual(self._pinned()[KEYS.park_reason], _support.PARK_CONTENT_DRIFT)
        _content_replies.reply(self.issue, _support.BARE_CONTINUE)

        revised, resumed = self._revise()

        self.assertEqual(revised.disposition, _LateDisposition.REVISED)
        prompt = resumed.call_args.args[1]
        self.assertIn(_content_replies.GUIDANCE_BODY, prompt)
        self.assertIn(_support.EDITED_TITLE, prompt)

    def _stopped(self, stopped_reply) -> None:
        """Run the developer the guidance bought, its CLI stopping before it works with `stopped_reply`.

        The run parks as one that answered nothing, over guidance still
        unread: no late watermark moved and no requirements baseline was
        recorded.
        """
        outcome, _spawn = self._revise(
            reply=stopped_reply,
            seed=_stage_support.UNCHANGED,
            measurement=_stage_support.ACKNOWLEDGED,
        )
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_REVISION_UNANSWERED)
        self.assertNotIn(_support.KEY_COMMENT_WATERMARK, pinned)
        self.assertNotIn(KEY_USER_CONTENT_HASH, pinned)


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

    def test_a_continue_keeps_the_parked_report(self) -> None:
        # A revision that finished on a report over a clean commit nothing
        # could measure parks with that report handed to the delivery in the
        # park's own write. The continue re-measures the same commit with no
        # developer run, and so no report of its own, and the report the run
        # finished on is still the one the delivery holds.
        for name, seed, measured in (
            ("a new commit", WorktreeSeed(head=_support.REVISED_SHA), _stage_support.REMEASURED),
            ("the commit as it stood", _stage_support.UNCHANGED, _stage_support.ACKNOWLEDGED),
        ):
            with self.subTest(name):
                self._parked_on_its_report(seed)
                _content_replies.reply(self.issue, _support.BARE_CONTINUE)

                continued = self._revise(seed=seed, measurement=measured)

                self.assertEqual(continued[0].disposition, _LateDisposition.REVISED)
                continued[1].assert_not_called()
                pinned = self._pinned()
                self.assertEqual(pinned[_support.KEY_GENERATION], NEXT_GENERATION)
                self.assertEqual(pinned[_captured.DELIVERED]["report"], _captured.DEV_REPORT_TEXT)
                self.assertEqual(_captured.capture_of(pinned).stage, _captured.HANDED_OFF)

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

    def _parked_on_its_report(self, seed: WorktreeSeed) -> None:
        """A revision that finished on its report over `seed`'s clean commit, parked as one nothing could measure."""
        self._seed_drifted()
        parked = self._revise(_captured.DEV_REPORT, seed=seed, measurement=_stage_support.UNMEASURED)[0]
        self.assertEqual(parked.disposition, _LateDisposition.PARKED)
        self.assertEqual(self._pinned()[KEYS.park_reason], _support.PARK_REVISION_UNMEASURED)


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




class CapturedRevisionTest(_captured.CapturedRevisionCase):
    """A revision that finished on a report keeps that report, held or not, for one owner at a time."""

    def test_a_held_report_is_captured_alone(self) -> None:
        # Under either control the return is kept whole beside its accounting
        # and nothing else of the run moves: the guidance unread, the
        # generation and the park where they stood, no report delivered, and
        # nothing said, relabelled, or published. Dispatches while the
        # control stands reach nothing at all.
        for control in _captured.CONTROLS:
            with self.subTest(control=control):
                self._seed_drifted()

                held = self._held(control)[0]

                self.assertEqual(held.disposition, _LateDisposition.DEFERRED)
                pinned = self._pinned()
                self._captured_alone(pinned)
                writes = self.github.write_state_calls
                self._dispatched().assert_not_called()
                self.assertEqual((self._pinned(), self.github.write_state_calls), (pinned, writes))

    def test_a_returned_report_is_handed_on(self) -> None:
        # An unpaused return is captured too, and handed to the delivery in
        # the very write that re-measures it; a report-only revision over the
        # unchanged commit is the answer its report says it is, re-measured
        # rather than parked as a reply that vouched for nothing.
        for name, seed, measured in (
            ("a new commit", WorktreeSeed(head=_support.REVISED_SHA), _stage_support.REMEASURED),
            ("the commit as it stood", _stage_support.UNCHANGED, _stage_support.ACKNOWLEDGED),
        ):
            with self.subTest(name):
                self._seed_drifted()

                revised = self._revise(_captured.DEV_REPORT, seed=seed, measurement=measured)[0]

                self.assertEqual(revised.disposition, _LateDisposition.REVISED)
                _captured.finished(self, seed.head)

    def test_no_report_is_accounted_alone(self) -> None:
        # An `ACK:`, a question, and a run that did not finish leave no
        # capture: each keeps its accounting and its own road, as before.
        for name, answered in (
            ("an ACK", _stage_support.DEV_ACK),
            ("a question", _stage_support.DEV_QUESTION),
            ("a timed-out report", agent_reply(_captured.DEV_REPORT, timed_out=True)),
        ):
            with self.subTest(name):
                self._seed_drifted()

                self._revise(answered)

                self.assertNotIn(_captured.CAPTURED, self._pinned())

    def test_a_parked_reconciliation_withdraws_it(self) -> None:
        # A tree nothing can vouch for parks, and the report it was handed
        # describes no candidate anything will publish, so the capture is
        # withdrawn right behind the park's own write and nothing is
        # delivered.
        self._seed_drifted()

        parked = self._revise(
            _captured.DEV_REPORT,
            seed=WorktreeSeed(head=_support.REVISED_SHA, dirty=_stage_support.DIRTY_TREE),
        )[0]

        self.assertEqual(parked.disposition, _LateDisposition.PARKED)
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_REVISION_DIRTY)
        self.assertEqual(_captured.capture_of(pinned).stage, _captured.RETIRED)
        self.assertNotIn(_captured.DELIVERED, pinned)

    def test_an_uncaptured_report_is_held_owed(self) -> None:
        # A comment with no room for the run's capture as it returned leaves
        # no capture to hand the report on, and the report is not dropped:
        # the delivery's own recording takes it, and with no room for it
        # either, parks for a human with the report owed -- the candidate
        # re-measured and the guidance consumed beside that debt.
        self._seed_drifted()
        self._filled(_ROOM_FOR_NEITHER)

        held = self._revise(_captured.DEV_REPORT)[0]

        self.assertEqual(held.disposition, _LateDisposition.DEFERRED)
        pinned = self._pinned()
        self.assertNotIn(_captured.CAPTURED, pinned)
        self.assertTrue(pinned[_OWED_REPORT])
        self.assertEqual(pinned.get(KEYS.park_reason), _UNDELIVERABLE)
        self.assertEqual(pinned[_support.KEY_GENERATION], NEXT_GENERATION)
        self.assertEqual(pinned[_support.KEY_COMMENT_WATERMARK], self.guidance.id)

    def test_a_lost_withdrawal_buys_no_second_run(self) -> None:
        # The park, the guidance it consumed, and the owed read land with the
        # capture still pending, and the capture is withdrawn right behind
        # them. Lost as that withdrawal went out, the capture is left for the
        # next dispatch's recovery to settle; lost once it landed, the park
        # stands over guidance already read. Neither resumes the developer
        # again over the same guidance.
        dirty = WorktreeSeed(head=_support.REVISED_SHA, dirty=_stage_support.DIRTY_TREE)
        for lost in _captured.LOST_WITHDRAWALS:
            with self.subTest(lost=lost):
                self._seed_drifted()
                with self._lost_at_the_handoff(lost, _captured.RETIRED):
                    self._revise(_captured.DEV_REPORT, seed=dirty)

                self._dispatched(seed=dirty).assert_not_called()

                pinned = self._pinned()
                self.assertEqual(pinned[KEYS.park_reason], _support.PARK_REVISION_DIRTY)
                self.assertEqual(pinned[_support.KEY_COMMENT_WATERMARK], self.guidance.id)
                self.assertEqual(_captured.capture_of(pinned).stage, _captured.RETIRED)
                self.assertEqual(self._developer_runs(), 1)

    def _captured_alone(self, pinned: dict) -> None:
        """Assert `pinned` carries the run's capture and nothing else of the run moved or said."""
        captured = _captured.capture_of(pinned)
        self.assertEqual(
            (captured.handoff.route, captured.run.source_sha, captured.outcome.report),
            (_routes.CompletionRoute.LATE_REVISION, _support.REVISED_SHA, _captured.DEV_REPORT_TEXT),
        )
        self.assertEqual(pinned[_support.KEY_GENERATION], GENERATION_NUMBER)
        self.assertEqual(pinned.get(KEYS.candidate_sha), CANDIDATE_SHA)
        unread = (_support.KEY_COMMENT_WATERMARK, KEY_USER_CONTENT_HASH, _captured.DELIVERED)
        self.assertEqual([field for field in unread if field in pinned], [])
        self.assertTrue(pinned[KEYS.awaiting])
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_CONTENT_DRIFT)
        self.assertNotIn(_stage_support.REMEASURED_NOTICE, "".join(self._bodies()))
        self.assertEqual((self.github.label_history, self.github.opened_prs), ([], []))
