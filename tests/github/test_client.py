# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Construction, worker cloning, and the label cache on the `client` owner."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from github import GithubException

from orchestrator.config import credentials as _config_credentials
from orchestrator.github import client as _client
from orchestrator.github.client import GitHubClient

_BOT = "orchestrator-bot"
_REPO_SLUG = "owner/repo"
_SPEC_SLUG = "other/repo"
_TOKEN = "tok"
_IMPLEMENTING_LABEL = "workflow:implementing"
_LEGACY_LABEL = "implementing"
_FORBIDDEN_STATUS = 403
_NOT_FOUND_STATUS = 404


def _bare_client(repo: _CountingRepo) -> GitHubClient:
    # Bypass the networked __init__; wire only what _cached_label touches.
    gh = GitHubClient.__new__(GitHubClient)
    gh.repo = repo
    gh._label_cache = {}
    gh._absent_after_sweep = {}
    gh._pollable_calls = 0
    gh._closed_sweeps = 0
    return gh


class _StubLabel:
    def __init__(self, name: str) -> None:
        self.name = name


class _CountingRepo:
    """Minimal stand-in for PyGithub's Repository that records how many times
    `get_label` is called, so the cache can be asserted without network.

    `missing` names answer 404 -- the repository confirming it has no such
    label. `unavailable` names answer 403, which says only that the question
    could not be asked. `recover` lifts the 403s and `add_label` makes a
    missing name resolve, so a test can assert what the next lookup sees.
    """

    def __init__(
        self,
        *,
        missing: set[str] | None = None,
        unavailable: set[str] | None = None,
    ) -> None:
        self.get_label_calls: list[str] = []
        self._missing = missing or set()
        self._unavailable = unavailable or set()

    def recover(self) -> None:
        """Clear the transient failures, as a lifted rate limit would."""
        self._unavailable = set()

    def add_label(self, name: str) -> None:
        """Make a missing label resolve, as a human re-adding it would."""
        self._missing = self._missing - {name}

    def get_label(self, name: str):
        self.get_label_calls.append(name)
        if name in self._unavailable:
            raise GithubException(
                _FORBIDDEN_STATUS,
                {"message": "Forbidden"},
                None,
            )
        if name in self._missing:
            raise GithubException(
                _NOT_FOUND_STATUS,
                {"message": "Not Found"},
                None,
            )
        return _StubLabel(name)


class ClientConstructionTest(unittest.TestCase):
    """Construction resolves the token per repository and fails loudly.

    The token is a per-repository credential the operator may keep in a token
    file rather than the environment, so an explicit token wins, a `repo_spec`
    picks the slug its own credential is resolved against, and an unresolvable
    token has to stop the client instead of opening an unauthenticated session.
    """

    def setUp(self) -> None:
        self.github_class = patch("orchestrator.github.client.Github").start()
        patch("orchestrator.github.client.Auth").start()
        self.addCleanup(patch.stopall)
        self.github_class.return_value.get_user.return_value = MagicMock(
            login=_BOT,
        )

    def test_explicit_token_skips_resolution(self) -> None:
        with patch.object(_config_credentials, "resolve_github_token") as resolve:
            client = GitHubClient(token=_TOKEN, repo_slug=_REPO_SLUG)
            resolve.assert_not_called()

        self.assertEqual(client._token, _TOKEN)
        self.github_class.return_value.get_repo.assert_called_once_with(
            _REPO_SLUG,
        )

    def test_repo_spec_slug_resolves_its_own_token(self) -> None:
        spec = MagicMock(slug=_SPEC_SLUG)
        with patch.object(
            _config_credentials,
            "resolve_github_token",
            return_value=_TOKEN,
        ) as resolve:
            client = GitHubClient(repo_slug=_REPO_SLUG, repo_spec=spec)
            resolve.assert_called_once_with(_SPEC_SLUG)

        self.assertEqual(client._repo_slug, _SPEC_SLUG)

    def test_unresolvable_token_is_refused(self) -> None:
        # The message names the token file for the slug being opened, so the
        # operator knows which repository credential is missing.
        with (
            patch.object(_config_credentials, "resolve_github_token", return_value=""),
            self.assertRaisesRegex(RuntimeError, _REPO_SLUG),
        ):
            GitHubClient(repo_slug=_REPO_SLUG)


class BotLoginResolutionTest(unittest.TestCase):
    """The orchestrator login is resolved once at construction and threaded
    into worker-thread clones so the parallel path issues no extra
    `GET /user` per worker."""

    def test_worker_clone_reuses_resolved_login(self) -> None:
        with patch("orchestrator.github.client.Github") as GH, \
             patch("orchestrator.github.client.Auth"):
            gh_inst = GH.return_value
            gh_inst.get_repo.return_value = MagicMock()
            gh_inst.get_user.return_value = MagicMock(login=_BOT)

            client = GitHubClient(token=_TOKEN, repo_slug=_REPO_SLUG)
            self.assertEqual(client._bot_login, _BOT)
            gh_inst.get_user.assert_called_once()

            gh_inst.get_user.reset_mock()
            worker = client._for_worker_thread()
            self.assertEqual(worker._bot_login, _BOT)
            # Clone inherits the login instead of re-fetching it.
            gh_inst.get_user.assert_not_called()


class CachedLabelTest(unittest.TestCase):
    """`_cached_label` must fetch each workflow label at most once per client
    (labels are immutable after `ensure_workflow_labels`), while still
    retrying a failed lookup every call so a fixed PAT / created label is
    picked up without a restart.
    """

    def test_resolved_label_is_fetched_once(self) -> None:
        repo = _CountingRepo()
        gh = _bare_client(repo)
        for _ in range(5):
            label = gh._cached_label(_IMPLEMENTING_LABEL)
            self.assertEqual(label.name, _IMPLEMENTING_LABEL)
        self.assertEqual(repo.get_label_calls, [_IMPLEMENTING_LABEL])

    def test_failed_lookup_is_not_cached_and_retries(self) -> None:
        repo = _CountingRepo(missing={_IMPLEMENTING_LABEL})
        gh = _bare_client(repo)
        self.assertIsNone(gh._cached_label(_IMPLEMENTING_LABEL))
        self.assertIsNone(gh._cached_label(_IMPLEMENTING_LABEL))
        # Both calls hit GitHub: a label a human may still create must not be
        # written off after one miss.
        self.assertEqual(
            repo.get_label_calls,
            [_IMPLEMENTING_LABEL, _IMPLEMENTING_LABEL],
        )

    def test_confirmed_absence_is_throttled(self) -> None:
        # `throttle_absent` is for a name a migrated repository is expected to
        # be missing -- the pre-namespace spellings the closed-issue sweep
        # also asks for. Inside the window a 404 is taken at its word, so the
        # sweep does not spend a request per pass on a certain miss.
        repo = _CountingRepo(missing={_LEGACY_LABEL})
        gh = _bare_client(repo)
        for _ in range(3):
            self.assertIsNone(
                gh._cached_label(_LEGACY_LABEL, throttle_absent=True),
            )
        self.assertEqual(repo.get_label_calls, [_LEGACY_LABEL])

    def test_absent_label_resolves_once_it_reappears(self) -> None:
        # The throttle is a window, not a verdict: a human (or an older
        # integration) re-applying the pre-namespace label must be picked up
        # without a restart, or the closed issues now carrying it are stranded
        # for the life of the process.
        repo = _CountingRepo(missing={_LEGACY_LABEL})
        gh = _bare_client(repo)

        self.assertIsNone(
            gh._cached_label(_LEGACY_LABEL, throttle_absent=True),
        )
        repo.add_label(_LEGACY_LABEL)
        gh._closed_sweeps += _client._ABSENT_LABEL_RETRY_SWEEPS
        reappeared = gh._cached_label(_LEGACY_LABEL, throttle_absent=True)

        self.assertEqual(reappeared.name, _LEGACY_LABEL)
        self.assertEqual(repo.get_label_calls, [_LEGACY_LABEL, _LEGACY_LABEL])

    def test_transient_failure_retries_and_recovers(self) -> None:
        # 403 is what an exhausted primary rate limit answers, and it says
        # nothing about whether the label exists. Caching it as absence would
        # strand the closed legacy-labeled issues this lookup exists to reach,
        # so it stays retryable even under `throttle_absent` -- and the lookup
        # resolves as soon as the limit lifts.
        repo = _CountingRepo(unavailable={_LEGACY_LABEL})
        gh = _bare_client(repo)

        for _ in range(2):
            self.assertIsNone(
                gh._cached_label(_LEGACY_LABEL, throttle_absent=True),
            )
        repo.recover()
        recovered = gh._cached_label(_LEGACY_LABEL, throttle_absent=True)

        self.assertEqual(recovered.name, _LEGACY_LABEL)
        self.assertEqual(
            repo.get_label_calls,
            [_LEGACY_LABEL, _LEGACY_LABEL, _LEGACY_LABEL],
        )


if __name__ == "__main__":
    unittest.main()
