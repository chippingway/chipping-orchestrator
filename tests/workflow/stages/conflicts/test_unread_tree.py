# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A checkout that could not say what it is carrying, on the roads that push.

A `git status` that established nothing names no paths, and so does a tree with
nothing in it -- so a probe that reports the paths alone answers the same for
both. What hangs off that answer is whether the commit about to be published is
the whole of what the worktree holds: taken as clean, a checkout carrying
uncommitted edits is pushed as a SHA that silently omits them, and the reviewer
behind it runs on a tree the pull request does not have.

The size gate proves the tree for itself, but that proof is part of the
MEASUREMENT: an install running `DECOMPOSE=off` freezes no entry, so nothing
proves anything and the push goes out. A proof taken after the effect can park
and cannot take a remote update back. So these run with the switch OFF, which
is where the stage's own reading is the only reading there is.

Two ticks each, because the park these leave is a transient one: the reading is
what clears it, so the tick after it retries rather than waiting on a human.
What the second tick establishes is that the refusal is the *reading's* and not
a one-off -- it stands for exactly as long as the status does not read.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from tests.workflow.patch_models import _agent
from tests.workflow.stages.conflicts.conflicts_test_support import (
    CONFLICT_PR_HEAD_SHA,
    RESOLVED_HEAD_SHA,
    _ResolvingConflictMixin,
)

CONFLICT_ISSUE = 200

BEFORE_HEAD = CONFLICT_PR_HEAD_SHA
MERGED_HEAD = RESOLVED_HEAD_SHA

# The head an interrupted tick left on the branch and never pushed.
RECOVERED_HEAD = "1ec04e5e" * 5

# What `git rev-list --count HEAD..origin/<base>` answers for recovered
# commits that already carry their base.
ON_BASE = "0\n"

# The switch that decides whether a candidate is measured at all. Off is the
# world these are about: no entry is frozen, so the gate's own tree proof
# never runs and this stage's reading is the only one there is.
DECOMPOSE = "DECOMPOSE"

PUSH_BRANCH = "_push_branch"
RUN_AGENT = "run_agent"

AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
USER_CONTENT_HASH = "user_content_hash"
PARK_UNREADABLE_WORKTREE = "unreadable_worktree"

BODY_EDIT = "the requirement moved while the rebase was in flight"

# A path a readable status names, which is the park a reply unsticks
# rather than the reading no reply can answer.
DIRTY_PATH = "a.py"


class _UnreadTreeMixin(_ResolvingConflictMixin):
    """Ticks run with the size gate switched off and a status nobody read."""

    def _switched_off(self, github, issue, **run_options):
        """One tick over an unreadable tree, with the gate turned off."""
        run_options.setdefault("head_shas", [BEFORE_HEAD, MERGED_HEAD])
        with patch.object(config, DECOMPOSE, False):
            return self._run_with_merge(
                github, issue,
                tree_readable=False,
                push_branch=True,
                **run_options,
            )[0]

    def _assert_refused(self, github, mocks) -> None:
        """Nothing left this checkout, and the refusal names the reading."""
        mocks[PUSH_BRANCH].assert_not_called()
        pinned = self._pinned(github)
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], PARK_UNREADABLE_WORKTREE)


class ConflictUnreadTreeRecoveryTest(unittest.TestCase, _UnreadTreeMixin):
    """The recovered push, which publishes a commit an earlier tick made."""

    def test_an_unread_tree_publishes_nothing(self) -> None:
        # Read as clean, the commit goes out omitting whatever was
        # uncommitted beside it -- and with the switch off there is no
        # measurement behind which the gate would have proved the tree, so
        # the push really lands and no later proof takes it back.
        github, mocks = self._recovering()

        self._assert_refused(github, mocks)

    def test_an_unread_tree_is_refused_on_every_tick(self) -> None:
        # The park is transient, so the tick after it retries the reading
        # rather than waiting on a human. What it must not do is retry into
        # the push: the refusal stands for as long as the status does not
        # read.
        github, issue = self._seed()[:2]
        self._switched_off(
            github, issue, **self._recovery_world(),
        )

        mocks = self._switched_off(
            github, issue, **self._recovery_world(),
        )

        self._assert_refused(github, mocks)

    def _recovering(self):
        """One recovered push taken over a tree nothing could read."""
        github, issue = self._seed()[:2]
        return github, self._switched_off(
            github, issue, **self._recovery_world(),
        )

    def _recovery_world(self) -> dict:
        """The commits an earlier tick left, already carrying their base."""
        return {
            "branch_ahead_behind": (1, 0),
            "behind_base": ON_BASE,
            "head_shas": [RECOVERED_HEAD, RECOVERED_HEAD],
        }


class ConflictUnreadTreeResumeTest(unittest.TestCase, _UnreadTreeMixin):
    """The body-edit resume, which ends in a publication from this checkout."""

    def test_an_unread_tree_resumes_nobody(self) -> None:
        # What the resume ends in is a push from this worktree, and the probe
        # in front of that push reports paths alone -- so an unreadable status
        # reaches it as a clean tree, and with the switch off nothing else
        # looks.
        github, mocks = self._edited()

        self._assert_refused(github, mocks)
        mocks[RUN_AGENT].assert_not_called()

    def test_a_refused_edit_survives_for_the_retry(self) -> None:
        # The hash is the whole of what says the body moved, so an edit
        # consumed by a resume that is then refused is one nothing detects
        # again. Refused ahead of the resume, the second tick still sees it.
        github, issue = self._seed()[:2]
        self._seed_with_baseline_hash(github, issue)
        baseline = self._pinned(github)[USER_CONTENT_HASH]
        issue.body = BODY_EDIT

        self._switched_off(github, issue)
        mocks = self._switched_off(github, issue)

        self._assert_refused(github, mocks)
        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(self._pinned(github)[USER_CONTENT_HASH], baseline)

    def _edited(self):
        """One body edit arriving on a tree nothing could read."""
        github, issue = self._seed()[:2]
        self._seed_with_baseline_hash(github, issue)
        issue.body = BODY_EDIT
        return github, self._switched_off(
            github, issue,
            run_agent_result=_agent(
                session_id="dev-sess", last_message="resolved the edit",
            ),
        )


class ConflictReadableTreeTest(unittest.TestCase, _UnreadTreeMixin):
    """What says the refusals above are about the reading rather than the road.

    A tree that is merely DIRTY is not an unread one: that is the park a reply
    exists to unstick, and the dev is resumed over it to clean it up.
    """

    def test_a_dirty_tree_still_resumes(self) -> None:
        github, issue = self._seed()[:2]
        self._seed_with_baseline_hash(github, issue)
        issue.body = BODY_EDIT

        with patch.object(config, DECOMPOSE, False):
            mocks = self._run_with_merge(
                github, issue,
                dirty_files=(DIRTY_PATH,),
                head_shas=[BEFORE_HEAD, MERGED_HEAD],
                push_branch=True,
                run_agent_result=_agent(
                    session_id="dev-sess", last_message="resolved the edit",
                ),
            )[0]

        mocks[RUN_AGENT].assert_called_once()


if __name__ == "__main__":
    unittest.main()
