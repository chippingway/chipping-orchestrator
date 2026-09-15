# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Construction, worker cloning, and the label cache on the `client` owner."""
from __future__ import annotations

import unittest
import warnings
from types import MappingProxyType
from unittest.mock import MagicMock, call, patch

from github import GithubException
from github.Requester import Requester

from orchestrator import config
from orchestrator.github import labels as _label_cache
from orchestrator.github.client import GitHubClient

_BOT = "orchestrator-bot"
_REPO_SLUG = "owner/repo"
_SPEC_SLUG = "other/repo"
_TOKEN = "tok"
_IMPLEMENTING_LABEL = "workflow:implementing"
_LEGACY_LABEL = "implementing"
_FORBIDDEN_STATUS = 403
_NOT_FOUND_STATUS = 404
_NUMBER = 7
_BRANCH = "orchestrator/issue-7"

# The repository as GitHub describes it back: a spelling the configured slug
# does not share, so a reading taken off the unfetched URL is told apart.
_CANONICAL_OWNER = "Owner"
_CANONICAL_SLUG = f"{_CANONICAL_OWNER}/Repo"
_CANONICAL_URL = f"https://api.github.com/repos/{_CANONICAL_SLUG}"
_CANONICAL_PULLS_URL = f"{_CANONICAL_URL}/pulls"
_REPO_PATH = f"/repos/{_REPO_SLUG}"
_MISSING_LABEL_PATH = f"{_REPO_PATH}/labels/{_LEGACY_LABEL}"
_WIRE_BODIES = MappingProxyType({
    _REPO_PATH: {
        "url": _CANONICAL_URL,
        "full_name": _CANONICAL_SLUG,
        "owner": {"login": _CANONICAL_OWNER},
    },
    "/user": {"login": _BOT},
})


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


class _RecordingWire:
    """GitHub's REST API as every PyGithub requester reaches it.

    Each request is recorded with the requester that sent it, so a test can
    tell the parent's connection from a worker's and count exactly what a
    mint, a metadata read, or a URL-based operation put on the wire.
    """

    def __init__(self) -> None:
        self.requests: list[tuple[Requester, str, dict | None]] = []

    def answer(self, requester: Requester, verb: str, url: str, **options):
        self.requests.append((requester, url, options.get("parameters")))
        if url == _MISSING_LABEL_PATH:
            raise GithubException(
                _NOT_FOUND_STATUS,
                {"message": "Not Found"},
                None,
            )
        if url == _CANONICAL_PULLS_URL:
            return {}, []
        return {}, _WIRE_BODIES.get(url, {"url": url, "number": _NUMBER})

    def sent_by(self, client: GitHubClient) -> list[str]:
        """The URLs one client's own requester asked for, in order."""
        return [
            url for requester, url, _ in self.requests
            if requester is client._gh.requester
        ]


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
        with patch.object(config, "_resolve_github_token") as resolve:
            client = GitHubClient(token=_TOKEN, repo_slug=_REPO_SLUG)
            resolve.assert_not_called()

        self.assertEqual(client._token, _TOKEN)

    def test_parent_fetches_while_worker_defers(self) -> None:
        # Both clients take their repository from `get_repo`: the enumerating
        # parent fetches it, and a worker asks for it lazily and hands it the
        # worker's own requester back, so the issues, pull requests, and labels
        # it returns are still fetched when asked.
        gh_instance = self.github_class.return_value
        parent = GitHubClient(token=_TOKEN, repo_slug=_REPO_SLUG)
        self.assertEqual(
            gh_instance.get_repo.call_args_list, [call(_REPO_SLUG)],
        )

        worker = parent._for_worker_thread()

        self.assertEqual(
            gh_instance.get_repo.call_args_list,
            [call(_REPO_SLUG), call(_REPO_SLUG, lazy=True)],
        )
        self.assertIs(worker.repo, gh_instance.get_repo.return_value)
        self.assertIs(worker.repo._requester, gh_instance.requester)
        self.assertEqual(self.github_class.call_count, 2)

    def test_repo_spec_slug_resolves_its_own_token(self) -> None:
        spec = MagicMock(slug=_SPEC_SLUG)
        with patch.object(
            config,
            "_resolve_github_token",
            return_value=_TOKEN,
        ) as resolve:
            client = GitHubClient(repo_slug=_REPO_SLUG, repo_spec=spec)
            resolve.assert_called_once_with(_SPEC_SLUG)

        self.assertEqual(client._repo_slug, _SPEC_SLUG)

    def test_unresolvable_token_is_refused(self) -> None:
        # The message names the token file for the slug being opened, so the
        # operator knows which repository credential is missing.
        with (
            patch.object(config, "_resolve_github_token", return_value=""),
            self.assertRaisesRegex(RuntimeError, _REPO_SLUG),
        ):
            GitHubClient(repo_slug=_REPO_SLUG)


class WorkerClientTest(unittest.TestCase):
    """A worker client is minted without a request and fetches on demand.

    Every scheduled handler mints one, so what a mint sends is paid per issue
    per tick. The parent resolves the repository and the bot login when it is
    built; a worker reuses the token and login, keeps a requester of its own
    because PyGithub's request state is not thread-safe, and fetches its
    repository only when something reads the repository's own metadata.
    """

    def setUp(self) -> None:
        # PyGithub deprecates `get_repo`'s `lazy` argument for a lazy `Github`,
        # whose laziness every object it returns would share; the worker mint
        # asks through the argument on purpose.
        self.enterContext(warnings.catch_warnings())
        warnings.filterwarnings(
            "ignore",
            message="Argument lazy is deprecated",
            category=DeprecationWarning,
        )
        self.wire = _RecordingWire()
        patch.object(
            Requester,
            "requestJsonAndCheck",
            autospec=True,
            side_effect=self.wire.answer,
        ).start()
        self.addCleanup(patch.stopall)
        self.parent = GitHubClient(token=_TOKEN, repo_slug=_REPO_SLUG)

    def test_parent_fetches_repository_eagerly(self) -> None:
        self.assertEqual(self.wire.sent_by(self.parent), [_REPO_PATH, "/user"])
        self.assertTrue(self.parent.repo.completed)
        self.assertEqual(self.parent.repo_slug, _CANONICAL_SLUG)
        self.assertEqual(len(self.wire.requests), 2)

    def test_mint_sends_nothing_on_its_own_requester(self) -> None:
        self.wire.requests.clear()

        worker = self.parent._for_worker_thread()

        self.assertEqual(self.wire.requests, [])
        self.assertEqual(
            (worker._token, worker._bot_login, worker._repo_slug),
            (_TOKEN, _BOT, _REPO_SLUG),
        )
        self.assertIsNot(worker._gh.requester, self.parent._gh.requester)
        self.assertIs(worker.repo.requester, worker._gh.requester)
        self.assertFalse(worker.repo.completed)

    def test_identity_completes_the_repository_once(self) -> None:
        # Built from the configured slug, an unfetched repository already
        # spells a `full_name`; the canonical one is only on the fetched body.
        worker = self.parent._for_worker_thread()

        for _ in range(2):
            self.assertEqual(worker.repo_slug, _CANONICAL_SLUG)
            self.assertTrue(worker.is_own_repository(_CANONICAL_SLUG))
        self.assertEqual(worker.repo.owner.login, _CANONICAL_OWNER)

        self.assertEqual(self.wire.sent_by(worker), [_REPO_PATH])

    def test_branch_lookup_completes_the_owner_once(self) -> None:
        worker = self.parent._for_worker_thread()

        for _ in range(2):
            self.assertIsNone(worker.find_open_pr(branch=_BRANCH))

        self.assertEqual(
            self.wire.sent_by(worker),
            [_REPO_PATH, _CANONICAL_PULLS_URL, _CANONICAL_PULLS_URL],
        )
        self.assertEqual(
            {
                query["head"] for _, url, query in self.wire.requests
                if url == _CANONICAL_PULLS_URL
            },
            {f"{_CANONICAL_OWNER}:{_BRANCH}"},
        )

    def test_number_lookups_fetch_at_the_call(self) -> None:
        # The repository's requester is the client's eager one, so a number
        # lookup still asks GitHub when it is called -- where its callers catch
        # what it raises -- and addresses the repository by URL alone.
        for operation, fetch, path in (
            ("issue", GitHubClient.get_issue, f"{_REPO_PATH}/issues/{_NUMBER}"),
            ("pull request", GitHubClient.get_pr, f"{_REPO_PATH}/pulls/{_NUMBER}"),
        ):
            with self.subTest(operation=operation):
                worker = self.parent._for_worker_thread()

                fetch(worker, _NUMBER)

                self.assertEqual(self.wire.sent_by(worker), [path])
                self.assertFalse(worker.repo.completed)

    def test_missing_label_still_answers_at_the_call(self) -> None:
        # The label cache tells a missing label by the 404 `get_label` raises.
        # A deferred lookup would hand back a label nobody checked, and adding
        # it to an issue posts its name -- which GitHub answers by creating it.
        worker = self.parent._for_worker_thread()

        self.assertIsNone(worker._cached_label(_LEGACY_LABEL))

        self.assertEqual(self.wire.sent_by(worker), [_MISSING_LABEL_PATH])
        self.assertFalse(worker.repo.completed)


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
        gh._closed_sweeps += _label_cache._ABSENT_LABEL_RETRY_SWEEPS
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
