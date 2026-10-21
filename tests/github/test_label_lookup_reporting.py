# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a closed-issue sweep reports about the labels it could not resolve."""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import MagicMock, patch

from github import GithubException

from orchestrator import config
from orchestrator.github.client import GitHubClient

_LOG_CHANNEL = "orchestrator.github"
_REPO_SLUG = "owner/repo"
_INFO_LEVEL = "INFO"
_WARNING_LEVEL = "WARNING"
_FAILURE_STATUSES = (404, 403, 502)
_CANONICAL_LABEL = "workflow:implementing"
_SWEEP_CADENCE_ATTR = "CLOSED_ISSUE_SWEEP_EVERY_N_TICKS"
_SWEEPS = 2


def _label_lookup(
    failing: tuple[str, ...], status: int, name: str,
) -> MagicMock:
    """Answer `status` for the named labels and resolve every other one."""
    if name in failing:
        raise GithubException(status, {"message": "nope"}, None)
    return MagicMock(name=f"{name}_label")


def _sweeping_client(*, failing: tuple[str, ...], status: int) -> GitHubClient:
    """A bare client whose repo fails the named label lookups."""
    # Bypass the networked __init__; wire only what the poll generator reads.
    client = GitHubClient.__new__(GitHubClient)
    client.repo = MagicMock()
    client._repo_slug = _REPO_SLUG
    client._pollable_calls = 0
    client._label_cache = {}
    client.repo.get_issues.side_effect = lambda **_: iter([])
    client.repo.get_label.side_effect = partial(_label_lookup, failing, status)
    return client


def _sweeps(client: GitHubClient) -> None:
    """Drain `_SWEEPS` polls, so each sweep runs past the end of its lookup loop."""
    for _ in range(_SWEEPS):
        list(client.list_pollable_issues())


# Pinned, because a poll only sweeps on the cadence and the operator's own
# environment sets it: unpinned, the second poll of a test would answer
# "nothing reported" by never having swept.
@patch.object(config, _SWEEP_CADENCE_ATTR, 1)
class LookupFailureReportingTest(unittest.TestCase):
    """A failed lookup is a warning an operator can act on; nothing else is.

    The sweep asks only for canonical labels, so any lookup that fails is one
    the operator has to act on: a label that is not there leaves the closed
    issues carrying it unswept, and a 403 or a 5xx says the question could not
    be asked at all. Each sweep asks again, so each one that fails says so.
    """

    def test_failed_lookup_warns_each_sweep(self) -> None:
        for status in _FAILURE_STATUSES:
            with self.subTest(status=status):
                client = _sweeping_client(
                    failing=(_CANONICAL_LABEL,), status=status,
                )

                with self.assertLogs(_LOG_CHANNEL, level=_INFO_LEVEL) as captured:
                    _sweeps(client)
                    reported = list(captured.records)

                self.assertEqual(len(reported), _SWEEPS)
                for record in reported:
                    self.assertEqual(record.levelname, _WARNING_LEVEL)
                    self.assertIn(_CANONICAL_LABEL, record.getMessage())
                    self.assertIn(str(status), record.getMessage())

    def test_resolved_sweep_says_nothing(self) -> None:
        # A repository defining every canonical label has nothing to report,
        # on the first sweep or any after it.
        client = _sweeping_client(failing=(), status=_FAILURE_STATUSES[0])

        with self.assertNoLogs(_LOG_CHANNEL, level=_INFO_LEVEL):
            _sweeps(client)


if __name__ == "__main__":
    unittest.main()
