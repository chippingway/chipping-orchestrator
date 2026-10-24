# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The open PRs this orchestrator never opened, and the one ping each earns.

This pass has no per-issue home. A PR opened by somebody else carries no pinned
state for a handler to consult, so nothing dispatches it and the tick drives
the sweep itself instead -- once, ahead of the scheduler / in-tick split, so a
newly opened outsider PR is answered on either dispatch path.

`ALLOWED_ISSUE_AUTHORS` is what decides there is anything to sweep at all. An
empty list -- which startup refuses to run on -- trusts every author, so the
sweep returns before it costs a request. A PR that is an issue's own artifact
is never swept, listed or not -- one the token's own account opened, or one
standing on a branch of this repository in the orchestrator-owned namespace,
which a publication adopts whoever opened it: what is written to it is that
issue's dispatch to decide, refusals included.

The label is the sweep's own dedup marker rather than an operator control,
which is why the ping is posted BEFORE it. A label write that fails repeats a
ping on the next tick; a label written ahead of a comment that fails would
suppress the ping forever and no human would ever be called. Only the
namespaced label is that marker: a bare `community_contribution` is one of the
repository's own labels, so a PR carrying nothing else is pinged and marked
like any unmarked PR, and keeps the bare label beside the namespaced one.

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
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.labels import COMMUNITY_CONTRIBUTION_LABEL

log = logging.getLogger("orchestrator.workflow")


@dataclass(frozen=True)
class _CommunityContribution:
    author: str


def _community_contribution_for_pr(
    gh: GitHubClient, pr, allowed_lower: set[str],
) -> _CommunityContribution | None:
    user = getattr(pr, "user", None)
    if getattr(user, "type", None) == "Bot":
        return None
    author = getattr(user, "login", None) or ""
    if author.lower() in allowed_lower or _an_issue_artifact(gh, pr, author):
        return None
    if gh.pr_has_label(pr, COMMUNITY_CONTRIBUTION_LABEL):
        return None
    return _CommunityContribution(author)


def _an_issue_artifact(gh: GitHubClient, pr, author: str) -> bool:
    """Whether the PR is an issue's own artifact rather than a contribution.

    Either of two existing ownership rules is enough. The account behind this
    client's token opened it -- matched exactly, as the pinned state's author
    is; a client that does not know its own login answers that half for
    nobody. Or its head is a branch of this very repository in the
    orchestrator-owned namespace (`git/worktrees/naming.py`), where every issue
    branch lives: a publication adopts the open pull request standing on its
    issue's branch whoever opened it, so such a PR is that issue's whatever its
    author. A fork's branch of the same name is no branch of this repository.

    Either way what is written to it is that issue's dispatch to decide --
    nothing at all where the issue's pinned record is one admission refuses --
    so the sweep never writes to it, whether or not its author is listed.
    """
    own_login = getattr(gh, "_bot_login", None)
    if own_login is not None and author == own_login:
        return True
    head = getattr(pr, "head", None)
    head_ref = getattr(head, "ref", None) or ""
    return head_ref.startswith(_naming._OWNED_NAMESPACE) and gh.is_own_repository(
        getattr(getattr(head, "repo", None), "full_name", None),
    )


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
    a PR already carrying that label is skipped, so the comment fires exactly
    once per PR.

    Bot-authored PRs (Dependabot, Renovate, CI bots) are skipped by GitHub's
    `user.type == "Bot"` flag -- they open PRs structurally and are not
    community contributions, so they never earn the label or ping. So are an
    issue's own PRs: the token's own account's, and any standing on this
    repository's orchestrator-owned branches.
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
