# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A plan PR head a human moved past the plan, judged over real objects.

The recovery that adopts such a pull request turns on one question: does the
head the remote is on still CONTAIN the commit this publication pushed? It is
asked with `git merge-base --is-ancestor`, a local command over local objects,
and the id it is asked about is the remote's own answer about a branch this
host has not fetched since. The human's commit was made after the checkout
was, so a worktree a crash left behind has never seen it, git refuses an id it
cannot resolve, and that refusal is indistinguishable from a branch somebody
reset out from under the plan: the publication parks `discussion_push_failed`,
the reply that retries it reaches the same unfetched id, and the plan stays
published, reviewable, and unreachable from the issue that produced it.

Real repositories rather than mocked git for that reason -- an ancestry result
handed in answers for the very thing under test -- and each case proves the
trap first on the same world: before the tick runs, the amended head is neither
present here nor answerable as an ancestor.

The other half is what a head the fetch does not deliver does. Adopting a pull
request on a reading nobody could take would record it against an ancestry
never established, so an unresolvable head is left to the lease, which refuses
the push and says what is on the branch while the plan commit stays put.

The world is built by the real-git support module beside this one, and the
stage's own fixtures are reached through their module rather than name by name,
since what these two tests need from them is most of the vocabulary.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.git.verification import probes
from orchestrator.workflow.stages.discussion import (
    models as _models,
    recovery as _recovery,
)
from tests.support.checkout_identity import stated_identity
from tests.support.fakes import FakePR, FakePRRef
from tests.workflow.fixtures import KEY_PARK_REASON
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.discussion import (
    discussion_real_git_test_support as _real_git,
    discussion_test_support as _support,
)

_ISSUE_NUMBER = 1274

PLAN_PATH = f"plans/issue-{_ISSUE_NUMBER}.md"
AMENDED_PLAN_TEXT = "# the plan\n\nwith the correction its reviewer made\n"
RACED_FILE = "landed_on_the_base_meanwhile.py"
RACED_TEXT = "print('another branch entirely')\n"
TEMP_PREFIX = "orch-discussion-amended-"
PLAN_PR_NUMBER = 8123
OPEN_STATE = "open"
UNRESOLVABLE_TIP = "how the tip is left unresolvable"


class DiscussionAmendedPlanHeadTest(unittest.TestCase):
    """What a recovery makes of a plan PR head the humans pushed onto."""

    def setUp(self) -> None:
        world = tempfile.TemporaryDirectory(prefix=TEMP_PREFIX)
        self.addCleanup(world.cleanup)
        root = Path(world.name)
        self._spec = _real_git._real_git_spec(root)
        self._upstream = root / _real_git.UPSTREAM_DIR
        self._worktree = root / f"issue-{_ISSUE_NUMBER}"
        self._branch = _support._issue_branch(_ISSUE_NUMBER)
        self._build_world()
        # The worktree sits beside the clone rather than at a layout path, so
        # its ownership reads are stated.
        stated_identity(self)

    def test_an_amended_head_is_fetched_then_adopted(self) -> None:
        # The trap the fetch closes: the human's commit is on the remote and
        # nowhere near this clone, so the ancestry that would recognize their
        # push as a fast-forward over the plan reads exactly like a branch
        # somebody reset out from under it.
        self.assertFalse(probes._commit_present(self._worktree, self._amended))
        self.assertFalse(probes._commit_contains(
            self._worktree, self._plan_head, self._amended,
        ))

        gh, issue, push = self._settle(
            self._amended, _real_git._fetch_upstream,
        )

        # Nothing is pushed -- the branch already carries the plan, and the
        # only thing a push could send is the older SHA over their work -- and
        # the pull request that carries it is what the issue comes out holding.
        push.assert_not_called()
        self.assertEqual(gh.opened_prs, [])
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(pinned_data[_support.KEY_PR_NUMBER], PLAN_PR_NUMBER)
        self.assertEqual(pinned_data[_support.KEY_PLAN_PATH], PLAN_PATH)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON],
            _support.PARK_DISCUSSION_PLAN_PUBLISHED,
        )
        self.assertIsNone(pinned_data[_support.KEY_PUBLISHING_SHA])

    def test_an_unresolvable_tip_is_refused(self) -> None:
        # Two ways the head stays unreadable: a remote that refused the fetch,
        # and a branch that moved again between the tip read and the fetch, so
        # what arrives is not the commit that was named. Adopting on either
        # would record a pull request against an ancestry nobody established.
        for fetch, remote_tip in (
            (_real_git._failed_fetch, self._amended),
            (_real_git._fetch_upstream, self._raced),
        ):
            with self.subTest(**{UNRESOLVABLE_TIP: fetch.__name__}):
                self._assert_refused(*self._settle(remote_tip, fetch))

    def _assert_refused(self, gh, issue, push) -> None:
        """The plan held where it is, on a park an operator can answer."""
        push.assert_not_called()
        self.assertEqual(gh.opened_prs, [])
        pinned_data = gh.pinned_data(issue.number)
        self.assertIsNone(pinned_data.get(_support.KEY_PR_NUMBER))
        self.assertEqual(
            pinned_data[KEY_PARK_REASON],
            _support.PARK_DISCUSSION_PUSH_FAILED,
        )

    def _settle(self, remote_tip: str, fetch):
        """Settle the publication one crashed tick left half-finished."""
        gh, issue = self._seed_interrupted_publication()
        push = MagicMock(return_value=True)
        with (
            seam_patch(
                _support.WORKTREE_PATH, MagicMock(return_value=self._worktree),
            ),
            seam_patch(
                _support.REMOTE_BASE_TIP, MagicMock(return_value=remote_tip),
            ),
            seam_patch(_support.AUTHED_TARGET_FETCH, fetch),
            seam_patch(_support.PUSH_BRANCH, push),
        ):
            self.assertTrue(_recovery._settle_pending_publication(
                _models._DiscussionRun.start(gh, self._spec, issue),
            ))
        return gh, issue, push

    def _seed_interrupted_publication(self):
        """An issue whose marker names a plan already pushed and PR'd.

        The pull request is open on the human's own head and still carries the
        commit this publication put there, which is the pair a recovery has to
        recognize -- and the number the crash never got to write down.
        """
        gh, issue = _support._seed_discussion(_ISSUE_NUMBER)
        gh.seed_state(
            issue.number,
            **{
                _support.KEY_PUBLISHING_SHA: self._plan_head,
                _support.KEY_ROUND_BRANCH: self._branch,
                _support.KEY_ROUND_SHA: self._base_sha,
                _support.KEY_BASE_SHA: self._base_sha,
                _support.KEY_DISCUSSION_AGENT: _support.SPEC_WITH_ARGS,
                _support.KEY_DISCUSSION_SESSION_ID: _support.DISCUSSION_SESSION,
            },
        )
        gh.add_pr(FakePR(
            number=PLAN_PR_NUMBER,
            head_branch=self._branch,
            head=FakePRRef(sha=self._amended),
            commit_shas=(self._plan_head,),
            state=OPEN_STATE,
        ))
        return gh, issue

    def _build_world(self) -> None:
        """The plan pushed, a commit of the humans' on it, and a stale clone.

        The plan reaches the upstream the way the crashed publication's push
        put it there, and a reviewer's own correction lands on top of it. The
        clone is left where that tick left it: holding the plan commit it made
        and nothing anybody has done since.
        """
        self._base_sha = _real_git._seed_upstream_clone(
            self._spec, self._upstream, self._worktree, self._branch,
        )
        self._plan_head = _real_git._commit_file(
            self._worktree, PLAN_PATH, _real_git.PLAN_TEXT,
        )
        _real_git._git(
            self._upstream, "fetch", _real_git.QUIET_FLAG,
            str(self._spec.target_root),
            f"+refs/heads/{self._branch}:refs/heads/{self._branch}",
        )
        _real_git._git(
            self._upstream, "checkout", _real_git.QUIET_FLAG, self._branch,
        )
        self._amended = _real_git._commit_file(
            self._upstream, PLAN_PATH, AMENDED_PLAN_TEXT,
        )
        _real_git._git(
            self._upstream, "checkout", _real_git.QUIET_FLAG,
            _real_git.BASE_BRANCH,
        )
        # A commit on the base rather than on the plan's branch, so fetching
        # that branch cannot bring it: what a tip read moments before a fetch
        # turns out to be when the branch moves between the two commands.
        self._raced = _real_git._commit_file(
            self._upstream, RACED_FILE, RACED_TEXT,
        )


if __name__ == "__main__":
    unittest.main()
