# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing concurrency behavior.

Two windows, and both are about a human writing while a tick runs. The one
BEHIND the disposition is the ordinary watermark race: a comment landing after
the batch was cut may not be recorded as answered by the round that never
quoted it. The one AHEAD of it is what the stage's single thread read exists
for: the batch, the watermarks it settles, the requirements a report is stamped
with, and the conversation a fresh spawn is re-grounded on all come off the
SCAN's own read, so a comment landing after it enters none of them -- where a
second read taken later in the tick would put it in some and not others.
"""

from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_record_state as _record_state
from tests.workflow.stages.fixing import (
    fixing_test_support as support,
    report_crash_support as crash,
)
from tests.workflow.stages.fixing.prompt_expectations import (
    only_prompt,
    pr_feedback_prompt,
)

IssueScenario = support.IssueScenario

ALICE = support.ALICE
AWAITING_HUMAN = support.AWAITING_HUMAN
BOB = support.BOB
CONCURRENT_COMMENT_ID = support.CONCURRENT_COMMENT_ID
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_SESSION = support.DEV_SESSION
FIX_FEEDBACK = support.FIX_FEEDBACK
FakeComment = support.FakeComment
FakeUser = support.FakeUser
ISSUE = support.ISSUE
LAST_ACTION_COMMENT_ID = support.LAST_ACTION_COMMENT_ID
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PUSHED_MESSAGE = support.PUSHED_MESSAGE
RUN_AGENT = support.RUN_AGENT
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
STALE_PRE_COMMENT_HASH = support.STALE_PRE_COMMENT_HASH
TRIGGER_ID = support.TRIGGER_ID
USER_CONTENT_HASH = support.USER_CONTENT_HASH
VALIDATING = support.VALIDATING
_FixingFixtureMixin = support._FixingFixtureMixin
_InjectCommentAfterCall = support._InjectCommentAfterCall
_agent = support._agent
config = support.config
DEV_SESSION_ID = support.DEV_SESSION_ID
RESCAN = support.RESCAN
BATCH_ISSUE_ID = support.BATCH_ISSUE_ID
CAROL = support.CAROL
COMMAND_COMMENT_ID = support.COMMAND_COMMENT_ID
CONTINUE_COMMAND = support.CONTINUE_COMMAND
DAVE = support.DAVE
PARK_AGENT_SILENT = support.PARK_AGENT_SILENT
PARK_REASON = support.PARK_REASON
PARKED_COMMENT_WATERMARK = support.PARKED_COMMENT_WATERMARK
# The streak of silent parks that retires a session, set one short of the
# threshold the park that opened this round would have pushed it past.
SILENT_PARK_COUNT = "silent_park_count"
feedback = support.feedback
dev_fix = support.dev_fix
datetime = support.datetime
patch = support.patch
timedelta = support.timedelta
timezone = support.timezone


# What a human types while the tick is running, and the two moments it can
# land in: right after the scan cut the batch, and while the agent is out.
# Both are ahead of every answer the round still owes the issue thread.
_RUN_WINDOW_REPLY = "and please also drop the dead flag"

# The triggering feedback a poisoned round left bookmarked, which only the
# recorded ids can surface once the watermarks have moved past it.
_BOOKMARKED_FEEDBACK = "fix the null check"

# The two shapes that turn this stage's resume into a fresh SPAWN -- the road
# that re-grounds an agent by QUOTING the thread: no session to resume at all,
# and one the streak of silent parks has retired.
_RETIRED_SESSIONS = (
    ("missing", {DEV_SESSION_ID: None}),
    ("rotated", {SILENT_PARK_COUNT: 2}),
)


class FixingRunWindowTest(unittest.TestCase, _FixingFixtureMixin):
    """A reply written after the scan, and the answers it may not enter.

    The round's report is stamped with the requirements it was HANDED, so the
    settlement comparing its own fresh read against that revision refuses to
    publish -- which is the whole guard against answering questions nobody
    asked. Taken after the run instead, the fingerprint would fold the reply in,
    the settlement would find the two equal, and the reviewer would be handed a
    head over a comment no session ever saw and no watermark records.
    """

    def test_a_run_window_reply_is_no_requirement(self) -> None:
        for window, after_the_scan in (
            ("after the scan", True), ("during the run", False),
        ):
            with self.subTest(window=window):
                scenario = self._seeded()
                landed = self._landing(scenario)

                self._ran_over(scenario, landed, after_the_scan)

                pinned = scenario.github.pinned_data(ISSUE)
                # The report is recorded and still OWED: the settlement read
                # the issue again, found requirements the record does not
                # answer, and declined -- so nothing was published, the round
                # was not handed back, and the readers stay where they were
                # for the tick that answers this reply.
                self.assertIsNotNone(
                    crash.frozen_record(PinnedState(state_data=pinned))
                    or _record_state.read_pending_report(
                        PinnedState(state_data=pinned),
                    ),
                )
                self.assertEqual(scenario.github.label_history, [])
                self.assertLess(pinned[PR_LAST_COMMENT_ID], TRIGGER_ID)

    def test_a_fresh_spawn_quotes_the_scan_s_own_read(self) -> None:
        # The other answer the round owes that surface. A retired or missing
        # session turns this resume into a spawn, and a spawn re-grounds the
        # agent by quoting the thread -- off the read the batch was cut from,
        # never a second one. Taken at spawn time it is minutes newer, so the
        # agent is shown a comment the watermarks stop below and the next poll
        # pays a second developer to answer it.
        for case, retired in _RETIRED_SESSIONS:
            with self.subTest(session=case):
                scenario = self._seeded(**retired)
                landed = self._landing(scenario)

                with _after_the_scan(scenario, landed):
                    mocks = self._ticked(scenario)

                self.assertNotIn(_RUN_WINDOW_REPLY, only_prompt(mocks))
                self.assertIn(FIX_FEEDBACK, only_prompt(mocks))

    def _seeded(self, **extra_state):
        """A `fixing` issue with one unread reply, past the quiet window."""
        return IssueScenario(*self._seed(
            pr=self._open_pr(),
            issue_comments=[_aged(TRIGGER_ID, FIX_FEEDBACK, ALICE)],
            extra_state=extra_state or None,
        ))

    def _landing(self, scenario):
        """The comment a human writes while this tick is already running."""
        return _aged(
            scenario.github.next_reply_id(scenario.issue),
            _RUN_WINDOW_REPLY,
            BOB,
        )

    def _ran_over(self, scenario, landed, after_the_scan: bool):
        """One tick with `landed` written in the window this case is about."""
        if not after_the_scan:
            return self._ticked(scenario, mid_run=landed)
        with _after_the_scan(scenario, landed):
            return self._ticked(scenario)

    def _ticked(self, scenario, *, mid_run=None):
        """One whole fixing tick whose developer reports and pushes."""
        finished = _agent(
            session_id=DEV_SESSION, last_message=PUSHED_MESSAGE,
        )
        runs = support.MagicMock(return_value=finished)
        if mid_run is not None:
            runs = support.MagicMock(
                side_effect=_WritesWhileTheAgentIsOut(
                    scenario.issue, mid_run, finished,
                ),
            )
        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            return self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=runs,
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )


def _aged(comment_id: int, body: str, author: str):
    """One trusted human comment, old enough to clear the quiet window."""
    return FakeComment(
        id=comment_id,
        body=body,
        user=FakeUser(author),
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )


def _after_the_scan(scenario, comment):
    """Land `comment` the moment the scan's own read of the thread is cut."""
    return patch.object(
        feedback,
        RESCAN,
        _InjectCommentAfterCall(
            feedback._rescan_fixing_feedback, scenario.issue, comment,
        ),
    )


class _CountsThreadReads:
    """Every read of the issue thread, with the count at the agent run kept.

    The window the single-read contract is about is the one AHEAD of the
    developer: the batch a prompt quotes, the watermarks that batch settles,
    the requirements fingerprint and the conversation a fresh spawn is
    re-grounded on all have to come off one read, so what this records is how
    many were taken by the time the run began.
    """

    def __init__(self, issue, finished) -> None:
        self._reads = issue.get_comments
        self._finished = finished
        self.taken = 0
        self.before_the_run = None

    def __call__(self, *_called, **_options):
        """The developer run, noting what had been read by the time it began."""
        self.before_the_run = self.taken
        return self._finished

    def reading(self):
        """One read of the thread, counted, through the issue's own reader."""
        self.taken += 1
        return self._reads()


class _WritesWhileTheAgentIsOut:
    """The agent run a human comments during, rather than one they wait out.

    Spelled as the run itself because that is the only place this window is
    reachable: the agent seam is installed by the harness, so a case that
    wrapped it from outside would be replaced by the mock going in.
    """

    def __init__(self, issue, comment, finished) -> None:
        self._issue = issue
        self._comment = comment
        self._finished = finished

    def __call__(self, *_called, **_options):
        self._issue.comments.append(self._comment)
        return self._finished


class AcceptedRetryReadsOnceTest(unittest.TestCase, _FixingFixtureMixin):
    """An accepted `/orchestrator continue`, and the one read it may take.

    A replay is part of the batch rather than beside it: the resume settles
    what it replayed joined with the fresh rescan, and the report that round
    writes is stamped with the requirements of the same read. Rebuilt from a
    SECOND read of the thread, a bookmarked comment edited or deleted between
    the two reaches the developer in the prompt while the fingerprint beside
    it never saw it -- and the report that round writes is then one no
    settlement can place.
    """

    def test_a_replay_is_cut_from_the_scan_s_own_read(self) -> None:
        scenario = self._parked_with_a_batch()
        finished = _agent(
            session_id=DEV_SESSION, last_message=PUSHED_MESSAGE,
        )
        counted = _CountsThreadReads(scenario.issue, finished)

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS), \
                patch.object(
                    scenario.issue, "get_comments", counted.reading,
                ):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=support.MagicMock(side_effect=counted),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        self.assertEqual(counted.before_the_run, 1)
        # And the replay really happened off it: the bookmarked comment the
        # advanced watermarks no longer surface is in the prompt.
        self.assertIn(_BOOKMARKED_FEEDBACK, only_prompt(mocks))

    def _parked_with_a_batch(self):
        """A session-failure park whose triggering batch is bookmarked.

        The batch comment sits BELOW the advanced watermark -- the shape a
        poisoned resume leaves -- so only the recorded ids surface it, while
        the bare command above that watermark is what the rescan finds.
        """
        bookmarked = _aged(BATCH_ISSUE_ID, _BOOKMARKED_FEEDBACK, CAROL)
        command = _aged(COMMAND_COMMENT_ID, CONTINUE_COMMAND, DAVE)
        return IssueScenario(*self._seed(
            pr=self._open_pr(),
            issue_comments=[bookmarked, command],
            extra_state={
                AWAITING_HUMAN: True,
                PARK_REASON: PARK_AGENT_SILENT,
                PR_LAST_COMMENT_ID: PARKED_COMMENT_WATERMARK,
                "pending_fix_issue_ids": [BATCH_ISSUE_ID],
                support.PENDING_FIX_ISSUE_MAX_ID: BATCH_ISSUE_ID,
            },
        ))


class FixingContentHashAndConcurrencyTest(
    unittest.TestCase,
    _FixingFixtureMixin,
):
    def test_consumed_comment_refreshes_content_hash(
        self,
    ) -> None:
        # When fixing feeds a fresh issue-thread comment to the dev,
        # the next tick's `_handle_validating` would otherwise see the
        # same comment as user-content drift (the hash covers title +
        # body + human issue-thread comments) and resume the dev a
        # second time on input it already handled. The hash must
        # advance with the consumption so the validating drift check
        # is a no-op on the next tick.
        from orchestrator.workflow.engine.content_hash import _compute_user_content_hash

        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="please fix the docstring",
            user=FakeUser(ALICE),
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(
            *self._seed(
                pr=pr,
                issue_comments=[comment],
                extra_state={
                    # Stale hash from before the human comment landed.
                    USER_CONTENT_HASH: STALE_PRE_COMMENT_HASH,
                },
            )
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        self._pinned_data = scenario.github.pinned_data(ISSUE)
        # Pushed successfully, flipped directly to validating.
        self.assertIn((ISSUE, VALIDATING), scenario.github.label_history)
        # The stored hash matches the current computed hash, i.e. the
        # validating tick's `_detect_user_content_change` will be a
        # no-op rather than re-resuming the dev on the already-consumed
        # comment.
        from orchestrator.workflow.engine.comments import _orchestrator_ids

        expected = _compute_user_content_hash(
            scenario.issue,
            _orchestrator_ids(
                PinnedState(data=dict(self._pinned_data)),
            ),
        )
        self.assertEqual(self._pinned_data.get(USER_CONTENT_HASH), expected)
        self.assertNotEqual(
            self._pinned_data.get(USER_CONTENT_HASH),
            STALE_PRE_COMMENT_HASH,
        )

    def test_failed_fix_refreshes_content_hash(self) -> None:
        # Symmetric guard for the failure path: the dev saw the
        # comment via the resume prompt even when the push failed,
        # so the hash baseline must move with the consumption.
        # Otherwise a later relabel out of `fixing` into a stage
        # that consults `_detect_user_content_change` would re-fire
        # on the same comment.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body=FIX_FEEDBACK,
            user=FakeUser(ALICE),
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(
            *self._seed(
                pr=pr,
                issue_comments=[comment],
                extra_state={USER_CONTENT_HASH: STALE_PRE_COMMENT_HASH},
            )
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(timed_out=True),
                head_shas=(SHA_BEFORE,),
            )

        pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertNotEqual(
            pinned_data.get(USER_CONTENT_HASH),
            STALE_PRE_COMMENT_HASH,
        )

    def test_pushed_bump_keeps_concurrent_comment(
        self,
    ) -> None:
        # Race window: a human posts an issue-thread comment AFTER the
        # handler's rescan but BEFORE the post-push watermark advance.
        # The pushed-fix bump MUST NOT leap past the unseen comment;
        # otherwise the next in_review tick (after validating completes)
        # would skip the feedback and the in_review HITL ready-ping
        # could advertise the PR as ready for human merge over it. The
        # legacy in_review pushed-fix path had the same constraint and
        # advanced only to comments actually fed to the dev.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        triggering = FakeComment(
            id=TRIGGER_ID,
            body="please fix the bug",
            user=FakeUser(ALICE),
            created_at=long_ago,
        )
        self._pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=self._pr, issue_comments=[triggering]))

        # Splice in a concurrent human comment with id higher than the
        # triggering one mid-handler so the bump's `latest_comment_id`
        # candidate would otherwise leap past it.
        concurrent = FakeComment(
            id=CONCURRENT_COMMENT_ID,
            body="actually also rename helper",
            user=FakeUser(BOB),
            created_at=long_ago,
        )
        fix_and_inject = _InjectCommentAfterCall(
            dev_fix._handle_dev_fix_result,
            scenario.issue,
            concurrent,
        )

        with (
            patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
            patch.object(
                dev_fix,
                "_handle_dev_fix_result",
                fix_and_inject,
            ),
        ):
            self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        self._pinned_data = scenario.github.pinned_data(ISSUE)
        # What the round recorded as consumed stops at the triggering comment
        # and does NOT leap past the concurrent one: the record is what the
        # write completing the publication applies, so a pair frozen past an
        # unquoted comment would swallow it for good. Read off the
        # TRANSACTION, since the binding this tick made moved the record
        # there -- the frozen pairs travel with the debt.
        self.assertEqual(
            _record_state.read_pending_report(
                PinnedState(state_data=self._pinned_data),
            ).watermarks,
            (
                (LAST_ACTION_COMMENT_ID, TRIGGER_ID),
                (PR_LAST_COMMENT_ID, TRIGGER_ID),
            ),
        )
        # And the reviewer is not handed the head, because the comment that
        # landed mid-run moved the requirements the report was written
        # against: the settlement declines, so the readers stay where they
        # were and the next tick reads the concurrent comment as fresh.
        self.assertEqual(scenario.github.label_history, [])
        self.assertLess(self._pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)

    def test_failed_bump_keeps_concurrent_comment(
        self,
    ) -> None:
        # Symmetric guard for the failure path: a human posts an
        # issue-thread comment AFTER the rescan but BEFORE the
        # post-park watermark advance. The bump MUST NOT leap past it;
        # otherwise the next fixing tick sees `awaiting_human` with no
        # new feedback, the gate fires, and the human's comment is
        # silently dropped. Verifies the "comments arriving while
        # already labeled `fixing`" contract on the timeout/dirty/push-
        # fail paths, mirroring the success-path guard above.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        triggering = FakeComment(
            id=TRIGGER_ID,
            body="please fix the bug",
            user=FakeUser(ALICE),
            created_at=long_ago,
        )
        self._pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=self._pr, issue_comments=[triggering]))

        concurrent = FakeComment(
            id=CONCURRENT_COMMENT_ID,
            body="actually also rename helper",
            user=FakeUser(BOB),
            created_at=long_ago,
        )
        fail_and_inject = _InjectCommentAfterCall(
            dev_fix._handle_dev_fix_result,
            scenario.issue,
            concurrent,
        )

        with (
            patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
            patch.object(
                dev_fix,
                "_handle_dev_fix_result",
                fail_and_inject,
            ),
        ):
            self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(timed_out=True),
                head_shas=(SHA_BEFORE,),
            )

        self._pinned_data = scenario.github.pinned_data(ISSUE)
        # Parked awaiting human (timeout failure).
        self.assertTrue(self._pinned_data.get(AWAITING_HUMAN))
        # Watermark advanced past the consumed triggering comment but
        # NOT past the concurrent one -- the next fixing tick must
        # still see the concurrent comment as fresh feedback, and so
        # must the issue-action reader the same round settles.
        self.assertGreaterEqual(self._pinned_data.get(PR_LAST_COMMENT_ID), TRIGGER_ID)
        self.assertLess(self._pinned_data.get(PR_LAST_COMMENT_ID), CONCURRENT_COMMENT_ID)
        self.assertLess(
            self._pinned_data.get(LAST_ACTION_COMMENT_ID), CONCURRENT_COMMENT_ID,
        )

        # Second tick: rescan picks up the concurrent comment so
        # `awaiting_human and not new_feedback` is False; park flags
        # clear and the dev resumes with the human's text. Use a
        # successful agent result this time so the second tick
        # produces a push and we can assert the flow recovered.
        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        # The next resume is handed the concurrent comment and NOTHING else:
        # the batch the first tick consumed is answered, so a prompt carrying
        # it again is the replay this settlement exists to prevent.
        self.assertEqual(
            only_prompt(self._mocks), pr_feedback_prompt([concurrent]),
        )
