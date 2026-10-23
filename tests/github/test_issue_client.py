# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Real-client sweep polling and child creation over the composed client."""
from __future__ import annotations

import unittest
from functools import partial
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from github import GithubException

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.state import WorkflowLabel

_STATE_OPEN = "open"
_STATE_CLOSED = "closed"
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_PARENT_ISSUE_NUMBER = 42
_REPO_SLUG = "owner/repo"
_SWEPT_ISSUE_NUMBER = 77
_SWEEP_CADENCE_ATTR = "CLOSED_ISSUE_SWEEP_EVERY_N_TICKS"

# Every name one sweep asks for, spelled as GitHub stores it: the eight
# recovery labels -- `in_review`, `question`, and `discussion` canonical under
# their bare spelling -- then the four cleanup ones.
_CANONICAL_SWEEP_NAMES = (
    "workflow:implementing",
    "workflow:documenting",
    "workflow:validating",
    "in_review",
    "workflow:fixing",
    "workflow:resolving_conflict",
    "question",
    "discussion",
    "workflow:decomposing",
    "workflow:umbrella",
    "workflow:ready",
    "workflow:blocked",
)
_SWEPT_LABEL_COUNT = len(_CANONICAL_SWEEP_NAMES)
_FAILING_SWEEP_NAME = "workflow:fixing"


def _label_lookup(
    sweep_labels: dict[str, MagicMock],
    failing: frozenset[str],
    status: int,
    name: str,
) -> MagicMock:
    """Answer `status` for the failing names and resolve the other canonical ones.

    Any other name answers 404, so a lookup the sweep should never make is
    recorded on the mock rather than raising out of the poll.
    """
    if name in failing:
        raise GithubException(status, {"message": "nope"}, None)
    if name not in sweep_labels:
        raise GithubException(_HTTP_NOT_FOUND, {"message": "Not Found"}, None)
    return sweep_labels[name]


def _closed_sweep_fixture():
    """Return a bare client whose repo resolves each canonical swept label."""
    # Bypass the networked __init__; wire only what the poll generator reads.
    client = GitHubClient.__new__(GitHubClient)
    client.repo = MagicMock()
    client._repo_slug = _REPO_SLUG
    client._pollable_calls = 0
    client._label_cache = {}
    client.repo.get_issues.side_effect = lambda **_: iter([])
    sweep_labels = {
        name: MagicMock(name=f"{name}_label")
        for name in _CANONICAL_SWEEP_NAMES
    }
    client.repo.get_label.side_effect = partial(
        _label_lookup, sweep_labels, frozenset(), _HTTP_NOT_FOUND,
    )
    return client, sweep_labels


def _requests(client: GitHubClient) -> SimpleNamespace:
    """What the client asked the repository for, by kind."""
    queries = client.repo.get_issues.call_args_list
    return SimpleNamespace(
        looked_up=[call.args[0] for call in client.repo.get_label.call_args_list],
        open=[call for call in queries if call.kwargs["state"] == _STATE_OPEN],
        closed=[call for call in queries if call.kwargs["state"] == _STATE_CLOSED],
    )


def _sweep_through_failure(status: int):
    """Sweep once with one label's lookup failing `status`, then once with it resolving."""
    client, sweep_labels = _closed_sweep_fixture()
    client.repo.get_label.side_effect = partial(
        _label_lookup, sweep_labels, frozenset((_FAILING_SWEEP_NAME,)), status,
    )
    with patch.object(config, _SWEEP_CADENCE_ATTR, 1):
        list(client.list_pollable_issues())
        failed = _requests(client)
        client.repo.get_label.side_effect = partial(
            _label_lookup, sweep_labels, frozenset(), status,
        )
        list(client.list_pollable_issues())
    return failed, _requests(client), sweep_labels[_FAILING_SWEEP_NAME]


class ClosedIssueSweepLabelTest(unittest.TestCase):
    """The closed-issue sweep asks for canonical names and queries by Label.

    Real PyGithub's `Repository.get_issues(labels=...)` reads `label.name`, so
    a raw string list raises a TypeError before the generator yields anything.
    That exception escapes the per-issue try/except in `tick()`, so every tick
    would fail once the open issues were processed and externally-merged
    in_review issues would never finalize to `done`. Poking the real client
    against a mocked Repository is what pins the argument type down.
    """

    def test_sweep_queries_canonical_label_objects(self) -> None:
        # Exactly the canonical names, each once: no pre-namespace spelling is
        # asked for or queried, and the bare canonical names are not dropped.
        client, sweep_labels = _closed_sweep_fixture()

        list(client.list_pollable_issues())

        requests = _requests(client)
        self.assertEqual(
            sorted(requests.looked_up), sorted(_CANONICAL_SWEEP_NAMES),
        )
        labels_passed = [call.kwargs["labels"] for call in requests.closed]
        self.assertEqual(len(labels_passed), _SWEPT_LABEL_COUNT)
        for expected_label in sweep_labels.values():
            self.assertIn([expected_label], labels_passed)

    def test_missing_label_skips_closed_sweep(self) -> None:
        # If `get_label` raises (under-scoped PAT, label not yet bootstrapped)
        # the generator must complete the open-issue sweep AND swallow the
        # closed-issue branch -- otherwise `tick()` aborts mid-loop.
        client, _ = _closed_sweep_fixture()
        client.repo.get_label.side_effect = GithubException(
            _HTTP_NOT_FOUND,
            {"message": "Not Found"},
            None,
        )

        polled = list(client.list_pollable_issues())

        self.assertEqual(polled, [])
        states = [
            call.kwargs.get("state")
            for call in client.repo.get_issues.call_args_list
        ]
        self.assertEqual(states, [_STATE_OPEN])

    def test_issue_seen_twice_is_yielded_once(self) -> None:
        # A closed issue a human left on two swept labels comes back from both
        # queries, and the open poll can list one closed while the sweep runs;
        # `seen_numbers` is what collapses that into the single handler
        # dispatch the dispatcher expects.
        client, _ = _closed_sweep_fixture()
        swept = SimpleNamespace(number=_SWEPT_ISSUE_NUMBER, pull_request=None)
        client.repo.get_issues.side_effect = lambda **_: iter([swept])

        polled = list(client.list_pollable_issues())

        self.assertEqual([issue.number for issue in polled], [_SWEPT_ISSUE_NUMBER])


class ClosedSweepRequestCostTest(unittest.TestCase):
    """What the sweep costs in requests across polls, and how it recovers.

    A resolved label is a request paid once per client; the closed queries are
    paid once per sweep, and the cadence decides how many polls that is. A
    lookup that failed is not remembered either way, so the next sweep asks
    for it again and queries it once it resolves.
    """

    def test_labels_asked_once_queried_per_sweep(self) -> None:
        polls_per_sweep = 3
        polls = 2 * polls_per_sweep
        client, _ = _closed_sweep_fixture()

        with patch.object(config, _SWEEP_CADENCE_ATTR, polls_per_sweep):
            for _ in range(polls):
                list(client.list_pollable_issues())

        requests = _requests(client)
        self.assertEqual(len(requests.open), polls)
        self.assertEqual(len(requests.closed), 2 * _SWEPT_LABEL_COUNT)
        self.assertEqual(
            sorted(requests.looked_up), sorted(_CANONICAL_SWEEP_NAMES),
        )

    def test_failed_lookup_is_asked_again_next_sweep(self) -> None:
        # Neither answer is cached as an absence: a 404 is a label a human may
        # still add, and a 403 is what an exhausted rate limit answers. The
        # failed label's query is the one the first sweep skips, and the only
        # label the second sweep has to ask for again.
        for status in (_HTTP_NOT_FOUND, _HTTP_FORBIDDEN):
            with self.subTest(status=status):
                failed, recovered, retried_label = _sweep_through_failure(status)

                self.assertEqual(len(failed.closed), _SWEPT_LABEL_COUNT - 1)
                self.assertEqual(
                    recovered.looked_up[len(failed.looked_up):],
                    [_FAILING_SWEEP_NAME],
                )
                second_sweep = recovered.closed[len(failed.closed):]
                self.assertEqual(len(second_sweep), _SWEPT_LABEL_COUNT)
                self.assertIn(
                    [retried_label],
                    [call.kwargs["labels"] for call in second_sweep],
                )


class CreateChildIssueAlwaysUsesParentRepoTest(unittest.TestCase):
    """`create_child_issue` is structurally bound to `self.repo` so a
    misuse cannot accidentally file a child against a different repo
    than the parent. Worth a regression test anyway.
    """

    def test_creates_child_in_repo_with_parent_link(self) -> None:
        client = GitHubClient.__new__(GitHubClient)
        client.repo = MagicMock()
        sentinel = MagicMock(name="created_issue")
        client.repo.create_issue.return_value = sentinel

        created = client.create_child_issue(
            title="A",
            body="do A",
            parent_number=_PARENT_ISSUE_NUMBER,
            labels=["workflow:ready"],
        )

        self.assertIs(created, sentinel)
        client.repo.create_issue.assert_called_once()
        create_kwargs = client.repo.create_issue.call_args.kwargs
        self.assertEqual(create_kwargs["title"], "A")
        self.assertEqual(create_kwargs["labels"], [WorkflowLabel.READY])
        # Parent link prepended via the helper (not by the caller) so the
        # workflow code can hand the agent's raw body straight in.
        self.assertIn(
            f"Parent: #{_PARENT_ISSUE_NUMBER}",
            create_kwargs["body"],
        )

    def test_an_obsolete_birth_label_creates_nothing(self) -> None:
        # A bare `ready` names no state, so a child born on it would be an
        # unlabeled issue the next tick picks up as fresh work.
        client = GitHubClient.__new__(GitHubClient)
        client.repo = MagicMock()

        with self.assertRaises(ValueError):
            client.create_child_issue(
                title="A",
                body="do A",
                parent_number=_PARENT_ISSUE_NUMBER,
                labels=["ready"],
            )

        client.repo.create_issue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
