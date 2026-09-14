# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a published subject line may say, and which one gets written.

Every surface here answers one question -- what subject the orchestrator
writes on a pull request and on the commit a squash collapses to -- and each
is built from the one below it: the vocabulary says which prefixes count, the
predicates read a line against it, the two history reads supply the lines they
are read on, and the inference and the selection above them decide. A type
added to the list cannot drift from the regex that recognizes it, and a
predicate cannot drift from the caller that picks a title with it.

The history reads are commit MESSAGES, not branch geometry: what is asked of
git here is what past subjects say, so ``probes`` beside this owner keeps the
ahead/behind and fork-point reads and this one never consults them.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git import commands

_CONVENTIONAL_TYPES = (
    "feat", "fix", "chore", "docs", "refactor",
    "test", "perf", "build", "ci", "style", "revert",
)

_CONVENTIONAL_TYPES_ALT = "|".join(_CONVENTIONAL_TYPES)

_CONVENTIONAL_RE = re.compile(
    rf"^(?:{_CONVENTIONAL_TYPES_ALT})"
    r"(?:\([^)]+\))?!?:\s+\S",
)

_PREFIXED_RE = re.compile(r"^[a-z][a-z0-9-]*(?:\([^)]+\))?!?:\s+\S")

_PREFIX_TOKEN_RE = re.compile(r"^([a-z][a-z0-9-]*)(?:\([^)]+\))?!?:\s+\S")


def _first_commit_subject(spec: _config_models.RepoSpec, worktree: Path) -> str:
    """Subject line of the oldest commit in `origin/<base>..HEAD`, or ''.

    Used by `_on_commits` to derive a PR title from what the agent actually
    wrote, so the PR title matches the commit history when the subject is
    reusable. Reads the base branch from the spec so a multi-repo deployment
    with mixed default branches (e.g. one repo on `main`, another on
    `master`) compares against the right remote.
    """
    log_result = commands._git(
        "log", "--reverse", "--format=%s",
        f"{spec.remote_name}/{spec.base_branch}..HEAD",
        cwd=worktree,
    )
    if log_result.returncode != 0:
        return ""
    lines = (log_result.stdout or "").splitlines()
    return lines[0].strip() if lines else ""


def _is_conventional_subject(subject: str) -> bool:
    return bool(_CONVENTIONAL_RE.match(subject or ""))


def _is_prefixed_subject(subject: str) -> bool:
    """True if `subject` is a reusable `<token>: <subject>` line.

    Broader than `_is_conventional_subject`: any lowercase prefix counts,
    so a repo-local `event:` / `career:` subject is reused verbatim rather
    than discarded for a synthesized `feat:`.
    """
    return bool(_PREFIXED_RE.match(subject or ""))


def _subject_prefix(subject: str) -> str | None:
    """Bare prefix token of a `<token>[(scope)][!]: ...` subject, or None."""
    prefix_match = _PREFIX_TOKEN_RE.match(subject or "")
    return prefix_match.group(1) if prefix_match else None


def _recent_base_subjects(
    spec: _config_models.RepoSpec, worktree: Path, limit: int = 30
) -> list[str]:
    """Subjects of the most recent non-merge base-branch commits (newest
    first), or `[]` on git error.

    Reads `<remote>/<base>` so the sample reflects the repo's own commit
    history rather than the topic branch under construction. Merge commits
    are excluded so their `Merge pull request #...` subjects don't drown
    out the real prefix style.
    """
    log_result = commands._git(
        "log", "--no-merges", f"--max-count={limit}", "--format=%s",
        f"{spec.remote_name}/{spec.base_branch}",
        cwd=worktree,
    )
    if log_result.returncode != 0:
        return []
    return [
        line.strip()
        for line in (log_result.stdout or "").splitlines()
        if line.strip()
    ]


def _infer_subject_prefix(
    spec: _config_models.RepoSpec, worktree: Path, issue: Issue
) -> str:
    """Fallback `<type>` prefix for an orchestrator-synthesized subject.

    Called only when neither the agent's first commit subject nor the issue
    title already carries a reusable `<prefix>:` form. When a repo-local
    prefix (one outside the Conventional Commits allowlist, e.g. `event:` /
    `career:`) dominates recent base-branch history, reuse it so the
    synthesized subject matches the repo's own style instead of blindly
    defaulting to `feat:`. Otherwise fall back to `fix` for bug-labelled
    issues and `feat` everywhere else.
    """
    counts: Counter[str] = Counter()
    for subject in _recent_base_subjects(spec, worktree):
        prefix = _subject_prefix(subject)
        if prefix:
            counts[prefix] += 1
    if counts:
        # `most_common` breaks ties by first insertion; subjects arrive
        # newest-first, so the most recent of any tied prefixes wins.
        dominant = counts.most_common(1)[0][0]
        if dominant not in _CONVENTIONAL_TYPES:
            return dominant
    label_names = {
        (getattr(issue_label, "name", "") or "").lower()
        for issue_label in (issue.labels or [])
    }
    if {"bug", "fix"} & label_names:
        return "fix"
    return "feat"


def _pr_title_from_commit_or_issue(
    issue: Issue, first_subject: str, fallback_prefix: str = "feat",
) -> str:
    """Pick a PR title (also reused as the squash subject).

    Prefer the agent's first commit subject when it already carries a
    reusable `<prefix>:` form (so the PR title matches the commit history),
    then the issue title when it does, and only otherwise synthesize a
    `<fallback_prefix>: <issue title>` -- `fallback_prefix` comes from
    `_infer_subject_prefix`, so the synthesized form honors the repo's own
    style. Traceability is preserved by the `Resolves #<n>` line in the PR
    body, so the title stays clean.
    """
    subject = (first_subject or "").strip()
    if _is_prefixed_subject(subject):
        return subject
    issue_title = (issue.title or "").strip()
    if _is_prefixed_subject(issue_title):
        return issue_title
    body = issue_title or f"address issue #{issue.number}"
    return f"{fallback_prefix}: {body}"
