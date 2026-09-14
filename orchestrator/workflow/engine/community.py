# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The open PRs this orchestrator never opened, and the one ping each earns.

This pass has no per-issue home. A PR opened by somebody else carries no pinned
state for a handler to consult, so nothing dispatches it and the tick drives
the sweep itself instead -- once, ahead of the scheduler / in-tick split, so a
newly opened outsider PR is answered on either dispatch path.

`ALLOWED_ISSUE_AUTHORS` is what decides there is anything to sweep at all. An
empty list is the default, and it leaves a single-user deployment the legacy
"anyone is trusted" behavior: the sweep returns before it costs a request.

The label is the sweep's own dedup marker rather than an operator control,
which is why the ping is posted BEFORE it. A label write that fails repeats a
ping on the next tick; a label written ahead of a comment that fails would
suppress the ping forever and no human would ever be called. Both spellings are
read for the same reason -- a PR labeled on a repository the bootstrap rename
could not reach has already had its one ping, and re-labeling it would repeat
that ping.

Nothing here may raise. The enumeration and each per-PR step are caught
separately, so a PyGithub lazy-load failure on one PR costs that PR's ping
rather than the rest of the sweep, and the sweep cannot cost the tick its
issues.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.labels import (
    COMMUNITY_CONTRIBUTION_LABEL,
    COMMUNITY_CONTRIBUTION_LABEL_NAMES,
)

log = logging.getLogger("orchestrator.workflow")


@dataclass(frozen=True)
class _CommunityContribution:
    author: str


def _has_contribution_label(gh: GitHubClient, pr) -> bool:
    """Whether the sweep already marked this PR, under either spelling.

    A PR labeled before the namespace -- on a repository whose label the
    bootstrap rename could not reach -- has already had its one HITL ping.
    """
    return any(
        gh.pr_has_label(pr, label_name)
        for label_name in COMMUNITY_CONTRIBUTION_LABEL_NAMES
    )


def _community_contribution_for_pr(
    gh: GitHubClient, pr, allowed_lower: set[str],
) -> _CommunityContribution | None:
    user = getattr(pr, "user", None)
    if getattr(user, "type", None) == "Bot":
        return None
    author = getattr(user, "login", None) or ""
    if author.lower() in allowed_lower:
        return None
    if _has_contribution_label(gh, pr):
        return None
    return _CommunityContribution(author)


def _label_community_contribution(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    pr,
    contribution: _CommunityContribution,
) -> None:
    # The label is the dedup marker, so the ping must land first. A label
    # failure may repeat a ping; a comment failure must not suppress one.
    author = contribution.author or "unknown"
    gh.pr_comment(
        pr.number,
        f"{config.HITL_MENTIONS} community contribution from "
        f"@{author} -- please review this PR.",
    )
    gh.add_pr_label(pr, COMMUNITY_CONTRIBUTION_LABEL)
    log.info(
        "repo=%s pr=#%s author=%r pinged HITL and labeled %r",
        spec.slug, pr.number, contribution.author, COMMUNITY_CONTRIBUTION_LABEL,
    )


def _sweep_pr_contribution(
    gh: GitHubClient, spec: _config_models.RepoSpec, pr, allowed_lower: set,
) -> None:
    """Label one open PR when its author is an outside community contributor."""
    contribution = _community_contribution_for_pr(gh, pr, allowed_lower)
    if contribution is not None:
        _label_community_contribution(gh, spec, pr, contribution)


def _sweep_community_contribution_prs(
    gh: GitHubClient, spec: _config_models.RepoSpec
) -> None:
    """Label open PRs from authors outside ALLOWED_ISSUE_AUTHORS and ping HITL.

    Every open PR whose author is not in the list earns the
    `workflow:community_contribution` label and a one-shot HITL ping comment;
    a PR already carrying either spelling of that label is skipped, so the
    comment fires exactly once per PR.

    Bot-authored PRs (Dependabot, Renovate, CI bots) are skipped by GitHub's
    `user.type == "Bot"` flag -- they open PRs structurally and are not
    community contributions, so they never earn the label or ping.
    """
    allowed = config.ALLOWED_ISSUE_AUTHORS
    if not allowed:
        return
    allowed_lower = {github_handle.lower() for github_handle in allowed}
    try:
        prs = list(gh.iter_open_prs())
    except Exception:
        log.exception(
            "repo=%s community-contribution sweep: open-PR enumeration failed",
            spec.slug,
        )
        return
    for pr in prs:
        try:
            _sweep_pr_contribution(gh, spec, pr, allowed_lower)
        except Exception:
            log.exception(
                "repo=%s pr=#%s community-contribution sweep step failed; continuing",
                spec.slug, getattr(pr, "number", "?"),
            )
