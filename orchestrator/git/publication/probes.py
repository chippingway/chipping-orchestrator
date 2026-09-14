# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Branch geometry: distance from a remote tip, and the fork point behind it.

The two reads sit together because they answer the same question from either
end: where a checkout stands against the branch it is published onto, and
where it stands against the base it is measured over. Both are facts about
where commits sit, so nothing here reads what any of them SAY -- what a
subject line has to look like is title policy, and ``titles`` owns it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import commands


@dataclass(frozen=True)
class _BranchDivergence:
    """Where a checkout stands against the remote tip it was compared with.

    One reading rather than two facts read separately, and the commit is why.
    The counts are a CLAIM ABOUT `tip`: "ahead of it and not behind it" is
    what licenses a force-push, and the push is pinned to that same commit.
    Read the ref twice -- once to compare against and once to name -- and
    anything moving it in between (another worker in the same checkout, a
    fetch racing this one) leaves the branch proved against one head and the
    push pinned to another. Where the pull request has moved to the second,
    the lease is satisfied and the force-push lands on top of it. So the ref
    is resolved ONCE and the comparison is taken against that immutable id.

    `readable` is what every caller acts on first, and it is not `(0, 0)`.
    Zero and zero is what an in-sync branch answers; a ref nothing could
    resolve, a comparison git refused, and a count in a shape this cannot
    parse are readings that did not happen at all. Collapsed into "in sync"
    they are how a stale checkout gets rebased, spawned over, and
    force-pushed on evidence nobody took.
    """

    tip: str = ""
    ahead: int = 0
    behind: int = 0
    readable: bool = False

    @classmethod
    def taken(
        cls, spec: _config_models.RepoSpec, worktree: Path, branch: str,
    ) -> _BranchDivergence:
        """Resolve `<remote>/<branch>` once, then count HEAD against it.

        The caller must have fetched that ref immediately before calling, so
        what is resolved here is the tip the remote had a moment ago.
        """
        tip = cls._resolved_tip(spec, worktree, branch)
        if not tip:
            return cls()
        return cls._counted_against(worktree, tip)

    @classmethod
    def _resolved_tip(
        cls, spec: _config_models.RepoSpec, worktree: Path, branch: str,
    ) -> str:
        """The commit the fetched remote-tracking ref names, or "".

        Read from the ref rather than from the remote: asking the remote
        again would answer about a different moment, and the whole point of
        this reading is to name the one the caller's fetch established.
        """
        resolved = commands._git_hardened(
            "rev-parse", f"refs/remotes/{spec.remote_name}/{branch}",
            cwd=worktree,
        )
        if resolved.returncode != 0:
            return ""
        return (resolved.stdout or "").strip()

    @classmethod
    def _counted_against(
        cls, worktree: Path, tip: str,
    ) -> _BranchDivergence:
        """HEAD's distance from one immutable commit, or an unreadable one.

        `ahead` is what HEAD has and the tip does not -- unpushed local work.
        `behind` is what the tip has and HEAD does not -- a stale checkout.
        """
        counted = commands._git_hardened(
            "rev-list", "--left-right", "--count", f"{tip}...HEAD",
            cwd=worktree,
        )
        if counted.returncode != 0:
            return cls()
        parts = (counted.stdout or "").strip().split()
        if len(parts) != 2:
            return cls()
        try:
            distance = [int(part) for part in parts]
        except ValueError:
            return cls()
        # `rev-list --left-right` reports the left side first, which is the
        # tip: what it has and HEAD does not is `behind`.
        return cls(
            tip=tip, ahead=distance[1], behind=distance[0], readable=True,
        )


def _branch_divergence(
    spec: _config_models.RepoSpec, worktree: Path, branch: str
) -> _BranchDivergence:
    """How far HEAD stands from the freshly-fetched `<remote>/<branch>` tip.

    The seam every caller reaches this reading through, so a test names one
    owner and the record above keeps the reasoning.
    """
    return _BranchDivergence.taken(spec, worktree, branch)


def _fork_point(spec: _config_models.RepoSpec, worktree: Path, revision: str) -> str:
    """The commit `<remote>/<base>` and one revision last had in common, or "".

    The base a contribution is read over. A three-dot range against the base
    branch resolves to exactly this commit, so naming it names what the diff a
    reviewer would be handed is taken from -- and a rewrite that moves a
    branch onto a base which has advanced needs both of them: the fork point
    the replaced commit was read over, and the fork point the commit replacing
    it is. Only the first can still be read while the branch stands where it
    did, which is why it is read there rather than derived afterwards.

    Empty is a reading that did not HAPPEN: a base ref nothing fetched, a
    revision this host does not hold, two histories with no ancestor between
    them. Every caller treats it as evidence it cannot produce rather than as
    a base, because a base nobody established would fingerprint a contribution
    over a range that means nothing.
    """
    read = commands._git_hardened(
        "merge-base", f"{spec.remote_name}/{spec.base_branch}", revision,
        cwd=worktree,
    )
    if read.returncode != 0:
        return ""
    return (read.stdout or "").strip()
