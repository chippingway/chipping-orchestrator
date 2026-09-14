# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One whole tick that publishes what a transient `validating` park stranded.

The fixture both silent recoveries are driven through. Neither has an agent
behind it: the issue is parked, no comment arrived, and what the tick does is
push a commit an earlier round left on the branch -- so the world every case
here seeds is the world AFTER that round, and the only thing a case spells is
the fact it is about.

It is a `validating` scenario and lives with that stage's tests because what
it seeds and runs is this stage's handler, whichever seam the case is aimed
at.
"""

from __future__ import annotations

import pathlib
from unittest import mock

from orchestrator import config as _config

# The recovery cases name this module `support` and read the frozen commit
# off it rather than the measurement owner. Nothing here reads it, so the
# same-name alias is what declares the import a re-export.
from orchestrator.git.measurement.models import FrozenCommit as FrozenCommit
from orchestrator.git.worktrees import paths as _worktree_paths
from tests.support import fakes
from tests.workflow import fixtures
from tests.workflow.stages import implementing_fixing_test_cases

config = _config
patch = mock.patch
IssueScenario = implementing_fixing_test_cases.IssueScenario

MEASURED_BASE_SHA = fixtures.MEASURED_BASE_SHA
LABEL_DECOMPOSING = fixtures.LABEL_DECOMPOSING
LABEL_VALIDATING = fixtures.LABEL_VALIDATING

# The clause each healed park names, worded by the recovery owner and asserted
# from the leaf both stage packages share.
RECOVERED_PREFIX = fixtures.RECOVERED_PREFIX
PUSH_RETRIED_DETAIL = fixtures.PUSH_RETRIED_DETAIL
TIMEOUT_PUSHED_DETAIL = fixtures.TIMEOUT_PUSHED_DETAIL
TIMEOUT_EMPTY_DETAIL = fixtures.TIMEOUT_EMPTY_DETAIL

RECOVERY_ISSUE = 700
RECOVERY_PR = 77

# The mention the park left, which is what a healed park has to retire and
# what scopes the follow-up search to this episode.
PARK_MENTION_ID = 900

# A checkout the recovery can read. The handler asks whether the path exists
# before it probes anything, so the fixture answers with one that does.
PRESENT_WORKTREE = pathlib.Path("/tmp")

# The head the pull request was left standing on when the parked round opened:
# the branch is in sync with its publication at that point, since the reviewer
# has just read that head.
PUBLICATION_HEAD = fakes.DEFAULT_PR_HEAD_SHA

# The commit the parked round left in the checkout and never published, which
# is the head the recovery proves that checkout to.
STRANDED_CANDIDATE = fixtures.MEASURED_CANDIDATE_SHA

# A head somebody else pushed while the issue sat parked.
MOVED_HEAD = "ab" * (fixtures.SHA_LENGTH // 2)

# A commit the checkout went to between the recovery's own read and the proof
# the gate takes, for the race the reading refuses rather than publishes.
MOVED_MID_TICK = "de" * (fixtures.SHA_LENGTH // 2)

PARK_PUSH_FAILED = fixtures.PUSH_FAILED_PARK
PARK_AGENT_TIMEOUT = fixtures.AGENT_TIMEOUT_PARK
PARK_MEASUREMENT_FAILED = "late_measurement_failed"

AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
PRE_DEV_FIX_SHA = "pre_dev_fix_sha"
REVIEW_ROUND = "review_round"

# The approval a measured candidate earns and the head it is pinned to, which
# is all a failed push leaves behind: the generation naming the commit was
# retired by the write that granted them.
KEY_APPROVED_SHA = "late_approved_sha"
KEY_APPROVED_LEASE = "late_approved_lease"

# The receipt a landed gated push writes: the commit that reached the remote,
# the head that push replaced, and the pull request it went onto. The three
# are written together and read together -- the head dates the receipt to one
# publication attempt, and the number says which publication received it.
KEY_RECEIPT_SHA = "implementing_published_sha"
KEY_RECEIPT_LEASE = "implementing_published_lease"
KEY_RECEIPT_PR = "implementing_published_pr"

# The pinned fields a held candidate is handed to the adjudication under.
KEY_CANDIDATE_SHA = "late_candidate_sha"
KEY_BASE_SHA = "late_base_sha"
KEY_ADDITIONS = "late_additions"
KEY_PUBLISHED_SHA = "late_published_sha"
KEY_SOURCE_STAGE = "late_source_stage"

COUNT_ADDED_LINES = "_count_added_lines"
PUSH_BRANCH = "_push_branch"
RUN_AGENT = "run_agent"
WORKTREE_PATH = "_worktree_path"

# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"

CEILING = 5
UNDER_THE_CEILING = 4
PAST_THE_CEILING = 6
MAX_ADDED_LINES = "MAX_ADDED_LINES"
DECOMPOSE = "DECOMPOSE"


class _RecoveredPublicationAssertions:
    """What a tick that went through the gate on this seam looks like after."""

    def _pinned(self, scenario) -> dict:
        """What the pinned comment says once this tick has finished."""
        return scenario.github.pinned_data(RECOVERY_ISSUE)

    def _assert_pushed_once(self, mocks):
        """One push went out, reported so its keywords can be read off it."""
        pushed = mocks[PUSH_BRANCH]
        pushed.assert_called_once()
        return pushed.call_args

    def _assert_measured(self, mocks) -> None:
        """The candidate went through the reading rather than past it."""
        mocks[COUNT_ADDED_LINES].assert_called_once()

    def _assert_unmeasured(self, mocks) -> None:
        """No reading was taken -- the candidate was decided about already."""
        mocks[COUNT_ADDED_LINES].assert_not_called()

    def _assert_park_stands(self, scenario, reason: str) -> None:
        """The park is where the tick found it, and nothing was announced."""
        pinned = self._pinned(scenario)
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], reason)
        self.assertEqual(scenario.github.posted_comments, [])

    def _assert_park_cleared(self, scenario) -> None:
        """The park healed, so the flags are down and the label has not moved."""
        pinned = self._pinned(scenario)
        self.assertFalse(pinned[AWAITING_HUMAN])
        self.assertIsNone(pinned[PARK_REASON])
        self.assertEqual(scenario.github.label_history, [])

    def _assert_nothing_healed(self, scenario) -> None:
        """No follow-up, because no park of this stage's healed itself."""
        self.assertFalse([
            body for _, body in scenario.github.posted_comments
            if RECOVERED_PREFIX in body
        ])


class _RecoveredPublicationMixin(
    fixtures._PatchedWorkflowMixin,
    fixtures._RecoveryFollowupAssertions,
    _RecoveredPublicationAssertions,
):
    """The parked issue every silent recovery here starts from."""

    def _seed_park(self, *, reason: str, **extra_state):
        """A `validating` issue parked on `reason` with nobody having replied.

        The transient branch fires only when NO comment arrived since the
        park's own mention, so the thread is left exactly as the park left it
        and the watermark is the mention's own id.
        """
        github = fakes.FakeGitHubClient()
        issue = fakes.make_issue(RECOVERY_ISSUE, label=LABEL_VALIDATING)
        github.add_issue(issue)
        seeded = {
            "pr_number": RECOVERY_PR,
            "branch": fixtures._issue_branch(RECOVERY_ISSUE),
            "dev_agent": fixtures.BACKEND_CLAUDE,
            "dev_session_id": "dev-sess",
            REVIEW_ROUND: 1,
            AWAITING_HUMAN: True,
            PARK_REASON: reason,
            fixtures.LAST_ACTION_COMMENT_ID: PARK_MENTION_ID,
        }
        seeded.update(extra_state)
        github.seed_state(RECOVERY_ISSUE, **seeded)
        fixtures._open_pr_for(
            github, issue_number=RECOVERY_ISSUE, pr_number=RECOVERY_PR,
        )
        return IssueScenario(github, issue)

    def _seed_deferred_push(self, **extra_state):
        """The park a gated push that missed leaves behind.

        The approval and the head it is pinned to are the whole of it: the
        generation naming the commit was retired by the write that granted
        them, deliberately and before the push, so what is left on the comment
        is one commit owed a publication and the head that publication was
        measured against.
        """
        return self._seed_park(
            reason=PARK_PUSH_FAILED,
            **{
                KEY_APPROVED_SHA: STRANDED_CANDIDATE,
                KEY_APPROVED_LEASE: PUBLICATION_HEAD,
                **extra_state,
            },
        )

    def _seed_timed_out(self, **extra_state):
        """The park a dev run the timeout killed leaves behind.

        `pre_dev_fix_sha` is the head that run began at, which is the head its
        pull request was standing on: a fix round opens with the branch in
        sync with its publication.
        """
        return self._seed_park(
            reason=PARK_AGENT_TIMEOUT,
            **{PRE_DEV_FIX_SHA: PUBLICATION_HEAD, **extra_state},
        )

    def _recover(self, scenario, *, worktree=PRESENT_WORKTREE, **run_options):
        """One whole validating tick over the parked issue, gate on.

        The checkout reads as the stranded candidate throughout: the recovery
        proves the head, the gate proves it again, and the publication proves
        it once more past its own push -- and in production those are three
        readings of a checkout nothing touched, so a fixture spelling them
        apart would be modelling the race rather than the tick.
        """
        run_options.setdefault("head_shas", (STRANDED_CANDIDATE,) * 6)
        with patch.object(
            _worktree_paths, WORKTREE_PATH, return_value=worktree,
        ), patch.object(config, DECOMPOSE, True):
            return self._run_validating(
                scenario.github, scenario.issue,
                run_agent=fixtures._agent(), **run_options,
            )
