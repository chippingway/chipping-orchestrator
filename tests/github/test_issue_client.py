# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Real-client sweep polling and child creation over the composed client."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from github import GithubException

from orchestrator.config import settings as config
from orchestrator.github import labels as _label_cache
from orchestrator.github.client import GitHubClient
from orchestrator.github.issue_polling import SWEEP_LOOKUPS
from orchestrator.workflow.state import WorkflowLabel

_STATE_OPEN = "open"
_STATE_CLOSED = "closed"
_SWEPT_LABEL_COUNT = len(SWEEP_LOOKUPS)
_HTTP_NOT_FOUND = 404
_PARENT_ISSUE_NUMBER = 42
_LEGACY_SWEEP_NAME = "implementing"
_REPO_SLUG = "owner/repo"
_SWEPT_ISSUE_NUMBER = 77
_SWEEP_CADENCE_ATTR = "CLOSED_ISSUE_SWEEP_EVERY_N_TICKS"


def _closed_sweep_fixture():
    """Return a bare client whose repo resolves each swept label by name."""
    # Bypass the networked __init__; wire only what the poll generator reads.
    client = GitHubClient.__new__(GitHubClient)
    client.repo = MagicMock()
    client._repo_slug = _REPO_SLUG
    client._pollable_calls = 0
    client._closed_sweeps = 0
    client._label_cache = {}
    client._absent_after_sweep = {}
    client.repo.get_issues.return_value = iter([])
    sweep_labels = {
        name: MagicMock(name=f"{name}_label")
        for name, _ in SWEEP_LOOKUPS
    }
    client.repo.get_label.side_effect = sweep_labels.__getitem__
    return client, sweep_labels


def _raise_not_found() -> None:
    raise GithubException(_HTTP_NOT_FOUND, {"message": "Not Found"}, None)


def _absent_legacy_fixture() -> GitHubClient:
    """A client whose repo resolves every swept label but the legacy one."""
    client, sweep_labels = _closed_sweep_fixture()
    client.repo.get_label.side_effect = lambda name: (
        _raise_not_found()
        if name == _LEGACY_SWEEP_NAME
        else sweep_labels[name]
    )
    return client


def _legacy_lookups(client: GitHubClient) -> int:
    """How many times the repository was asked for the legacy label."""
    return len([
        call for call in client.repo.get_label.call_args_list
        if call.args[0] == _LEGACY_SWEEP_NAME
    ])


class ClosedIssueSweepLabelTest(unittest.TestCase):
    """The closed-issue sweep queries with Label objects, never label names.

    Real PyGithub's `Repository.get_issues(labels=...)` reads `label.name`, so
    a raw string list raises a TypeError before the generator yields anything.
    That exception escapes the per-issue try/except in `tick()`, so every tick
    would fail once the open issues were processed and externally-merged
    in_review issues would never finalize to `done`. Poking the real client
    against a mocked Repository is what pins the argument type down.
    """

    def test_closed_sweep_uses_label_object(self) -> None:
        client, sweep_labels = _closed_sweep_fixture()

        list(client.list_pollable_issues())

        calls = SimpleNamespace(
            looked_up={
                call.args[0]
                for call in client.repo.get_label.call_args_list
            },
            closed=[
                call
                for call in client.repo.get_issues.call_args_list
                if call.kwargs.get("state") == _STATE_CLOSED
            ],
        )
        self.assertEqual(calls.looked_up, set(sweep_labels))
        self.assertEqual(len(calls.closed), _SWEPT_LABEL_COUNT)
        labels_passed = [call.kwargs["labels"] for call in calls.closed]
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


class LegacyClosedSweepTest(unittest.TestCase):
    """The sweep asks for the pre-namespace spelling too, on a throttle.

    A closed issue is the one case no other pass revisits, so on a repository
    whose labels the bootstrap could not rename the bare spelling is all that
    is left to find it by. Every such query costs a request, though, and on a
    migrated repository the answer is a certain miss -- so consecutive sweeps
    inside the retry window reuse it instead of re-asking. The window's own
    expiry is `CachedLabelTest`'s.
    """

    def test_both_spellings_are_queried(self) -> None:
        client, _ = _closed_sweep_fixture()

        list(client.list_pollable_issues())

        looked_up = [
            call.args[0] for call in client.repo.get_label.call_args_list
        ]
        self.assertIn(str(WorkflowLabel.IMPLEMENTING), looked_up)
        self.assertIn(_LEGACY_SWEEP_NAME, looked_up)

    def test_issue_seen_twice_is_yielded_once(self) -> None:
        # A repository mid-migration can carry both labels on one issue, so
        # the two queries return it twice; `seen_numbers` is what collapses
        # that into the single handler dispatch the dispatcher expects.
        client, _ = _closed_sweep_fixture()
        swept = SimpleNamespace(number=_SWEPT_ISSUE_NUMBER, pull_request=None)
        client.repo.get_issues.side_effect = lambda **kwargs: iter(
            [] if kwargs.get("state") == _STATE_OPEN else [swept],
        )

        polled = list(client.list_pollable_issues())

        self.assertEqual([issue.number for issue in polled], [_SWEPT_ISSUE_NUMBER])

    def test_absent_legacy_label_throttled(self) -> None:
        # Three sweeps inside one retry window ask once. Without the throttle
        # every migrated repository would spend a request per legacy name per
        # sweep on an answer that is not going to change for a long while.
        client = _absent_legacy_fixture()

        for _ in range(3):
            list(client.list_pollable_issues())

        self.assertEqual(_legacy_lookups(client), 1)

    def test_window_counts_sweeps_not_polls(self) -> None:
        # Under a non-default cadence most polls never reach the sweep at all.
        # Measured in polls, the window would erode as the cadence rises --
        # expiring after a third of the sweeps at `N=3`, and before the very
        # next one at any `N` past the window itself.
        polls_per_sweep = 3
        sweeps = _label_cache._ABSENT_LABEL_RETRY_SWEEPS
        client = _absent_legacy_fixture()

        with patch.object(
            config, _SWEEP_CADENCE_ATTR, polls_per_sweep,
        ):
            for _ in range(sweeps * polls_per_sweep):
                list(client.list_pollable_issues())

        self.assertEqual(client._closed_sweeps, sweeps)
        self.assertEqual(_legacy_lookups(client), 1)

    def test_window_expires_on_the_sweep_past_it(self) -> None:
        # One sweep past the window the question is asked again, so a label
        # re-applied by hand is picked up rather than written off.
        polls_per_sweep = 3
        sweeps = _label_cache._ABSENT_LABEL_RETRY_SWEEPS + 1
        client = _absent_legacy_fixture()

        with patch.object(
            config, _SWEEP_CADENCE_ATTR, polls_per_sweep,
        ):
            for _ in range(sweeps * polls_per_sweep):
                list(client.list_pollable_issues())

        self.assertEqual(_legacy_lookups(client), 2)


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


if __name__ == "__main__":
    unittest.main()
