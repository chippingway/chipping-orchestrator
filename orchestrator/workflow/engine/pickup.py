# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The first tick an unlabeled issue gets, and the anchors it leaves behind.

Two decisions live here and nothing else does. `ALLOWED_ISSUE_AUTHORS` decides
whether the orchestrator answers an unlabeled issue at all -- it is the abuse
guard that keeps a stranger on a public repo from spending agent budget, and it
fires only on this path, so a maintainer who labels an outsider's issue by hand
still drives it through every later stage. `DECOMPOSE` decides which stage
answers: `decomposing` normally, or `implementing` directly when the switch is
off.

Both starts then write the same four things in the same order, because
everything downstream reads them back. The pickup comment goes first so its id
can anchor the thread records: `pickup_comment_id`, which says this issue's
pickup is announced -- a later `ready` handoff reads it rather than greeting
the issue a second time -- and `last_action_comment_id`, the reply boundary a
park waits above. Standing the boundary there hands nobody the thread beneath
it, so it records no delivery: what counts as answered feedback is the
stretch the first spawn's bounded prompt records as quoted
(`thread_delivery`), and a comment that prompt left out stays unread. A human
comment posted after the pickup -- a "do not merge yet" while the developer
ran -- is above both, and never consumed for being older than some later
post of ours. The `user_content_hash` baseline is computed after that comment
exists and with its id filtered out, so the orchestrator's own greeting is not
the first drift the next tick reports. The workflow label is written before the
pinned state so a crash between the two leaves an issue the next tick still
routes to the stage it was committed to, rather than an unlabeled one that would
be greeted a second time.

The chosen handler runs in the same tick rather than waiting for the next one:
the label write already committed the issue to that stage, so returning here
would buy nothing but a poll interval.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    usage as _usage,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _pickup_author_allowed(spec: _config_models.RepoSpec, issue: Issue) -> bool:
    # Author allowlist: when configured, silently skip unlabeled issues from
    # anyone outside the list so random users can't burn agent budget on a
    # public repo. Maintainers can still drive an outsider's issue manually
    # by adding a workflow label themselves -- the guard only fires here.
    if not config.ALLOWED_ISSUE_AUTHORS:
        return True
    author = getattr(getattr(issue, "user", None), "login", None) or ""
    allowed = {
        github_handle.lower()
        for github_handle in config.ALLOWED_ISSUE_AUTHORS
    }
    if author.lower() in allowed:
        return True
    log.info(
        "repo=%s issue=#%s author=%r not in ALLOWED_ISSUE_AUTHORS; skipping pickup",
        spec.slug, issue.number, author,
    )
    return False


def _record_pickup_comment(state: PinnedState, pickup) -> None:
    """Anchor the thread records on the comment this pickup just posted.

    `pickup_comment_id` records the announcement, which the `ready` handoff
    reads so it posts no second one. The shared `last_action_comment_id` is
    the reply boundary: nothing already on the thread is a reply to anything,
    and it is the floor the park ending the first agent run walks from, which
    may not read the thread's tip. Standing it there delivers nothing, and
    records nothing as delivered: the spawn below quotes this thread bounded,
    and only what that prompt records as quoted (`thread_delivery`) may count
    as answered feedback.
    """
    pickup_id = getattr(pickup, "id", None)
    if pickup_id is not None:
        state.set("pickup_comment_id", int(pickup_id))
        state.set("last_action_comment_id", int(pickup_id))


def _start_decomposing(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> None:
    # The handler is reached through a call-time import: the stage tree imports
    # this subpackage, so binding it at module scope would point that edge back
    # at itself. The owner named here is the one `_STAGE_HANDLER_TARGETS` names,
    # so a patch here lands where dispatch patches.
    from orchestrator.workflow.stages.decomposition.run import _handle_decomposing

    pickup = _comments._post_issue_comment(
        gh, issue, state,
        ":robot: orchestrator picking this up; decomposing.",
    )
    _record_pickup_comment(state, pickup)
    state.set(
        "user_content_hash",
        _content_hash._compute_user_content_hash(issue, _comments._orchestrator_ids(state)),
    )
    gh.set_workflow_label(issue, WorkflowLabel.DECOMPOSING)
    gh.write_pinned_state(issue, state)
    _handle_decomposing(gh, spec, issue)


def _start_implementing(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> None:
    # Legacy path with DECOMPOSE=off: skip decomposition entirely and route
    # the unlabeled issue straight to implementing, exactly as the
    # bootstrap-milestone code did.
    from orchestrator.workflow.stages.implementing.handler import _handle_implementing

    pickup = _comments._post_issue_comment(
        gh, issue, state,
        ":robot: orchestrator picking this up. Decomposition stage is "
        "disabled; going straight to implementation.",
    )
    _record_pickup_comment(state, pickup)
    state.set(
        "user_content_hash",
        _content_hash._compute_user_content_hash(issue, _comments._orchestrator_ids(state)),
    )
    gh.set_workflow_label(issue, WorkflowLabel.IMPLEMENTING)
    gh.write_pinned_state(issue, state)
    _handle_implementing(gh, spec, issue)


def _handle_pickup(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    if not _pickup_author_allowed(spec, issue):
        return
    state = PinnedState()
    state.set("created_at", _usage._now_iso())
    if config.DECOMPOSE:
        _start_decomposing(gh, spec, issue, state)
    else:
        _start_implementing(gh, spec, issue, state)
