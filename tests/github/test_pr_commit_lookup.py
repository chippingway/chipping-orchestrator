# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The commit-pinned pull-request lookup, and its three possible answers.

`find_pr_for_commit` is what a publication that crashed before recording its
number is recovered by, and its caller PUSHES on a `None`. So the difference
between "no pull request carries this commit" and "nobody could say" is the
difference between finishing that publication and republishing over one that
already landed: after the plan PR was amended, squash-merged, and had its head
branch auto-deleted, a miss has the branch recreated and a second pull request
opened that proposes taking the amendment back out.

The head and the commit list are asked in that order because they cost
differently and answer differently. The head is a field already in hand and
covers the ordinary case; the commit list is a request to GitHub, and the only
place a merged-and-amended publication is still visible.

The enumeration those are read from is a request too, and its pages are a
request each, so the candidate that would have matched can be one the walk
never reaches. That is the same "nobody could say" one level up, and it is
tested the same way: the failure has to be told apart from a branch with no
pull requests on it, because only one of the two is safe to publish over.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from github import GithubException

from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.github.client import GitHubClient

_PR_NUMBER = 7
_SECOND_PR_NUMBER = 8
_HTTP_SERVER_ERROR = 500
_BRANCH = "orchestrator/issue-7"
_BASE = "main"
_OWNER_LOGIN = "geserdugarov"
_HEAD_SHA = "f00dcafe"
_MOVED_HEAD_SHA = "0ddba11f"
_STATE_ALL = "all"
_SERVER_ERROR_TEXT = "Server Error"


def _server_error() -> GithubException:
    """What GitHub raises when the commit list simply does not come back."""
    return GithubException(
        _HTTP_SERVER_ERROR, {"message": _SERVER_ERROR_TEXT}, None,
    )


def _pages_then_error(*yielded):
    """Walk a first page, then fail the way a later one does."""
    yield from yielded
    raise _server_error()


class _CommitListPR:
    """A pull request whose head is a field and whose commits are a read.

    The split is the point: the head costs nothing and is already loaded,
    while `get_commits` is a request that can fail on its own.
    """

    def __init__(
        self,
        *,
        number: int = _PR_NUMBER,
        head_sha: str = _MOVED_HEAD_SHA,
        commit_shas: tuple = (),
        error: Exception | None = None,
    ) -> None:
        self.number = number
        self.head = MagicMock(sha=head_sha)
        self.commit_reads = 0
        self._commit_shas = commit_shas
        self._error = error

    def get_commits(self):
        self.commit_reads += 1
        if self._error is not None:
            raise self._error
        return [MagicMock(sha=sha) for sha in self._commit_shas]


class _LookupTestCase(unittest.TestCase):
    """A client whose repository is a mock, and the one call under test."""

    def setUp(self) -> None:
        # Bypass the networked __init__; the method reads only `self.repo`.
        self.gh = GitHubClient.__new__(GitHubClient)
        self.gh.repo = MagicMock()
        self.gh.repo.owner.login = _OWNER_LOGIN

    def _lookup(self):
        return self.gh.find_pr_for_commit(
            branch=_BRANCH, base=_BASE, head_sha=_HEAD_SHA,
        )


class CommitPinnedLookupTest(_LookupTestCase):
    """What one candidate is read for, and what that reading costs."""

    def test_a_matching_head_costs_no_commit_read(self) -> None:
        pull_request = _CommitListPR(head_sha=_HEAD_SHA)
        self.gh.repo.get_pulls.return_value = iter([pull_request])

        self.assertIs(self._lookup(), pull_request)
        self.assertEqual(pull_request.commit_reads, 0)
        # Every state, since the pull request this recovers may have merged.
        self.gh.repo.get_pulls.assert_called_once_with(
            state=_STATE_ALL,
            head=f"{_OWNER_LOGIN}:{_BRANCH}",
            base=_BASE,
        )

    def test_an_unnamed_base_is_left_off(self) -> None:
        # A caller measuring whether GitHub holds this commit at all -- rather
        # than which thread it would push onto -- must see a pull request
        # retargeted onto another base, so the filter is left out of the query.
        self.gh.repo.get_pulls.return_value = iter([])

        self.gh.find_pr_for_commit(branch=_BRANCH, head_sha=_HEAD_SHA)

        self.gh.repo.get_pulls.assert_called_once_with(
            state=_STATE_ALL, head=f"{_OWNER_LOGIN}:{_BRANCH}",
        )

    def test_a_carried_commit_survives_a_moved_head(self) -> None:
        # What a human pushing onto the plan branch leaves, and what a merge
        # of that branch leaves after them: the head is theirs, the published
        # commit is still one of the commits the pull request is made of.
        pull_request = _CommitListPR(commit_shas=(_HEAD_SHA,))
        self.gh.repo.get_pulls.return_value = iter([pull_request])

        self.assertIs(self._lookup(), pull_request)

    def test_a_pr_carrying_nothing_of_ours_is_none(self) -> None:
        self.gh.repo.get_pulls.return_value = iter([
            _CommitListPR(commit_shas=(_MOVED_HEAD_SHA,)),
        ])

        self.assertIsNone(self._lookup())

    def test_an_unreadable_commit_list_is_not_a_miss(self) -> None:
        # A `None` here has the recovery push a branch the merge deleted and
        # ask GitHub for a second pull request -- one proposing to take the
        # humans' own amendment back out.
        self.gh.repo.get_pulls.return_value = iter([
            _CommitListPR(error=_server_error()),
        ])

        self.assertIs(self._lookup(), _pr_reads.PR_LOOKUP_UNREADABLE)

    def test_a_match_outranks_an_unreadable_pr(self) -> None:
        # One pull request nobody could read says nothing about another that
        # plainly carries the commit, so the definite answer still wins.
        carrying = _CommitListPR(
            number=_SECOND_PR_NUMBER, commit_shas=(_HEAD_SHA,),
        )
        self.gh.repo.get_pulls.return_value = iter([
            _CommitListPR(error=_server_error()), carrying,
        ])

        self.assertIs(self._lookup(), carrying)


class PrEnumerationFailureTest(_LookupTestCase):
    """The same question one level up: the walk that finds the candidates."""

    def test_an_enumeration_failure_is_not_a_miss(self) -> None:
        # The lookup nobody got to take at all. Answered `None`, a fresh
        # round's publication pushes on it -- and, worse, does so before the
        # write that would have persisted the session it was made under.
        self.gh.repo.get_pulls.side_effect = _server_error()

        self.assertIs(self._lookup(), _pr_reads.PR_LOOKUP_UNREADABLE)

    def test_a_failing_page_is_not_a_miss(self) -> None:
        # The same failure one page in: the pull requests already walked did
        # not carry the commit, and the ones this never reached are exactly
        # what the answer would have to be built from.
        self.gh.repo.get_pulls.return_value = _pages_then_error(
            _CommitListPR(commit_shas=(_MOVED_HEAD_SHA,)),
        )

        self.assertIs(self._lookup(), _pr_reads.PR_LOOKUP_UNREADABLE)

    def test_a_match_before_a_failing_page_stands(self) -> None:
        # A match is returned where it is found, so a page that fails after it
        # loses only the question -- never an answer already given.
        carrying = _CommitListPR(commit_shas=(_HEAD_SHA,))
        self.gh.repo.get_pulls.return_value = _pages_then_error(carrying)

        self.assertIs(self._lookup(), carrying)


if __name__ == "__main__":
    unittest.main()
