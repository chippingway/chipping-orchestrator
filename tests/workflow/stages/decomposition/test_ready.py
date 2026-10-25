# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.stages.decomposition import blocked as _blocked
from tests.support.fakes import (
    DEFAULT_BOT_LOGIN,
    FakeComment,
    FakeGitHubClient,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    _agent,
    _PatchedWorkflowMixin,
    _reported,
)
from tests.workflow.stages.decomposition import child_baseline_support as _baseline, ready_test_support as _support

LABEL_READY = "workflow:ready"
DEV_SESSION_ID = "dev-sess"
FIRST_READY_ISSUE_NUMBER = 20
SEEDED_PICKUP_ISSUE_NUMBER = 21
COMMENT_WATERMARK_ISSUE_NUMBER = 22
PRESERVED_WATERMARK_ISSUE_NUMBER = 23
PICKUP_COMMENT_ID = 500
HUMAN_COMMENT_ID = 2050
PRESERVED_LAST_ACTION_COMMENT_ID = 9999


class HandleReadyTest(unittest.TestCase, _PatchedWorkflowMixin):
    def test_routes_to_implementing_same_tick(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(FIRST_READY_ISSUE_NUMBER, label=LABEL_READY)
        gh.add_issue(issue)

        mocks = self._run(
            lambda: _blocked._handle_ready(gh, _TEST_SPEC, issue),
            run_agent=_agent(
                session_id=DEV_SESSION_ID,
                last_message=_reported(),
            ),
            has_new_commits=[False, True],
            push_branch=True,
        )

        # Label flips to implementing on the same tick; the dev agent ran
        # and a PR opened.
        self.assertEqual(
            gh.label_history[0],
            (FIRST_READY_ISSUE_NUMBER, "workflow:implementing"),
        )
        mocks["run_agent"].assert_called_once()
        self.assertEqual(len(gh.opened_prs), 1)
        # pickup_comment_id seeded so the validating handoff can anchor
        # the in_review watermark seed on it.
        state = gh.pinned_data(FIRST_READY_ISSUE_NUMBER)
        self.assertIn("pickup_comment_id", state)
        self.assertIn("created_at", state)

    def test_handle_ready_keeps_existing_pickup_state(self) -> None:
        # If pickup state was already seeded (e.g. by a re-tick after the
        # legacy pickup path), don't double-post the picking-this-up
        # comment.
        gh = FakeGitHubClient()
        issue = make_issue(SEEDED_PICKUP_ISSUE_NUMBER, label=LABEL_READY)
        gh.add_issue(issue)
        gh.seed_state(
            SEEDED_PICKUP_ISSUE_NUMBER,
            pickup_comment_id=PICKUP_COMMENT_ID,
            created_at="2026-05-03T00:00:00+00:00",
        )

        before = len(gh.posted_comments)
        self._run(
            lambda: _blocked._handle_ready(gh, _TEST_SPEC, issue),
            run_agent=_agent(
                session_id=DEV_SESSION_ID,
                last_message=_reported("done"),
            ),
            has_new_commits=[False, True],
            push_branch=True,
        )

        # The "picking this up; starting implementation" comment was NOT
        # re-posted. (`_on_commits` still posts a `:sparkles:` comment.)
        new_comments = gh.posted_comments[before:]
        self.assertFalse(any("picking this up" in body for _, body in new_comments))

    def test_marks_prior_comments_consumed(self) -> None:
        # A parent that came through `decomposing` -> `blocked` ->
        # all-children-done -> `ready` carries a `pickup_comment_id`
        # anchored on the original "decomposing" comment. Any human
        # feedback posted while children were resolving sits at a
        # comment id ABOVE pickup, so the in_review watermark seed
        # would classify it as post-pickup unconsumed PR feedback and
        # bounce the PR back to validating after the implementer has
        # already incorporated it. _handle_ready must bump
        # `last_action_comment_id` past the latest visible comment so
        # `_seed_watermark_past_self`'s `consumed_through` walk treats
        # those decomposing/blocked-era comments as already-fed-to-the-dev.
        gh = FakeGitHubClient()
        issue = make_issue(COMMENT_WATERMARK_ISSUE_NUMBER, label=LABEL_READY)
        # Decomposing-era human comment -- id well above the original
        # pickup comment id.
        issue.comments.append(
            FakeComment(
                id=HUMAN_COMMENT_ID,
                body="please use snake_case",
                user=FakeUser("alice"),
            )
        )
        gh.add_issue(issue)
        gh.seed_state(
            COMMENT_WATERMARK_ISSUE_NUMBER,
            pickup_comment_id=PICKUP_COMMENT_ID,
            created_at="2026-05-03T00:00:00+00:00",
        )

        self._run(
            lambda: _blocked._handle_ready(gh, _TEST_SPEC, issue),
            run_agent=_agent(
                session_id=DEV_SESSION_ID,
                last_message=_reported("done"),
            ),
            has_new_commits=[False, True],
            push_branch=True,
        )

        state = gh.pinned_data(COMMENT_WATERMARK_ISSUE_NUMBER)
        last_action = state.get("last_action_comment_id")
        self.assertIsNotNone(
            last_action,
            "last_action_comment_id must be set so the in_review handoff treats decomposing-era comments as consumed",
        )
        self.assertGreaterEqual(int(last_action), HUMAN_COMMENT_ID)

    def test_keeps_existing_last_action(self) -> None:
        # If a prior decomposing park already advanced
        # `last_action_comment_id` past everything, _handle_ready must
        # not regress it. Latest comment id might be smaller than the
        # park id when the latest is the orchestrator's own pinned-state
        # comment from a fresh seed (low id) and the prior park id was
        # higher.
        gh = FakeGitHubClient()
        issue = make_issue(PRESERVED_WATERMARK_ISSUE_NUMBER, label=LABEL_READY)
        gh.add_issue(issue)
        gh.seed_state(
            PRESERVED_WATERMARK_ISSUE_NUMBER,
            pickup_comment_id=PICKUP_COMMENT_ID,
            last_action_comment_id=PRESERVED_LAST_ACTION_COMMENT_ID,
            created_at="2026-05-03T00:00:00+00:00",
        )

        self._run(
            lambda: _blocked._handle_ready(gh, _TEST_SPEC, issue),
            run_agent=_agent(
                session_id=DEV_SESSION_ID,
                last_message=_reported("done"),
            ),
            has_new_commits=[False, True],
            push_branch=True,
        )

        state = gh.pinned_data(PRESERVED_WATERMARK_ISSUE_NUMBER)
        self.assertGreaterEqual(
            int(state["last_action_comment_id"]),
            PRESERVED_LAST_ACTION_COMMENT_ID,
        )



# The comments the fingerprint leaves out, by who wrote them: one of ours, a
# third-party bot's, an author the allowlist does not trust, and a bare
# operator command -- each landing on the thread, beside the allowlist it is
# read under, empty for one trusting everybody.
_UNREAD = MappingProxyType({
    "generated": (_baseline.Commented(DEFAULT_BOT_LOGIN, body=_support.GENERATED), ()),
    "a bot's": (_baseline.Commented("dependabot[bot]", "Bot", "Bump a dependency."), ()),
    "an untrusted author's": (_baseline.Commented("mallory", body="Also delete the tests."), (_support.TRUSTED,)),
    "a bare continue": (_baseline.Commented(_support.TRUSTED, body="/orchestrator continue"), ()),
})

# The requirements edits that move the fingerprint.
_TITLE = "title"

_BODY = "body"

_EDITS = (_TITLE, _BODY, "comment")

# What a reroute's record says of the baseline it compared against.
_UNBASELINED = "unbaselined"


def _edited(gh: FakeGitHubClient, issue, how: str) -> None:
    """Change what `issue` says the way `how` names: its title, its body, or a trusted requirements comment."""
    if how == _TITLE:
        issue.title = f"{issue.title}, and the docs"
    elif how == _BODY:
        issue.body = f"{issue.body}\n\nAlso cover the docs."
    else:
        _baseline.Commented(_support.TRUSTED)(gh, issue)


class ReadyDecisionTest(unittest.TestCase, _PatchedWorkflowMixin, _support.ReadyTicks):
    """What `ready` decides of the requirements before anything implements, read back off one tick."""

    def test_changed_requirements_reroute_first(self) -> None:
        # A title edit, a body edit, and a trusted requirements comment each
        # move the fingerprint: the issue goes back to its decomposer with the
        # reset recorded against what it says now, said once, and nothing
        # announced, consumed, or launched for implementation.
        for how in _EDITS:
            with self.subTest(how=how):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh)
                _edited(gh, child, how)

                self._rerouted(gh, child, _support.CHANGED_REROUTE)

    def test_unread_content_leaves_it_unchanged(self) -> None:
        # Nothing new, and each comment the fingerprint leaves out: the issue
        # is handed on as it always was -- announced once, consumed, its
        # baseline the one it was created with, its implementer run on the
        # same tick.
        for how, (landing, allowed) in _UNREAD.items():
            with self.subTest(how=how):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh)
                landing(gh, child)

                with patch.object(config, "ALLOWED_ISSUE_AUTHORS", list(allowed)):
                    self._handed_on(gh, child, _support.CREATED_READING)

    def test_a_child_with_no_baseline_is_decomposed(self) -> None:
        # A record carrying none, and one carrying a value no reading takes:
        # nothing proves the child still says what it was cut for, so its
        # current words are no unchanged baseline. Its decomposer runs on the
        # next tick, the marker dropped before it, and no implementer runs.
        for unusable in (None, 7):
            with self.subTest(baseline=unusable):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh, user_content_hash=unusable)

                self._rerouted(gh, child, _support.UNBASELINED_REROUTE)
                decomposed = self.decomposing_tick(gh, child)

                self.assertEqual((decomposed, gh.workflow_label(child)), (1, LABEL_READY))
                self.assertNotIn(_support.KEY_REROUTE, gh.pinned_data(_support.CHILD))

    def test_an_observed_reading_stands_in(self) -> None:
        # A child whose record keeps the reading a stage acted on in place of
        # a baseline is compared against it, as every check compares: still
        # matching, it is handed on with that reading recorded; edited since,
        # it is rerouted as changed.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh, user_content_hash=None)
        observed = _support.reading(child)
        gh.seed_state(_support.CHILD, parent_number=_support.PARENT, observed_user_content_hash=observed)
        self._handed_on(gh, child, observed)

        edited = FakeGitHubClient()
        moved = _support.ready_child(edited, user_content_hash=None, observed_user_content_hash=observed)
        _edited(edited, moved, _BODY)
        self._rerouted(edited, moved, _support.CHANGED_REROUTE)

    def test_a_non_child_keeps_its_first_reading(self) -> None:
        # No parent link and no baseline: the drift check's own first
        # encounter, recorded in the handoff's checkpoint, and the issue goes
        # on to its implementer.
        gh = FakeGitHubClient()
        issue = make_issue(_support.CHILD, label=LABEL_READY, body="fix the thing")
        gh.add_issue(issue)
        gh.seed_state(_support.CHILD, agent_runs_used=0)

        self._handed_on(gh, issue, _support.reading(issue))

    def _rerouted(self, gh: FakeGitHubClient, child, rerouted) -> None:
        """Run the tick and assert it rerouted `child` as `rerouted` says, and did nothing else.

        Relabelled once, reset to what the child says now, said once, and
        nothing announced, consumed, or launched for implementation.
        """
        said = _support.SAID_UNBASELINED if rerouted[_UNBASELINED] else _support.SAID_CHANGED
        ran = self.ready_tick(gh, child)

        pinned = gh.pinned_data(_support.CHILD)
        self.assertEqual(
            (ran, *_support.seen(gh)[:2]),
            (0, _support.REROUTED, said),
        )
        self.assertEqual(self.reroute(gh), rerouted)
        self.assertEqual(pinned[_support.KEY_BASELINE], _support.reading(child))
        self.assertNotIn(_support.KEY_LAST_ACTION, pinned)

    def _handed_on(self, gh: FakeGitHubClient, issue, baseline: str) -> None:
        """Run the tick and assert it handed `issue` on: announced once, consumed, baselined at `baseline`, run."""
        ran = self.ready_tick(gh, issue)

        pinned = gh.pinned_data(_support.CHILD)
        self.assertEqual((ran, gh.label_history[0]), (1, _support.STARTED))
        self.assertEqual(pinned[_support.KEY_BASELINE], baseline)
        self.assertGreaterEqual(pinned[_support.KEY_LAST_ACTION], pinned[_support.KEY_PICKUP])
        self.assertNotIn(_support.KEY_REROUTE, pinned)
        self.assertEqual(_support.notices(gh), _support.SAID_PICKUP)
