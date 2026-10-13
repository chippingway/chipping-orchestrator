# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reading a finished docs run, in the order the checks have to happen.

A run an account quota stopped is asked about before either check below
would park it: past its timeout or over a dirty tree it parks as the session
limit, through the shared question park, since both of those parks would
leave the operator without the reset and the retry a quota needs. A timeout
is answered next because nothing the run left on disk can be trusted, and
parks as `agent_timeout`. The dirty-tree check is third and blocks every
outcome after it: a push ships only committed work, so an agent that edited
files without committing would have its edits silently dropped by the
publication path and silently abandoned by the no-change and question paths
alike.

A run that did not succeed is refused every outcome past that
(`failed_pass._fell_short`): an unfinished tool step, the failure record a
backend keeps of a run it normalized to a failure -- Antigravity's error,
cancelled, interrupted, or missing terminal result -- or an Antigravity
process that exited nonzero behind a terminal that said it succeeded. Its
commit, the tool calls it completed, and a `DOCS: NO_CHANGE` it wrote are none
of them a finished pass, so it parks through the shared question classifier,
handed no final message, which names a quota as the session limit, an
unfinished step as an execution failure, and the rest as a silent exit. The
commit stays on the branch unpublished, and the retry a human authorizes
reruns the full documentation prompt over it, so only a pass that succeeds
publishes it. Only then does the `before_sha` comparison get to say whether
THIS run produced a commit.

On a clean tree with no new commit the agent either checked the diff and found
nothing to write, or it stopped for some other reason. The explicit
`DOCS: NO_CHANGE` marker is the only thing that distinguishes the two -- an
absent marker is not agreement, so anything else parks for a human rather than
advancing an issue whose docs were never actually reviewed.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator import config
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import completion_verdicts as _completion_verdicts
from orchestrator.workflow.stages.documenting import (
    failed_pass as _failed_pass,
    models as _models,
    parks as _parks,
    publication as _publication,
)
from orchestrator.workflow.stages.implementing import session_read as _session_read


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


def _parks_a_quota_stop(
    ctx: _models._DocumentingContext, run: _models._DocumentingRun, wt,
) -> bool:
    """Park a run an account quota stopped as the session limit where a timeout or an unclean tree would park it.

    Returns True where it parked. Unclean is anything short of a status that
    PROVED the tree clean: a status nobody could take lists no paths, and read
    as clean it would hand the publication a checkout nothing vouched for. The timeout's park would drop the quota,
    its reset, and the diagnostics, and the dirty-tree park pins no retryable
    reason, so the bare continue a quota needs would be refused. Nothing is
    published either way, and the uncommitted edits stay in the checkout for
    the developer that continue resumes. A quota stop over a clean tree reads
    on to the failed-run park below, whose classifier names it the session
    limit too.
    """
    agent_result = run.agent_result
    if not _session_read._is_session_limit(agent_result):
        return False
    if not agent_result.timed_out and _worktree_status._worktree_status(wt).is_clean:
        return False
    _parks._park_documenting_question(ctx, agent_result, before_sha=run.before_sha)
    return True


def _dispose_documenting_outcome(
    ctx: _models._DocumentingContext, run: _models._DocumentingRun,
) -> None:
    """Route the post-agent outcome: timeout / dirty / failed run / commit /
    no-change / question.

    Writes pinned state on every terminal branch; the caller returns
    unconditionally.
    """
    wt = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    # Every branch below writes pinned state, and that write records what
    # answers for the launch -- a park or a publication -- so the record the
    # launch landed goes with it.
    _failed_pass._forget(ctx.state)
    if _parks_a_quota_stop(ctx, run, wt):
        return
    if run.agent_result.timed_out:
        _parks._park_documenting(
            ctx,
            f"{config.HITL_MENTIONS} agent timed out after "
            f"{config.AGENT_TIMEOUT}s, manual intervention needed.",
            "agent_timeout",
        )
        return

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

    if _failed_pass._fell_short(ctx, run.agent_result):
        # Classified with no final message, as Antigravity hands back every
        # run it failed: a response its own nonzero exit followed is no answer
        # a human owes guidance on, so it parks as the retryable silent exit
        # rather than as a question a bare continue would be refused on.
        _parks._park_documenting_question(
            ctx, replace(run.agent_result, last_message=""), before_sha=run.before_sha,
        )
        return

    if after_sha and after_sha != run.before_sha:
        _publication._push_docs_and_advance(
            ctx, wt, after_sha,
            _publication._documenting_commit_notice(run.recovered),
            entered_head=run.entered_head,
        )
        return

    _dispose_documenting_clean(ctx, wt, run, after_sha)
