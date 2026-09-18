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
can anchor `pickup_comment_id`: the validating handoff seeds its watermark past
the orchestrator's own comments, and with no anchor the earliest bot id it can
find is a much later "PR opened" or approval -- which would silently consume
every human comment in between, including a "do not merge yet" posted while the
developer ran. The `user_content_hash` baseline is computed after that comment
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
    """Anchor both thread cursors on the comment this pickup just posted.

    `pickup_comment_id` is the validating handoff's floor; the shared
    `last_action_comment_id` is every other reader's, and an issue that starts
    without one starts with no floor at all. The first agent this pickup
    spawns runs for minutes, and the park that ends it may only record the
    thread read as far as it can walk our own identified comments -- a walk
    with nothing under it has nowhere to start, and reading the thread's tip
    instead would cross whatever a human wrote while that agent was out.

    Saying it here is saying something true rather than convenient: the spawn
    below quoted this thread as it stands to the agent, so what is on it has
    been delivered, and the comment we just posted is the last word of that
    reading.
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
    # Anchor the validating-handoff seed-watermark on the exact pickup
    # comment id. Without this, an issue that started under an older
    # version of the orchestrator (where bot ids were not tracked) would
    # have its first recorded bot id be a much later comment (PR-opened or
    # approval), causing `_seed_watermark_past_self` to silently advance
    # past every issue/PR comment in between -- including any human
    # "do not merge yet" posted during implementing.
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
