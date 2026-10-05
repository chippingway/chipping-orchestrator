# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""REPOS parsing, target selection, and target validation.

Turns the ``REPOS`` environment value (entry tokenizing, owner/name and
option validation, duplicate-slug detection, per-repo parallel-limit
parsing) into the ``RepoSpec`` list threaded through the workflow. When
``REPOS`` is unset, the developer fallback built from ``REPO`` /
``TARGET_REPO_ROOT`` / ``BASE_BRANCH`` / ``REMOTE_NAME`` stands in for it, but
only where the caller offers one -- a package running from this project's own
source checkout. An installed package offers none, so it has no target but
the ones ``REPOS`` names. Every selected target is then held to a git
checkout, as ``checkouts`` reads one, so a missing or unusable clone stops the
process at import, before anything connects to GitHub.

The abort-on-invalid diagnostic lives in ``orchestrator.config`` (its single
configuration-failure funnel) and is injected here as a callable, so this
module parses without importing config back. The data types it produces
(``RepoSpec``, ``RepoEnvEntry``) live in ``models``.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NoReturn

from orchestrator.config.checkouts import checkout_problem
from orchestrator.config.models import RepoEnvEntry, RepoSpec

# The diagnostic injected from ``orchestrator.config`` keeps configuration
# failure policy out of the parsing leaf: ``config_error`` aborts import.
ConfigError = Callable[[str], NoReturn]

_REPOS_REQUIRED = (
    "orchestrator: REPOS is unset, and an installed package has no default "
    "target; set REPOS to one or more 'owner/name|target_root|base_branch' "
    "entries separated by ';'. REPO and TARGET_REPO_ROOT are developer "
    "settings, read only when the orchestrator runs from its own source "
    "checkout"
)


def iter_repos_entries(raw_repos: str) -> Iterator[tuple[int, str]]:
    """Yield numbered, non-comment entries from a ``REPOS`` value."""
    for entry_no, raw_line in enumerate(
        raw_repos.replace(";", "\n").splitlines(), start=1,
    ):
        line = raw_line.strip()
        if line and not line.startswith("#"):
            yield entry_no, line


def _validate_required_fields(
    entry_no: int,
    slug: str,
    target_root: str,
    base_branch: str,
    config_error: ConfigError,
) -> None:
    """Validate the required fields of one ``REPOS`` entry."""
    slug_components = slug.split("/")
    if len(slug_components) != 2 or not all(slug_components):
        config_error(
            f"orchestrator: REPOS entry #{entry_no} has invalid "
            f"owner/name {slug!r}; expected exactly 'owner/name' "
            "with non-empty owner and name",
        )
    if not target_root:
        config_error(
            f"orchestrator: REPOS entry #{entry_no} has empty target_root",
        )
    if not base_branch:
        config_error(
            f"orchestrator: REPOS entry #{entry_no} has empty base_branch",
        )


def parse_repo_entry(
    entry_no: int,
    line: str,
    config_error: ConfigError,
) -> RepoEnvEntry:
    """Parse and validate the fields of one ``REPOS`` entry."""
    entry_parts = tuple(part.strip() for part in line.split("|"))
    if len(entry_parts) not in (3, 4, 5):
        config_error(
            f"orchestrator: REPOS entry #{entry_no} is malformed "
            "(expected 'owner/name|target_root|base_branch' "
            "with optional '|remote_name' and '|parallel_limit'): "
            f"{line!r}",
        )
    slug, target_root, base_branch = entry_parts[:3]
    # Remote validation precedes required-field validation to keep the
    # original abort ordering.
    if len(entry_parts) == 3:
        remote_name = "origin"
    else:
        remote_name = entry_parts[3]
        if not remote_name:
            config_error(
                f"orchestrator: REPOS entry #{entry_no} has empty "
                "remote_name (omit the trailing '|' to default to 'origin')",
            )
    _validate_required_fields(
        entry_no,
        slug,
        target_root,
        base_branch,
        config_error,
    )
    return RepoEnvEntry(
        entry_no=entry_no,
        slug=slug,
        target_root=target_root,
        base_branch=base_branch,
        remote_name=remote_name,
        parallel_limit_raw=entry_parts[4] if len(entry_parts) == 5 else None,
    )


def _parse_parallel_limit(
    entry: RepoEnvEntry,
    default_parallel_limit: int,
    config_error: ConfigError,
) -> int:
    """Validate one entry's optional parallel limit."""
    if entry.parallel_limit_raw is None:
        return default_parallel_limit
    if not entry.parallel_limit_raw:
        config_error(
            f"orchestrator: REPOS entry #{entry.entry_no} has empty "
            "parallel_limit (omit the trailing '|' to default to "
            f"MAX_PARALLEL_ISSUES_PER_REPO={default_parallel_limit})",
        )
    try:
        parallel_limit = int(entry.parallel_limit_raw)
    except ValueError:
        config_error(
            f"orchestrator: REPOS entry #{entry.entry_no} parallel_limit "
            f"{entry.parallel_limit_raw!r} is not a valid integer; expected "
            "a positive integer (>= 1)",
        )
    if parallel_limit < 1:
        config_error(
            f"orchestrator: REPOS entry #{entry.entry_no} parallel_limit "
            f"{entry.parallel_limit_raw!r} must be >= 1 (zero or negative "
            "would block all work for this repo)",
        )
    return parallel_limit


def parse_repos_env(
    raw: str,
    *,
    default_parallel_limit: int,
    config_error: ConfigError,
) -> list[RepoSpec]:
    """Parse the REPOS env value into a list of RepoSpecs.

    Format: one entry per line,
    ``owner/name|target_root|base_branch[|remote_name[|parallel_limit]]``.
    The fourth (``remote_name``, defaults to ``origin``) and fifth
    (``parallel_limit``, defaults to ``MAX_PARALLEL_ISSUES_PER_REPO`` via
    ``default_parallel_limit``) fields are optional. The fifth field is
    positional, so overriding ``parallel_limit`` requires also writing the
    ``remote_name`` (use ``origin`` explicitly to keep the default).
    Blank lines and lines starting with ``#`` are skipped. ``;`` is also
    accepted as an entry separator so the value fits on a single line in a
    ``.env`` file (the simple parser in `_dotenv.load_dotenv` cannot
    represent multi-line values). Aborts (SystemExit) on malformed entries or
    duplicate slugs. It reads only the value: whether each ``target_root`` is
    a checkout is ``build_repo_specs``'s question, asked once every entry has
    parsed.
    """
    specs: list[RepoSpec] = []
    seen_slugs: set[str] = set()
    for entry_no, line in iter_repos_entries(raw):
        entry = parse_repo_entry(entry_no, line, config_error)
        # Duplicate-slug rejection precedes option parsing so a repeated repo
        # aborts before any per-entry option error on the duplicate row.
        if entry.slug in seen_slugs:
            config_error(
                f"orchestrator: REPOS lists duplicate slug {entry.slug!r}; "
                "each repo can appear only once",
            )
        seen_slugs.add(entry.slug)
        specs.append(RepoSpec(
            slug=entry.slug,
            target_root=Path(entry.target_root),
            base_branch=entry.base_branch,
            remote_name=entry.remote_name,
            parallel_limit=_parse_parallel_limit(
                entry,
                default_parallel_limit,
                config_error,
            ),
        ))
    if not specs:
        config_error(
            "orchestrator: REPOS is set but contains no valid entries; "
            "provide at least one 'owner/name|target_root|base_branch' entry, "
            "or unset it to fall back to the developer settings when running "
            "from a source checkout"
        )
    return specs


def _require_checkouts(
    specs: list[RepoSpec],
    setting: str,
    config_error: ConfigError,
) -> None:
    """Abort unless every selected target is a git checkout.

    Every target is inspected before the abort, so one start names each
    unusable target rather than the first of them.
    """
    problems: list[str] = []
    for spec in specs:
        problem = checkout_problem(spec.target_root)
        if problem is not None:
            problems.append(
                f"orchestrator: {setting} target {spec.target_root} for "
                f"{spec.slug!r} {problem}; point it at a local clone or "
                f"linked worktree of {spec.slug}",
            )
    if problems:
        config_error("\n".join(problems))


def build_repo_specs(
    repos_raw: str,
    *,
    default_spec: RepoSpec | None,
    default_parallel_limit: int,
    config_error: ConfigError,
) -> list[RepoSpec]:
    """Select the configured targets and hold each to a git checkout.

    One element per ``REPOS`` entry whenever ``REPOS`` is set, whatever the
    developer settings say, with ``default_parallel_limit`` (i.e.
    ``MAX_PARALLEL_ISSUES_PER_REPO``) as each entry's ``parallel_limit``
    default. Unset, it is the single ``default_spec`` -- the developer
    fallback built from ``REPO`` / ``TARGET_REPO_ROOT`` / ``BASE_BRANCH`` /
    ``REMOTE_NAME`` -- which the caller passes only for a package running from
    a verified source checkout; ``None`` is an installed package, where an
    unset ``REPOS`` aborts rather than fall back to any target. Whichever was
    selected, every target has to be a checkout before this returns.
    """
    if repos_raw.strip():
        specs = parse_repos_env(
            repos_raw,
            default_parallel_limit=default_parallel_limit,
            config_error=config_error,
        )
        setting = "REPOS"
    elif default_spec is None:
        config_error(_REPOS_REQUIRED)
    else:
        specs = [default_spec]
        setting = "TARGET_REPO_ROOT"
    _require_checkouts(specs, setting, config_error)
    return specs
