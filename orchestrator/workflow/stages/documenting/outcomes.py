# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reading a finished docs run, in the order the checks have to happen.

A timeout is answered first because nothing the run left on disk can be
trusted. The dirty-tree check is second and blocks every outcome after it: a
push ships only committed work, so an agent that edited files without
committing would have its edits silently dropped by the publication path and
silently abandoned by the no-change and question paths alike. Only then does
the `before_sha` comparison get to say whether THIS run produced a commit.

On a clean tree with no new commit the agent either checked the diff and found
nothing to write, or it stopped for some other reason. The explicit
`DOCS: NO_CHANGE` marker is the only thing that distinguishes the two -- an
absent marker is not agreement, so anything else parks for a human rather than
advancing an issue whose docs were never actually reviewed.
"""
from __future__ import annotations

from orchestrator.config import settings as config
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import completion_verdicts as _completion_verdicts
from orchestrator.workflow.stages.documenting import (
    models as _models,
    parks as _parks,
    publication as _publication,
)


def _dispose_documenting_clean(
    ctx: _models._DocumentingContext,
    wt,
    run: _models._DocumentingRun,
    after_sha: str,
) -> None:
    """No new commit on a clean tree: the agent either declared no change or
    asked a question. The explicit `DOCS: NO_CHANGE` marker is the only signal
    that confirms the diff was checked and nothing was needed; anything else
    parks via `_on_question`."""
    verdict, body = _completion_verdicts._parse_documentation_verdict(
        run.agent_result.last_message or "",
    )
    if verdict == "no_change":
        _publication._route_documenting_no_change(ctx, wt, run, after_sha, body)
        return
    _parks._park_documenting_question(ctx, run.agent_result)


def _dispose_documenting_outcome(
    ctx: _models._DocumentingContext, run: _models._DocumentingRun,
) -> None:
    """Route the post-agent outcome: timeout / dirty / commit / no-change
    / question.

    Writes pinned state on every terminal branch; the caller returns
    unconditionally.
    """
    if run.agent_result.timed_out:
        _parks._park_documenting(
            ctx,
            f"{config.HITL_MENTIONS} agent timed out after "
            f"{config.AGENT_TIMEOUT}s, manual intervention needed.",
            "agent_timeout",
        )
        return

    wt = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    after_sha = _verification_probes._head_sha(wt)

    # A dirty worktree blocks every downstream outcome -- commit + push would
    # publish a branch that omits the dirty files, and the no-change /
    # on_question paths would silently leave docs edits behind on disk that the
    # eventual reviewer never sees. Check before any other decision so an agent
    # that edited files without committing (and then either emitted
    # `DOCS: NO_CHANGE`, asked a question, or produced nothing) cannot slip past.
    dirty = _worktree_status._worktree_dirty_files(wt)
    if dirty:
        _parks._park_documenting_dirty(ctx, run.agent_result, dirty)
        return

    if after_sha and after_sha != run.before_sha:
        _publication._push_docs_and_advance(
            ctx, wt, after_sha,
            _publication._documenting_commit_notice(run.recovered),
            entered_head=run.entered_head,
        )
        return

    _dispose_documenting_clean(ctx, wt, run, after_sha)
