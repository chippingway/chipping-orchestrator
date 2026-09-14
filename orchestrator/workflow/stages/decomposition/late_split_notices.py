# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publish late-split forward links and word cycle-bound supersession notices.

A thread receipt recovers an announcement whose pinned write was lost.
Every notice retains the exact snapshot, candidate, and ordered children.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.github import comments as _github_comments
from orchestrator.workflow.engine import comments as _comments, usage as _usage
from orchestrator.workflow.late_split import (
    phases as _late_phases,
)
from orchestrator.workflow.late_split.models import (
    LateGeneration,
)
from orchestrator.workflow.stages.decomposition import (
    late_park_state as _late_park_state,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.models import _SplitPlan

_DECOMPOSED_AT = "decomposed_at"


# Stamped on the two comments this transaction owes, so a retry recognizes one
# it posted even when the write that was supposed to record it never landed.
# Both are scoped to the exact adjudication: a pull request outlives a cycle
# and an issue thread outlives everything, so an unscoped marker would
# read an earlier episode's receipt as this one's. HTML comments, so neither is
# visible in the rendered thread.
_SUPERSESSION_MARKER = (
    "<!--orchestrator-late-supersession:issue={issue}"
    ":cycle={cycle}:generation={generation}-->"
)


_FORWARD_LINK_MARKER = (
    "<!--orchestrator-late-split:cycle={cycle}:generation={generation}-->"
)


_FORWARD_LINKS = (
    ":scissors: the late decomposer read the committed candidate `{sha}` as "
    "{count} separable changes, so this issue becomes an umbrella and the "
    "work is handed to its children:\n\n{children}\n\nThe committed work is "
    "preserved on the immutable ref `{ref}` at `{sha}`; each child reuses the "
    "part of it their own scope covers. This issue has no implementation of "
    "its own and closes once every child resolves.\n\n{marker}"
)


_SUPERSESSION_NOTICE = (
    ":scissors: **Superseded.** The committed implementation for issue "
    "#{parent} was adjudicated as {count} separable changes, so this pull "
    "request is closed without merging and issue #{parent} is now an "
    "umbrella.\n\nThe work it carried is preserved on the immutable ref "
    "`{ref}` at `{sha}` -- nothing is lost, and each child reuses the part of "
    "it their scope covers:\n\n{children}\n\n{marker}"
)


def _announced(
    context: _LateContext, plan: _SplitPlan, snapshot_ref: str,
) -> None:
    """Say on the parent what it became, exactly once.

    Two gates, because neither answers the whole question on its own. The
    generation's own `links_announced` flag is the cheap one and the one that
    holds on the ordinary retry -- it is scoped to this adjudication, unlike
    `decomposed_at`, which an EARLIER decomposition of the same issue already
    wrote and which would therefore suppress this announcement entirely. The
    thread is the expensive one and the one that covers the window the flag
    cannot: a comment that landed and a process that died before the write is
    indistinguishable from the outside, so the marker this generation stamps
    into its own sentence is looked for among the comments before another is
    posted. It is asked only when the flag is unset, so a resume past the
    announcement costs nothing.

    `decomposed_at` is written all the same, because it is what the stage's
    own readers date a decomposition by; it is simply not this step's receipt.
    """
    if context.generation.links_announced:
        return
    if not _links_on_thread(context):
        _comments._post_issue_comment(
            context.gh,
            context.issue,
            context.state,
            _FORWARD_LINKS.format(
                sha=context.generation.candidate_sha,
                count=len(plan.created),
                children=_child_lines(plan),
                ref=snapshot_ref,
                marker=_forward_marker(context.generation),
            ),
        )
    context.state.set(_DECOMPOSED_AT, _usage._now_iso())
    context.generation = replace(
        context.generation,
        phase=_late_phases.LatePhase.SUPERSEDING,
        links_announced=True,
    )
    _late_park_state._persist(context)


def _links_on_thread(context: _LateContext) -> bool:
    """Whether this generation's own forward links are already said.

    Walked whole rather than from a watermark: the post moves every watermark
    this mode keeps past itself, so a scan bounded by one would start above
    the very comment it is looking for.
    """
    return _github_comments.carries_own_marker(
        context.gh.comments_after(context.issue, None),
        _forward_marker(context.generation),
        bot_login=getattr(context.gh, "_bot_login", None),
    )


def _forward_marker(generation: LateGeneration) -> str:
    """The receipt this generation's forward-link comment carries."""
    return _FORWARD_LINK_MARKER.format(
        cycle=generation.cycle_id, generation=generation.generation,
    )


def _supersession_marker(context: _LateContext) -> str:
    """The receipt this generation's supersession notice carries."""
    return _SUPERSESSION_MARKER.format(
        issue=context.issue.number,
        cycle=context.generation.cycle_id,
        generation=context.generation.generation,
    )


def _supersession_notice(
    context: _LateContext, plan: _SplitPlan, snapshot_ref: str,
) -> str:
    """What either road tells the pull request it is closing.

    One sentence for both, because what it says is a fact about the SPLIT
    rather than about which pull request carried the work: the umbrella it
    became, the children it went to, the ref it is preserved on, and the exact
    commit. Which pull request hears it is the caller's question.
    """
    return _SUPERSESSION_NOTICE.format(
        parent=context.issue.number,
        count=len(plan.created),
        ref=snapshot_ref,
        sha=context.generation.candidate_sha,
        children=_child_lines(plan),
        marker=_supersession_marker(context),
    )


def _child_lines(plan: _SplitPlan) -> str:
    """The forward links one split owes every reader of it."""
    return "\n".join(
        f"- #{number}: {child['title']}" for number, child in plan.created
    )
