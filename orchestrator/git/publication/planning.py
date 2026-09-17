# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Squash planning: the preconditions gathered before the branch rewrite.

Every probe here runs while the original branch is still intact, so a
failure raises `_SquashPreparationError` and the caller aborts with nothing
to undo. How many commits are on the branch is one of them and is walked
rather than derived from the subjects beside it: a commit written with no
message contributes no subject and is still a commit, so a count taken from
the subjects is short by however many of those there are -- which decides
both what kind of rewrite the branch is owed and what a human is told their
history was collapsed from. The plan also pins `original_head` -- the rollback target, the head
the entry takes its lease from, and the commit the gate is told this rewrite
collapsed -- so the rewrite never has to re-read a HEAD its own reset has
already moved.

Whether a rewrite is owed at all is decided here too, and the count alone
does not decide it. More than one commit is a collapse whatever the subjects
say. Exactly one is a rewrite only of its SUBJECT, owed wherever the shared
normalization would write that subject differently -- a line missing this
publication's reference, and one still carrying the tracked issue's beside a
reference an earlier publication appended -- so the same reset-and-recommit
answers a branch that has to be flattened and a branch that only has to be
referenced, and a branch already committed under the subject a publication
writes is left exactly as the developer committed it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git import commands
from orchestrator.git.publication import pr_references, titles
from orchestrator.git.verification import probes as verification_probes, status as _worktree_status


class _SquashPreparationError(RuntimeError):
    """A pre-rewrite probe failed while the original branch was intact."""


@dataclass(frozen=True)
class _SquashPlan:
    """Inputs that remain stable across the destructive squash rewrite.

    `count` and `subjects` are not two spellings of one fact. The count is how
    many commits are really on the branch over its base, and it is what says
    which rewrite the branch is owed and what a human is told their history
    was collapsed from. The subjects are what the squash message is BUILT
    from, and a commit with an empty message contributes none -- so a branch
    of three where one was committed with no subject offers two subjects and
    is still three commits. Counted from the subjects, that branch reads as
    two, and a branch of two where one is blank reads as nothing to squash at
    all.
    """

    base_sha: str
    original_head: str
    subjects: tuple[str, ...] = ()
    message: str = ""
    count: int = 0

    @property
    def rewrites(self) -> bool:
        """Whether this plan has a rewrite for the branch at all.

        The message answers it rather than a flag beside it, because the
        message is what the rewrite COMMITS: a plan carrying one has a subject
        this branch is not already standing on, and a plan carrying none has
        nothing to write. Held as two facts they could disagree, and a plan
        claiming a rewrite with no message would commit an empty subject over
        the work a reviewer approved.
        """
        return bool(self.message)


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
    contributes one to this. What turns on the answer is which rewrite this
    branch is owed -- a collapse, a subject, or nothing -- and what the notice
    behind a landed squash announces, and neither may be short by the number
    of commits somebody wrote no message for.

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
    planned: _SquashPlan,
    pr_number: int | None,
) -> str:
    """The subject-only message `planned`'s rewrite commits, or "" for none.

    Handed the plan rather than the subjects alone, because what the branch
    is owed is not a question the subjects answer: the COUNT decides which of
    the two rewrites is on the table, and the two are owed on different terms.
    More than one commit is a collapse, owed whatever the subjects on it say,
    since the history itself is what is being replaced. Exactly one commit is
    already the shape a collapse leaves, so the only thing left to rewrite is
    the subject over it -- and it is owed that only where the shared
    normalization would write that subject differently, asked through
    `pr_references` with both numbers, so what counts as already published
    cannot drift from what the line below writes. A subject missing the
    reference is owed the rewrite and so is one still carrying the tracked
    issue's beside it; a branch an earlier round already published, one on an
    install that references nothing, and a branch carrying no commits at all
    each come back with no message, which is how a plan says there is nothing
    to do.

    One selection serves both rewrites. A collapse takes the first of the
    commits it is replacing; a one-commit branch has that same first subject
    and only the reference to add to it, so neither road may pick a different
    line for the same work.

    A branch whose commits were all written with no subject at all offers
    nothing to reuse, so the message is inferred from the issue exactly as it
    is for a first subject carrying no reusable prefix.

    Whichever of the two picked the subject, it is normalized against
    `pr_number` and this issue's own number through the owner every publisher
    shares: the line ends in exactly one reference to the pull request, so a
    reused first subject an earlier approval round already squashed to is not
    given a second one, and the tracked issue's reference is dropped, whether
    a developer copied it out of recent history or an earlier publication left
    it standing ahead of its own. None is a squash whose subject references no
    pull request, and it gets the selected subject back exactly as it was
    picked -- nothing appended, and nothing stripped on the way to a reference
    that is never written.
    """
    if not planned.count:
        return ""
    first_subject = planned.subjects[0] if planned.subjects else ""
    if planned.count == 1 and not pr_references._subject_owes_the_reference(
        first_subject, pr_number, issue.number,
    ):
        return ""
    if titles._is_prefixed_subject(first_subject):
        subject = first_subject
    else:
        fallback_prefix = titles._infer_subject_prefix(spec, worktree, issue)
        subject = titles._pr_title_from_commit_or_issue(
            issue, first_subject, fallback_prefix,
        )
    if pr_number is not None:
        subject = pr_references._subject_with_pr_reference(
            subject, pr_number, issue.number,
        )
    return f"{subject}\n"


def _prepare_squash(
    spec: _config_models.RepoSpec,
    worktree: Path,
    issue: Issue,
    pr_number: int | None,
) -> _SquashPlan:
    """Collect every precondition before the branch rewrite begins.

    `pr_number` is the pull request the squash message references, or None
    where it references none. On a branch of several commits it decides that
    subject alone; on a branch of one it decides whether there is a rewrite at
    all, since such a branch is rewritten only to carry the reference. The
    tracked issue the message is normalized against is `issue`'s own number,
    read off the issue already handed in for the subject inference rather than
    passed beside it: the two are the same issue, and a second parameter is a
    second thing that could name a different one.

    The plan is taken before the message and the message is folded into it,
    rather than both being assembled at once, because the message is decided
    FROM the plan: what the branch is owed turns on the count and the subjects
    together, and reading them out of a half-built argument list is how the
    two come apart.
    """
    base_sha = _squash_base_sha(spec, worktree)
    original_head = verification_probes._head_sha(worktree)
    if not original_head:
        raise _SquashPreparationError("could not read original HEAD")
    if _worktree_status._worktree_dirty_files(worktree):
        raise _SquashPreparationError("worktree has uncommitted changes")
    planned = _SquashPlan(
        base_sha,
        original_head,
        # Walked first and read second, because the two are not one fact: a
        # commit written with no message contributes no subject and still
        # contributes one commit.
        count=_squash_commit_count(worktree, base_sha),
        subjects=_squash_subjects(worktree, base_sha),
    )
    return replace(
        planned,
        message=_squash_message(spec, worktree, issue, planned, pr_number),
    )
