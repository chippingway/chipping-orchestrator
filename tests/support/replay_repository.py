# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real repository whose branch is replayed onto a base that moved.

The one scenario a mocked reading cannot settle. Whether a rebase carried a
change a human already adjudicated is a question about BYTES -- the fork point
git resolves for each end, and the canonical digest of the contribution
between them -- and every double that stands in for either answers whatever a
case seeded rather than what the objects say.

So this builds the world instead: a base branch, a topic commit over it, a
base that advances, and a real `git rebase` onto the new tip. Two shapes come
out of it. The REPLAYED one is history-only -- the same work over a base that
moved -- and the AMENDED one is that same replay with a single byte written
into it, which is what a resolution somebody authored looks like to every
reader downstream.

Shared rather than owned by either caller, because the probe that reads the
fork points and the transfer that decides on them are tested from the two
packages those owners live in, and a second copy of this repository would let
one drift from the other.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

from orchestrator.config import models as _config_models

BASE_BRANCH = "main"
REMOTE_NAME = "origin"
TOPIC_BRANCH = "orchestrator/chippingway__orchestrator/issue-9"

# What the topic commit writes, and the single byte an authored change moves in
# it. One character, because the claim under test is that ANY covered byte
# takes the ordinary gate rather than riding somebody else's verdict.
TOPIC_FILE = "feature.txt"
TOPIC_CONTENT = "one\ntwo\nthree\n"
AMENDED_CONTENT = "one\ntwo\nthrees\n"

# What the base branch advances by. A file the topic never touches, so the
# replay is clean and the only thing that moves is which commit the
# contribution is read over.
BASE_FILE = "unrelated.txt"

# What a base nobody published carries, and the branch it is parked on. The
# ref an agent's checkout shares decides which commit a rebase replays onto
# and which one the fork point behind it comes back as, so a commit this side
# of the remote is all it takes to read a contribution over a base the base
# branch has never had.
FORGED_FILE = "unpublished.txt"

_FORGED_BRANCH = "forged-base"

# Who every object this fixture writes is authored and committed by. Handed to
# each command that writes one -- the commits, the amend, and the rebase --
# rather than left to the host, since a checkout with no git identity
# configured has none to inherit and git will not invent one.
_AUTHOR = MappingProxyType({
    "GIT_AUTHOR_NAME": "Dev",
    "GIT_AUTHOR_EMAIL": "dev@example.com",
    "GIT_COMMITTER_NAME": "Dev",
    "GIT_COMMITTER_EMAIL": "dev@example.com",
})

# The one command every named commit in this fixture is read back by, and the
# one every branch in it is moved onto.
_REV_PARSE = "rev-parse"
_CHECKOUT = "checkout"
_HEAD = "HEAD"


@dataclass(frozen=True)
class ReplayedBranch:
    """One replay, named by every commit a reader of it has to be able to ask.

    `accepted` is the commit a verdict was reached on and `accepted_base` the
    fork point it was read over; `replayed` is what the rebase produced and
    `replayed_base` the fork point it landed on. The two bases differ, which
    is the whole of what a rebase does to a contribution.

    `accepted` is also what the remote's own copy of the branch is left
    standing on, since the replay is never pushed here: that is the pull
    request a recovery would find, and the head it would lease against.
    """

    worktree: Path
    spec: _config_models.RepoSpec
    accepted: str
    accepted_base: str
    replayed: str
    replayed_base: str


def run_git(*args: str, cwd: Path, env_extra: dict | None = None) -> str:
    """One git command against the fixture, failing loudly rather than quietly."""
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env_extra or {})},
        check=True,
    )
    return completed.stdout


def _commit(worktree: Path, message: str) -> str:
    run_git("add", ".", cwd=worktree)
    run_git("commit", "-m", message, cwd=worktree, env_extra=_AUTHOR)
    return _named(worktree)


def _named(worktree: Path, revision: str = _HEAD) -> str:
    """The commit one revision in this fixture resolves to."""
    return run_git(_REV_PARSE, revision, cwd=worktree).strip()


class ReplayRepositoryMixin:
    """A real remote, a topic branch over it, and the rebase that replays it."""

    def build_replay(self) -> ReplayedBranch:
        """Advance the base under a topic commit, then replay it onto the tip.

        The rebase is git's own, so what comes out is the object a production
        replay would produce over these two bases rather than a stand-in for
        one.
        """
        worktree = self._seed_repository()
        accepted = _named(worktree)
        accepted_base = self._fork_point(worktree)
        self._advances_the_base(worktree)
        # A rebase replays commits, so it needs a committer of its own: the
        # production one runs under the hardened envelope that injects one,
        # and a host with no git identity configured has none to inherit.
        run_git(
            "rebase", f"{REMOTE_NAME}/{BASE_BRANCH}",
            cwd=worktree, env_extra=_AUTHOR,
        )
        return ReplayedBranch(
            worktree=worktree,
            spec=self._spec(worktree),
            accepted=accepted,
            accepted_base=accepted_base,
            replayed=_named(worktree),
            replayed_base=self._fork_point(worktree),
        )

    def replays_onto_a_forged_base(
        self, replay: ReplayedBranch,
    ) -> ReplayedBranch:
        """Point the base ref at a commit the remote has not got, and replay.

        The shape a base-relative reading cannot tell from an honest one.
        `refs/remotes/<remote>/<base>` lives in the object store the agent's
        checkout shares, so a commit made here and never pushed is a base as
        far as every local reading is concerned: the rebase replays onto it,
        and the fork point behind the object that comes out names it.

        What makes it worth a real repository is what the digests then say.
        The forged base carries work the branch is no longer read as adding,
        so the replay contributes exactly what the adjudication accepted and
        fingerprints to the same id -- while the commit it produced carries
        that work and the adjudicated change together.
        """
        worktree = replay.worktree
        run_git(
            _CHECKOUT, "-B", _FORGED_BRANCH,
            f"{REMOTE_NAME}/{BASE_BRANCH}", cwd=worktree,
        )
        (worktree / FORGED_FILE).write_text("work no remote has\n")
        forged = _commit(worktree, "feat: unpublished")
        run_git(_CHECKOUT, TOPIC_BRANCH, cwd=worktree)
        run_git(
            "update-ref", f"refs/remotes/{REMOTE_NAME}/{BASE_BRANCH}", forged,
            cwd=worktree,
        )
        run_git(
            "rebase", f"{REMOTE_NAME}/{BASE_BRANCH}",
            cwd=worktree, env_extra=_AUTHOR,
        )
        return replace(
            replay,
            replayed=_named(worktree),
            replayed_base=self._fork_point(worktree),
        )

    def writes_one_byte(self, replay: ReplayedBranch) -> str:
        """Amend a single byte into the replayed commit, and name what it left.

        What a resolution somebody authored looks like from here: the same one
        commit over the same base, contributing something no verdict was ever
        taken over.
        """
        (replay.worktree / TOPIC_FILE).write_text(AMENDED_CONTENT)
        run_git("add", ".", cwd=replay.worktree)
        run_git(
            "commit", "--amend", "--no-edit",
            cwd=replay.worktree, env_extra=_AUTHOR,
        )
        return _named(replay.worktree)

    def _seed_repository(self) -> Path:
        tmpdir = Path(
            self.enterContext(
                tempfile.TemporaryDirectory(
                    prefix="orch-replay-test-", ignore_cleanup_errors=True,
                ),
            ),
        )
        remote = tmpdir / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", "-b", BASE_BRANCH, str(remote)],
            check=True, capture_output=True,
        )
        worktree = tmpdir / "work"
        subprocess.run(
            ["git", "clone", str(remote), str(worktree)],
            check=True, capture_output=True,
        )
        (worktree / "README.md").write_text("hello\n")
        _commit(worktree, "initial")
        run_git("push", REMOTE_NAME, BASE_BRANCH, cwd=worktree)
        run_git(_CHECKOUT, "-b", TOPIC_BRANCH, cwd=worktree)
        (worktree / TOPIC_FILE).write_text(TOPIC_CONTENT)
        _commit(worktree, "feat: the adjudicated change")
        # Published before the base moves, so the remote stands on the head
        # the replay is about to replace. Without it there is no pull-request
        # branch to diverge FROM, and the divergence a rebase really leaves is
        # the whole shape a recovery has to be read against.
        run_git("push", REMOTE_NAME, TOPIC_BRANCH, cwd=worktree)
        return worktree

    def _advances_the_base(self, worktree: Path) -> None:
        """Move the base branch on, the way another issue's merge does."""
        run_git(_CHECKOUT, BASE_BRANCH, cwd=worktree)
        (worktree / BASE_FILE).write_text("somebody else's work\n")
        _commit(worktree, "feat: unrelated")
        run_git("push", REMOTE_NAME, BASE_BRANCH, cwd=worktree)
        run_git(_CHECKOUT, TOPIC_BRANCH, cwd=worktree)
        run_git("fetch", REMOTE_NAME, cwd=worktree)

    def _fork_point(self, worktree: Path) -> str:
        """Where this checkout left the base, read straight out of git."""
        return run_git(
            "merge-base", f"{REMOTE_NAME}/{BASE_BRANCH}", "HEAD", cwd=worktree,
        ).strip()

    def _spec(self, worktree: Path) -> _config_models.RepoSpec:
        return _config_models.RepoSpec(
            slug="chippingway/orchestrator",
            target_root=worktree,
            base_branch=BASE_BRANCH,
        )


def base_tip(worktree: Path) -> str:
    """The commit the fetched base ref is standing at."""
    return _named(worktree, f"{REMOTE_NAME}/{BASE_BRANCH}")


def divergence_from_the_publication(replay: ReplayedBranch) -> tuple[int, int]:
    """How far the replayed checkout stands from the head it replaced.

    Ahead AND behind, which is what a rebase always leaves: the head it
    replayed stops being an ancestor, so the branch carries commits the
    publication has not got and the publication carries one the branch no
    longer has. Read off the objects rather than asserted, because the shape
    is the whole reason a recovery needs a record to be let past the diverged
    park.
    """
    counted = run_git(
        "rev-list", "--left-right", "--count",
        f"{REMOTE_NAME}/{TOPIC_BRANCH}...HEAD", cwd=replay.worktree,
    ).split()
    behind, ahead = (int(side) for side in counted)
    return ahead, behind
