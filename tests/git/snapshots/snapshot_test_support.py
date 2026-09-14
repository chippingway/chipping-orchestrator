# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real remote, a real clone, and real commits for the snapshot transport.

These are not mocked. What the snapshot operations promise -- that a ref is
created only where none exists, that an occupied one is never overwritten, that
a created ref can be FETCHED back and resolved locally, and that deleting an
absent ref succeeds -- are properties of git and of the refspecs and leases the
transport builds, and a recorder asserting on argv would pass for a command git
rejects. So the tests drive `git` itself against a bare repository on disk.

What is replaced is exactly one thing: the askpass session, whose auth URL
points at GitHub. Pointing it at the local bare repository leaves every other
part of the envelope -- the hardened argv prefix, the detached config, the
pre-flight transport-config refusal, and the per-target-root lock -- running as
it does in production.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import models as _config_models
from tests.git.auth_session_test_support import _SESSIONS

GIT = "git"

QUIET = "-q"

BASE_BRANCH = "main"

SLUG = "owner/repo"

# The second repository a shared `target_root` carries. A different slug is
# what keeps its snapshots off the first one's local refs.
OTHER_SLUG = "owner/private"

# Which of the two a pair takes, keyed on whether it shares a clone.
_CONFIGURED_SLUGS = (SLUG, OTHER_SLUG)

# A remote path nothing was ever cloned from: what an unreachable remote looks
# like to `ls-remote`, which is the read every snapshot decision starts with.
UNREACHABLE = "unreachable.git"

PLUMBING_LOG = "orchestrator.git_plumbing"


@dataclass(frozen=True)
class RealRemote:
    """One disposable repository pair and the two commits in it."""

    spec: _config_models.RepoSpec
    clone: Path
    remote: Path
    sha: str
    other_sha: str

    def remote_ref_sha(self, ref: str) -> str:
        """What the bare repository itself says the ref is at, or ""."""
        listed = _git(
            "ls-remote", str(self.remote), ref, cwd=self.clone,
        ).stdout
        for output_line in listed.splitlines():
            parts = output_line.split()
            if len(parts) >= 2 and parts[1] == ref:
                return parts[0]
        return ""

    def plant_ref(self, ref: str, sha: str) -> None:
        """Put a ref on the remote without going through the transport."""
        _git("push", str(self.remote), f"{sha}:{ref}", cwd=self.clone)

    def drop_remote_ref(self, ref: str) -> None:
        """Take a ref off the remote without going through the transport."""
        _git("push", str(self.remote), f":{ref}", cwd=self.clone)

    def point_local_ref(self, ref: str, sha: str) -> None:
        """Point a ref in the shared clone at another commit.

        What anything holding this checkout can do to a ref in it, the agent
        running in one of its worktrees included -- which is why a copy of a
        snapshot is read for the commit it carries rather than for existing.
        """
        _git("update-ref", ref, sha, cwd=self.clone)

    def lock_ref(self, ref: str) -> None:
        """Leave a local ref where nothing may delete it.

        The lock file a crashed git leaves behind, which is how a ref store
        several worktrees of one clone share really refuses to give a ref up:
        the delete fails and every read still answers, which is the pair a
        teardown that trusts a failed read cannot tell apart from success.
        """
        held = self.clone / ".git" / f"{ref}.lock"
        held.parent.mkdir(parents=True, exist_ok=True)
        held.touch()


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run one plain git command, raising with its stderr when it fails."""
    completed = subprocess.run(
        [GIT, *args], cwd=str(cwd), capture_output=True, text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"git {args} failed: {completed.stderr}")
    return completed


@contextlib.contextmanager
def real_remote(
    *, reachable: bool = True, clone: Path | None = None, slug: str | None = None,
):
    """Yield a bare remote, a clone carrying two commits, and its spec.

    `clone` shares an existing checkout's `target_root`, which is the shape a
    single local clone with a public and a private remote produces -- and the
    one where two repositories' snapshots meet in one ref store. `slug` names
    the repository, for the tests about what a long one does to a ref built
    from it.
    """
    with tempfile.TemporaryDirectory(prefix="orch-snapshot-test-") as scratch:
        prepared = _prepared_pair(Path(scratch), clone, slug)
        reached = prepared.remote if reachable else Path(scratch) / UNREACHABLE
        with _SESSIONS.registered(prepared.spec.slug, str(reached)):
            yield prepared


def _prepared_pair(
    root: Path, shared: Path | None = None, slug: str | None = None,
) -> RealRemote:
    """Build the bare repository and the clone that has pushed to it."""
    remote = root / "remote.git"
    _git("init", "--bare", QUIET, str(remote), cwd=root)
    clone = shared or _fresh_clone(root)
    first, second = _commit(clone, f"first in {root.name}"), _commit(
        clone, f"second in {root.name}",
    )
    _git("push", QUIET, str(remote), f"HEAD:refs/heads/{BASE_BRANCH}", cwd=clone)
    return RealRemote(
        spec=_config_models.RepoSpec(
            # A pair sharing an existing clone is the SECOND repository of a
            # shared `target_root`, so it takes the other slug: the whole
            # point of that shape is two repositories in one ref store.
            slug=slug or _CONFIGURED_SLUGS[shared is not None],
            target_root=clone,
            base_branch=BASE_BRANCH,
        ),
        clone=clone,
        remote=remote,
        sha=first,
        other_sha=second,
    )


def _fresh_clone(root: Path) -> Path:
    """Initialize the working clone this pair's commits are made in."""
    clone = root / "clone"
    clone.mkdir()
    _git("init", QUIET, "-b", BASE_BRANCH, str(clone), cwd=root)
    _git("config", "user.email", "t@example.invalid", cwd=clone)
    _git("config", "user.name", "t", cwd=clone)
    return clone


def _commit(clone: Path, written: str) -> str:
    """Add one commit to the clone and return its object id."""
    (clone / "work.txt").write_text(f"{written}\n")
    _git("add", "work.txt", cwd=clone)
    _git("commit", QUIET, "-m", written, cwd=clone)
    return _git("rev-parse", "HEAD", cwd=clone).stdout.strip()
