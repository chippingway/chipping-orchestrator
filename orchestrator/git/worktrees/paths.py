# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Local checkout placement and issue-number recognition.

The naming owner defines repository segments and branch identities. This owner
maps those segments onto the configured checkout root and recognizes both
repository-scoped and legacy checkout paths.
"""
from __future__ import annotations

import re
from pathlib import Path

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming

# The `issue-<n>` tail every name below ends in, anchored whole and with no
# room for a leading zero: `n` is a GitHub issue number, and those start at 1
# and are written without padding. The digit run is bounded because the match
# is converted to an int, and `int()` refuses a string past its digit ceiling
# (4300 by default) by raising: eighteen digits is far past any number a
# repository issues and far short of that ceiling, so a ref carrying thousands
# of them is a name that parses to nothing rather than one that raises out of
# a read whose whole job is to fail closed.
_ISSUE_SEGMENT_RE = re.compile(r"issue-([1-9][0-9]{0,17})")


def _repo_worktrees_root(spec: _config_models.RepoSpec) -> Path:
    """Per-repo subdirectory under WORKTREES_DIR for this spec.

    Two specs with the same issue number must not collide on disk, so the
    issue-N / decompose-N segments live inside a sanitized-slug parent
    instead of directly under WORKTREES_DIR.
    """
    return config.WORKTREES_DIR / _naming._sanitize_slug(spec.slug)


def _worktree_path(spec: _config_models.RepoSpec, issue_number: int) -> Path:
    return _repo_worktrees_root(spec) / f"issue-{issue_number}"


def _legacy_worktree_path(issue_number: int) -> Path:
    """The pre-slug-namespacing checkout path for an issue.

    The path counterpart of `_legacy_branch_name`, and it carries no slug for
    the same reason that name does not: before the per-repo parent existed,
    every configured repository put its `issue-<n>` checkout directly under
    `WORKTREES_DIR`. Nothing writes here now, and it is derived rather than
    guessed because a caller reading such a directory has only its name to go
    on -- and, since the derivation is the same for every entry, no name to say
    which of them made it.
    """
    return config.WORKTREES_DIR / f"issue-{issue_number}"


def _issue_worktree_paths(
    spec: _config_models.RepoSpec, issue_number: int,
) -> tuple[Path, ...]:
    """Every path this orchestrator could have checked one issue out at.

    The per-repository path it writes now and the flat one an issue checked out
    before slug namespacing is still sitting at -- both, in that order, because
    a host running across the migration can be holding both at once and a
    teardown takes the current one first.
    """
    return (
        _worktree_path(spec, issue_number),
        _legacy_worktree_path(issue_number),
    )


def _issue_segment_number(segment: str) -> int | None:
    """The issue number an `issue-<n>` name segment carries, or None.

    The inverse of the tail `_branch_name` and `_worktree_path` build, kept
    beside them so the pair cannot drift: a caller reading an existing branch
    or worktree directory has only its name to go on, and a name these
    derivations would never write is not one of this orchestrator's to read.

    Deliberately narrower than `int()`, which answers 7 for `issue-007`,
    `issue-+7`, and `issue- 7` alike -- three names nothing here published,
    each of which would arrive at a caller as a claim on issue #7 -- and
    which raises outright on a run of digits past its conversion ceiling.
    Only the canonical spelling of a positive number, at a width a repository
    can actually reach, parses; everything else is answered rather than
    thrown, because a caller reading a ref store it does not control cannot
    have one name in it end the read.

    Even a parsed number is half an answer where several repositories share
    one clone: it says nothing about WHICH of them published the name, so a
    caller reading that ref store settles it by re-deriving each spec's own
    name and comparing.
    """
    matched = _ISSUE_SEGMENT_RE.fullmatch(segment)
    if matched is None:
        return None
    return int(matched.group(1))
