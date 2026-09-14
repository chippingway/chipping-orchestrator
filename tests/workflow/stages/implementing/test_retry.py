# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for implementing retry behavior."""

from __future__ import annotations

import unittest

from orchestrator.workflow.engine import issue_processing
from tests.workflow.stages.implementing import retry_test_support as support

IssueScenario = support.IssueScenario

ACTION_COMMENT_ID = support.ACTION_COMMENT_ID
BACKEND_CLAUDE = support.BACKEND_CLAUDE
COMMENTS_AFTER = support.COMMENTS_AFTER
CONTINUE_COMMAND = support.CONTINUE_COMMAND
DEFAULT_SESSION = support.DEFAULT_SESSION
DEV_SESSION = support.DEV_SESSION
DONE_MESSAGE = support.DONE_MESSAGE
DRIFT_RESUME_NOTICE = support.DRIFT_RESUME_NOTICE
EXPIRED_WINDOW_HOURS = support.EXPIRED_WINDOW_HOURS
FIRST_REPLY_ID = support.FIRST_REPLY_ID
FakeComment = support.FakeComment
FakeGitHubClient = support.FakeGitHubClient
FakeLabel = support.FakeLabel
FakeUser = support.FakeUser
GRANTED_ATTEMPTS = support.GRANTED_ATTEMPTS
GUIDANCE_REPLY = support.GUIDANCE_REPLY
HARD_SKIP_LABELS = support.HARD_SKIP_LABELS
HUMAN_REPLY_ID = support.HUMAN_REPLY_ID
KEY_AWAITING_HUMAN = support.KEY_AWAITING_HUMAN
KEY_DEV_AGENT = support.KEY_DEV_AGENT
KEY_DEV_SESSION_ID = support.KEY_DEV_SESSION_ID
KEY_LAST_ACTION_COMMENT_ID = support.KEY_LAST_ACTION_COMMENT_ID
KEY_PARK_REASON = support.KEY_PARK_REASON
KEY_RETRY_CAP_CONTINUED = support.KEY_RETRY_CAP_CONTINUED
KEY_RETRY_CAP_NOTICE = support.KEY_RETRY_CAP_NOTICE
KEY_RETRY_CAP_STAGE = support.KEY_RETRY_CAP_STAGE
KEY_RETRY_COUNT = support.KEY_RETRY_COUNT
LABEL_DONE = support.LABEL_DONE
LABEL_IMPLEMENTING = support.LABEL_IMPLEMENTING
OK_MESSAGE = support.OK_MESSAGE
OUTSIDE_AUTHOR = support.OUTSIDE_AUTHOR
OWED_NOTICE = support.OWED_NOTICE
CONTINUE_PR_NUMBER = support.CONTINUE_PR_NUMBER
PARKED_WATERMARK = support.PARKED_WATERMARK
RETRY_CAP_CONTINUE_ISSUE = support.RETRY_CAP_CONTINUE_ISSUE
PARK_RETRY_CAP = support.PARK_RETRY_CAP
PHASE_CONTINUED = support.PHASE_CONTINUED
PHASE_DELIVERED = support.PHASE_DELIVERED
PHASE_RECONCILED = support.PHASE_RECONCILED
PHASE_STANDING = support.PHASE_STANDING
PR_CLOSED = support.PR_CLOSED
RETRY_CAP_PARK_ISSUE = support.RETRY_CAP_PARK_ISSUE
RETRY_CAP_TICKS = support.RETRY_CAP_TICKS
RESUME_PROMPT_FRAGMENT = support.RESUME_PROMPT_FRAGMENT
RUN_AGENT = support.RUN_AGENT
STAGE_IMPLEMENTING = support.STAGE_IMPLEMENTING
STALE_CONTENT_HASH = support.STALE_CONTENT_HASH
STUCK_MESSAGE = support.STUCK_MESSAGE
TRUSTED_AUTHOR = support.TRUSTED_AUTHOR
TRUSTED_COMMAND = support.TRUSTED_COMMAND
TRUSTED_GUIDANCE = support.TRUSTED_GUIDANCE
UNTOUCHED_RECORDS = support.UNTOUCHED_RECORDS
_RetryCapContinueMixin = support._RetryCapContinueMixin
_RetryCapFixtureMixin = support._RetryCapFixtureMixin
_RetryCapParkMixin = support._RetryCapParkMixin
_TEST_SPEC = support._TEST_SPEC
_agent = support._agent
_iso_hours_ago = support._iso_hours_ago
config = support.config
make_issue = support.make_issue
patch = support.patch
_retry_budget = support._retry_budget


class HandleImplementingRetryCapTest(
    unittest.TestCase,
    _RetryCapFixtureMixin,
):
    """Bound the implementing loop with MAX_RETRIES_PER_DAY in pinned state.

    Resumes on human reply and recovered-worktree pushes are explicitly NOT
    counted; only fresh codex spawns consume the budget.
    """

    def test_fourth_fresh_attempt_parks_before_codex(self) -> None:
        # Run three fresh attempts that each park as a question, then assert
        # the fourth tick parks before run_agent is called. Pin the cap at 3
        # so the test is hermetic against a `MAX_RETRIES_PER_DAY` env
        # override that would otherwise let the fourth tick spawn through.
        scenario = IssueScenario(*self._seeded())

        with patch.object(config, "MAX_RETRIES_PER_DAY", 3):
            # First three ticks: codex returns no commits + a question, parking on
            # awaiting_human. Each tick consumes one retry from the budget.
            for tick in range(3):
                self._run_implementing(
                    scenario.github,
                    scenario.issue,
                    run_agent=_agent(last_message=f"q{tick}"),
                    has_new_commits=False,
                )
                # Clear the awaiting-human flag manually so the next tick takes
                # the fresh-spawn branch again (simulating that the human answered
                # but the agent still failed to commit). We do NOT update
                # last_action_comment_id, but we also drop awaiting_human so the
                # else branch runs.
                pinned_data = scenario.github._pinned[8].data
                pinned_data["awaiting_human"] = False

            self.assertEqual(scenario.github.pinned_data(8).get(KEY_RETRY_COUNT), 3)
            self.assertIsNotNone(scenario.github.pinned_data(8).get("retry_window_start"))

            # Fourth tick: must park before codex spawns.
            mocks = self._run_implementing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(last_message="should not run"),
                has_new_commits=False,
            )

        mocks[RUN_AGENT].assert_not_called()
        self.assertTrue(scenario.github.pinned_data(8).get("awaiting_human"))
        last_comment = scenario.github.posted_comments[-1][1]
        self.assertIn("hit retry cap (3/day)", last_comment)
        self.assertIn("Window opened at", last_comment)

    def test_successful_commits_clear_counter(self) -> None:
        # Pre-seed near-cap state, then run a successful tick (commits + clean
        # tree + push succeeds). The PR-open path must clear the budget.
        gh, issue = self._seeded(
            retry_count=2,
            retry_window_start=_iso_hours_ago(1),
            retry_cap_continued=1,
        )

        self._run_implementing(
            gh,
            issue,
            run_agent=_agent(session_id=DEFAULT_SESSION, last_message=DONE_MESSAGE),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
        )

        pinned_data = gh.pinned_data(8)
        self.assertEqual(pinned_data.get(KEY_RETRY_COUNT), 0)
        # window_start cleared back to falsy, and with it the attempts a
        # continuation left on this issue's budget.
        self.assertFalse(pinned_data.get("retry_window_start"))
        self.assertFalse(pinned_data.get("retry_cap_continued"))
        self.assertEqual(len(gh.opened_prs), 1)

    def test_window_older_than_one_day_resets_counter(self) -> None:
        # Cap exhausted but the window is 25h old: next fresh attempt opens a
        # new window with count=1 and codex actually spawns.
        gh, issue = self._seeded(
            retry_count=3,
            retry_window_start=_iso_hours_ago(EXPIRED_WINDOW_HOURS),
        )

        mocks = self._run_implementing(
            gh,
            issue,
            run_agent=_agent(last_message="ask again"),
            has_new_commits=False,
        )

        mocks[RUN_AGENT].assert_called_once()
        pinned_data = gh.pinned_data(8)
        # Reset to 0 by the window-expired branch, then incremented to 1.
        self.assertEqual(pinned_data.get(KEY_RETRY_COUNT), 1)
        # Park message must NOT be the cap message.
        last_comment = gh.posted_comments[-1][1]
        self.assertNotIn("hit retry cap", last_comment)

    def test_human_resume_keeps_counter(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(9, label=LABEL_IMPLEMENTING)
        reply = FakeComment(
            id=HUMAN_REPLY_ID,
            body="please use sqlite",
            user=FakeUser("alice"),
        )
        issue.comments.append(reply)
        gh.add_issue(issue)
        gh.seed_state(
            9,
            awaiting_human=True,
            last_action_comment_id=ACTION_COMMENT_ID,
            codex_session_id="sess-old",
            retry_count=2,
            retry_window_start=_iso_hours_ago(1),
        )

        mocks = self._run_implementing(
            gh,
            issue,
            run_agent=_agent(session_id="sess-old", last_message=OK_MESSAGE),
            has_new_commits=[True],
            dirty_files=(),
            push_branch=True,
        )

        # Resume happened (codex was called once with the followup comment).
        mocks[RUN_AGENT].assert_called_once()
        # retry_count NOT incremented by the resume itself. The successful
        # _on_commits then clears it to 0.
        pinned_data = gh.pinned_data(9)
        self.assertEqual(pinned_data.get(KEY_RETRY_COUNT), 0)


class RetryCapParkDeliveryTest(unittest.TestCase, _RetryCapParkMixin):
    """What a refused fresh spawn says, and how often it says it.

    The gate is asked again on every eligible tick -- that is what makes the
    refusal idempotent -- so the notice is the one thing that may not be.
    """

    def test_repeated_ticks_park_once_and_say_it_once(self) -> None:
        gh, issue = self._exhausted()

        refusals = [
            self._refuse(gh, issue) for _ in range(RETRY_CAP_TICKS)
        ]

        self.assertEqual(refusals, [False, False, False])
        self.assertEqual(len(gh.posted_comments), 1)
        self.assertIn("hit retry cap", gh.posted_comments[0][1])
        self.assertEqual(
            self._phases(gh),
            [PHASE_DELIVERED, PHASE_STANDING, PHASE_STANDING],
        )
        # Durable and stable: the park survives the restart each re-read is.
        pinned = gh.pinned_data(RETRY_CAP_PARK_ISSUE)
        self.assertTrue(pinned.get(KEY_AWAITING_HUMAN))
        self.assertEqual(pinned.get(KEY_PARK_REASON), "retry_cap")
        self.assertEqual(pinned.get(KEY_RETRY_COUNT), RETRY_CAP_TICKS)

    def test_an_unbounded_cap_does_not_lift_the_park(self) -> None:
        # The gate answers the park before it answers the cap, so an operator
        # who turns the budget off does not resume a workflow whose notice
        # asked for a human -- only an explicit continuation does.
        gh, issue = self._exhausted()

        self._refuse(gh, issue)
        lifted = self._refuse(gh, issue, cap=0)

        self.assertFalse(lifted)
        self.assertEqual(len(gh.posted_comments), 1)
        self.assertEqual(
            self._phases(gh), [PHASE_DELIVERED, PHASE_STANDING],
        )

    def test_a_notice_on_the_thread_is_not_repeated(self) -> None:
        # A tick that posted and died before its write leaves the sentence
        # owed by a thread that already has it.
        gh, issue = self._exhausted()

        self._refuse(gh, issue, persist=False)
        self._refuse(gh, issue)

        self.assertEqual(len(gh.posted_comments), 1)
        self.assertEqual(
            self._phases(gh), [PHASE_DELIVERED, PHASE_RECONCILED],
        )

    def test_an_unreadable_thread_says_nothing(self) -> None:
        # The window the reconciliation exists for: a notice that landed under
        # a pinned write that then failed is on the thread, and a read that
        # fails cannot tell that from a thread with nothing on it. Posting on
        # a failed read is the duplicate this protocol is here to stop, so the
        # tick says nothing and the notice stays owed for the next one.
        gh, issue = self._exhausted()
        self._refuse(gh, issue, persist=False)

        with patch.object(gh, "comments_after", side_effect=RuntimeError):
            quiet = self._refuse(gh, issue)
        said_later = self._refuse(gh, issue)

        self.assertEqual([quiet, said_later], [False, False])
        self.assertEqual(len(gh.posted_comments), 1)
        # The tick that could read the thread found the sentence on it and
        # recorded it as said rather than saying it twice.
        self.assertEqual(
            self._phases(gh), [PHASE_DELIVERED, PHASE_RECONCILED],
        )

    def test_a_park_that_cannot_persist_says_nothing(self) -> None:
        # The park goes down before the sentence goes out. A notice nothing
        # durable backs is one no later tick would reconcile -- and the window
        # under it would roll over a day later with the issue running again
        # beneath a comment saying it had stopped.
        gh, issue = self._exhausted()
        state = gh.read_pinned_state(issue)

        with (
            patch.object(config, "MAX_RETRIES_PER_DAY", RETRY_CAP_TICKS),
            patch.object(gh, "write_pinned_state", side_effect=RuntimeError),
            self.assertRaises(RuntimeError),
        ):
            _retry_budget._charge_or_park(
                gh, issue, state, stage=STAGE_IMPLEMENTING,
            )

        self.assertEqual(gh.posted_comments, [])
        self.assertFalse(
            gh.pinned_data(RETRY_CAP_PARK_ISSUE).get(KEY_AWAITING_HUMAN),
        )


class RetryCapNoticeReplayTest(unittest.TestCase, _RetryCapParkMixin):
    """The sentence a stranded park is still owed, said at the next entry.

    A park routes the tick to a resume or to nothing, and neither road passes
    the gate that took it, so nothing below stage entry would ever say it.
    """

    def test_a_stranded_notice_is_said_at_stage_entry(self) -> None:
        client, parked = self._exhausted()
        with patch.object(client, "comments_after", side_effect=RuntimeError):
            self._refuse(client, parked)

        mocks = self._run_implementing(
            client, parked, run_agent=_agent(), has_new_commits=False,
        )

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(len(client.posted_comments), 1)
        self.assertIn("hit retry cap", client.posted_comments[0][1])
        # Said, and then refused: the same tick that finally delivers the
        # sentence is one the park stops, which is what the second record is.
        self.assertEqual(
            self._phases(client), [PHASE_DELIVERED, PHASE_STANDING],
        )
        # Said once and settled durably, so the tick after it says nothing.
        self.assertNotIn(
            KEY_RETRY_CAP_NOTICE, client.pinned_data(RETRY_CAP_PARK_ISSUE),
        )


class RetryCapContinueGateTest(unittest.TestCase, _RetryCapContinueMixin):
    """What lifts a standing retry-cap park, and what may not.

    The park is the budget's rather than a question's: nothing under this
    stage can pay for a spawn while it stands, so the one reply that changes
    anything is the one that buys another attempt.
    """

    def test_a_trusted_command_anywhere_buys_one(self) -> None:
        for reply, replies, answered in (
            ("nothing new on the thread", (), None),
            (
                "guidance carrying no command",
                (TRUSTED_GUIDANCE,),
                None,
            ),
            (
                "the command from outside the allowlist",
                ((CONTINUE_COMMAND, OUTSIDE_AUTHOR),),
                None,
            ),
            (
                "the command alone",
                (TRUSTED_COMMAND,),
                FIRST_REPLY_ID,
            ),
            (
                "the command carrying an explanation",
                ((f"{CONTINUE_COMMAND}\n\n{GUIDANCE_REPLY}", TRUSTED_AUTHOR),),
                FIRST_REPLY_ID,
            ),
            (
                "words written after the command",
                (
                    TRUSTED_COMMAND,
                    TRUSTED_GUIDANCE,
                ),
                FIRST_REPLY_ID + 1,
            ),
            (
                "the command written after the words",
                (
                    TRUSTED_GUIDANCE,
                    TRUSTED_COMMAND,
                ),
                FIRST_REPLY_ID + 1,
            ),
        ):
            with self.subTest(reply=reply):
                github, parked = self._parked(*replies)

                self.assertEqual(
                    self._decide(github, parked), answered is None,
                )
                self._assert_bought(github, answered=answered)

    def test_a_later_command_answers_over_chatter(self) -> None:
        # A refused tick consumes nothing, so what a human wrote before
        # reaching for the command stays on the unread side of the watermark
        # -- and the tick that reads both has to act on the command rather
        # than be talked out of it, or the park is unanswerable for good.
        github, parked = self._parked(TRUSTED_GUIDANCE)

        self.assertTrue(self._decide(github, parked))
        self._assert_bought(github, answered=None)
        parked.comments.append(FakeComment(
            id=FIRST_REPLY_ID + 1,
            body=CONTINUE_COMMAND,
            user=FakeUser(TRUSTED_AUTHOR),
        ))

        self.assertFalse(self._decide(github, parked))
        self._assert_bought(github, answered=FIRST_REPLY_ID + 1)

    def test_a_failed_notice_read_buys_nothing(self) -> None:
        # The entry replay could not read the thread, so the sentence this
        # park owes is still unsaid -- and a command written before the
        # question was asked is no answer to it. Read here instead, a second
        # attempt at the same request would buy an attempt off those words
        # and then clear the notice the human was owed on the way out.
        github, parked = self._parked(
            TRUSTED_COMMAND, retry_cap_notice=OWED_NOTICE,
        )

        with (
            self._only_trusted(),
            patch.object(
                github,
                COMMENTS_AFTER,
                side_effect=[RuntimeError, parked.comments],
            ),
        ):
            mocks = self._run_implementing(
                github, parked, run_agent=_agent(), has_new_commits=False,
            )

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(github.posted_comments, [])
        self._assert_bought(github, answered=None)
        # Still owed, so the tick that can read the thread says it first.
        self.assertIn(KEY_RETRY_CAP_NOTICE, self._pinned(github))
        self.assertEqual(self._phases(github), [PHASE_STANDING])

    def _assert_bought(self, github, *, answered: int | None) -> None:
        """What the tick left durable, on each side of the one answer.

        `answered` is the comment the watermark should have been moved to,
        or None for a tick that refused. The grant and the park it lifts are
        one write, so a tick that dies past it cannot hand the same command
        out twice -- and a tick that refused wrote nothing at all.
        """
        bought = answered is not None
        pinned = self._pinned(github)
        self.assertEqual(bool(pinned.get(KEY_AWAITING_HUMAN)), not bought)
        self.assertEqual(
            pinned.get(KEY_PARK_REASON), None if bought else PARK_RETRY_CAP,
        )
        self.assertEqual(
            pinned.get(KEY_RETRY_CAP_CONTINUED),
            GRANTED_ATTEMPTS if bought else None,
        )
        self.assertEqual(KEY_RETRY_CAP_STAGE in pinned, not bought)
        self.assertEqual(
            pinned.get(KEY_LAST_ACTION_COMMENT_ID),
            answered if bought else PARKED_WATERMARK,
        )


class RetryCapGrantedAttemptTest(unittest.TestCase, _RetryCapContinueMixin):
    """What the attempt a human bought is, once the park is out of the way.

    One fresh spawn through the shared gate, and no other agent run: every
    other road to one resumes a session, which passes no gate and would leave
    the attempt on the issue with a run already made against it.
    """

    def test_the_tick_takes_the_bought_attempt(self) -> None:
        github, parked = self._parked(TRUSTED_COMMAND)

        with self._only_trusted():
            mocks = self._run_implementing(
                github,
                parked,
                run_agent=_agent(last_message=STUCK_MESSAGE),
                has_new_commits=False,
            )

        self._assert_fresh_run(mocks)
        pinned = self._pinned(github)
        # One attempt, spent by the spawn it bought: the window reopened at
        # the grant, so the count is this run and nothing before it.
        self.assertEqual(pinned.get(KEY_RETRY_COUNT), 1)
        self.assertEqual(pinned.get(KEY_RETRY_CAP_CONTINUED), 0)
        self.assertEqual(self._phases(github), [PHASE_CONTINUED])

    def test_an_edit_while_parked_spawns_fresh(self) -> None:
        # The requirements move while a human takes their time, and the
        # session that spent the budget is still pinned. Resumed against the
        # edit it would run the agent the continuation paid for and leave the
        # grant on the issue, ready to buy a second run nothing counted.
        github, parked = self._parked(
            TRUSTED_COMMAND,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            user_content_hash=STALE_CONTENT_HASH,
        )

        with self._only_trusted():
            mocks = self._run_implementing(
                github,
                parked,
                run_agent=_agent(last_message=STUCK_MESSAGE),
                has_new_commits=False,
            )

        self._assert_one_charged_spawn(github, mocks)

    def test_a_restart_still_owes_the_bought_attempt(self) -> None:
        # The grant is durable and the attempt is charged in memory, so a
        # process that died between them comes back to an unparked issue with
        # the attempt still owed -- and it is owed as a fresh spawn, whatever
        # the thread and the pinned session have become since.
        github, granted = self._granted(
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            user_content_hash=STALE_CONTENT_HASH,
        )

        mocks = self._run_implementing(
            github,
            granted,
            run_agent=_agent(last_message=STUCK_MESSAGE),
            has_new_commits=False,
        )

        self._assert_one_charged_spawn(github, mocks)

    def test_a_spawn_with_no_id_retires_the_old(self) -> None:
        # The spawn replaces the pinned id only when the run hands one back,
        # so nothing downstream of the grant can drop the session the cap
        # stopped: left pinned, the next reply would carry straight on from
        # the transcript that ran the budget out. The grant is durable, so
        # the tick that spends it is not always the one that read the
        # command -- and the budget is shared, so an issue can arrive here
        # carrying a grant this stage never granted.
        for road, on_the_command in (
            ("the tick that reads the command", True),
            ("a restart on the durable grant", False),
        ):
            with self.subTest(road=road):
                self._assert_retires_the_old_session(
                    on_the_command=on_the_command,
                )

    def _assert_retires_the_old_session(self, *, on_the_command: bool) -> None:
        """One grant-funded spawn that hands no id back, on either road."""
        seed = self._parked if on_the_command else self._granted
        replies = (TRUSTED_COMMAND,) if on_the_command else ()
        github, funded = seed(
            *replies, dev_agent=BACKEND_CLAUDE, dev_session_id=DEV_SESSION,
        )

        with self._only_trusted():
            self._run_implementing(
                github,
                funded,
                run_agent=_agent(session_id="", last_message=STUCK_MESSAGE),
                has_new_commits=False,
            )

        pinned = self._pinned(github)
        self.assertFalse(pinned.get(KEY_DEV_SESSION_ID))
        # The backend the issue is pinned to survives the retirement: what a
        # spent budget is not is a backend-selection problem.
        self.assertEqual(pinned.get(KEY_DEV_AGENT), BACKEND_CLAUDE)
        self._assert_reply_regrounds(github, funded)

    def _assert_reply_regrounds(self, github, parked) -> None:
        """The reply after the granted run starts a session of its own.

        Numbered off the thread rather than off the seed, because the tick
        before this one posted its own sentence there: ids ascend across a
        thread, so a hand-picked id would land on top of that sentence and be
        a reply no reader ever reaches.
        """
        parked.comments.append(FakeComment(
            id=github.next_reply_id(parked),
            body=GUIDANCE_REPLY,
            user=FakeUser(TRUSTED_AUTHOR),
        ))

        with self._only_trusted():
            mocks = self._run_implementing(
                github,
                parked,
                run_agent=_agent(last_message=STUCK_MESSAGE),
                has_new_commits=False,
            )

        resumed = self._assert_fresh_run(mocks)
        self.assertIn(RESUME_PROMPT_FRAGMENT, resumed.call_args[0][1])

    def _assert_one_charged_spawn(self, github, mocks) -> None:
        """The grant bought a fresh spawn, and the gate is what took it."""
        self._assert_fresh_run(mocks)
        self.assertFalse(
            any(
                DRIFT_RESUME_NOTICE in body
                for _, body in github.posted_comments
            ),
        )
        pinned = self._pinned(github)
        self.assertEqual(pinned.get(KEY_RETRY_COUNT), 1)
        self.assertEqual(pinned.get(KEY_RETRY_CAP_CONTINUED), 0)


class RetryCapParkOwnsTheTickTest(unittest.TestCase, _RetryCapContinueMixin):
    """The park is answered ahead of the drift and resume roads below it.

    Both of those would act on it as an ordinary awaiting-human issue -- the
    resume lifting the flag on any reply at all, and charging nothing for the
    session it starts -- so what they may reach is a park a human has bought
    an attempt for, and nothing else.
    """

    def test_a_park_nobody_answered_spends_nothing(self) -> None:
        for park, replies, window_hours in (
            ("a window the clock ran out of", (), EXPIRED_WINDOW_HOURS),
            ("a reply that is not the command", (TRUSTED_GUIDANCE,), 1),
        ):
            with self.subTest(park=park):
                self._assert_stands(*replies, window_hours=window_hours)

    def test_a_merged_pr_outranks_the_park(self) -> None:
        # The park is answered inside the preflight rather than ahead of it,
        # so a pull request that landed still ends the issue over a standing
        # one -- and a poll that leaves no `retry_cap` record behind is not a
        # park that lifted.
        github, finished = self._parked(
            TRUSTED_COMMAND, pr_number=CONTINUE_PR_NUMBER,
        )
        landed = github.pulls[CONTINUE_PR_NUMBER]
        landed.merged = True
        landed.state = PR_CLOSED

        with self._only_trusted():
            mocks = self._run_implementing(
                github, finished, run_agent=_agent(),
            )

        mocks[RUN_AGENT].assert_not_called()
        self.assertIn(
            (RETRY_CAP_CONTINUE_ISSUE, LABEL_DONE), github.label_history,
        )
        # Nothing was decided about the budget on the way past: no record,
        # and the command still sits unread on a thread that is finished.
        self.assertEqual(self._phases(github), [])
        self.assertEqual(
            self._pinned(github).get(KEY_LAST_ACTION_COMMENT_ID),
            PARKED_WATERMARK,
        )

    def test_a_hard_skipped_issue_buys_nothing(self) -> None:
        # `paused` / `backlog` park the issue outside the state machine, so
        # the command sits on the thread unread until the label comes off --
        # it is not consumed, and it buys no spawn under a hold.
        for skip_label in HARD_SKIP_LABELS:
            with self.subTest(label=skip_label):
                github, skipped = self._parked(TRUSTED_COMMAND)
                skipped.labels.append(FakeLabel(skip_label))
                seeded = self._pinned(github)

                with self._only_trusted():
                    issue_processing._process_issue(github, _TEST_SPEC, skipped)

                self.assertEqual(self._pinned(github), seeded)
                self.assertEqual(github.posted_comments, [])
                self.assertEqual(github.recorded_events, [])

    def _assert_stands(self, *replies, window_hours: int) -> None:
        """One tick over a park nobody answered, and what it left alone.

        The sentence was said when the park was taken, so a tick that refuses
        again says nothing and writes nothing -- and the records the size gate
        and the publication own are not this park's to spend.
        """
        github, parked = self._parked(
            *replies, window_hours=window_hours, **UNTOUCHED_RECORDS
        )
        seeded = self._pinned(github)
        writes = github.write_state_calls

        with self._only_trusted():
            mocks = self._run_implementing(
                github, parked, run_agent=_agent(), has_new_commits=False,
            )

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(github.posted_comments, [])
        self.assertEqual(github.write_state_calls, writes)
        self.assertEqual(self._pinned(github), seeded)
        self.assertEqual(self._phases(github), [PHASE_STANDING])
