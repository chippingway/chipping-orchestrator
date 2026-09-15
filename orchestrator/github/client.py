# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Authenticated repository client and canonical repository identity.

The concrete client resolves credentials, opens the PyGithub connection,
creates independent worker clients whose repository is fetched on its first
metadata read, and pairs stage-entry records across the audit and analytics
sinks. Repository identity comes from the API object, with the configured slug
as fallback and case-insensitive ownership checks.
"""
from __future__ import annotations

import logging

from github import Auth, Github
from github.Issue import Issue
from github.Label import Label
from github.Repository import Repository

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.checks import GitHubChecksMixin
from orchestrator.github.labels import GitHubLabelMixin
from orchestrator.github.reviews import GitHubReviewMixin
from orchestrator.observability.analytics.recording import events as _recording_events

log = logging.getLogger("orchestrator.github")


def _open_repository(gh: Github, slug: str, *, lazy: bool) -> Repository:
    """The client's repository, fetched now or on its first metadata read.

    `get_repo(..., lazy=True)` hands the repository a lazy copy of the
    requester, and every issue, pull request, label, and commit the repository
    returns would inherit it: each of those fetches would move from the call to
    a later attribute read, and a missing label would stop raising the 404
    `_cached_label` catches -- so adding it to an issue would post its name,
    which GitHub answers by creating the label. The repository is handed the
    client's own requester back, so only the repository itself waits.
    """
    if not lazy:
        return gh.get_repo(slug)
    repository = gh.get_repo(slug, lazy=True)
    repository._requester = gh.requester
    return repository


class GitHubClient(
    GitHubReviewMixin,
    GitHubLabelMixin,
    GitHubChecksMixin,
):
    """Authenticated repository client with a worker-safe clone seam.

    Review, label, and check collaborators own their respective operations.
    Repository identity is read from the same client that fetched a pull
    request, so a caller cannot prove ownership against a different spec.
    """

    def __init__(
        self,
        token: str | None = None,
        repo_slug: str | None = None,
        repo_spec: _config_models.RepoSpec | None = None,
        *,
        bot_login: str | None = None,
        lazy_repository: bool = False,
    ) -> None:
        slug = repo_slug or config.REPO if repo_spec is None else repo_spec.slug
        if token is None:
            token = config._resolve_github_token(slug)
        if not token:
            raise RuntimeError(
                "GITHUB_TOKEN is empty. Export it in the orchestrator's "
                "environment or write it to "
                f"~/.config/{slug}/token "
                "(override path with ORCHESTRATOR_TOKEN_FILE). "
                "Do NOT put it in REPO_ROOT/.env -- the implementer agent "
                "can read that file.",
            )
        self._gh = Github(auth=Auth.Token(token))
        self.repo: Repository = _open_repository(
            self._gh, slug, lazy=lazy_repository,
        )
        self._repo_slug = slug
        self._token = token
        self._bot_login = (
            self._gh.get_user().login
            if bot_login is None
            else bot_login
        )
        self.recorded_events: list[dict] = []
        self._label_cache: dict[str, Label] = {}
        self._absent_after_sweep: dict[str, int] = {}
        self._pollable_calls = 0
        self._closed_sweeps = 0

    @property
    def repo_slug(self) -> str:
        """The repository this client reads and writes, as GitHub spells it.

        Answered from the repository object rather than from the configured
        slug, so what comes back is the canonical name: the configuration is
        whatever an operator typed, and `ChippingWay/Orchestrator` resolves the
        same repository as `chippingway/orchestrator` while being a name no
        human would recognize in a refusal. The configured spelling is the
        fallback for a client whose repository could not be described.

        A worker client's repository is completed here first. Until it has
        been fetched, PyGithub spells `full_name` out of the URL it was built
        on -- the configured slug -- which would compare a renamed repository's
        own pull requests against its old name. On a completed repository the
        completion sends nothing.
        """
        repo = getattr(self, "repo", None)
        if isinstance(repo, Repository):
            repo.complete()
        return getattr(repo, "full_name", None) or self._repo_slug

    def is_own_repository(self, full_name: str | None) -> bool:
        """Whether `full_name` names the repository this client is for.

        Case-INSENSITIVELY, which is the whole reason this is asked here
        rather than spelled as an equality at each call site: owner and
        repository names are case-insensitive on GitHub, so a repository is
        `octo/Repo` in one answer and `Octo/repo` in a hand-typed setting, and
        compared exactly one of this repository's own publications reads as a
        fork's.

        A head naming no repository at all answers False. That is a pull
        request whose head repository is gone -- a deleted fork is the plain
        case -- and nothing about it says it was ever this repository's.
        """
        if not full_name:
            return False
        return full_name.casefold() == self.repo_slug.casefold()

    def _for_worker_thread(self) -> GitHubClient:
        """Build a fresh requester/repository pair for one worker thread.

        Every scheduled handler mints one, so the mint asks GitHub nothing:
        the token and bot login are the ones this client already resolved, and
        the repository waits for the first read of its own metadata. A handler
        that never reads it never fetches it.
        """
        return GitHubClient(
            token=self._token,
            repo_slug=self._repo_slug,
            bot_login=self._bot_login,
            lazy_repository=True,
        )

    def _emit_stage_enter(self, issue: Issue, stage: str) -> None:
        """Record matching audit and analytics stage-enter events."""
        issue_number = getattr(issue, "number", 0) or 0
        self.emit_event(
            "stage_enter",
            issue_number=issue_number,
            stage=stage,
        )
        _recording_events.record_stage_enter(
            repo=self._repo_slug,
            issue=issue_number,
            stage=stage,
        )
