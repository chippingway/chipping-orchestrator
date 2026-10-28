# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The real-checkout fixture the fixing drift router is exercised over.

Its own module because it is the one fixing fixture that puts a directory on
disk and patches the two owners a parked dispatch reaches out to -- the PR
comment poster and the validating recovery -- and the routing values beside it
are shared with cases that need none of that.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import tempfile

from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.validating import (
    recovery as _validating_recovery,
)
from tests.support.checkout_identity import stated_identity
from tests.workflow.stages.fixing import (
    fixing_routing_test_support as routing_support,
    fixing_test_support as _fixing_support,
)

BACKEND_CLAUDE = routing_support.BACKEND_CLAUDE
DEV_SESSION = routing_support.DEV_SESSION
DRIFT_FEEDBACK_WATERMARK = routing_support.DRIFT_FEEDBACK_WATERMARK
DRIFT_PR_HEAD = routing_support.DRIFT_PR_HEAD
DRIFT_PR_NUMBER_OFFSET = routing_support.DRIFT_PR_NUMBER_OFFSET
FakeGitHubClient = routing_support.FakeGitHubClient
FakePR = routing_support.FakePR
FakePRRef = routing_support.FakePRRef
KEY_AWAITING_HUMAN = routing_support.KEY_AWAITING_HUMAN
LABEL_FIXING = routing_support.LABEL_FIXING
LABEL_RESOLVING_CONFLICT = routing_support.LABEL_RESOLVING_CONFLICT
MagicMock = routing_support.MagicMock
Path = routing_support.Path
STATE_OPEN = routing_support.STATE_OPEN
make_issue = routing_support.make_issue
STAGE_FIXING = routing_support.STAGE_FIXING
patch = routing_support.patch
seam_patch = routing_support.seam_patch


class _FixingWorktreeDriftFixtureMixin:
    """A stuck validating-route transient can route through conflict handling.

    When a validating-route transient park (e.g. `push_failed`) cannot
    clear via the self-recovery (`_try_recover_validating_transient_park`
    returns "stuck"), `_handle_fixing` falls through to
    `_reconcile_parked_fixing` so a base advance that
    landed mid-park can still unstick the issue. The helper must hand
    both drift shapes to `resolving_conflict` while leaving any park
    that could be hiding a real dev question parked for the human.
    """

    def setUp(self) -> None:
        # The router probes `wt.exists()`, so the patched `_worktree_path`
        # must point at a directory that is really on disk.
        self._wt_dir = tempfile.mkdtemp(prefix="fixing-drift-wt-")
        self.addCleanup(shutil.rmtree, self._wt_dir, ignore_errors=True)
        # A plain directory rather than a worktree at a layout path, so its
        # ownership reads are stated.
        stated_identity(self)

    def _git_behind(self, behind: int) -> MagicMock:
        return MagicMock(
            return_value=subprocess.CompletedProcess(
                args=["git"],
                returncode=0,
                stdout=f"{behind}\n",
                stderr="",
            )
        )

    def _seed_parked_fixing(
        self,
        gh: FakeGitHubClient,
        number: int,
        *,
        park_reason: str | None = "push_failed",
        pending_fix_at: str | None = None,
    ) -> None:
        issue = make_issue(number, label=LABEL_FIXING)
        gh.add_issue(issue)
        pr = FakePR(
            number=DRIFT_PR_NUMBER_OFFSET + number,
            head_branch=_fixing_support._branch(number),
            head=FakePRRef(sha=DRIFT_PR_HEAD),
            state=STATE_OPEN,
        )
        gh.add_pr(pr)
        state = {
            "pr_number": pr.number,
            "branch": pr.head_branch,
            "dev_agent": BACKEND_CLAUDE,
            "dev_session_id": DEV_SESSION,
            "awaiting_human": True,
            # Default: a stuck validating-route transient (`push_failed`)
            # with no `pending_fix_at` so the validating-route recovery
            # branch fires. Per-test overrides exercise the other shapes
            # the router must refuse to auto-recover.
            "park_reason": park_reason,
            "pending_fix_at": pending_fix_at,
            # Watermarks above any seeded comment so the rescan finds nothing.
            "pr_last_comment_id": DRIFT_FEEDBACK_WATERMARK,
            "pr_last_review_comment_id": 0,
            "pr_last_review_summary_id": 0,
            "review_round": 1,
        }
        gh.seed_state(number, **state)

    @contextlib.contextmanager
    def _drift_patches(
        self,
        behind: int,
        *,
        dirty=(),
        local_head=DRIFT_PR_HEAD,
        recovery: str = "stuck",
    ):
        wt_path = Path(self._wt_dir)
        self.post = MagicMock()
        self.recover = MagicMock(return_value=recovery)
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                seam_patch("_worktree_path", MagicMock(return_value=wt_path)),
            )
            stack.enter_context(
                seam_patch(
                    "_worktree_dirty_files", MagicMock(return_value=list(dirty)),
                ),
            )
            stack.enter_context(seam_patch("_git", self._git_behind(behind)))
            stack.enter_context(
                seam_patch("_head_sha", MagicMock(return_value=local_head)),
            )
            stack.enter_context(
                patch.object(
                    _comments,
                    "_post_pr_comment",
                    self.post,
                )
            )
            # The parked dispatch imports the recovery attempt from the
            # validating owner, so the mock has to land there.
            stack.enter_context(
                patch.object(
                    _validating_recovery,
                    "_try_recover_validating_transient_park",
                    self.recover,
                )
            )
            yield

    def _assert_routed(self, gh, number) -> None:
        self.assertIn((number, LABEL_RESOLVING_CONFLICT), gh.label_history)
        pinned_data = gh.pinned_data(number)
        self.assertFalse(pinned_data.get(KEY_AWAITING_HUMAN))
        self.assertEqual(pinned_data.get("conflict_round"), 0)
        # The in_review watermark survives so the eventual in_review
        # re-entry can still re-discover any feedback past it.
        self.assertEqual(pinned_data.get("pr_last_comment_id"), DRIFT_FEEDBACK_WATERMARK)
        self.post.assert_called_once()
        entered = [
            event
            for event in gh.recorded_events
            if event.get("issue") == number
            and event.get("event") == "conflict_round"
            and event.get("action") == "entered"
        ]
        self.assertEqual(len(entered), 1)
        self.assertEqual(entered[0].get("stage"), STAGE_FIXING)
