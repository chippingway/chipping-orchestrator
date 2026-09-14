# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git import commands as _git_commands
from orchestrator.workflow.stages.conflicts import guards as _guards
from tests.support.fakes import (
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    make_issue,
)
from tests.workflow.fixtures import (
    _FAKE_WT,
    _TEST_SPEC,
    LABEL_DECOMPOSING,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _PatchedWorkflowMixin,
)

PUBLISH_ISSUE = 310
PUBLISH_BRANCH = "orchestrator/issue-310"
PUBLISH_PR = 910
# A whole git object id, because the size gate freezes the head its pull
# request stands on before it measures and reads a commit field at its exact
# length -- an abbreviation is no head at all there.
PUBLISH_PR_HEAD = "5da1e" * 8

CEILING = 5
PAST_THE_CEILING = 6
MAX_ADDED_LINES = "MAX_ADDED_LINES"


def _assert_diverged_park(test_case, gh) -> None:
    test_case.assertNotIn((PUBLISH_ISSUE, "workflow:validating"), gh.label_history)
    test_case.assertTrue(gh.pinned_data(PUBLISH_ISSUE).get("awaiting_human"))
    parks = [
        event
        for event in gh.recorded_events
        if event.get("event") == "park_awaiting_human" and event.get("reason") == "diverged_branch"
    ]
    test_case.assertEqual(len(parks), 1)


class _PublishFixtureMixin(_PatchedWorkflowMixin):
    def _seed(self):
        gh = FakeGitHubClient()
        issue = make_issue(PUBLISH_ISSUE, label="workflow:resolving_conflict")
        gh.add_issue(issue)
        pr = FakePR(
            number=PUBLISH_PR,
            head_branch=PUBLISH_BRANCH,
            head=FakePRRef(sha=PUBLISH_PR_HEAD),
            state="open",
        )
        gh.add_pr(pr)
        gh.seed_state(
            PUBLISH_ISSUE,
            pr_number=PUBLISH_PR,
            branch=PUBLISH_BRANCH,
            dev_agent="claude",
            dev_session_id="dev-sess",
            review_round=2,
            conflict_round=0,
            # `_handle_documenting`'s success exits are the one place
            # production code records the orchestrator's pushed head, so
            # the force-publish guard recognises this state.
            docs_checked_sha=PUBLISH_PR_HEAD,
        )
        return gh, issue, pr

    def _publish(self, gh, issue, **run_options):
        """The recovered-push route, with the reading it is measured by."""
        return self._run_diverged(
            gh, issue, on_base=True, recognized=True, **run_options,
        )

    def _run_diverged(self, gh, issue, *, on_base, recognized, **run_options):
        # The worktree is 4 ahead / 2 behind the remote PR head (a rebase
        # rewrote history). Patch the two safety probes on the owner the
        # divergence guard calls them through, so the handler's
        # publish-vs-park branch is exercised in isolation.
        # After a successful force-publish the handler probes
        # `rev-list HEAD..origin/<base>` to decide between the fast
        # path and a follow-up rebase; this scenario is "already on
        # base", so the probe returns 0 and the fast path fires.
        git_on_base = MagicMock(
            return_value=MagicMock(returncode=0, stdout="0\n", stderr=""),
        )
        with (
            patch.object(
                _guards,
                "_already_rebased_onto_base",
                MagicMock(return_value=on_base),
            ),
            patch.object(
                _guards,
                "_pr_head_orchestrator_produced",
                MagicMock(return_value=recognized),
            ),
            patch.object(_git_commands, "_git", git_on_base),
        ):
            return self._run_resolving_conflict(
                gh,
                issue,
                run_agent=_agent(session_id="dev-sess"),
                branch_ahead_behind=(4, 2),
                push_branch=True,
                # The head this stage reads is the commit the gate proves
                # the checkout to: one read of one worktree, and a push named
                # against anything else is the race the gate refuses.
                head_shas=(MEASURED_CANDIDATE_SHA, MEASURED_CANDIDATE_SHA),
                **run_options,
            )


class ResolvingConflictPublishesAlreadyRebasedTest(
    unittest.TestCase,
    _PublishFixtureMixin,
):
    """Publish only recognized PR heads already rebased onto current base."""

    def test_publishes_when_on_base_and_recognized(self) -> None:
        gh, issue, _ = self._seed()
        mocks = self._run_diverged(gh, issue, on_base=True, recognized=True)
        # Force-published over the stale PR head -> validating, no park.
        self.assertIn((PUBLISH_ISSUE, "workflow:validating"), gh.label_history)
        state = gh.pinned_data(PUBLISH_ISSUE)
        self.assertFalse(state.get("awaiting_human"))
        self.assertNotEqual(state.get("park_reason"), "diverged_branch")
        self.assertEqual(state.get("review_round"), 0)
        rounds = [
            event
            for event in gh.recorded_events
            if event.get("event") == "conflict_round" and event.get("action") == "incremented"
        ]
        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0].get("outcome"), "recovered_push")
        # The push must be leased to the EXACT PR head we validated as
        # orchestrator-produced. A bare `_push_branch(spec, wt, branch)`
        # would do a fresh `ls-remote` and lease against whatever SHA
        # is live at push time, silently clobbering any foreign push
        # that landed between `gh.get_pr()` and this push.
        mocks["_push_branch"].assert_called_once_with(
            _TEST_SPEC,
            _FAKE_WT,
            PUBLISH_BRANCH,
            revision=MEASURED_CANDIDATE_SHA,
            force_with_lease=PUBLISH_PR_HEAD,
        )

    def test_an_oversized_recovery_is_held(self) -> None:
        # A crash between a commit and the gate is exactly the window this
        # recovery exists for, so the commits it finds are the ones least
        # likely ever to have been read. Publishing them on the strength of
        # "an earlier tick meant to" is the unmeasured publication the gate
        # exists to stop.
        gh, issue, _pr = self._seed()

        with patch.object(config, MAX_ADDED_LINES, CEILING):
            mocks = self._publish(gh, issue, added_lines=PAST_THE_CEILING)

        mocks["_push_branch"].assert_not_called()
        self.assertNotIn(
            (PUBLISH_ISSUE, "workflow:validating"), gh.label_history,
        )
        self.assertIn(
            (PUBLISH_ISSUE, LABEL_DECOMPOSING), gh.label_history,
        )

    def test_parks_when_not_on_base(self) -> None:
        gh, issue, _ = self._seed()
        self._run_diverged(gh, issue, on_base=False, recognized=True)
        _assert_diverged_park(self, gh)

    def test_parks_when_pr_head_unrecognized(self) -> None:
        gh, issue, _ = self._seed()
        self._run_diverged(gh, issue, on_base=True, recognized=False)
        _assert_diverged_park(self, gh)


if __name__ == "__main__":
    unittest.main()
