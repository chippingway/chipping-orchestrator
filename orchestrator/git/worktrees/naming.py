# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Repository-safe segments and the issue branch identity this orchestrator owns.

Lossy branch rewrites include a digest so distinct slugs keep distinct refs.
Only the repository-scoped `_branch_name` derivation is an owned artifact
name: a flat `orchestrator/issue-<n>`, an `orchestrator/` prefix, or a pinned
value alone attributes nothing to an issue and licenses no cleanup. The live
resolver answers with that same name or refuses (`BranchRefused`): a pinned
branch that is anything else, and a recorded pull request with no branch
pinned beside it, name no branch live work may stand on, and nothing is
derived in their place. Local checkout placement uses the shared slug encoding
through the paths owner.
"""
from __future__ import annotations

import hashlib
import logging
import re

from orchestrator.config import models as _config_models
from orchestrator.github import pinned_refusal as _pinned_refusal
from orchestrator.github.pinned_state import PinnedState

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so a refused branch reports where their
# filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

_SLUG_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]")

_SAFE_CHAR = "_"

_SLUG_DIGEST_LEN = 16

# The namespace every issue branch this orchestrator publishes lives under. It
# is no ownership evidence: the community sweep spares a pull request standing
# in it from a ping, and the live resolver below honors only the exact
# current-layout name inside it.
_OWNED_NAMESPACE = "orchestrator/"

# The pinned keys the live resolver reads: the branch an issue's work stands
# on, and the pull request that says the work has been published.
_PINNED_BRANCH = "branch"
_PINNED_PR = "pr_number"


def _sanitize_slug(slug: str) -> str:
    """Turn an `owner/name` repo slug into a single filesystem-safe segment.

    `/` collapses to `__` so two repos with the same issue number cannot
    share a worktree path. Any other character outside `[A-Za-z0-9_.-]`
    becomes `_`. A leading `.` is escaped to `_.` so the per-repo subdir
    is never a dotfile-hidden directory. An empty/all-stripped input
    falls back to `_` rather than collapsing into the bare WORKTREES_DIR.
    """
    cleaned = _SLUG_SAFE_RE.sub(_SAFE_CHAR, (slug or "").replace("/", "__"))
    if not cleaned:
        return _SAFE_CHAR
    if cleaned.startswith("."):
        cleaned = _SAFE_CHAR + cleaned
    return cleaned


def _slug_digest(slug: str) -> str:
    """Return the short content digest used for lossy ref rewrites."""
    encoded_slug = (slug or "").encode("utf-8")
    slug_hash = hashlib.sha1(encoded_slug)
    return slug_hash.hexdigest()[:_SLUG_DIGEST_LEN]


def _sanitize_branch_segment(slug: str) -> str:
    """Make a slug safe for use as a single git branch-name segment.

    Layers on top of `_sanitize_slug` (filesystem-safe single segment)
    the additional `git check-ref-format` rules so a branch like
    `orchestrator/<segment>/issue-N` is accepted by git. Without this,
    a configured `REPOS` slug whose name contains `.lock`, `..`, or a
    trailing `.` would yield a ref name git rejects, breaking every
    push for that repo before the PR even exists -- the
    filesystem-only sanitizer happily produces `owner__foo.lock` /
    `owner__foo..bar` / `owner__foo.` even though `git
    check-ref-format` flags them.

    Rules applied beyond `_sanitize_slug`:

    * Collapse any run of two or more dots to a single `_` so the
      segment never carries the forbidden `..` sequence. A single
      `.` mid-segment is allowed by git and left alone.
    * Replace a trailing `.lock` with `_lock` -- git rejects any
      slash-separated component ending in `.lock` (reserved for
      git's own lock files).
    * Replace any trailing `.` with `_` -- git rejects refs ending
      in `.`.

    Any of those three rewrites is information-lossy: `foo.lock` and
    `foo_lock` would both collapse to `foo_lock`, so two `REPOS`
    entries sharing a `target_root` could still collide on the same
    branch and defeat slug-namespacing. To stay injective, whenever
    the ref-only rewrites change the filesystem-safe form, the
    segment carries a `__h<digest>` suffix derived from the
    untransformed slug. Distinct slugs therefore always hash to
    distinct branches; the suffix only appears on the rare
    pathological inputs, so common slugs keep their readable
    `<owner>__<name>` form. (The hash is 64 bits; an exact-match
    collision would require an attacker-crafted REPOS entry, which
    is not in our threat model.)

    Path layout (`_repo_worktrees_root`) keeps the filesystem-only
    `_sanitize_slug` because directory names tolerate `.lock` /
    trailing-dot just fine; the branch segment is the stricter
    surface, so it gets its own sanitizer rather than tightening the
    filesystem one and uglifying every common slug's worktree path.
    """
    sanitized_path = _sanitize_slug(slug)
    sanitized_segment = sanitized_path
    # `..` anywhere is forbidden. Collapse any run of dots to a single
    # `_` so a segment cannot smuggle the sequence past the trailing-
    # dot / `.lock` checks below.
    sanitized_segment = re.sub(r"\.{2,}", _SAFE_CHAR, sanitized_segment)
    # `.lock` suffix on a component is reserved by git.
    if sanitized_segment.endswith(".lock"):
        trimmed = sanitized_segment[: -len(".lock")]
        sanitized_segment = f"{trimmed}_lock"
    # Trailing `.` on a component is rejected. Loop so any
    # follow-on dot revealed by the trim is also handled.
    while sanitized_segment.endswith("."):
        sanitized_segment = sanitized_segment[:-1] + _SAFE_CHAR
    # Defensive fallbacks: the substitutions above could in principle
    # produce an empty / leading-dot string (e.g. an input of `.` or
    # `..` collapses far enough that the leading-dot escape from
    # `_sanitize_slug` no longer covers the result).
    if not sanitized_segment:
        sanitized_segment = _SAFE_CHAR
    if sanitized_segment.startswith("."):
        sanitized_segment = _SAFE_CHAR + sanitized_segment
    if sanitized_segment == sanitized_path:
        return sanitized_segment
    # Ref-only rewrites changed the filesystem form. Append a
    # content-derived hash of the ORIGINAL slug so two distinct
    # inputs that collapsed to the same `s` (e.g. `owner/foo.lock`
    # and `owner/foo_lock`) stay distinct on the branch ref --
    # without this, two `REPOS` entries sharing a `target_root`
    # would collide on the same branch and the slug-namespacing
    # fix would silently regress for those slug shapes.
    digest = _slug_digest(slug)
    return f"{sanitized_segment}__h{digest}"


def _branch_name(spec: _config_models.RepoSpec, issue_number: int) -> str:
    """Per-issue branch name namespaced by the spec's git-ref-safe slug.

    Two RepoSpecs that share the same `target_root` (a single local clone
    with multiple remotes, e.g. `lance-open-source` and `lance-private`)
    would otherwise collide on `orchestrator/issue-<n>` because git
    refuses to check the same branch out in two worktrees of one repo.
    Including the sanitized slug keeps each spec's worktree on its own
    branch. This exact name is the only branch an issue's artifact
    ownership and cleanup recognize: attribution, the reclaim identity
    check, and every teardown compare against it character for character
    rather than testing a namespace.

    Uses `_sanitize_branch_segment` rather than the filesystem-only
    `_sanitize_slug` so a slug like `owner/foo.lock` or
    `owner/foo..bar` does not produce a branch name `git
    check-ref-format` rejects.
    """
    return (
        f"orchestrator/{_sanitize_branch_segment(spec.slug)}"
        f"/issue-{issue_number}"
    )


class BranchRefused(_pinned_refusal.RecordRefused):
    """Live work met a branch this issue cannot be trusted to stand on.

    Raised by the resolver over a record naming no branch live work may use,
    and by the creators over a branch that is not the issue's current-layout
    name or a checkout at the issue's path that is not proven the issue's own.
    Every caller asks one of them before its first checkout, launch, or push.
    A `RecordRefused` because the answer is the same: the dispatcher abandons
    the handler with nothing past that point done, every boundary that lets a
    refused record through lets this through too, and the branches, checkout,
    and pull request stay for a human. The refusal has been said in a local
    line by the time it is raised.
    """


def _trusted_branch(
    state: PinnedState, spec: _config_models.RepoSpec, issue_number: int,
) -> str | None:
    """The branch this record lets live work use, or None where it names none.

    Two records answer, and both with the current-layout derivation: one that
    pins exactly that name, and one that pins nothing and records no pull
    request, which is fresh work. A pin naming anything else -- the flat
    `orchestrator/issue-<n>`, another repository's branch, any other name in
    the `orchestrator/` namespace, a value that is no string -- is refused,
    and so is a recorded pull request with no branch pinned beside it: every
    current publication pins the branch it pushed with the number, so a
    record holding one without the other says nothing about where the pull
    request's commits are, and the derived name in its place would publish
    onto a branch that pull request was never open on.
    """
    current = _branch_name(spec, issue_number)
    pinned = state.get(_PINNED_BRANCH)
    if pinned is None:
        return current if state.get(_PINNED_PR) is None else None
    return current if pinned == current else None


def _resolve_branch_name(
    state: PinnedState, spec: _config_models.RepoSpec, issue_number: int,
) -> str:
    """The branch this issue's live work stands on, or `BranchRefused`.

    The current-layout `_branch_name(spec, issue_number)` wherever the record
    lets live work use it (`_trusted_branch`), so fresh work and every pinned
    current branch get the same name the artifact owners recognize. Anything
    else raises, said once on the lifecycle channel with what the record
    holds: no flat name is inferred from a recorded pull request, no prefix
    stands in for the exact name, and no derived name replaces a pin, since
    each would move publication onto a branch the record never named.
    """
    branch = _trusted_branch(state, spec, issue_number)
    if branch is not None:
        return branch
    log.warning(
        "issue=#%d records branch %r and pull request %r, naming no branch "
        "live work may use (its current branch is %r); refusing every "
        "checkout, launch, and push and leaving its branches, checkout, and "
        "pull request for a human",
        issue_number, state.get(_PINNED_BRANCH), state.get(_PINNED_PR),
        _branch_name(spec, issue_number),
    )
    raise BranchRefused(f"issue #{issue_number} records no branch live work may use")
