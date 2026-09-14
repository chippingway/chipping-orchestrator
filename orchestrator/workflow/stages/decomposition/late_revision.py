# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer run a human's guidance earns, and the prompt it runs under.

Guidance about an oversized candidate is not a decomposition question, so it
does not go to the late decomposer. The work itself has to change, and the
session that wrote it is the one that knows what it wrote -- so the ORIGINAL
developer session is resumed, with the human's comments quoted, in the
worktree the candidate already lives in. It runs under `agent_role=developer`
and `stage=decomposing`, because that is what it is and where it happened: the
issue never leaves `workflow:decomposing`, and an analytics row that claimed
otherwise would put a developer run in a stage the issue was not in.

The budgets are the ones that already exist. The resume budget and the
session rotation behind it belong to the shared developer resume, which this
goes through rather than around; the per-issue daily retry cap counts fresh
spawns, and a resume driven by a human's reply is an unblock signal rather
than a retry, exactly as it is in every other stage that resumes on one.

The prompt is this owner's own, and one line of it is a contract with the
reconciliation: it asks for the same `ACK:` marker every other drift resume
asks for, because an unchanged commit needs one before it may be re-measured
as an answer. What the marker is read against, and what a commit nobody
vouched for earns instead, are decided where the checkout is.

Nothing before that reconciliation is durable. The guidance is consumed, the
park is cleared, and the session is recorded in memory; the write that keeps
any of it is the one the reconciliation itself makes. A mid-run pause and a
shutdown sweep therefore leave the issue exactly as the prior tick did, with
the human's guidance still unread -- which costs one repeated developer run
and never a dropped instruction.

Two owners carry the halves this one asks for rather than performs.
`late_revision_obligations` decides whether the committed candidate may be
replaced at all, and it is asked first on both roads in, ahead of the notice
and the spawn; `late_revision_reconciliation` proves the tree, re-freezes
whatever commit the checkout ends on, and measures it again. Both are reached
from here and neither reaches back, so the two entry points below -- the
guidance that buys a developer run, and the reply to a revision that stalled
-- are the whole of what the stage calls.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import settings as config
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    messages as _messages,
    prompt_context as _prompt_context,
    prompt_notes as _prompt_notes,
    usage as _usage,
)
from orchestrator.workflow.stages.decomposition import (
    late_content as _late_content,
    late_owner as _late_owner,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_revision_obligations as _late_obligations,
    late_revision_reconciliation as _late_reconciliation,
)
from orchestrator.workflow.stages.decomposition.late_content_models import _LateContentSettlement, _LateContentSignal
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from orchestrator.workflow.stages.implementing import resume as _dev_resume

log = logging.getLogger("orchestrator.workflow")

_DECOMPOSING_STAGE = "decomposing"

_LAST_AGENT_ACTION_AT = "last_agent_action_at"

_REVISING_NOTICE = (
    ":pencil2: resuming the developer against your guidance; the committed "
    "candidate is re-measured from whatever it ends on."
)

_REVISION_PROMPT = (
    "The human replied about this issue while your committed work was being "
    "adjudicated for its size, and the issue ITSELF may have been edited "
    "since you last read it. What follows is the current requirements, not "
    "the ones your session started from -- re-read all of it, decide what it "
    "means for the work you already committed, and COMMIT any further "
    "changes in your current worktree. Do NOT push -- the orchestrator "
    "measures whatever commit the worktree ends on and takes it from "
    "there.\n\n"
    "Issue title: {title!r}\n\n"
    "Issue body:\n\n{body}\n\n"
    "Guidance:\n{guidance}\n\n"
    "Leave the worktree CLEAN: anything uncommitted is not part of the "
    "candidate and stops the re-measurement.\n\n"
    "If your existing commits already satisfy the guidance and no further "
    "change is needed, leave the commit exactly as it is and end your final "
    "message with EXACTLY this marker, alone on its own line:\n\n"
    "  ACK: <one-line justification>\n\n"
    "The marker is the only thing that lets an unchanged commit through: "
    "without it, a run that changed nothing is read as one that could not "
    "answer, and the orchestrator parks for a human instead of re-measuring. "
    "So use `ACK:` ONLY when you are certain the committed work covers the "
    "guidance. If you have a clarification question or are unsure, do NOT use "
    "it -- reply with the question and the orchestrator will park awaiting a "
    "human, quoting what you asked.\n\n"
    "{commit_style}\n\n"
    "{foreground}"
)

_NO_BODY = "(no body)"


def _revise_from_guidance(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Resume the locked developer session with this guidance, then remeasure.

    The guidance is consumed in memory before the run, so the comments quoted
    into the prompt and the ones the watermark covers are the same set, and it
    becomes durable only on a path that reconciles what the run left. That is
    the same order every stage that resumes on a human reply keeps: a mid-run
    pause and a shutdown sweep both mean this tick did not happen, and a
    consumption made durable by one of them would drop a human's instruction
    on the floor with nothing left on the issue pointing at it. The cost is
    the one every declined run has -- the next tick resumes the developer
    again on the same reply, and it sees its own prior commit.

    The park this answers goes the same way. Clearing it is staged here so a
    run that then fails re-parks with the reason it actually failed for rather
    than leaving the issue claiming it is still waiting to be told what the
    edit meant.

    A close a poll observed stops it before the agent and again after, and
    the "before" is asked twice: the resume is the same kind of step a spawn
    is -- an agent on somebody's repository, paid for and free to decide --
    and the notice this call posts ahead of it is a request the poll runs
    beside. So the reading is taken as the tick is entered, again right
    against the resume, and once more when the run comes back, because no one
    of the three covers the other two: the first two stop the agent, and the
    last stops the remeasure that would write a fresh candidate over a cycle
    a close already ended.
    """
    stranded = _late_obligations._stranded_by_effects(context)
    if stranded is not None:
        return stranded
    latched = _latched_close(context)
    if latched is not None:
        return latched
    _comments._post_issue_comment(
        context.gh, context.issue, context.state, _REVISING_NOTICE,
    )
    _consume(context, signal)
    _late_parks._answer_park(context)
    return _resumed(context, signal)


def _resumed(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Start the developer this guidance bought, then read what it left.

    The notice above is a request and the park answer is a write, so the poll
    can observe the close inside either -- which is why the latch is asked
    once more here, immediately against the resume, and once again when the
    run comes back.
    """
    latched = _latched_close(context)
    if latched is not None:
        return latched
    worktree, agent_result, paused = _dev_resume._resume_dev_with_text(
        context.gh,
        context.spec,
        context.issue,
        context.state,
        _revision_prompt(context.issue, signal.guidance),
        stage=_DECOMPOSING_STAGE,
        pause_guard=True,
    )
    if paused or _guards._ignore_if_interrupted(context.issue, agent_result):
        return _LateContentSettlement(
            disposition=_LateDisposition.DEFERRED,
        )
    context.state.set(_LAST_AGENT_ACTION_AT, _usage._now_iso())
    latched = _latched_close(context)
    if latched is not None:
        return latched
    if agent_result.timed_out:
        log.warning(
            "issue=#%d the developer revision timed out after %ds; reading "
            "the worktree it left anyway",
            context.issue.number, config.AGENT_TIMEOUT,
        )
    return _late_reconciliation._reconcile_revised_candidate(
        context, worktree, agent_result,
    )


def _latched_close(
    context: _LateContext,
) -> _LateContentSettlement | None:
    """Whether a poll's own reading ends this revision instead of running it.

    The latch alone, like every barrier whose step is too tight for a request:
    a claim names `owner_check`, and writing it over the boundary this tick
    reached is the rewind the record refuses. `persisted` is set because the
    mark it leaves IS a durable write, and the caller must not take it as an
    outcome it still owes one for.
    """
    if _late_owner._latch_stops(context) is None:
        return None
    return _LateContentSettlement(
        disposition=_LateDisposition.CANCELLED, persisted=True,
    )


def _retry_revision(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """What a human's reply to a stalled revision earns.

    Guidance means the work still has to change and buys another developer
    run. A bare continue does not: the developer already finished, and what
    failed was the reading of what it left -- so the checkout is re-read, the
    commit re-frozen, and the size measured again, with no agent spawned at
    all.
    """
    if signal.guidance:
        return _revise_from_guidance(context, signal)
    if not signal.bare_continue:
        return _LateContentSettlement(disposition=_LateDisposition.PARKED)
    stranded = _late_obligations._stranded_by_effects(context)
    if stranded is not None:
        return stranded
    _consume(context, signal)
    return _late_reconciliation._reconcile_revised_candidate(
        context,
        _worktree_paths._worktree_path(context.spec, context.issue.number),
    )


def _consume(context: _LateContext, signal: _LateContentSignal) -> None:
    """Record the conversation this tick is acting on as read.

    Two watermarks, because two different consumers read the same thread. The
    generation's own covers the late fingerprints, so the same comments do not
    come back as fresh guidance. The issue-wide `last_action_comment_id` is
    ratcheted for the reason every other developer resume ratchets it: the dev
    has seen these comments, and the later validating -> in_review handoff
    would otherwise replay them as fresh PR feedback and resume it a second
    time on input it already handled.

    Both cover the whole trusted run this reading folded in rather than the
    guidance alone. A bare continue that re-read the checkout was acted on
    just as a quoted comment was, and leaving it behind the shared watermark
    would hand it to that same handoff as feedback nobody had answered.
    """
    context.generation = _late_content._rebaselined(
        context.generation, signal.fingerprint,
    )
    _late_park_state._mark_replies_read(
        context, signal.fingerprint.comment_watermark_id,
    )


def _revision_prompt(issue: Issue, guidance: tuple) -> str:
    """The followup one developer revision is resumed with.

    The title and body are quoted beside the guidance because a resume is
    exactly the case that cannot see them: the session's replayed transcript
    holds the issue as it read when the work started, and the commonest reason
    to be here is that a human edited it since. A developer left to act on the
    text it remembers would revise against requirements nobody is asking for.
    """
    quoted = "\n\n".join(
        _prompt_context._quote_comment_line(issue_comment)
        for issue_comment in guidance
    )
    return _REVISION_PROMPT.format(
        title=(issue.title or "").strip() or f"#{issue.number}",
        body=_messages._as_blockquote(
            (issue.body or "").strip() or _NO_BODY,
        ),
        guidance=quoted or f"(see issue #{issue.number})",
        commit_style=_prompt_notes._COMMIT_STYLE_NOTE,
        foreground=_prompt_notes._FOREGROUND_ONLY_NOTE,
    )
