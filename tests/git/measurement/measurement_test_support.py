# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real remote, a candidate worktree, and the transports pointed at them.

Every reading tested here runs against git rather than against a mocked answer
from it, because the things being pinned down are git's own: what `--numstat`
reports for a path it calls binary, what a moved file looks like with rename
detection off, which bytes of a path arrive unquoted, and which commits a
three-dot range between two frozen ids resolves. A fake would answer whatever
the test expected, which is the one answer that proves nothing here.

The candidate lives in a linked worktree of the clone, the way an issue's
checkout really does, so the object store a reading takes is the store the
agent could write into -- which is what makes the remote-authoritative base
read worth testing at all.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport, ref_transport

GIT_COMMAND = "git"
QUIET_FLAG = "--quiet"
MESSAGE_FLAG = "-m"
PUSH_COMMAND = "push"
BASE_BRANCH = "main"
ORIGIN_REMOTE = "origin"
REPO_SLUG = "acme/widget"
CANDIDATE_BRANCH = "orchestrator/acme__widget/issue-1402"
AUTHOR_NAME = "Dev"
AUTHOR_EMAIL = "dev@example.com"

# A file the BASE branch carries, with lines to lose. What a rename has to
# move for the diff to be a rename at all: a file first written on the
# candidate's own branch is an addition either way, and a test that moved one
# would pass with rename detection on.
BASE_FILE = "legacy.py"
BASE_FILE_TEXT = "one\ntwo\nthree\n"
BASE_FILE_LINES = 3

# The other file the BASE branch carries. A reading that has to change one
# base-carried path and leave another alone -- a mode set here, a rename
# there -- needs two of them.
SEED_FILE = "README.md"
SEED_TEXT = "hello\n"

AUTHOR_ENV = MappingProxyType({
    "GIT_AUTHOR_NAME": AUTHOR_NAME,
    "GIT_AUTHOR_EMAIL": AUTHOR_EMAIL,
    "GIT_COMMITTER_NAME": AUTHOR_NAME,
    "GIT_COMMITTER_EMAIL": AUTHOR_EMAIL,
})

# A well-formed object id no repository built here holds. Full-length on
# purpose: git resolves one to itself without ever consulting the store, which
# is exactly the reading a candidate recorded on another host produces.
ABSENT_SHA = "0123456789012345678901234567890123456789"


def run_git(
    *args: str, cwd: Path, env_extra: Mapping[str, str] | None = None,
) -> str:
    """Run one git command in `cwd`, failing the test if git does."""
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


def head_of(checkout: Path) -> str:
    """The commit a checkout is on."""
    return run_git("rev-parse", "HEAD", cwd=checkout).strip()


def commit_all(checkout: Path, message: str) -> str:
    """Commit everything in a checkout under a fixed identity, and return it.

    The identity is passed per invocation rather than configured: a clone made
    here inherits nothing, and a commit with no identity fails outright.
    """
    run_git("add", "-A", cwd=checkout)
    run_git(
        "commit", QUIET_FLAG, MESSAGE_FLAG, message,
        cwd=checkout, env_extra=AUTHOR_ENV,
    )
    return head_of(checkout)


def point_local_base_at(repo, sha: str) -> None:
    """Repoint `refs/remotes/<remote>/<base>` inside the shared store.

    What an agent with a writable worktree can do to the ref that merely NAMES
    the base, and the reason a measurement asks the remote instead.
    """
    run_git(
        "update-ref", f"refs/remotes/{ORIGIN_REMOTE}/{BASE_BRANCH}", sha,
        cwd=repo.clone,
    )


class _LocalTransport:
    """The two token-bearing reads, redirected at a file:// remote.

    Both keep the signatures the owners call them by, since they are installed
    on the owner that defines them; all that changes is that the URL is a path
    this test built rather than a host a token opens. The tip read is a real
    `ls-remote` against the bare repository, which is what makes "the remote
    decides the base, not the local ref" a claim these tests can check.
    """

    def fetch(self, spec, branch):
        """Fetch one branch into the clone, reporting failure as git does."""
        return subprocess.run(
            [GIT_COMMAND, "fetch", QUIET_FLAG, spec.remote_name, branch],
            cwd=str(spec.target_root),
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            check=False,
        )

    def read(self, spec, worktree, branch):
        """What the remote says that branch is at, or `""` when it has none.

        Handed back in the record the owner answers with, since a failure this
        transport never has is exactly the case the tests arrange for
        themselves.
        """
        listed = run_git(
            "ls-remote", spec.remote_name, f"refs/heads/{branch}",
            cwd=spec.target_root,
        )
        first_line = (listed or "").split("\n")[0].strip()
        return ref_transport._RefRead(
            sha=first_line.split()[0] if first_line else "",
        )


class _WorldBuilder:
    """The construction of one measurement world, kept off the world itself."""

    def __init__(self, repo) -> None:
        self._repo = repo

    def build(self, test_case, *, patched_transport: bool) -> None:
        """Raise the remote, the clone, the checkout, and the transports."""
        self._initialize_remote()
        self._seed_initial_commit()
        self._add_candidate_worktree()
        if patched_transport:
            self._patch_transports(test_case)

    def _initialize_remote(self) -> None:
        repo = self._repo
        subprocess.run(
            [GIT_COMMAND, "init", "--bare", "-b", BASE_BRANCH, str(repo.remote)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [GIT_COMMAND, "clone", str(repo.remote), str(repo.clone)],
            check=True,
            capture_output=True,
        )

    def _seed_initial_commit(self) -> None:
        repo = self._repo
        (repo.clone / SEED_FILE).write_text(SEED_TEXT)
        (repo.clone / BASE_FILE).write_text(BASE_FILE_TEXT)
        commit_all(repo.clone, "initial")
        run_git(PUSH_COMMAND, ORIGIN_REMOTE, BASE_BRANCH, cwd=repo.clone)

    def _add_candidate_worktree(self) -> None:
        repo = self._repo
        repo.worktree.parent.mkdir(parents=True, exist_ok=True)
        run_git(
            "worktree", "add", QUIET_FLAG, "-b", CANDIDATE_BRANCH,
            str(repo.worktree), BASE_BRANCH, cwd=repo.clone,
        )

    def _patch_transports(self, test_case) -> None:
        transport = _LocalTransport()
        transport_patches = (
            patch.object(
                branch_transport, "_authed_target_fetch",
                side_effect=transport.fetch,
            ),
            patch.object(
                branch_transport, "_remote_branch_read",
                side_effect=transport.read,
            ),
        )
        for transport_patch in transport_patches:
            transport_patch.start()
            test_case.addCleanup(transport_patch.stop)


class CandidateRepo:
    """A seeded bare remote, a clone of it, and the candidate's own checkout.

    `prepare` leaves the world a measurement meets: `worktree` is the issue's
    linked checkout branched off the remote base, with nothing committed on it
    yet, so each test commits the candidate it wants measured.
    """

    def __init__(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="orch-measure-real-"))
        self.remote = self._tmpdir / "remote.git"
        self.clone = self._tmpdir / "work"
        self.worktree = self._tmpdir / "worktrees" / "issue-1402"
        self._advances = 0
        self.spec = _config_models.RepoSpec(
            slug=REPO_SLUG,
            target_root=self.clone,
            base_branch=BASE_BRANCH,
            remote_name=ORIGIN_REMOTE,
        )

    def prepare(self, test_case, *, patched_transport: bool = True) -> None:
        """Build the world and hand its teardown to the test case.

        `patched_transport=False` leaves the token-bearing reads real, for the
        one thing a redirected transport cannot answer: what the owners do with
        the output of a call that really ran.
        """
        test_case.addCleanup(
            shutil.rmtree, str(self._tmpdir), ignore_errors=True,
        )
        _WorldBuilder(self).build(
            test_case, patched_transport=patched_transport,
        )

    def base(self) -> str:
        """The commit the remote base branch is at, as this clone knows it."""
        return head_of(self.clone)

    def commit(
        self,
        written: Mapping[str, str | bytes],
        message: str = "work",
    ) -> str:
        """Write paths into the candidate checkout, commit, and return its SHA.

        Bytes are written as bytes so a test can commit content git has to
        call binary rather than one that merely looks odd.
        """
        for relative_path, payload in written.items():
            written_path = self.worktree / relative_path
            written_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(payload, bytes):
                written_path.write_bytes(payload)
            else:
                written_path.write_text(payload)
        return commit_all(self.worktree, message)

    def move(self, from_path: str, to_path: str) -> str:
        """Rename a committed path in the candidate checkout, and commit it."""
        (self.worktree / to_path).parent.mkdir(parents=True, exist_ok=True)
        run_git("mv", from_path, to_path, cwd=self.worktree)
        return commit_all(self.worktree, "move")

    def advance_base_from_elsewhere(self, text: str = "base moved on\n") -> str:
        """Publish a further commit on the remote base branch, from off-host.

        Committed in a throwaway clone rather than in this one, which is how
        the base really advances under a candidate: somebody else's merge
        lands, and this clone learns nothing about it until it fetches. That
        is what leaves the remote naming a commit the measurement's own store
        does not yet hold.
        """
        self._advances += 1
        elsewhere = self._tmpdir / f"elsewhere-{self._advances}"
        subprocess.run(
            [GIT_COMMAND, "clone", str(self.remote), str(elsewhere)],
            check=True,
            capture_output=True,
        )
        (elsewhere / f"base-{self._advances}.txt").write_text(text)
        advanced = commit_all(elsewhere, "advance the base")
        run_git(PUSH_COMMAND, ORIGIN_REMOTE, BASE_BRANCH, cwd=elsewhere)
        return advanced

    def take_in_advanced_base(self) -> None:
        """Fetch the advanced base here, and take it into the candidate branch.

        What a developer does when the base moves under a long round, and both
        halves matter to a measurement. The fetch moves
        `refs/remotes/<remote>/<base>`, so a reading that consulted that ref
        instead of a frozen id would move with it; the merge puts the new base
        commits into the candidate's own history, which is what makes the two
        readings differ at all -- a three-dot range from the frozen base then
        covers commits the range from the current tip does not.
        """
        run_git("fetch", QUIET_FLAG, ORIGIN_REMOTE, BASE_BRANCH, cwd=self.clone)
        run_git(
            "merge", QUIET_FLAG, "--no-edit",
            f"{ORIGIN_REMOTE}/{BASE_BRANCH}",
            cwd=self.worktree, env_extra=AUTHOR_ENV,
        )
