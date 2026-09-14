# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Why a run that produced no publishable commit stopped, and what that costs.

A commit-less run reaches exactly one of four parks, and the difference
between them is not cosmetic: `park_reason` is the field
`/orchestrator continue` keys off. A quota notice, a provider that refused to
serve the turn, and an empty result are all tagged `agent_silent` -- retryable
session failures an operator can continue once the other side is back -- and
all advance the silent-park streak that eventually rotates a poisoned session
to a fresh spawn. What makes the first two worth separating from a real
question is that both arrive as ORDINARY non-empty final messages: the text
the CLI hands back is the refusal, not the agent's words, so the field a
question is read off says nothing about the run. A real question is the
opposite: it clears the reason and zeroes the streak, because it needs a
human's words before anything should run again, and a stale transient reason
left behind would let a later tick auto-recover over a question nobody
answered.

The dirty-worktree park is the fifth, and it exists to refuse a push rather
than to explain a failure: the branch would omit the uncommitted files, so the
PR would not match what the agent produced. A tree nothing could READ is that
same refusal with the other half missing -- `git status` failing, or an index
entry git was told to stop comparing, establishes nothing about what the
checkout carries -- and it is its own park because what an operator has to fix
there is a repository rather than a file list. Every park here posts the HITL
comment, ratchets `last_action_comment_id` past its own notice so the next tick
reads the human's reply and not that notice, and emits `park_awaiting_human` --
but leaves the pinned-state write to the handler, so the park composes with
whatever else that tick staged.

Past its own notice and no FURTHER, which is the whole of what a run these
parks end can be interleaved with. An agent takes minutes, and a human writing
in that window has written something nothing here has read: ratcheted to
whatever the thread ends on, the notice this park posts carries the watermark
over their comment and it is skipped for good. On this stage that comment can
be the `/orchestrator authorize-oversized` an adjudicated candidate is waiting
for, and the road that could act on it never sees it.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents import provider_failures as _provider_failures
from orchestrator.agents.models import AgentResult
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import agent_diagnostics as _agent_diagnostics, comments as _comments
from orchestrator.workflow.stages.implementing import (
    session_read as _session_read,
    state as _state,
)
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")


def _mark_agent_silent_park(state: PinnedState) -> None:
    """Flag a retryable `agent_silent` park and advance the silent-park streak.

    Shared by the session-limit and empty-output parks: both are retryable
    `agent_silent` failures, not real questions. `_resume_dev_with_text` reads
    the streak (via `_dev_session_retirement_reason`) to rotate a poisoned
    session to a fresh spawn once it reaches `_SILENT_PARKS_BEFORE_FRESH_SESSION`.
    """
    count = int(state.get(_state._SILENT_PARK_COUNT) or 0)
    state.set(_state._AWAITING_HUMAN, True)
    state.set(_state._PARK_REASON, "agent_silent")
    state.set(_state._SILENT_PARK_COUNT, count + 1)


def _park_session_limit(
    gh: GitHubClient, issue: Issue, state: PinnedState, raw: str
) -> str:
    """Park a session/usage-quota notice as a RETRYABLE session failure.

    A known quota notice ("You've hit your session limit ...") is non-empty but
    is NOT a real agent question: the session is healthy, the account quota is
    exhausted, and the only recovery is to wait for the reset and retry.
    Parking it as `agent_silent` (the same reason a silent poisoned resume
    uses) lets an operator's `/orchestrator continue` after the reset drop the
    session and re-ground a fresh one; classifying it as a real question
    (`park_reason=None`) would refuse that continue as "needs your actual
    guidance". The silent-park streak is incremented so a session that keeps
    returning the quota notice is eventually rotated, mirroring the
    empty-message branch. Returns the distinct EVENT reason
    (`agent_session_limit`) for observability -- the pinned `park_reason` stays
    `agent_silent` (the control field `/orchestrator continue` keys off).
    """
    quoted = _session_read._as_blockquote(raw)
    _comments._post_issue_comment(
        gh, issue, state,
        f"{config.HITL_MENTIONS} agent hit a session/usage limit and "
        "stopped; retry with `/orchestrator continue` once it "
        f"resets:\n\n{quoted}",
    )
    _mark_agent_silent_park(state)
    return "agent_session_limit"


def _park_provider_unavailable(
    gh: GitHubClient, issue: Issue, state: PinnedState, raw: str
) -> str:
    """Park a transient provider refusal as a RETRYABLE session failure.

    An `API Error: 529 Overloaded` reaches this stage as an ordinary non-empty
    final message, so without this branch it would be posted as "agent needs
    your input" -- a question the operator cannot answer, whose reply then
    RESUMES the same session and gets the same refusal back. The park is the
    one a quota stop takes: `agent_silent`, so `/orchestrator continue` drops
    the failed session, re-grounds a fresh one on the preserved fixing batch,
    and skips the feedback debounce. The bookmarks that batch is rebuilt from
    (`pending_fix_*`, `pending_fix_reviewer_comment_id`) are untouched here --
    only a pushed fix retires them.

    The comment names the command verbatim because a retry is the whole
    recovery and any other reply would be read as implementation guidance.
    Returns the distinct EVENT reason for observability; the pinned
    `park_reason` stays `agent_silent`.
    """
    quoted = _session_read._as_blockquote(raw)
    _comments._post_issue_comment(
        gh, issue, state,
        f"{config.HITL_MENTIONS} the model provider is temporarily "
        "unavailable, so the agent stopped before doing any work. Nothing "
        "here needs your judgment: reply with exactly `/orchestrator "
        "continue` to retry this on a fresh session.\n\n"
        f"{quoted}",
    )
    _mark_agent_silent_park(state)
    return "agent_provider_unavailable"


def _park_real_question(
    gh: GitHubClient, issue: Issue, state: PinnedState, raw: str
) -> str:
    """Park a genuine agent clarification question awaiting a human reply."""
    quoted = _session_read._as_blockquote(raw)
    _comments._post_issue_comment(
        gh, issue, state,
        f"{config.HITL_MENTIONS} agent needs your input to proceed:\n\n{quoted}",
    )
    state.set(_state._AWAITING_HUMAN, True)
    # Real question parks are not transient: they need a human reply before the
    # in_review ready-ping gates should run again. Clear any stale
    # `park_reason` left behind by a prior in_review unmergeable park, and reset
    # the silent-park streak.
    state.set(_state._PARK_REASON, None)
    state.set(_state._SILENT_PARK_COUNT, 0)
    return "agent_question"


def _park_silent_failure(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    agent_result: AgentResult,
) -> str:
    """Park a run that produced no commit AND no message as a silent failure.

    Callers only invoke `_on_question` when the worktree has no new commits, so
    an empty `last_message` is a silent failure, not a content question -- most
    often a poisoned resume of a session killed mid-stream (e.g. by a Claude
    rate limit). Tag the park `agent_silent` so `_resume_dev_with_text` can
    drop the dev session id after enough consecutive silent parks, and surface
    the situation accurately instead of impersonating a real question park.
    """
    diag = _agent_diagnostics._format_stderr_diagnostics(agent_result, "Agent")
    _comments._post_issue_comment(
        gh, issue, state,
        f"{config.HITL_MENTIONS} agent produced no output (likely a "
        f"session-resume failure); manual intervention needed.{diag}",
    )
    log.warning(
        "issue=#%s agent produced no output; exit_code=%d "
        "timed_out=%s stderr_tail=%r",
        issue.number, agent_result.exit_code, agent_result.timed_out,
        _agent_diagnostics._stderr_log_tail(agent_result),
    )
    _mark_agent_silent_park(state)
    return "agent_silent"


def _on_question(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    agent_result: AgentResult,
) -> None:
    # Taken before anything is posted, because what separates this park's own
    # notice from a human's comment afterwards is which of them this ledger
    # gained.
    said_before = _comments._orchestrator_ids(state)
    raw = agent_result.last_message.strip()
    if raw and _session_read._is_session_limit_message(agent_result):
        park_reason = _park_session_limit(gh, issue, state, raw)
    elif raw and _provider_failures.is_transient_provider_failure(agent_result):
        park_reason = _park_provider_unavailable(gh, issue, state, raw)
    elif raw:
        park_reason = _park_real_question(gh, issue, state, raw)
    else:
        park_reason = _park_silent_failure(gh, issue, state, agent_result)
    read_to = _read_this_far(gh, issue, state, said_before)
    if read_to is not None:
        state.set(_state._LAST_ACTION_COMMENT_ID, read_to)
    gh.emit_event(
        "park_awaiting_human",
        issue_number=issue.number,
        stage=stage_name(gh.workflow_label(issue)),
        reason=park_reason,
    )


def _read_this_far(
    gh: GitHubClient, issue: Issue, state: PinnedState, said_before: set,
) -> int | None:
    """How far a park ending a RUN may record this thread as read.

    Past every comment of ours above the watermark and past nothing else. A
    park's notice has to carry the watermark over itself, or the next tick
    reads our own sentence as somebody's fresh guidance and pays a developer
    to answer it. But the run this park ends took minutes, and a human writing
    in that window wrote something no reading here has looked at: carried to
    the thread's TIP instead, the notice takes their comment with it and it is
    skipped for good. On this stage that comment can be the
    `/orchestrator authorize-oversized` an adjudicated candidate is waiting
    for, and the only road that could act on it never sees it.

    So the walk stops at the first comment that is not ours, which is the
    boundary between what this tick read and what landed behind its back.
    Which comments are ours is read off the ledger every post writes to, since
    that is the one record here that names them.

    Two answers fall back to the tip, and each is the lesser of what is left.
    A post whose id nothing could read adds nothing to that ledger, so no walk
    could pass our own notice and every tick after would answer it as
    guidance. And a watermark that was never set is a tick with nothing to
    bound: the spawn behind it quoted the whole thread to the agent, so the
    comments below have been answered rather than missed.
    """
    latest = gh.latest_comment_id(issue)
    ours = _comments._orchestrator_ids(state)
    read_to = state.get(_state._LAST_ACTION_COMMENT_ID)
    if ours == said_before or not isinstance(read_to, int):
        return latest
    for seen in sorted(gh.comments_after(issue, read_to), key=_comment_id):
        if _comment_id(seen) not in ours:
            break
        read_to = _comment_id(seen)
    return read_to


def _comment_id(seen) -> int:
    """One comment's own address, or 0 for one nothing here can name."""
    identified = getattr(seen, "id", None)
    return identified if isinstance(identified, int) else 0


def _on_unpublishable_tree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    agent_result: AgentResult,
    tree: _WorktreeStatus,
) -> None:
    """Park a tree a push may not be taken from, by which half of it failed.

    One seam for the one question a publication has to answer -- is this tree
    provably carrying nothing loose -- because the two ways it can answer no
    are a refusal either way and only the operator's next move differs. Paths
    git named are files to commit or clear; a reading that never happened is a
    repository to look at, and it must not be reported as the empty list it
    literally is.
    """
    if tree.paths:
        _on_dirty_worktree(gh, issue, state, agent_result, list(tree.paths))
        return
    _on_unreadable_worktree(gh, issue, state, agent_result)


def _on_dirty_worktree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    agent_result: AgentResult,
    dirty: list[str],
) -> None:
    """Park instead of pushing when the agent left uncommitted changes.

    Pushing here would publish a branch that omits the dirty files, so the PR
    would not match what the agent actually produced. We surface the situation
    to the human and resume the codex session on their reply, identical to the
    question path.
    """
    _park_unpushable_tree(
        gh, issue, state, _dirty_worktree_message(agent_result, dirty),
        {"reason": "dirty_worktree", "dirty_files": len(dirty)},
    )


def _on_unreadable_worktree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    agent_result: AgentResult,
) -> None:
    """Park instead of pushing when the tree could not be read at all.

    An unreadable tree is not a clean one. `git status` failing -- or an index
    entry git has been told to stop comparing, which makes the rest of what it
    reports unusable -- establishes nothing about what the checkout carries,
    and a push that went ahead on it would publish a branch nobody proved
    matches the work. So it is refused exactly as named dirty files are, and
    the comment says which of the two happened, since what an operator has to
    fix is a repository rather than a file list.
    """
    _park_unpushable_tree(
        gh, issue, state, _unreadable_worktree_message(agent_result),
        {"reason": "unreadable_worktree"},
    )


def _park_unpushable_tree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    message: str,
    reported: dict,
) -> None:
    """Post the refusal, hold the issue, and report it under its own reason."""
    said_before = _comments._orchestrator_ids(state)
    _comments._post_issue_comment(gh, issue, state, message)
    state.set(_state._AWAITING_HUMAN, True)
    # Mirror `_on_question`: this needs human input, so stale transient state
    # must not auto-recover over it.
    state.set(_state._PARK_REASON, None)
    state.set(_state._SILENT_PARK_COUNT, 0)
    read_to = _read_this_far(gh, issue, state, said_before)
    if read_to is not None:
        state.set(_state._LAST_ACTION_COMMENT_ID, read_to)
    gh.emit_event(
        "park_awaiting_human",
        issue_number=issue.number,
        stage=stage_name(gh.workflow_label(issue)),
        **reported,
    )


def _unreadable_worktree_message(agent_result: AgentResult) -> str:
    last_msg = agent_result.last_message.strip()
    tail = ""
    if last_msg:
        quoted = _session_read._as_blockquote(last_msg)
        tail = f"\n\n_Last agent message:_\n\n{quoted}"
    return (
        f"{config.HITL_MENTIONS} agent committed but this worktree's state "
        "could not be read (`git status` failed, or an index entry is marked "
        "`assume-unchanged`/`skip-worktree`); refusing to push a branch "
        "nothing here can prove matches the work. Clear what is blocking the "
        f"read, then reply and the orchestrator will resume the session.{tail}"
    )


def _dirty_worktree_message(
    agent_result: AgentResult, dirty: list[str],
) -> str:
    shown = dirty[:10]
    files_md = "\n".join(f"- `{file_path}`" for file_path in shown)
    if len(dirty) > len(shown):
        elided = len(dirty) - len(shown)
        files_md = f"{files_md}\n- … ({elided} more)"
    last_msg = agent_result.last_message.strip()
    tail = ""
    if last_msg:
        tail = f"\n\n_Last agent message:_\n\n{_session_read._as_blockquote(last_msg)}"
    return (
        f"{config.HITL_MENTIONS} agent committed but left {len(dirty)} "
        f"uncommitted change(s); refusing to push an incomplete branch. "
        f"Reply with guidance and the orchestrator will resume the session.\n\n"
        f"{files_md}{tail}"
    )
