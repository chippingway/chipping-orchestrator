# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Squash planning: the preconditions gathered before the branch rewrite.

Every probe here runs while the original branch is still intact, so a
failure raises `_SquashPreparationError` and the caller aborts with nothing
to undo. How many commits are on the branch is one of them and is walked
rather than derived from the subjects beside it: a commit written with no
message contributes no subject and is still a commit, so a count taken from
the subjects is short by however many of those there are -- which decides
both whether there is anything to collapse and what a human is told their
history was collapsed from. The plan also pins `original_head` -- the rollback target, the head
the entry takes its lease from, and the commit the gate is told this rewrite
collapsed -- so the rewrite never has to re-read a HEAD its own reset has
already moved.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git import commands
from orchestrator.git.publication import titles
from orchestrator.git.verification import probes as verification_probes, status as _worktree_status


class _SquashPreparationError(RuntimeError):
    """A pre-rewrite probe failed while the original branch was intact."""


@dataclass(frozen=True)
class _SquashPlan:
    """Inputs that remain stable across the destructive squash rewrite.

    `count` and `subjects` are not two spellings of one fact. The count is how
    many commits are really on the branch over its base, and it is what says
    whether there is anything to collapse and what a human is told their
    history was collapsed from. The subjects are what the squash message is
    BUILT from, and a commit with an empty message contributes none -- so a
    branch of three where one was committed with no subject offers two
    subjects and is still three commits. Counted from the subjects, that
    branch reads as two, and a branch of two where one is blank reads as
    nothing to squash at all.
    """

    base_sha: str
    original_head: str
    subjects: tuple[str, ...]
    message: str
    count: int = 0


def _squash_base_sha(spec: _config_models.RepoSpec, worktree: Path) -> str:
    """Return the topic branch merge base or raise a preparation error."""
    base_ref = f"{spec.remote_name}/{spec.base_branch}"
    merge_base_result = commands._git(
        "merge-base", base_ref, "HEAD", cwd=worktree,
    )
    if merge_base_result.returncode != 0:
        detail = (merge_base_result.stderr or "").strip()
        raise _SquashPreparationError(f"merge-base failed: {detail}")
    base_sha = (merge_base_result.stdout or "").strip()
    if not base_sha:
        raise _SquashPreparationError("merge-base returned empty")
    return base_sha


def _squash_subjects(worktree: Path, base_sha: str) -> tuple[str, ...]:
    """Return ordered topic-commit subjects or raise on an unreadable log."""
    log_result = commands._git(
        "log", "--reverse", "--pretty=%s", f"{base_sha}..HEAD",
        cwd=worktree,
    )
    if log_result.returncode != 0:
        detail = (log_result.stderr or "").strip()
        raise _SquashPreparationError(f"git log failed: {detail}")
    return tuple(
        output_line
        for output_line in (log_result.stdout or "").splitlines()
        if output_line.strip()
    )


def _squash_commit_count(worktree: Path, base_sha: str) -> int:
    """Return how many commits the branch carries over its base.

    Walked rather than counted from the subjects beside it, because a commit
    with an empty message is still a commit: it contributes no subject and it
    contributes one to this. What turns on the answer is whether there is
    anything to collapse at all and what the notice behind a landed squash
    announces, and neither may be short by the number of commits somebody
    wrote no message for.

    A walk that did not happen, or one whose output is not a number, raises
    rather than defaulting: a count nothing produced is not one this squash
    may decide on, and reading it as zero would report a branch full of
    approved work as having nothing to squash.
    """
    counted = commands._git(
        "rev-list", "--count", f"{base_sha}..HEAD", cwd=worktree,
    )
    if counted.returncode != 0:
        detail = (counted.stderr or "").strip()
        raise _SquashPreparationError(f"rev-list failed: {detail}")
    try:
        return int((counted.stdout or "").strip())
    except ValueError:
        raise _SquashPreparationError(
            "rev-list did not report a commit count",
        ) from None


def _squash_message(
    spec: _config_models.RepoSpec,
    worktree: Path,
    issue: Issue,
    subjects: tuple[str, ...],
) -> str:
    """Build the subject-only message for a multi-commit squash.

    A branch whose commits were all written with no subject at all offers
    nothing to reuse, so the message is inferred from the issue exactly as it
    is for a first subject carrying no reusable prefix.
    """
    first_subject = subjects[0] if subjects else ""
    if titles._is_prefixed_subject(first_subject):
        return f"{first_subject}\n"
    fallback_prefix = titles._infer_subject_prefix(spec, worktree, issue)
    subject = titles._pr_title_from_commit_or_issue(
        issue, first_subject, fallback_prefix,
    )
    return f"{subject}\n"


def _prepare_squash(
    spec: _config_models.RepoSpec, worktree: Path, issue: Issue,
) -> _SquashPlan:
    """Collect every precondition before the branch rewrite begins."""
    base_sha = _squash_base_sha(spec, worktree)
    original_head = verification_probes._head_sha(worktree)
    if not original_head:
        raise _SquashPreparationError("could not read original HEAD")
    if _worktree_status._worktree_dirty_files(worktree):
        raise _SquashPreparationError("worktree has uncommitted changes")
    count = _squash_commit_count(worktree, base_sha)
    subjects = _squash_subjects(worktree, base_sha)
    message = (
        _squash_message(spec, worktree, issue, subjects) if count > 1 else ""
    )
    return _SquashPlan(base_sha, original_head, subjects, message, count)
