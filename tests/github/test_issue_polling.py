# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The shared number set every query a poll takes is filtered through."""
from __future__ import annotations

import itertools
import unittest

from github.Consts import DEFAULT_PER_PAGE
from github.GithubObject import NotSet, _BadAttribute, _ValuedAttribute
from github.Issue import Issue
from github.IssuePullRequest import IssuePullRequest
from github.PaginatedList import PaginatedList

from orchestrator.github import issue_polling as _issue_polling

_ISSUES_URL = "https://api.github.com/repos/owner/repo/issues"
_NEXT_PAGE_URL = f"{_ISSUES_URL}?page=2"
_PULL_URL = "https://api.github.com/repos/owner/repo/pulls/2"
_GET = "GET"

# A trapped row built without any `_pull_request` slot.
_ABSENT = object()

# One list response: its headers, where the `Link` to the next page rides, and its rows.
_Page = tuple[dict[str, str], list[dict]]


class _StubIssue:
    """In-memory row with no PyGithub slot; read through its public attributes."""

    def __init__(self, number: int, *, is_pull_request: bool = False) -> None:
        self.number = number
        self.pull_request = object() if is_pull_request else None


class _CountingRequester:
    """The requester PyGithub rows are built on, recording every request.

    It serves the list pages it was given and answers any other URL with an
    empty record, so a row completed behind the filter's back shows up as a
    request the test did not expect rather than as an error.
    """

    per_page = DEFAULT_PER_PAGE
    is_not_lazy = True

    def __init__(self, pages: dict[str, _Page]) -> None:
        self.pages = pages
        self.requests: list[tuple[str, str]] = []

    def requestJsonAndCheck(self, verb, url, **request_options):
        self.requests.append((verb, url))
        return self.pages.get(url, ({}, {}))


class _TrappedRow:
    """A row that counts how often its public ``pull_request`` is asked."""

    def __init__(self, recorded: object, *, listed_as_pull_request: bool) -> None:
        self.number = 1
        self.public_reads = 0
        self._listed = object() if listed_as_pull_request else None
        if recorded is not _ABSENT:
            self._pull_request = recorded

    @property
    def pull_request(self) -> object | None:
        self.public_reads += 1
        return self._listed


def _row(number: int, **fields) -> dict:
    """One issue-list row, carrying the URL a completing read would fetch."""
    return {"number": number, "url": f"{_ISSUES_URL}/{number}", **fields}


def _filtered(row: _TrappedRow) -> list[_TrappedRow]:
    return list(_issue_polling.iter_new_non_pr_issues((row,), set()))


class IterNewNonPrIssuesTest(unittest.TestCase):
    """The poller sees each issue once and never sees a pull request.

    GitHub's issue endpoints return PRs alongside issues, and the open poll and
    the per-label closed sweep overlap, so a shared number set is what keeps a
    stage handler from running twice against the same issue in one tick.
    """

    def test_pull_requests_and_repeats_are_skipped(self) -> None:
        seen_numbers: set[int] = set()
        listed = (
            _StubIssue(1),
            _StubIssue(2, is_pull_request=True),
            _StubIssue(1),
            _StubIssue(3),
        )
        yielded = _issue_polling.iter_new_non_pr_issues(listed, seen_numbers)
        self.assertEqual([issue.number for issue in yielded], [1, 3])
        self.assertEqual(seen_numbers, {1, 3})

    def test_numbers_from_an_earlier_query_skipped(self) -> None:
        seen_numbers = {1}
        yielded = _issue_polling.iter_new_non_pr_issues(
            (_StubIssue(1), _StubIssue(4)),
            seen_numbers,
        )
        self.assertEqual([issue.number for issue in yielded], [4])
        self.assertEqual(seen_numbers, {1, 4})


class ListRowClassificationTest(unittest.TestCase):
    """A PyGithub list row is told apart from what its page carried.

    The issue list leaves ``pull_request`` off a real issue's row, and
    PyGithub's public property answers that absence with a detail GET, so the
    filter reads the slot PyGithub keeps and asks the property only about a
    row whose slot it does not recognize.
    """

    def test_a_walk_costs_its_pages_alone(self) -> None:
        requester = _CountingRequester({
            _ISSUES_URL: (
                {"link": f'<{_NEXT_PAGE_URL}>; rel="next"'},
                [_row(1), _row(2, pull_request={"url": _PULL_URL})],
            ),
            _NEXT_PAGE_URL: ({}, [_row(3), _row(4, pull_request=None)]),
        })
        listed = PaginatedList(Issue, requester, _ISSUES_URL, {})
        yielded = _issue_polling.iter_new_non_pr_issues(listed, set())
        self.assertEqual([issue.number for issue in yielded], [1, 3, 4])
        self.assertEqual(
            requester.requests,
            [(_GET, _ISSUES_URL), (_GET, _NEXT_PAGE_URL)],
        )

    def test_a_recognized_slot_answers_alone(self) -> None:
        pull_request = IssuePullRequest(
            _CountingRequester({}), {}, {"url": _PULL_URL},
        )
        for recorded, is_pull_request in (
            (NotSet, False),
            (_ValuedAttribute(None), False),
            (_ValuedAttribute(pull_request), True),
        ):
            with self.subTest(recorded=recorded):
                row = _TrappedRow(
                    recorded, listed_as_pull_request=not is_pull_request,
                )
                self.assertEqual(
                    _filtered(row), [] if is_pull_request else [row],
                )
                self.assertEqual(row.public_reads, 0)

    def test_any_other_slot_asks_the_property(self) -> None:
        slots = (
            _ABSENT,
            object(),
            _ValuedAttribute("not a pull request"),
            _BadAttribute("not a pull request", dict),
        )
        for recorded, is_pull_request in itertools.product(slots, (False, True)):
            with self.subTest(recorded=recorded, is_pull_request=is_pull_request):
                row = _TrappedRow(
                    recorded, listed_as_pull_request=is_pull_request,
                )
                self.assertEqual(
                    _filtered(row), [] if is_pull_request else [row],
                )
                self.assertEqual(row.public_reads, 1)


if __name__ == "__main__":
    unittest.main()
