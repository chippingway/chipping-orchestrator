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
from orchestrator.github.issue_polling import SWEEP_LOOKUPS

_LOG_CHANNEL = "orchestrator.github"
_REPO_SLUG = "owner/repo"
_INFO_LEVEL = "INFO"
_WARNING_LEVEL = "WARNING"
_NOT_FOUND_STATUS = 404
_FORBIDDEN_STATUS = 403
_SERVER_ERROR_STATUS = 502
_CANONICAL_LABEL = "workflow:implementing"
_SWEEP_CADENCE_ATTR = "CLOSED_ISSUE_SWEEP_EVERY_N_TICKS"

# Every pre-namespace spelling the sweep asks for beside a namespaced one,
# recovery states and cleanup states alike -- all of them answer 404 on a
# repository the rename reached.
_LEGACY_NAMES = tuple(
    name
    for name, absence_is_expected in SWEEP_LOOKUPS
    if absence_is_expected
)


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
    client._closed_sweeps = 0
    client._label_cache = {}
    client._absent_after_sweep = {}
    client.repo.get_issues.return_value = iter([])
    client.repo.get_label.side_effect = partial(_label_lookup, failing, status)
    return client


def _sweep(client: GitHubClient) -> list:
    """Drain one poll, so the sweep runs past the end of its lookup loop."""
    return list(client.list_pollable_issues())


# Pinned, because a poll only sweeps on the cadence and the operator's own
# environment sets it: unpinned, the second poll of a test would answer
# "nothing reported" by never having swept.
@patch.object(config, _SWEEP_CADENCE_ATTR, 1)
class AbsentLegacyLabelSummaryTest(unittest.TestCase):
    """Confirmed-absent legacy spellings are summarized, once per sweep.

    A repository the rename reached answers 404 for every pre-namespace
    spelling, so reporting them one at a time opens each fresh process with a
    burst of near-identical lines -- one per spelling per repo, naming neither
    the repository nor what the names are -- and repeats it whenever the retry
    window expires. One line per repository says the same thing.
    """

    def test_absent_spellings_are_one_repository_line(self) -> None:
        client = _sweeping_client(
            failing=_LEGACY_NAMES, status=_NOT_FOUND_STATUS,
        )

        with self.assertLogs(_LOG_CHANNEL, level=_INFO_LEVEL) as captured:
            _sweep(client)
            reported = list(captured.records)

        self.assertEqual(
            [record.levelname for record in reported],
            [_INFO_LEVEL],
        )
        summary = reported[0].getMessage()
        self.assertIn(_REPO_SLUG, summary)
        self.assertIn("legacy", summary)
        for legacy_name in _LEGACY_NAMES:
            self.assertIn(legacy_name, summary)

    def test_interrupted_sweep_carries_nothing_over(self) -> None:
        # A closed-issue query that raises abandons the sweep holding names it
        # never got to summarize. They belong to that pass: carried into the
        # next one they would restate a skip served from the retry window as a
        # freshly confirmed miss, with the window starting over.
        client = _sweeping_client(
            failing=_LEGACY_NAMES, status=_NOT_FOUND_STATUS,
        )
        client.repo.get_issues.side_effect = (
            iter([]),
            iter([]),
            GithubException(_SERVER_ERROR_STATUS, {"message": "boom"}, None),
        )
        with self.assertRaises(GithubException):
            _sweep(client)
        # The transient failure lifts, so the next sweep runs to its end.
        client.repo.get_issues.side_effect = None

        with self.assertLogs(_LOG_CHANNEL, level=_INFO_LEVEL) as captured:
            _sweep(client)
            reported = list(captured.records)

        summary = reported[0].getMessage()
        self.assertNotIn(_LEGACY_NAMES[0], summary)
        for unasked_name in _LEGACY_NAMES[1:]:
            self.assertIn(unasked_name, summary)

    def test_throttled_sweep_says_nothing(self) -> None:
        # A lookup skipped inside the retry window is not a fresh answer, so
        # the sweeps behind the first one add nothing to what it already said.
        client = _sweeping_client(
            failing=_LEGACY_NAMES, status=_NOT_FOUND_STATUS,
        )
        _sweep(client)

        with self.assertNoLogs(_LOG_CHANNEL, level=_INFO_LEVEL):
            _sweep(client)


class ActionableLookupFailureTest(unittest.TestCase):
    """A failure an operator has to act on keeps its own warning.

    Only a 404 on a spelling a migrated repository is expected to have dropped
    is routine. A canonical label that is not there leaves the closed issues
    carrying it unswept, and a 403 says the question could not be asked at all
    -- neither belongs in a summary of expected misses.
    """

    def test_canonical_miss_warns(self) -> None:
        self._assert_one_warning_names(
            _sweeping_client(
                failing=(_CANONICAL_LABEL,), status=_NOT_FOUND_STATUS,
            ),
            _CANONICAL_LABEL,
        )

    def test_transient_legacy_failure_warns(self) -> None:
        # 403 is what an exhausted primary rate limit answers, and it says
        # nothing about whether the label exists -- so even on a spelling
        # whose absence would be expected it stays a warning rather than
        # joining the summary of confirmed misses.
        self._assert_one_warning_names(
            _sweeping_client(
                failing=(_LEGACY_NAMES[0],), status=_FORBIDDEN_STATUS,
            ),
            _LEGACY_NAMES[0],
        )

    def _assert_one_warning_names(
        self, client: GitHubClient, label_name: str,
    ) -> None:
        """One warning per failed lookup, naming the label it was about."""
        with self.assertLogs(_LOG_CHANNEL, level=_INFO_LEVEL) as captured:
            _sweep(client)
            reported = list(captured.records)

        self.assertEqual(
            [record.levelname for record in reported],
            [_WARNING_LEVEL],
        )
        self.assertIn(label_name, reported[0].getMessage())


if __name__ == "__main__":
    unittest.main()
