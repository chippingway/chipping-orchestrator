# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real bare remote plus the worlds and drivers the creation tests run in.

`_RealGitWorktreeRepo` is the shared floor: a bare remote, a clone of it as
`target_root`, and the token-bearing fetch redirected at that path.
`_AmendedPlanRepo` builds the one shape the plan handoff faces on top of it --
a per-issue checkout on the plan this orchestrator published, and a different
head on the remote, committed from a second clone the way a reviewer's own edit
to a plan PR arrives.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import branch_transport, locks
from orchestrator.git.worktrees import creation, paths
from tests.git.concurrency_test_support import _start_and_join

GIT_COMMAND = "git"
QUIET_FLAG = "--quiet"
MESSAGE_FLAG = "-m"
BASE_BRANCH = "main"
ORIGIN_REMOTE = "origin"
GIT_PUSH = "push"
REAL_GIT_TIMEOUT_SECONDS = 30.0
PLAN_PATH = "plans/the-plan.md"
PUBLISHED_PLAN_TEXT = "# the plan, as this orchestrator published it\n"
AMENDED_PLAN_TEXT = "# the plan, as its reviewers left it\n"
REVIEWER_CLONE = "reviewer"
MERGED_CLONE = "merged"
MERGE_MESSAGE = "merge the plan"
AUTHOR_NAME = "Dev"
AUTHOR_EMAIL = "dev@example.com"


def _run_git(
    *args: str,
    cwd: Path,
    env_extra: dict | None = None,
) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if env_extra:
        env.update(env_extra)
    git_result = subprocess.run(
        [GIT_COMMAND, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return git_result.stdout


def _author_env() -> dict:
    """The identity every commit these worlds are built from is made under.

    Passed per invocation rather than configured in each repository: a clone
    made here inherits nothing, and a commit with no identity fails outright.
    """
    return {
        "GIT_AUTHOR_NAME": AUTHOR_NAME,
        "GIT_AUTHOR_EMAIL": AUTHOR_EMAIL,
        "GIT_COMMITTER_NAME": AUTHOR_NAME,
        "GIT_COMMITTER_EMAIL": AUTHOR_EMAIL,
    }


class _LocalTransport:
    """The two token-bearing reads, redirected at a file:// remote.

    Both keep the signatures the creators call them by, since they are
    installed on the owner that defines them: all that changes is that the URL
    is a path this test built rather than a host a token opens. Instance
    methods rather than free functions so the pair travels together, and one
    instance is enough -- neither of them holds anything.
    """

    def fetch(self, spec, branch):
        """Fetch one branch into the clone, reporting failure as git does."""
        return subprocess.run(
            [GIT_COMMAND, "fetch", "--quiet", spec.remote_name, branch],
            cwd=str(spec.target_root),
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            check=False,
        )

    def tip(self, spec, worktree, branch):
        """What the remote says that branch is at, or `""` when it has none.

        The third answer the real read gives -- `None` for a read that could
        not be taken -- is left to the test that wants one to patch in.
        """
        listed = _run_git(
            "ls-remote", ORIGIN_REMOTE, f"refs/heads/{branch}",
            cwd=spec.target_root,
        )
        first_line = (listed or "").split("\n")[0].strip()
        return first_line.split()[0] if first_line else ""


class _RealGitWorktreeRepo:
    """A seeded clone of a real bare remote for the creators to work in."""

    def __init__(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="orch-ensure-real-"))
        self._remote = self._tmpdir / "remote.git"
        self._work = self._tmpdir / "work"
        self.spec = config.RepoSpec(
            slug="acme/widget",
            target_root=self._work,
            base_branch=BASE_BRANCH,
            remote_name=ORIGIN_REMOTE,
        )

    def prepare(self, test_case) -> None:
        locks._TARGET_ROOT_LOCKS.clear()
        test_case.addCleanup(shutil.rmtree, str(self._tmpdir), ignore_errors=True)
        self._initialize_remote()
        self._seed_initial_commit()
        self._patch_runtime(test_case)

    def head_of(self, checkout: Path) -> str:
        return _run_git("rev-parse", "HEAD", cwd=checkout).strip()

    def _initialize_remote(self) -> None:
        subprocess.run(
            [GIT_COMMAND, "init", "--bare", "-b", BASE_BRANCH, str(self._remote)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [GIT_COMMAND, "clone", str(self._remote), str(self._work)],
            check=True,
            capture_output=True,
        )

    def _seed_initial_commit(self) -> None:
        (self._work / "README.md").write_text("hello\n")
        _run_git("add", ".", cwd=self._work)
        _run_git(
            "commit",
            MESSAGE_FLAG,
            "initial",
            cwd=self._work,
            env_extra=_author_env(),
        )
        _run_git(GIT_PUSH, ORIGIN_REMOTE, BASE_BRANCH, cwd=self._work)

    def _commit_plan(self, checkout: Path, text: str) -> str:
        """Write the plan in `checkout`, commit it, and return the new SHA."""
        plan = checkout / PLAN_PATH
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(text)
        _run_git("add", "-A", cwd=checkout)
        _run_git(
            "commit", QUIET_FLAG, MESSAGE_FLAG, PLAN_PATH,
            cwd=checkout,
            env_extra=_author_env(),
        )
        return self.head_of(checkout)

    def _patch_runtime(self, test_case) -> None:
        worktrees_patch = patch.object(
            config,
            "WORKTREES_DIR",
            self._tmpdir / "worktrees",
        )
        fetch_patch = patch.object(
            branch_transport,
            "_authed_target_fetch",
            side_effect=_LocalTransport().fetch,
        )
        tip_patch = patch.object(
            branch_transport,
            "_remote_branch_tip",
            side_effect=_LocalTransport().tip,
        )
        for runtime_patch in (worktrees_patch, fetch_patch, tip_patch):
            runtime_patch.start()
            test_case.addCleanup(runtime_patch.stop)


class _AmendedPlanRepo(_RealGitWorktreeRepo):
    """A published plan in the issue's checkout, an amended one on the remote.

    `plant` leaves the world the handoff meets: the per-issue worktree sits on
    the commit the orchestrator pushed, and the branch's remote head is a later
    commit this clone has never fetched -- which is what a human correcting the
    Markdown on the plan PR, or merging the base into it, really leaves behind.
    """

    def plant(self, test_case, issue_number: int, branch: str) -> None:
        self.prepare(test_case)
        self.worktree = paths._worktree_path(self.spec, issue_number)
        self.worktree.parent.mkdir(parents=True, exist_ok=True)
        _run_git(
            "worktree", "add", QUIET_FLAG, "-b", branch,
            str(self.worktree), BASE_BRANCH, cwd=self._work,
        )
        self.published = self._commit_plan(self.worktree, PUBLISHED_PLAN_TEXT)
        _run_git(
            GIT_PUSH, QUIET_FLAG, ORIGIN_REMOTE, branch, cwd=self.worktree,
        )
        self.amended = self._amend_from_a_second_clone(branch)

    def delete_on_remote(self, branch: str) -> None:
        """Drop the branch from the remote, the way a merged PR's deletion does.

        The local ref and its checkout stay exactly where they were, which is
        the shape the handoff meets: a head it cannot fetch, and nothing left on
        that branch for anything to overwrite.
        """
        _run_git(
            GIT_PUSH, QUIET_FLAG, ORIGIN_REMOTE, "--delete", branch,
            cwd=self._work,
        )

    def merge_into_base(self, branch: str) -> str:
        """Land the branch on the remote's base, and say where that put it.

        From the reviewers' own clone for the same reason their amendment is
        made there: what THIS clone's `<remote>/<base>` names has to stay the
        base as it stood before the merge, which is what a host that has not
        fetched since really holds -- and on that base the plan does not exist.
        """
        reviewer = self._tmpdir / REVIEWER_CLONE
        _run_git("checkout", QUIET_FLAG, BASE_BRANCH, cwd=reviewer)
        _run_git(
            "merge", QUIET_FLAG, "--no-ff", MESSAGE_FLAG, MERGE_MESSAGE, branch,
            cwd=reviewer, env_extra=_author_env(),
        )
        _run_git(GIT_PUSH, QUIET_FLAG, ORIGIN_REMOTE, BASE_BRANCH, cwd=reviewer)
        return self.head_of(reviewer)

    def delete_local_branch(self, branch: str) -> None:
        """Drop the local ref, leaving only what was fetched beside it."""
        _run_git("branch", "-D", branch, cwd=self._work)

    def remove_worktree(self) -> None:
        """Drop the checkout, the way a host restart or a cleanup would."""
        _run_git(
            "worktree", "remove", "--force", str(self.worktree),
            cwd=self._work,
        )

    def branch_tip(self, branch: str) -> str:
        return _run_git(
            "rev-parse", f"refs/heads/{branch}", cwd=self._work,
        ).strip()

    def _amend_from_a_second_clone(self, branch: str) -> str:
        """Put a later commit on the branch's remote head, from elsewhere.

        A second clone rather than this one, so the amendment exists only where
        the humans made it: on the remote. Committing it here would leave the
        local branch already carrying it and there would be nothing to fetch.
        """
        reviewer = self._tmpdir / REVIEWER_CLONE
        _run_git(
            "clone", QUIET_FLAG, "--branch", branch,
            str(self._remote), str(reviewer), cwd=self._tmpdir,
        )
        amended = self._commit_plan(reviewer, AMENDED_PLAN_TEXT)
        _run_git(GIT_PUSH, QUIET_FLAG, ORIGIN_REMOTE, branch, cwd=reviewer)
        return amended


class _MergedPlanRepo(_RealGitWorktreeRepo):
    """A plan that merged, whose branch the remote no longer has.

    The lifecycle a fresh host meets: the issue still records the PR, so every
    tick routes to the PR-aware creator, and neither the local branch nor the
    remote one exists any more. Both the branch and its merge are made in a
    second clone, so the clone the creators run in has never seen that ref.
    """

    def base_tip(self) -> str:
        """What the clone's remote-tracking base ref points at right now."""
        return _run_git(
            "rev-parse", f"refs/remotes/{ORIGIN_REMOTE}/{BASE_BRANCH}",
            cwd=self._work,
        ).strip()

    def plant(self, test_case, branch: str, *, deleted: bool = True) -> None:
        self.prepare(test_case)
        scratch = self._tmpdir / MERGED_CLONE
        _run_git(
            "clone", QUIET_FLAG, str(self._remote), str(scratch),
            cwd=self._tmpdir,
        )
        _run_git("checkout", QUIET_FLAG, "-b", branch, cwd=scratch)
        self._commit_plan(scratch, PUBLISHED_PLAN_TEXT)
        _run_git(GIT_PUSH, QUIET_FLAG, ORIGIN_REMOTE, branch, cwd=scratch)
        _run_git("checkout", QUIET_FLAG, BASE_BRANCH, cwd=scratch)
        _run_git(
            "merge", QUIET_FLAG, "--no-ff", MESSAGE_FLAG, MERGE_MESSAGE, branch,
            cwd=scratch, env_extra=_author_env(),
        )
        _run_git(
            GIT_PUSH, QUIET_FLAG, ORIGIN_REMOTE, BASE_BRANCH, cwd=scratch,
        )
        if deleted:
            _run_git(
                GIT_PUSH, QUIET_FLAG, ORIGIN_REMOTE, "--delete", branch,
                cwd=scratch,
            )


class _EnsureRecorder:
    """Run `_ensure_worktree` per worker and keep each thread's outcome."""

    def __init__(self, spec: config.RepoSpec) -> None:
        self.outcomes: list[tuple[int, Path | None, BaseException | None]] = []
        self._spec = spec
        self._lock = threading.Lock()

    def __call__(self, issue_number: int) -> None:
        try:
            outcome = (
                issue_number,
                creation._ensure_worktree(self._spec, issue_number),
                None,
            )
        except BaseException as error:  # noqa: BLE001 - asserted by the test
            outcome = (issue_number, None, error)
        with self._lock:
            self.outcomes.append(outcome)

    def run_workers(self, test_case, issue_numbers) -> None:
        threads = [
            threading.Thread(target=self, args=(issue_number,))
            for issue_number in issue_numbers
        ]
        _start_and_join(threads, timeout=REAL_GIT_TIMEOUT_SECONDS)
        for thread in threads:
            test_case.assertFalse(
                thread.is_alive(),
                "worker timed out (possible lock contention)",
            )

    def assert_all_succeeded(self, test_case, issue_numbers) -> None:
        errors = [
            (issue_number, error)
            for issue_number, _worktree, error in self.outcomes
            if error is not None
        ]
        test_case.assertEqual(errors, [])
        test_case.assertEqual(
            tuple(sorted(number for number, _, _ in self.outcomes)),
            issue_numbers,
        )

    def assert_worktrees_exist(self, test_case) -> None:
        for issue_number, worktree, _error in self.outcomes:
            test_case.assertTrue(
                worktree is not None and worktree.exists(),
                f"worktree {worktree} missing for issue #{issue_number}",
            )
