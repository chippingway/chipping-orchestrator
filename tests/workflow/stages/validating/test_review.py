# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from contextlib import ExitStack

from tests.workflow.stages.validating import (
    validating_review_test_support as review_support,
)

MagicMock = review_support.MagicMock
Path = review_support.Path
patch = review_support.patch
config = review_support.config
FakeComment = review_support.FakeComment
FakeGitHubClient = review_support.FakeGitHubClient
FakeUser = review_support.FakeUser
make_issue = review_support.make_issue
EVENT_AGENT_SPAWN = review_support.EVENT_AGENT_SPAWN
LABEL_DOCUMENTING = review_support.LABEL_DOCUMENTING
LABEL_FIXING = review_support.LABEL_FIXING
LABEL_IN_REVIEW = review_support.LABEL_IN_REVIEW
LABEL_VALIDATING = review_support.LABEL_VALIDATING
PROVIDER_OVERLOAD_MENTION = review_support.PROVIDER_OVERLOAD_MENTION
PROVIDER_OVERLOAD_MESSAGE = review_support.PROVIDER_OVERLOAD_MESSAGE
PROVIDER_UNAVAILABLE_PHRASE = review_support.PROVIDER_UNAVAILABLE_PHRASE
STAGE_FIXING = review_support.STAGE_FIXING
STAGE_VALIDATING = review_support.STAGE_VALIDATING
REVIEW_APPROVED_MESSAGE = review_support.REVIEW_APPROVED_MESSAGE
REVIEW_CHANGES_REQUESTED_MESSAGE = review_support.REVIEW_CHANGES_REQUESTED_MESSAGE
ROLE_DEVELOPER = review_support.ROLE_DEVELOPER
ROLE_REVIEWER = review_support.ROLE_REVIEWER
_PatchedWorkflowMixin = review_support._PatchedWorkflowMixin
_agent = review_support._agent
_issue_branch = review_support._issue_branch
_open_pr_for = review_support._open_pr_for
_FreshReviewFixtureMixin = review_support.FreshReviewFixtureMixin
_FixLoopFixtureMixin = review_support.FixLoopFixtureMixin
_ContinueCommandFixtureMixin = review_support.ContinueCommandFixtureMixin

FIX_LOOP_ISSUE = 6
RESUME_PR = 13
KEY_SOURCE_STAGE = "late_source_stage"
MAX_ADDED_LINES = "MAX_ADDED_LINES"
CEILING = 5
PAST_THE_CEILING = 6
SILENT_STREAK_ISSUE = 70
SILENT_STREAK_PR = 14
HUMAN_COMMENT_ID = 1100
ACTION_COMMENT_ID = 950
STDERR_PAYLOAD_SIZE = 8192
STDERR_PREFIX_SIZE = 4096
DEV_SESSION = "dev-sess"
RUN_AGENT = "run_agent"
FIXED_MESSAGE = "fixed"
BEFORE_FIX_SHA = review_support.BEFORE_FIX_SHA
AFTER_FIX_SHA = review_support.AFTER_FIX_SHA
FIX_HEAD_SHAS = review_support.FIX_HEAD_SHAS
CF_BLOB = (
    "cf_chl_opt … Enable JavaScript and cookies to continue. "
    "Verifying you are human. This may take a few seconds."
)
PUSH_BRANCH = "_push_branch"
# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"
REVIEW_ROUND = "review_round"
AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
AGENT_ROLE = "agent_role"
EVENT_NAME = "event"
BACKEND_CLAUDE = "claude"
BACKEND_CODEX = "codex"
HUMAN_LOGIN = "alice"


class HandleValidatingFreshReviewTest(
    unittest.TestCase,
    _FreshReviewFixtureMixin,
):
    """Route explicit review verdicts and surface unknown output."""

    def test_approved_flips_label_and_does_not_resume(self) -> None:
        gh, issue = self._seeded()
        mocks = self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
        )

        self.assertEqual(mocks[RUN_AGENT].call_count, 1)
        # Approval routes through `documenting` for the final docs pass
        # before in_review picks up.
        self.assertIn((5, LABEL_DOCUMENTING), gh.label_history)
        self.assertNotIn((5, LABEL_IN_REVIEW), gh.label_history)
        self.assertTrue(
            any(
                ":white_check_mark: codex review approved" in body
                for _, body in gh.posted_pr_comments
            )
        )

    def test_changes_requested_resume_and_bump_round(self) -> None:
        gh, issue = self._seeded()
        mocks = self._run_validating(
            gh,
            issue,
            run_agent=[
                _agent(
                    session_id="rev-sess",
                    last_message=REVIEW_CHANGES_REQUESTED_MESSAGE,
                ),
                _fixed(),
            ],
            dirty_files=(),
            push_branch=True,
            # 1: before_sha for the dev-fix run. 2: after_sha to confirm
            # the new commit.
            head_shas=FIX_HEAD_SHAS,
        )

        self._assert_dev_fix_call(mocks)

        self.assertTrue(
            any(
                ":eyes: codex review (round 1/" in body
                and "Fix typo" in body
                for _, body in gh.posted_pr_comments
            )
        )
        mocks[PUSH_BRANCH].assert_called_once()
        self.assertEqual(gh.pinned_data(5).get(REVIEW_ROUND), 1)
        # The dev-fix subphase runs under the `fixing` label so the active
        # job is observably "fixing reviewer-requested changes" rather
        # than "workflow:validating". On a successful pushed fix the handler flips
        # back to `validating` so the reviewer re-evaluates the new head
        # on the next tick. No documenting hop -- the docs pass only runs
        # as the final-docs handoff after approval.
        self._assert_fix_labels(gh)

    def test_unknown_verdict_parks_with_message(self) -> None:
        gh, issue = self._seeded()
        self._run_validating(
            gh,
            issue,
            run_agent=_agent(
                last_message="I'm not sure what to think",
                stderr="some subprocess noise",
            ),
        )

        self.assertTrue(gh.pinned_data(5).get(AWAITING_HUMAN))
        last_comment = gh.posted_comments[-1][1]
        self.assertIn("did not emit a VERDICT line", last_comment)
        self.assertIn("> I'm not sure what to think", last_comment)
        # Real reviewer text is present, so the operator does not need
        # subprocess stderr in addition -- skip the diagnostic block.
        self.assertNotIn("Reviewer stderr", last_comment)
        # Label stays validating: no in_review transition.
        self.assertNotIn((5, LABEL_IN_REVIEW), gh.label_history)

    def test_empty_review_park_shows_stderr_exit(self) -> None:
        # Codex hit a Cloudflare interstitial: the agent exited with
        # nothing on stdout but the CF blob landed on stderr (#36). The
        # park comment must carry that tail so the operator can
        # distinguish CF / quota / auth from a true silent review.
        gh, issue = self._seeded()
        log_capture = MagicMock()
        with ExitStack() as stack:
            log_capture.records = stack.enter_context(
                self.assertLogs("orchestrator.workflow", level="WARNING"),
            )
            self._run_validating(
                gh,
                issue,
                run_agent=_agent(
                    last_message="",
                    stderr=CF_BLOB,
                    exit_code=2,
                ),
            )

        self.assertTrue(gh.pinned_data(5).get(AWAITING_HUMAN))
        last_comment = gh.posted_comments[-1][1]
        self.assertIn("did not emit a VERDICT line", last_comment)
        self.assertIn("(reviewer produced no final message)", last_comment)
        self.assertIn("_Reviewer stderr (last 1KB):_", last_comment)
        self.assertIn("Enable JavaScript and cookies", last_comment)
        self.assertIn("_Reviewer exit code:_ 2", last_comment)
        # Same data flowed to a WARNING log so operators tailing the
        # orchestrator log don't have to read GitHub to triage.
        self.assertTrue(
            any(
                "reviewer emitted no VERDICT" in record.getMessage() and "exit_code=2" in record.getMessage()
                for record in log_capture.records.records
            )
        )

    def test_empty_review_park_truncates_long_stderr(self) -> None:
        # A multi-MB CF response must not bloat the issue body. The
        # park comment caps stderr at 1KB.
        gh, issue = self._seeded()
        padding = "X" * STDERR_PAYLOAD_SIZE
        huge = f"{padding}TAIL_MARKER"
        self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message="", stderr=huge, exit_code=1),
        )

        last_comment = gh.posted_comments[-1][1]
        self.assertIn("TAIL_MARKER", last_comment)
        # The leading head of the noise must be dropped by the cap.
        self.assertNotIn("X" * STDERR_PREFIX_SIZE, last_comment)

    def test_empty_review_without_stderr_omits_block(self) -> None:
        gh, issue = self._seeded()
        self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message="", stderr=""),
        )

        last_comment = gh.posted_comments[-1][1]
        self.assertIn("did not emit a VERDICT line", last_comment)
        self.assertNotIn("_Reviewer stderr", last_comment)
        self.assertNotIn("_Reviewer exit code:_", last_comment)


class HandleValidatingReviewerFailureTest(
    unittest.TestCase,
    _FreshReviewFixtureMixin,
):
    """Classify timeout, crash, and silent reviewer outcomes."""

    def test_reviewer_timeout_parks(self) -> None:
        failure_github, failure_issue = self._seeded()
        self._run_validating(
            failure_github,
            failure_issue,
            run_agent=_agent(timed_out=True),
        )

        failure_state = failure_github.pinned_data(5)
        self.assertTrue(failure_state.get(AWAITING_HUMAN))
        # Tagged transient so the next tick re-spawns the reviewer instead
        # of waiting for a human comment that the timeout itself does not
        # produce.
        self.assertEqual(failure_state.get(PARK_REASON), "reviewer_timeout")
        last_comment = failure_github.posted_comments[-1][1]
        self.assertIn("reviewer timed out", last_comment)
        self.assertNotIn((5, LABEL_IN_REVIEW), failure_github.label_history)

    def test_silent_crash_parks_reviewer_failed(self) -> None:
        # The reviewer agent crashed (e.g. codex returned `Error: No such
        # file or directory (os error 2)`): empty last_message + non-zero
        # exit code. Tag the park as `reviewer_failed` so the next tick's
        # transient-recovery branch re-spawns the reviewer silently
        # without needing a human comment.
        failure_github, failure_issue = self._seeded()
        self._run_validating(
            failure_github,
            failure_issue,
            run_agent=_agent(last_message="", stderr="boom", exit_code=2),
        )

        failure_state = failure_github.pinned_data(5)
        self.assertTrue(failure_state.get(AWAITING_HUMAN))
        self.assertEqual(failure_state.get(PARK_REASON), "reviewer_failed")

    def test_provider_refusal_parks_reviewer_failed(self) -> None:
        # The provider refused to serve the turn, so the reviewer's output
        # slot carries a NON-EMPTY message that is the server's words. Reading
        # it as a verdict the reviewer merely forgot to mark would send an
        # outage to manual adjudication; tag `reviewer_failed` so the next
        # tick's transient-recovery branch re-spawns the reviewer, and say so
        # in the comment rather than asking for a judgment nobody has to make.
        failure_github, failure_issue = self._seeded()
        self._run_validating(
            failure_github,
            failure_issue,
            run_agent=_agent(
                last_message=PROVIDER_OVERLOAD_MESSAGE,
                exit_code=1,
            ),
        )

        failure_state = failure_github.pinned_data(5)
        self.assertTrue(failure_state.get(AWAITING_HUMAN))
        self.assertEqual(failure_state.get(PARK_REASON), "reviewer_failed")
        last_comment = failure_github.posted_comments[-1][1]
        self.assertIn(PROVIDER_UNAVAILABLE_PHRASE, last_comment)
        self.assertNotIn("manual adjudication needed", last_comment)

    def test_text_unknown_verdict_not_tagged_failed(self) -> None:
        # When the reviewer DID emit text but no VERDICT line, the park
        # is real adjudication and must NOT be silently retried -- a
        # human needs to read the message. Park reason stays cleared. A
        # review that WROTE about a provider outage is such a message: the
        # refusal is its subject, not its outcome.
        for last_message in ("not sure what to think", PROVIDER_OVERLOAD_MENTION):
            with self.subTest(last_message=last_message):
                failure_github, failure_issue = self._seeded()
                self._run_validating(
                    failure_github,
                    failure_issue,
                    run_agent=_agent(
                        last_message=last_message,
                        exit_code=0,
                    ),
                )

                failure_state = failure_github.pinned_data(5)
                self.assertTrue(failure_state.get(AWAITING_HUMAN))
                self.assertIsNone(failure_state.get(PARK_REASON))

    def test_empty_zero_exit_message_not_failed(self) -> None:
        # Defensive: empty last_message but exit_code == 0 is not a
        # crash -- the agent reported success without producing output.
        # Don't tag transient; a clean exit with no text needs human
        # adjudication, not a silent retry that would loop the same way.
        failure_github, failure_issue = self._seeded()
        self._run_validating(
            failure_github,
            failure_issue,
            run_agent=_agent(last_message="", stderr="", exit_code=0),
        )

        failure_state = failure_github.pinned_data(5)
        self.assertTrue(failure_state.get(AWAITING_HUMAN))
        self.assertIsNone(failure_state.get(PARK_REASON))


class HandleValidatingFixLoopEdgeCasesTest(
    unittest.TestCase,
    _FixLoopFixtureMixin,
):
    """Keep unsafe reviewer-requested fixes parked without round drift."""

    def test_dev_fix_timeout_parks_agent_timeout(self) -> None:
        # The dev agent timed out mid-fix. The park must be tagged so the
        # next tick's recovery branch can rerun the reviewer instead of
        # waiting for a human comment that the timeout itself cannot
        # produce. The pre-agent SHA must also be persisted so recovery
        # can tell whether the agent committed before timing out (the
        # naive `_has_new_commits()` check is unconditionally true for a
        # PR worktree past its first fix).
        edge_github, edge_issue = self._seeded()
        self._run_validating(
            edge_github,
            edge_issue,
            run_agent=[
                self._changes_requested_review(),
                _agent(session_id=DEV_SESSION, timed_out=True),
            ],
            dirty_files=(),
            push_branch=True,
            head_shas=[BEFORE_FIX_SHA],
        )

        edge_state = edge_github.pinned_data(6)
        self.assertTrue(edge_state.get(AWAITING_HUMAN))
        self.assertEqual(edge_state.get(PARK_REASON), "agent_timeout")
        # `head_shas` are consumed in order: before_sha is the pre-run head,
        # which
        # is what gets persisted.
        self.assertEqual(edge_state.get("pre_dev_fix_sha"), BEFORE_FIX_SHA)
        last_comment = edge_github.posted_comments[-1][1]
        self.assertIn("agent timed out", last_comment)
        # CHANGES_REQUESTED flips the label to `fixing` BEFORE the dev
        # spawn so a parked subprocess leaves the active job labeled
        # `fixing` (the fixing handler then owns the awaiting-human
        # rescan + dev resume cycle on subsequent ticks).
        self.assertIn((FIX_LOOP_ISSUE, LABEL_FIXING), edge_github.label_history)
        self.assertNotIn((FIX_LOOP_ISSUE, LABEL_VALIDATING), edge_github.label_history)

    def test_no_commit_fix_parks_without_round_bump(self) -> None:
        edge_github, edge_issue = self._seeded()
        edge_patches = self._run_validating(
            edge_github,
            edge_issue,
            run_agent=[
                self._changes_requested_review(),
                _agent(session_id=DEV_SESSION, last_message="why?"),
            ],
            dirty_files=(),
            push_branch=True,
            # before_sha + after_sha (both the pre-run head -> no commit).
            head_shas=[BEFORE_FIX_SHA, BEFORE_FIX_SHA],
        )

        edge_patches[PUSH_BRANCH].assert_not_called()
        self.assertEqual(edge_github.pinned_data(6).get(REVIEW_ROUND), 0)
        self.assertTrue(edge_github.pinned_data(6).get(AWAITING_HUMAN))
        last_comment = edge_github.posted_comments[-1][1]
        self.assertIn("agent needs your input", last_comment)
        # The pre-spawn label flip is observed even on the no-commit park
        # path (the fixing handler then handles the awaiting-human rescan
        # on the next tick).
        self.assertIn((FIX_LOOP_ISSUE, LABEL_FIXING), edge_github.label_history)
        self.assertNotIn((FIX_LOOP_ISSUE, LABEL_VALIDATING), edge_github.label_history)

    def test_dev_fix_dirty_parks_round_unchanged(self) -> None:
        edge_github, edge_issue = self._seeded()
        edge_patches = self._run_validating(
            edge_github,
            edge_issue,
            run_agent=[
                self._changes_requested_review(),
                _agent(session_id=DEV_SESSION, last_message="partial"),
            ],
            dirty_files=["leftover.py"],
            push_branch=True,
            head_shas=FIX_HEAD_SHAS,
        )

        edge_patches[PUSH_BRANCH].assert_not_called()
        self.assertEqual(edge_github.pinned_data(6).get(REVIEW_ROUND), 0)
        self.assertTrue(edge_github.pinned_data(6).get(AWAITING_HUMAN))
        last_comment = edge_github.posted_comments[-1][1]
        self.assertIn("uncommitted change", last_comment)
        self.assertIn("leftover.py", last_comment)
        self.assertIn((FIX_LOOP_ISSUE, LABEL_FIXING), edge_github.label_history)
        self.assertNotIn((FIX_LOOP_ISSUE, LABEL_VALIDATING), edge_github.label_history)

    def test_dev_fix_push_fail_parks_round_unchanged(self) -> None:
        edge_github, edge_issue = self._seeded()
        self._run_validating(
            edge_github,
            edge_issue,
            run_agent=[
                self._changes_requested_review(),
                _agent(session_id=DEV_SESSION, last_message=FIXED_MESSAGE),
            ],
            dirty_files=(),
            push_branch=False,
            head_shas=FIX_HEAD_SHAS,
        )

        edge_state = edge_github.pinned_data(6)
        self.assertEqual(edge_state.get(REVIEW_ROUND), 0)
        self.assertTrue(edge_state.get(AWAITING_HUMAN))
        # The transient `push_failed` tag is what lets the next tick's
        # recovery branch silently retry the push without needing a human
        # comment to unstick the edge_issue.
        self.assertEqual(edge_state.get(PARK_REASON), "push_failed")
        last_comment = edge_github.posted_comments[-1][1]
        self.assertIn("git push failed", last_comment)
        self.assertIn((FIX_LOOP_ISSUE, LABEL_FIXING), edge_github.label_history)
        self.assertNotIn((FIX_LOOP_ISSUE, LABEL_VALIDATING), edge_github.label_history)

    def test_round_cap_parks_without_reviewer(self) -> None:
        edge_github, edge_issue = self._seeded(review_round=config.MAX_REVIEW_ROUNDS)
        edge_patches = self._run_validating(
            edge_github,
            edge_issue,
            run_agent=_agent(),
        )

        edge_patches[RUN_AGENT].assert_not_called()
        self.assertTrue(edge_github.pinned_data(6).get(AWAITING_HUMAN))
        last_comment = edge_github.posted_comments[-1][1]
        self.assertIn("review still has comments", last_comment)


def _fixed():
    """The dev run a CHANGES_REQUESTED tick spends after the reviewer's."""
    return _agent(session_id=DEV_SESSION, last_message=FIXED_MESSAGE)


class HandleValidatingFixLoopRoutingTest(
    unittest.TestCase,
    _FixLoopFixtureMixin,
):
    """Expose the fixing subphase and return pushed fixes to validating."""

    def test_a_held_fix_records_its_own_stage(self) -> None:
        # `stale_label_cache` writes `fixing` to the remote and leaves the
        # issue object at `validating`, so a size gate reading the label back
        # would freeze the state the issue has LEFT -- and a settled
        # adjudication continues at whatever the record names, which would
        # skip the fix loop's own completion entirely.
        held_github, held_issue = self._seeded(stale_label_cache=True)

        with patch.object(config, MAX_ADDED_LINES, CEILING):
            self._run_validating(
                held_github,
                held_issue,
                run_agent=[self._changes_requested_review(), _fixed()],
                dirty_files=(),
                push_branch=True,
                head_shas=FIX_HEAD_SHAS,
                added_lines=PAST_THE_CEILING,
            )

        pinned = held_github.pinned_data(FIX_LOOP_ISSUE)
        self.assertEqual(pinned[KEY_SOURCE_STAGE], LABEL_FIXING)

    def test_a_held_fix_still_spends_its_round(self) -> None:
        # This route counts the reviewer's round on a landed fix, and a held
        # one supersedes the rejected head just the same: the commit is on the
        # branch and a `single` verdict publishes it from there. The caller
        # returns before its own count, and nothing behind it counts either --
        # the settlement pushes the accepted commit and the resumed route
        # finds nothing left to publish -- so the round rides the gate's own
        # write, ahead of the relabel that hands the issue away.
        held_github, held_issue = self._seeded(stale_label_cache=True)

        with patch.object(config, MAX_ADDED_LINES, CEILING):
            self._run_validating(
                held_github,
                held_issue,
                run_agent=[self._changes_requested_review(), _fixed()],
                dirty_files=(),
                push_branch=True,
                head_shas=FIX_HEAD_SHAS,
                added_lines=PAST_THE_CEILING,
            )

        pinned = held_github.pinned_data(FIX_LOOP_ISSUE)
        self.assertEqual(pinned[REVIEW_ROUND], 1)
        self.assertIsNone(pinned.get("pending_fix_reviewer_comment_id"))

    def test_a_landed_fix_publishes_what_was_measured(self) -> None:
        # The push a fix earns is named against the commit the gate proved
        # rather than against the checkout it runs in, so work that landed on
        # the worktree between the reading and the push does not go out in its
        # place. It is pinned to the head this round began at -- the head the
        # reviewer read -- so a pull request somebody pushed to while the dev
        # was out refuses this push instead of being overwritten by work
        # measured against the head it used to be on.
        landed_github, landed_issue = self._seeded()

        landed_mocks = self._run_validating(
            landed_github,
            landed_issue,
            run_agent=[self._changes_requested_review(), _fixed()],
            dirty_files=(),
            push_branch=True,
            head_shas=FIX_HEAD_SHAS,
        )

        pushed = landed_mocks[PUSH_BRANCH].call_args
        self.assertEqual(pushed.kwargs[REVISION], AFTER_FIX_SHA)
        self.assertEqual(pushed.kwargs[LEASE], BEFORE_FIX_SHA)

    def test_enters_fixing_before_dev_spawn(self) -> None:
        # The dev-fix subphase must run under the `fixing` label so the
        # active job is observably "fixing reviewer-requested changes"
        # rather than "validating". The label flip lands BEFORE the dev
        # subprocess so an external observer never sees the dev work
        # labeled only `validating`; the `fixing` entry must therefore
        # appear in the label history strictly before any later flip
        # back to `validating`.
        #
        # `stale_label_cache` writes `fixing` to the remote but leaves
        # `route_issue.labels` at `validating` -- an issue object the write
        # did not refresh -- so the dev-run stage cannot be read back off the
        # route_issue: the reviewer-requested fix path must pass it explicitly.
        route_github, route_issue = self._seeded(stale_label_cache=True)
        self._run_validating(
            route_github,
            route_issue,
            run_agent=[
                self._changes_requested_review(),
                _agent(session_id=DEV_SESSION, last_message=FIXED_MESSAGE),
            ],
            dirty_files=(),
            push_branch=True,
            head_shas=FIX_HEAD_SHAS,
        )

        # Both flips landed in order: first `fixing` (pre-spawn), then
        # `validating` (post-push) so the reviewer reruns on the next tick.
        self.assertIn((6, LABEL_FIXING), route_github.label_history)
        self.assertIn((6, LABEL_VALIDATING), route_github.label_history)
        fixing_idx = route_github.label_history.index((6, LABEL_FIXING))
        validating_idx = route_github.label_history.index((6, LABEL_VALIDATING))
        self.assertLess(fixing_idx, validating_idx)
        # Reviewer work stays attributed to `validating`; the CHANGES_REQUESTED
        # developer fix is attributed to `fixing` even though the resume runs
        # on an `Issue` object whose labels still read `validating`.
        # Attributing the fix to `validating` would double-count its spend
        # against the reviewer/verify bucket.
        spawns_by_role = {
            event[AGENT_ROLE]: event for event in route_github.recorded_events if event[EVENT_NAME] == EVENT_AGENT_SPAWN
        }
        self.assertEqual(spawns_by_role[ROLE_REVIEWER]["stage"], STAGE_VALIDATING)
        self.assertEqual(spawns_by_role[ROLE_DEVELOPER]["stage"], STAGE_FIXING)

    def test_interrupted_fix_skips_write_and_push(self) -> None:
        # A shutdown-killed CHANGES_REQUESTED dev resume is ignored: the
        # handler does NOT persist the post-spawn state (so the per-session
        # resume budget `dev_resume_count` charged by `_resume_dev_with_text`
        # is not burned) and does NOT push. The pre-spawn `fixing` flip
        # stands; the next tick re-runs the cycle. Any local commit the
        # killed run left is republished by `_handle_dev_fix_result`'s
        # stranded-fix gate on the next clean resume, not this interrupted
        # one.
        route_github, route_issue = self._seeded(dev_agent=BACKEND_CLAUDE, dev_session_id=DEV_SESSION)
        route_patches = self._run_validating(
            route_github,
            route_issue,
            run_agent=[
                self._changes_requested_review(),
                _agent(
                    session_id=DEV_SESSION,
                    interrupted=True,
                    last_message="committed a partial fix before the SIGTERM",
                ),
            ],
            head_shas=[BEFORE_FIX_SHA],
        )

        # Reviewer + dev resume both ran.
        self.assertEqual(route_patches[RUN_AGENT].call_count, 2)
        # The interrupted run is not pushed.
        route_patches[PUSH_BRANCH].assert_not_called()
        # Pre-spawn flip landed; the route_issue did NOT bounce to validating this
        # tick (that happens on a later tick after a clean re-review).
        self.assertIn((6, LABEL_FIXING), route_github.label_history)
        self.assertNotIn((6, LABEL_VALIDATING), route_github.label_history)
        route_state = route_github.pinned_data(6)
        # Post-spawn write skipped: the resume-budget charge from
        # `_resume_dev_with_text` never persisted.
        self.assertIsNone(route_state.get("dev_resume_count"))
        # Interrupted is not a question / timeout / dirty park.
        self.assertFalse(route_state.get(AWAITING_HUMAN))

    def test_change_park_records_reviewer_anchor(self) -> None:
        # #742: on the validating -> fixing route the reviewer-feedback PR
        # comment id is anchored in `pending_fix_reviewer_comment_id` so a
        # session-failure park is retryable by `/orchestrator continue`.
        # `pending_fix_at` must stay UNSET -- it is the in_review-route
        # discriminator that drives the review-round reset, so setting it here
        # would mis-account the round on the eventual pushed fix.
        route_github, route_issue = self._seeded()
        self._run_validating(
            route_github,
            route_issue,
            run_agent=[
                self._changes_requested_review(),
                # No-commit park: the dev asks a question / goes silent.
                _agent(session_id=DEV_SESSION, last_message="why?"),
            ],
            dirty_files=(),
            push_branch=True,
            head_shas=[BEFORE_FIX_SHA, BEFORE_FIX_SHA],
        )

        route_state = route_github.pinned_data(6)
        self.assertTrue(route_state.get(AWAITING_HUMAN))
        # The reviewer feedback is anchored, and its id matches the PR comment
        # the handler posted this tick.
        self.assertIsNotNone(route_state.get("pending_fix_reviewer_comment_id"))
        # The in_review-route discriminator is NOT set on this route.
        self.assertIsNone(route_state.get("pending_fix_at"))
        self.assertIn((6, LABEL_FIXING), route_github.label_history)

    def test_pushed_fix_clears_reviewer_anchor(self) -> None:
        # On a pushed inline fix this reviewer round is addressed, so the
        # anchor is cleared (a later session-failure park must not replay it)
        # and the round bumps back on `validating`.
        route_github, route_issue = self._seeded(review_round=2)
        self._run_validating(
            route_github,
            route_issue,
            run_agent=[
                self._changes_requested_review(),
                _agent(session_id=DEV_SESSION, last_message=FIXED_MESSAGE),
            ],
            dirty_files=(),
            push_branch=True,
            head_shas=FIX_HEAD_SHAS,
        )

        route_state = route_github.pinned_data(6)
        self.assertIsNone(route_state.get("pending_fix_reviewer_comment_id"))
        self.assertEqual(route_state.get(REVIEW_ROUND), 3)
        self.assertEqual(route_github.label_history[-1], (6, LABEL_VALIDATING))


class HandleValidatingAwaitingHumanResumeTest(unittest.TestCase, _PatchedWorkflowMixin):
    def seed_human_resume(self):
        github = FakeGitHubClient()
        issue = make_issue(7, label=LABEL_VALIDATING)
        issue.comments.append(
            FakeComment(
                id=HUMAN_COMMENT_ID,
                body="use sqlite please",
                user=FakeUser(HUMAN_LOGIN),
            ),
        )
        github.add_issue(issue)
        github.seed_state(
            7,
            awaiting_human=True,
            last_action_comment_id=ACTION_COMMENT_ID,
            codex_session_id=DEV_SESSION,
            review_round=1,
            pr_number=RESUME_PR,
            branch=_issue_branch(7),
        )
        _open_pr_for(github, issue_number=7, pr_number=RESUME_PR)
        return github, issue

    def assert_human_resume(self, github, mocks) -> None:
        self.assertEqual(mocks[RUN_AGENT].call_count, 1)
        agent_call = mocks[RUN_AGENT].call_args
        self.assertEqual(agent_call.args[0], BACKEND_CODEX)
        self.assertEqual(agent_call.kwargs.get("resume_session_id"), DEV_SESSION)
        self.assertIn("use sqlite please", agent_call.args[1])
        mocks[PUSH_BRANCH].assert_called_once()
        state = github.pinned_data(7)
        self.assertFalse(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(REVIEW_ROUND), 2)
        self.assertNotIn((7, LABEL_DOCUMENTING), github.label_history)
        self.assertNotIn((7, LABEL_IN_REVIEW), github.label_history)

    def test_human_reply_bumps_round_without_reviewer(self) -> None:
        resume_github, resume_issue = self.seed_human_resume()

        resume_patches = self._run_validating(
            resume_github,
            resume_issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=FIXED_MESSAGE),
            dirty_files=(),
            push_branch=True,
            head_shas=FIX_HEAD_SHAS,
        )

        self.assert_human_resume(resume_github, resume_patches)

    def test_successful_fix_resets_silent_streak(self) -> None:
        # The validating / in_review fix paths exit on `_handle_dev_fix_result`
        # returning True without going through `_on_commits`. Without an
        # explicit reset on that branch, `silent_park_count` would still
        # carry over from earlier silent parks, and a later single empty
        # resume could tip an otherwise-healthy session past the
        # fresh-session threshold.
        resume_github = FakeGitHubClient()
        resume_issue = make_issue(SILENT_STREAK_ISSUE, label=LABEL_VALIDATING)
        resume_issue.comments.append(
            FakeComment(
                id=HUMAN_COMMENT_ID,
                body="please fix it",
                user=FakeUser(HUMAN_LOGIN),
            )
        )
        resume_github.add_issue(resume_issue)
        resume_github.seed_state(
            SILENT_STREAK_ISSUE,
            awaiting_human=True,
            last_action_comment_id=ACTION_COMMENT_ID,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            review_round=1,
            pr_number=SILENT_STREAK_PR,
            branch=_issue_branch(SILENT_STREAK_ISSUE),
            # Carryover from an earlier silent park; one short of the
            # fresh-session threshold.
            silent_park_count=1,
        )

        self._run_validating(
            resume_github,
            resume_issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=FIXED_MESSAGE),
            dirty_files=(),
            push_branch=True,
            head_shas=FIX_HEAD_SHAS,
        )

        resume_state = resume_github.pinned_data(SILENT_STREAK_ISSUE)
        self.assertEqual(
            resume_state.get("silent_park_count"),
            0,
            "a successful dev fix must reset the silent-park streak so a "
            "later transient empty result doesn't drop a healthy session",
        )


class HandleValidatingContinueCommandTest(
    unittest.TestCase,
    _ContinueCommandFixtureMixin,
):
    """Retry transient parks without forwarding the continue command."""

    def test_bare_continue_retries_without_literal(
        self,
    ) -> None:
        command_github, command_issue = self._seed(7, park_reason="agent_silent")

        command_patches = self._run_validating(
            command_github,
            command_issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=FIXED_MESSAGE),
            dirty_files=(),
            push_branch=True,
            head_shas=FIX_HEAD_SHAS,
        )

        self._assert_retry_result(command_github, command_patches)

    def test_bare_continue_on_question_park_refuses(self) -> None:
        command_github, command_issue = self._seed(8, park_reason=None)

        command_patches = self._run_validating(
            command_github,
            command_issue,
            run_agent=_agent(),
        )

        command_patches[RUN_AGENT].assert_not_called()
        self.assertTrue(
            any(
                "needs your actual guidance" in body
                for _, body in command_github.posted_comments
            )
        )
        command_state = command_github.pinned_data(8)
        self.assertTrue(command_state.get(AWAITING_HUMAN))
