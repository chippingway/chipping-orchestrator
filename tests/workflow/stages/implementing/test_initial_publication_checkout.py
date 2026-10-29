# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout an initial publication pushes from, opens its pull request over, and hands on, over a real clone.

The push runs through the real transport onto a real bare remote. Every
request the publication makes is a window a tree can be switched in, and one
switched onto the flat branch at the published commit passes every reading of
that commit and tree. So a head the checkout names is recorded as the intent
only behind a proof, the lease is read before the last proof rather than
inside the push, the pull request's lookup is followed by a proof before
anything is opened, and the handoff proves the checkout before its own write
and again between that write and the label: a switch in any of those windows
records, publishes, opens, or hands on nothing past it, and a refused handoff
stays owed, beside its receipt, for the tick that finds the checkout restored.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport, commands, credentials, ref_transport
from orchestrator.git.publication import titles
from orchestrator.git.worktrees import creation, naming
from orchestrator.workflow.engine import content_hash
from orchestrator.workflow.stages.implementing import models, publication
from tests.git.worktrees.real_git_test_support import _AmendedPlanRepo, _RealGitWorktreeRepo, _run_git
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.fixtures import _agent, _named_description

ISSUE = 300
PR_NUMBER = 42
SESSION = "sess-1"
VALIDATING = "workflow:validating"
_FLAT_BRANCH = f"orchestrator/issue-{ISSUE}"
_INTENT = "late_approved_sha"
_RECEIPT = "implementing_published_sha"
# What only the handoff's own write records: the pull request the label hands on.
_HANDED_PR = "pr_number"

# The reads ahead of the push a checkout is switched during, and which call of
# each: the lease read off the remote, and the push transport's own config read
# behind it -- the second, since the lease read takes one first.
_BEFORE_THE_PUSH = (
    (ref_transport, "_remote_ref_read", 1),
    (commands, "_unsafe_local_transport_config", 2),
)

# Who commits on a switched checkout, named so no ambient git identity is needed.
_OPERATOR = ("-c", "user.name=Operator", "-c", "user.email=operator@example.invalid")

# Where a case switches the checkout: behind the write recording which key, and
# whether the switched branch carries a commit of its own.
_SWITCHES = ((_RECEIPT, False), (_RECEIPT, True), (_HANDED_PR, False))

# The reads behind the receipt's write a checkout is switched during: the
# description's last one, and the checkout guards' readings -- switched behind
# the proof asked ahead of them, onto a branch carrying a commit of its own,
# which the moved-checkout guard parks as this issue's moved checkout before
# whose checkout it is can be asked again.
_DESCRIPTION_READ = "the description's last read"
_GUARD_READ = "the checkout guards' readings"

# Each of those reads beside the park it leaves: none, save the guard's.
_PAST_THE_RECEIPT = ((_DESCRIPTION_READ, None), (_GUARD_READ, "late_candidate_moved"))


def _seeded(github: FakeGitHubClient, branch: str):
    """The implementing issue a session committed under, on `branch`; the issue."""
    issue = make_issue(ISSUE, label="workflow:implementing")
    github.add_issue(issue)
    github.seed_state(
        ISSUE, branch=branch, dev_agent="claude", dev_session_id=SESSION,
        user_content_hash=content_hash._compute_user_content_hash(issue, set()),
    )
    return issue


def _switch(checkout, *, commits: bool = False) -> None:
    """Switch `checkout` onto the flat branch at the commit it stands on -- an operator's commit on top -- once."""
    if not _run_git("branch", "--list", _FLAT_BRANCH, cwd=checkout).strip():
        _run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=checkout)
        if commits:
            _run_git(*_OPERATOR, "commit", "-q", "--allow-empty", "-m", "operator work", cwd=checkout)


def _switching_behind_the_proof(checkout, recorded_in: FakeGitHubClient | None = None):
    """The checkout's proof, `checkout` switched onto a branch carrying its own commit behind the first one.

    Behind the first past the receipt's write, where `recorded_in` names the
    client that write lands in.
    """
    prove = creation._proven_checkout

    def wrapper(*args, **kwargs):
        proven = prove(*args, **kwargs)
        if recorded_in is None or recorded_in.pinned_data(ISSUE).get(_RECEIPT):
            _switch(checkout, commits=True)
        return proven
    return wrapper


def _switched_during(case, window: str):
    """A context in which `case`'s checkout is switched onto the flat branch during `window`."""
    if window == _GUARD_READ:
        proof = _switching_behind_the_proof(case.repo.worktree, case.gh)
        return patch.object(creation, "_proven_checkout", side_effect=proof)
    return patch.object(case.gh, "get_pr", side_effect=case._switched_read)


def _on_the_remote(spec, branch: str) -> bool:
    """Whether `spec`'s bare remote carries `branch`."""
    listed = _run_git("ls-remote", "origin", f"refs/heads/{branch}", cwd=spec.target_root)
    return bool(listed.strip())


class TransportCheckoutTest(unittest.TestCase):
    """A first publication of a fresh branch, through the real push transport."""

    def setUp(self) -> None:
        repo = _RealGitWorktreeRepo()
        repo.prepare(self)
        self.spec = repo.spec
        self.branch = naming._branch_name(repo.spec, ISSUE)
        self.checkout = creation._ensure_worktree(repo.spec, ISSUE, branch=self.branch)
        self.candidate = repo._commit_plan(self.checkout, "# candidate\n")
        self.gh = FakeGitHubClient()
        self.issue = _seeded(self.gh, self.branch)
        unconfigured = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        remote = str(repo._remote)
        authenticated = MagicMock()
        authenticated.__enter__.return_value = MagicMock(token="unused", auth_url=remote, env=unconfigured)
        self.enterContext(patch.object(credentials, "_resolved_git_token", return_value="unused"))
        self.enterContext(patch.object(credentials, "_git_auth_session", return_value=authenticated))
        self._through = None
        self._calls = 0
        self._switch_at = 1

    def test_the_issue_s_own_checkout_is_published(self) -> None:
        self._publishes()

        self.assertTrue(_on_the_remote(self.spec, self.branch))
        self.assertEqual(len(self.gh.opened_prs), 1)

    def test_a_switch_before_the_push_pushes_nothing(self) -> None:
        # Switched while the lease is read off the remote, or while the push
        # transport reads the worktree's config behind that read -- the
        # second config read, the lease read's own being the first: nothing
        # goes out, nothing is opened, and the intent waits for the restored
        # checkout.
        for owner, read, at in _BEFORE_THE_PUSH:
            with self.subTest(read=read):
                self.setUp()
                self._through = getattr(owner, read)
                self._switch_at = at
                with patch.object(owner, read, side_effect=self._switched):
                    self.assertRaises(naming.BranchRefused, self._publishes)

                self.assertFalse(_on_the_remote(self.spec, self.branch))
                self.assertEqual(self.gh.opened_prs, [])
                self.assertEqual(self.gh.pinned_data(ISSUE).get(_INTENT), self.candidate)

    def test_a_switch_past_the_push_opens_nothing(self) -> None:
        # Switched while the pull request is looked up, or while the title of
        # the one to open is read off the branch's history: the push stands,
        # nothing is opened, and the intent waits for the restored checkout.
        for owner, read in ((None, "find_open_pr"), (titles, "_first_commit_subject")):
            with self.subTest(read=read):
                self.setUp()
                owner = owner or self.gh
                self._through = getattr(owner, read)
                with patch.object(owner, read, side_effect=self._switched):
                    self.assertRaises(naming.BranchRefused, self._publishes)

                self.assertTrue(_on_the_remote(self.spec, self.branch))
                self.assertEqual(self.gh.opened_prs, [])
                self.assertEqual(self.gh.pinned_data(ISSUE).get(_INTENT), self.candidate)

    def test_a_switch_mid_head_read_records_nothing(self) -> None:
        # No gate named the commit, so the checkout's head names it, read
        # behind the entry proof -- and the tree is switched there onto a
        # branch carrying an operator's commit. Whose checkout it is is asked
        # again before that head is recorded as the intent, so the foreign
        # commit is neither recorded nor pushed, and the checkout once
        # restored publishes the session's own commit.
        proof = _switching_behind_the_proof(self.checkout)
        with patch.object(creation, "_proven_checkout", side_effect=proof):
            self.assertRaises(naming.BranchRefused, self._publishes, "")

        self.assertIsNone(self.gh.pinned_data(ISSUE).get(_INTENT))
        self.assertFalse(_on_the_remote(self.spec, self.branch))
        _run_git("checkout", "-q", self.branch, cwd=self.checkout)
        self._publishes("")
        self.assertEqual(self.gh.pinned_data(ISSUE).get(_RECEIPT), self.candidate)

    def _publishes(self, candidate: str | None = None) -> None:
        """One publication of the session's commit, or `candidate` as the gate named it, as the stage enters it."""
        state = self.gh.read_pinned_state(self.issue)
        named = self.candidate if candidate is None else candidate
        work = models._ApprovedWork(_agent(session_id=SESSION), self.checkout, named)
        publication._on_commits(self.gh, self.spec, self.issue, state, work)

    def _switched(self, *args, **kwargs):
        """The request this case stands in for, the checkout switched onto the flat branch during call `_switch_at`."""
        self._calls += 1
        if self._calls >= self._switch_at:
            _switch(self.checkout)
        return self._through(*args, **kwargs)


class HandoffCheckoutTest(unittest.TestCase):
    """A publication onto a pull request already open on the branch, handed on to review."""

    def setUp(self) -> None:
        self.repo = _AmendedPlanRepo()
        self.branch = naming._branch_name(self.repo.spec, ISSUE)
        self.repo.plant(self, ISSUE, self.branch)
        self.gh = FakeGitHubClient()
        pull_request = FakePR(
            number=PR_NUMBER, head_branch=self.branch, head=FakePRRef(sha=self.repo.published),
            body=_named_description(ISSUE, SESSION),
        )
        self.gh.add_pr(pull_request)
        self.gh.existing_open_pr[self.branch] = pull_request
        self.issue = _seeded(self.gh, self.branch)
        self._write = self.gh.write_pinned_state
        self._read = self.gh.get_pr
        self._reads = 0
        published = ref_transport._RefRead(sha=self.repo.published)
        self.enterContext(patch.object(branch_transport, "_push_branch", return_value=True))
        self.enterContext(patch.object(branch_transport, "_remote_branch_read", return_value=published))

    def test_the_issue_s_own_checkout_is_handed_on(self) -> None:
        self._publishes()

        self.assertIn((ISSUE, VALIDATING), self.gh.label_history)

    def test_a_switch_behind_a_write_holds(self) -> None:
        # Switched behind the write carrying the receipt -- at the published
        # commit, or carrying an operator's commit the moved-checkout guard
        # would otherwise park as this issue's -- or behind the handoff's own
        # write ahead of the label: the label stays, nothing is parked, the
        # receipt stands, and the handoff is owed for the restored checkout.
        for written, commits in _SWITCHES:
            with self.subTest(written=written, commits=commits):
                self.setUp()
                self._switch_behind = (written, commits)
                with patch.object(self.gh, "write_pinned_state", side_effect=self._switched_write):
                    state = self._publishes()

                recorded = self.gh.pinned_data(ISSUE)
                self.assertNotIn((ISSUE, VALIDATING), self.gh.label_history)
                self.assertEqual(state.get(_INTENT), self.repo.published)
                self.assertIsNone(state.get("park_reason"))
                self.assertEqual(recorded.get(_RECEIPT), self.repo.published)
                # Nothing of the handoff is written over a checkout already switched.
                self.assertEqual(bool(recorded.get(_HANDED_PR)), written == _HANDED_PR)

    def test_a_switch_mid_a_late_read_holds(self) -> None:
        # The description is read again last, behind the checkout guards, and
        # the tree is switched while that read runs: nothing of the handoff is
        # written over it, and the handoff is owed beside the receipt. Switched
        # while the moved-checkout guard reads the head instead, onto a branch
        # carrying a commit of its own, the handoff is held the same way, but
        # that guard has seen a moved head and parked, with its comment, before
        # whose checkout it is can be asked again.
        for window, parked_as in _PAST_THE_RECEIPT:
            with self.subTest(window=window):
                self.setUp()
                with _switched_during(self, window):
                    state = self._publishes()

                recorded = self.gh.pinned_data(ISSUE)
                self.assertNotIn((ISSUE, VALIDATING), self.gh.label_history)
                self.assertEqual(state.get(_INTENT), self.repo.published)
                self.assertEqual(recorded.get(_RECEIPT), self.repo.published)
                self.assertIsNone(recorded.get(_HANDED_PR))
                self.assertEqual(state.get("park_reason"), parked_as)
                self.assertEqual(len(self.gh.posted_comments), int(parked_as is not None))

    def _publishes(self):
        """One publication of the planted commit, as the stage enters it; the state it leaves."""
        repo = self.repo
        state = self.gh.read_pinned_state(self.issue)
        work = models._ApprovedWork(_agent(session_id=SESSION), repo.worktree, repo.published)
        publication._on_commits(self.gh, repo.spec, self.issue, state, work)
        return state

    def _switched_read(self, number: int):
        """Read pull request `number`, switching the checkout behind the second read past the receipt's write."""
        if self.gh.pinned_data(ISSUE).get(_RECEIPT):
            self._reads += 1
            if self._reads == 2:
                _switch(self.repo.worktree)
        return self._read(number)

    def _switched_write(self, issue, state, *args, **kwargs):
        """Land the write, switching the checkout onto the flat branch behind the first one recording the case's key."""
        written = self._write(issue, state, *args, **kwargs)
        key, commits = self._switch_behind
        if state.get(key):
            _switch(self.repo.worktree, commits=commits)
        return written


if __name__ == "__main__":
    unittest.main()
