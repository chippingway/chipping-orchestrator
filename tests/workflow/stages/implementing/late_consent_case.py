# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A parked implementation, its live state, and the gate or tick a reply resumes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import (
    PinnedState,
)
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    late_records as _records,
    state as _state,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_IMPLEMENTING,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _PatchedWorkflowMixin,
)
from tests.workflow.stages.implementing import (
    late_consent_comments as _consent_comments,
    late_consent_payloads as _consent_payloads,
)


class _ParkedCase(_consent_comments._ConsentComments, _PatchedWorkflowMixin):
    """An issue holding one adjudicated candidate nobody has authorized."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(_consent_payloads.ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self.github.seed_state(_consent_payloads.ISSUE_NUMBER)
        self._seed()

    def _seed(self, *, parked: bool = True, **state) -> None:
        """Replace the pinned comment with the one a case is about.

        `parked=False` is the same issue with nothing standing on it, which is
        what the cases about ENTERING this park are seeded with.
        """
        standing = {
            _state._AWAITING_HUMAN: True,
            _state._PARK_REASON: _command.PARK_UNAUTHORIZED_EXEMPTION,
        } if parked else {}
        self.github.seed_state(_consent_payloads.ISSUE_NUMBER, **{
            _state._LAST_ACTION_COMMENT_ID: _consent_payloads.PRIOR_ACTION_COMMENT_ID,
            _consent_payloads.KEY_EXEMPT_SHA: MEASURED_CANDIDATE_SHA,
            **standing,
            **state,
        })

    def _pinned(self) -> dict:
        return self.github.pinned_data(_consent_payloads.ISSUE_NUMBER)

    def _assert_still_parked(self) -> None:
        """The park exactly as it was: somebody waiting, behind this question."""
        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(
            pinned[_state._PARK_REASON], _command.PARK_UNAUTHORIZED_EXEMPTION,
        )

    def _run_tick(self, worktree: Path = _consent_payloads.TEMP_WORKTREE_ROOT, **run_options):
        """Run one whole implementing tick over this parked issue.

        The seams the recovery hands its answer to are the real ones, which is
        the only way a case can see what the publication below does to a park
        it was entered under.
        """
        run_options.setdefault("has_new_commits", True)
        # Past the ceiling by default, because that is the reading this park
        # exists for: a candidate the gate measures small needs nobody's
        # authorization and publishes on its own count.
        run_options.setdefault("added_lines", _consent_payloads.OVERSIZED_ADDITIONS)
        run_options.setdefault(
            "run_agent", _agent(last_message="implemented"),
        )
        with patch.object(
            _worktree_paths, _consent_payloads.WORKTREE_PATH, return_value=worktree,
        ):
            return self._run_implementing(
                self.github, self.issue, **run_options,
            )

    def _gate(self, state: PinnedState | None = None, **entered):
        """The gate call this park was taken on, or is being answered from."""
        return _records._Gate(
            gh=self.github,
            spec=_TEST_SPEC,
            issue=self.issue,
            state=self._state() if state is None else state,
            worktree=_consent_payloads.WORKTREE,
            **entered,
        )
