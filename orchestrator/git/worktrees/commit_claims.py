# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a terminal pull request already published a branch tip.

The second way a commit the base does not contain can still be safe to
delete. The first is the base itself; this is the pull request the commit went
out on and a human then closed without merging -- rejected work is still
published work, and the branch is a local copy of something GitHub has.

A different question from the ones the ``claims`` sibling puts. Those are
about the issue -- whether it ended, and whether anybody is still standing on
the branches it was published under -- and either settles a candidate before
any artifact is read. This one is about a single object id, and it is asked
last, once the base has been asked and had nothing to say: not whether the
work is finished, but whether deleting this commit loses it.

Exact, and it is the commit that makes it so. The lookup is by object id
rather than by branch name, so a pull request that once used this branch for
some earlier round does not account for what is on it now.

No base is named, for the same reason the open-pull-request claim names none:
what makes the commit safe to delete is that GitHub holds it, and a pull
request retargeted onto another base holds it exactly as well. Filtered by the
configured base, that publication would read as no publication at all and the
branch carrying it would be reclaimed.

The read is behind its own boundary, and the boundary produces a retention
rather than a raise or a default. A lookup that failed is not "no pull
request": read that way round, the reclamation deletes an unpublished branch
on the strength of a question nobody could put.
"""
from __future__ import annotations

import logging

from orchestrator.git.worktrees.models import Retention, RetentionReason
from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.github.client import GitHubClient

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so a question that could not be put
# reports where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

_OPEN_PULL_REQUEST = "open"


def _commit_accounting(
    gh: GitHubClient, branch: str, head_sha: str,
) -> tuple[Retention, ...]:
    """Whether a terminal pull request exactly accounts for one branch tip.

    The boundary around the lookup rather than the lookup itself. A pull
    request that CARRIES the tip has this exact commit under review, whether
    or not its head has moved past it since, and that is the only reading
    that reclaims.

    Three answers, and only one of them does. A lookup that could not be taken
    is retained on rather than read as "no pull request", because that reading
    is what deletes an unpublished branch. A pull request still open is
    retained on too -- the open-pull-request claim asked earlier should have
    caught it, and a disagreement between two readings of the same remote is
    not something to resolve in favour of deleting.
    """
    try:
        return _carrying_pull_request(gh, branch, head_sha)
    except Exception:
        log.warning(
            "the pull requests carrying %s on %r could not be read while "
            "classifying artifacts", head_sha, branch, exc_info=True,
        )
        return (Retention(
            RetentionReason.PULL_REQUEST_UNREADABLE, branch,
        ),)


def _carrying_pull_request(
    gh: GitHubClient, branch: str, head_sha: str,
) -> tuple[Retention, ...]:
    """The accounting itself, inside the boundary that owns its failures.

    Split from the boundary rather than written under it so the lookup and
    the state read it walks into are one guarded step: the pull request comes
    back lazy, so reading its state is another request, and a caller told
    only about the first would take a failure in the second as a pull request
    that is not open.
    """
    accounted = gh.find_pr_for_commit(branch=branch, head_sha=head_sha)
    if accounted is _pr_reads.PR_LOOKUP_UNREADABLE:
        return (Retention(
            RetentionReason.PULL_REQUEST_UNREADABLE, branch,
        ),)
    if accounted is None:
        return (Retention(RetentionReason.UNACCOUNTED_COMMITS, branch),)
    if gh.pr_state(accounted) == _OPEN_PULL_REQUEST:
        return (Retention(RetentionReason.OPEN_PULL_REQUEST, branch),)
    return ()
