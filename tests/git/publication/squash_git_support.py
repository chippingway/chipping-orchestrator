# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real bare remote and topic branch the squash owners run against.

The rewrite reaches git through hardened argv and env envelopes that a
subprocess double would let pass unchecked, so these fixtures build an
actual repository and stub only the network hop -- the authenticated push.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from orchestrator import config
from orchestrator.git import branch_transport
from orchestrator.git.publication import rewrite as _rewrite, squash
from tests.git.publication.squash_gate_support import (
    SQUASH_PR_NUMBER,
    PublicationSeed,
    SquashRun,
    _driven_reads,
    _InterruptsTheRewrite,
    _squash_gate,
)
from tests.support.fakes import make_issue

BASE_BRANCH_NAME = "main"
GIT_AUTHOR_NAME = "GIT_AUTHOR_NAME"
GIT_AUTHOR_EMAIL = "GIT_AUTHOR_EMAIL"
GIT_COMMITTER_NAME = "GIT_COMMITTER_NAME"
GIT_COMMITTER_EMAIL = "GIT_COMMITTER_EMAIL"
DEV_NAME = "Dev"
DEV_EMAIL = "dev@example.com"
GIT_ADD = "add"
GIT_COMMIT = "commit"
GIT_MESSAGE_FLAG = "-m"
REMOTE_NAME = "origin"
GIT_LOG = "log"
SUBJECT_FORMAT = "--pretty=%s"
PUSH_BRANCH_HELPER = "_push_branch"
GIT_RESET = "reset"
HARD_RESET = "--hard"
REMOTE_BASE_REF = "origin/main"
GIT_REV_PARSE = "rev-parse"
HEAD_REF = "HEAD"

# The seam `_InterruptsTheRewrite` is hung on, which is the step between the
# two entry readings: the first answered while the branch was intact, and
# the second is taken once this has run.
_SQUASH_COMMIT_HELPER = "_create_squash_commit"


def run_git(*args: str, cwd: Path, env_extra: dict | None = None) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if env_extra:
        env.update(env_extra)
    completed_process = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return completed_process.stdout


def author_env() -> dict[str, str]:
    return {
        GIT_AUTHOR_NAME: DEV_NAME,
        GIT_AUTHOR_EMAIL: DEV_EMAIL,
        GIT_COMMITTER_NAME: DEV_NAME,
        GIT_COMMITTER_EMAIL: DEV_EMAIL,
    }


def commit_files(
    worktree: Path,
    messages: tuple[str, ...],
    prefix: str,
) -> None:
    for commit_index, message in enumerate(messages, start=1):
        (worktree / f"{prefix}{commit_index}.txt").write_text(
            f"{commit_index}\n",
        )
        run_git(GIT_ADD, ".", cwd=worktree)
        run_git(
            GIT_COMMIT,
            GIT_MESSAGE_FLAG,
            message,
            cwd=worktree,
            env_extra=author_env(),
        )


class _SquashRepositoryFixtureMixin:
    def setUp(self) -> None:
        self.tmpdir = Path(
            self.enterContext(
                tempfile.TemporaryDirectory(
                    prefix="orch-squash-test-",
                    ignore_cleanup_errors=True,
                ),
            ),
        )
        self._init_remote()
        self._seed_base()
        self.branch = "orchestrator/chippingway__orchestrator/issue-9"
        self._seed_topic()

    def _init_remote(self) -> None:
        self.remote = self.tmpdir / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", "-b", BASE_BRANCH_NAME, str(self.remote)],
            check=True,
            capture_output=True,
        )
        self.work = self.tmpdir / "work"
        subprocess.run(
            ["git", "clone", str(self.remote), str(self.work)],
            check=True,
            capture_output=True,
        )

    def _seed_base(self) -> None:
        (self.work / "README.md").write_text("hello\n")
        run_git(GIT_ADD, ".", cwd=self.work)
        run_git(
            GIT_COMMIT,
            GIT_MESSAGE_FLAG,
            "initial",
            cwd=self.work,
            env_extra=author_env(),
        )
        run_git("push", REMOTE_NAME, BASE_BRANCH_NAME, cwd=self.work)

    def _seed_topic(self) -> None:
        run_git("checkout", "-b", self.branch, cwd=self.work)
        commit_files(
            self.work,
            ("fix: typo", "add foo", "add bar"),
            "f",
        )
        run_git("push", REMOTE_NAME, self.branch, cwd=self.work)
        run_git("fetch", REMOTE_NAME, cwd=self.work)


class _SquashReadsMixin:
    """What a case reads off the repository the squash runs against.

    Kept apart from the scenario builders below because the two answer
    different questions: these say where the branch stands, and those put it
    somewhere. The size gate reads the base through here too -- a real fixture
    answers the tree and the candidate for itself, and only the remote-side
    base freeze has to be stood in for.
    """

    def _head_sha(self) -> str:
        return run_git(GIT_REV_PARSE, HEAD_REF, cwd=self.work).strip()

    def _base_sha(self) -> str:
        """The commit the remote says the base branch is standing at."""
        return run_git(GIT_REV_PARSE, REMOTE_BASE_REF, cwd=self.work).strip()

    def _commits_over(self, marker: int) -> None:
        """Commit over this checkout, the way a stray agent run would."""
        (self.work / f"stray{marker}.txt").write_text(f"stray {marker}\n")
        run_git(GIT_ADD, ".", cwd=self.work)
        run_git(
            GIT_COMMIT,
            GIT_MESSAGE_FLAG,
            "stray: not the squash",
            cwd=self.work,
            env_extra=author_env(),
        )

    def _commits_on_branch(self) -> list[str]:
        """Subjects of all commits between origin/main and HEAD, oldest first."""
        out = run_git(
            GIT_LOG,
            "--reverse",
            SUBJECT_FORMAT,
            "origin/main..HEAD",
            cwd=self.work,
        )
        return [line for line in out.splitlines() if line.strip()]


class _SquashScenarioMixin:
    def _make_issue(self, title: str = "test issue", number: int = 9):
        return make_issue(number, title=title)

    def _rebuild_topic(
        self,
        messages: tuple[str, ...],
        prefix: str,
    ) -> None:
        run_git(GIT_RESET, HARD_RESET, REMOTE_BASE_REF, cwd=self.work)
        commit_files(self.work, messages, prefix)

    def _rebuild_single_commit(self) -> None:
        run_git(GIT_RESET, HARD_RESET, REMOTE_BASE_REF, cwd=self.work)
        (self.work / "only.txt").write_text("only\n")
        run_git(GIT_ADD, ".", cwd=self.work)
        run_git(
            GIT_COMMIT,
            GIT_MESSAGE_FLAG,
            "feat: only one",
            cwd=self.work,
            env_extra=author_env(),
        )

    def _seed_inferred_prefix_history(self) -> None:
        run_git("checkout", BASE_BRANCH_NAME, cwd=self.work)
        commit_files(
            self.work,
            (
                "event: launch the site",
                "event: add a gala",
                "event: add a meetup",
            ),
            "e",
        )
        run_git("push", REMOTE_NAME, BASE_BRANCH_NAME, cwd=self.work)
        run_git("checkout", self.branch, cwd=self.work)
        self._rebuild_topic(
            ("tweak the layout", "polish the copy"),
            "t",
        )

    def _squash(
        self,
        *,
        push_result: bool = True,
        publication: PublicationSeed | None = None,
        head_reads=None,
        proved_heads=None,
        **config_overrides,
    ) -> SquashRun:
        # A case about the window the push itself opens hands in a callable:
        # the worktree is writable for the whole of the request, so what it
        # does to the checkout has to happen inside the seam rather than
        # before or after it.
        push_mock = (
            mock.MagicMock(side_effect=push_result) if callable(push_result)
            else mock.MagicMock(return_value=push_result)
        )
        self.enterContext(
            mock.patch.object(branch_transport, PUSH_BRANCH_HELPER, push_mock),
        )
        # A case about the window between the squash and the gate's own proof
        # of the checkout drives the head reads itself; every other one takes
        # the repository's real answer.
        _driven_reads(self, head_reads=head_reads, proved_heads=proved_heads)
        for setting, setting_value in config_overrides.items():
            self.enterContext(
                mock.patch.object(config, setting, setting_value),
            )
        raw_result = squash._squash_and_force_push(
            _squash_gate(self, publication or PublicationSeed()),
            self.branch,
        )
        return SquashRun(outcome=raw_result, push_mock=push_mock)

    def _interrupted(self, squashed, **settlement):
        """One squash whose publication or worktree moves as it commits.

        The window only, so the ceiling and the gate stay the case's own:
        `_squashes` is what each fixture binds those with, and what a case
        about this window varies is what arrives in it.
        """
        with mock.patch.object(
            _rewrite,
            _SQUASH_COMMIT_HELPER,
            _InterruptsTheRewrite(
                squashed.gh.get_pr(SQUASH_PR_NUMBER), **settlement,
            ),
        ):
            return self._squashes(squashed)


class SquashGitFixtureMixin(
    _SquashRepositoryFixtureMixin,
    _SquashReadsMixin,
    _SquashScenarioMixin,
):
    """Compose repository setup, its reads, and the squash scenarios."""
