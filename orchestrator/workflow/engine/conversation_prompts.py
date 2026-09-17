# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Question, design-discussion, pull-request follow-up, and human-reply resume prompts.

Conversation context comes from the common trusted-thread reader. Discussion
rounds carry the publication and commit instructions their confirmed plan needs;
question and follow-up rounds preserve the response markers their readers expect,
and the developer resumes restate the report contract beside them."""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.workflow.engine import (
    messages as _messages,
    prompt_context as _prompt_context,
    prompt_notes as _prompt_notes,
)
from orchestrator.workflow.engine.prompt_context import _SECTION_SEP
from orchestrator.workflow.state import WorkflowLabel


def _build_question_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    specs: list[_config_models.RepoSpec],
) -> str:
    """Compose the read-only prompt used by the `question` stage.

    The agent runs in the per-issue `issue-N` worktree with read-only
    expectations: it must answer the standing question (or ask a focused
    follow-up of its own) without touching code, committing, or pushing.
    The orchestrator parks on any commit / dirty-tree output, so the
    prompt is explicit about that contract.

    The tracked-repos awareness block is included for a multi-repo
    deployment; it lists the sibling checkouts as read-only references
    and does not soften this stage's own no-write contract (the block's
    framing defers write permission to the surrounding prompt, which
    grants none here).
    """
    body = issue.body or _prompt_notes._NO_BODY
    convo = comments_text or _prompt_notes._NO_PRIOR_COMMENTS
    tracked = _prompt_context._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    return (
        f"You are answering a standing question on GitHub issue "
        f"#{issue.number}: {issue.title!r}.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
        "Read the issue and the conversation above, inspect the codebase "
        "with read-only commands (`git ls-files`, `git log`, `cat`, "
        "`grep`, etc.), and write a focused answer to the open question. "
        "Cite file paths or commits when useful. You MUST NOT modify, "
        "create, delete, commit, or push any file -- this stage is "
        "purely informational.\n\n"
        "If you need more information from the human before you can "
        "answer, end your message with a single, focused follow-up "
        "question. Otherwise end with a clear answer that the human can "
        "act on (close the issue, relabel it to "
        f"`{WorkflowLabel.IMPLEMENTING}`, etc.)."
    )


def _build_question_followup_prompt(comments: list) -> str:
    """Compose the resume prompt the question stage sends back to its
    locked agent session after a human reply.

    Mirrors `_resume_developer_on_human_reply`'s shape -- a quote of the
    incoming comments -- but reiterates the read-only / no-commit
    contract so a multi-tick conversation cannot drift into the agent
    deciding to "just implement the fix".
    """
    body = _SECTION_SEP.join(
        _prompt_context._quote_comment_line(comment) for comment in comments
    )
    quoted = _messages._as_blockquote(body)
    return (
        "The human replied on the issue thread. Continue the discussion "
        "and answer their reply.\n\n"
        f"Human reply:\n\n{quoted}\n\n"
        "Reminder: this is still the read-only question stage. Do NOT "
        "modify, create, delete, commit, or push any file. End with a "
        "clear answer or a single, focused follow-up question."
    )


def _build_discussion_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    specs: list[_config_models.RepoSpec],
    plan_path: str,
) -> str:
    """Compose the full-context prompt used by the `discussion` stage.

    Every round that cannot be handed to a live session gets this one: the
    conversation's first, and any later one whose backend returned no session
    id to resume. Both need the issue body, the title, and the trusted thread
    inline, because the agent reading it has nothing cached to answer against.

    The stage exists to widen a design before anyone commits to it, so this
    prompt is shaped against the two ways an agent narrows one. It has to
    research the repository itself, because a round spent asking humans for
    facts that `git log` answers is a round the design does not advance; and it
    has to keep the questions it comes back with at the architecture level,
    because trivia crowds out the decisions a human is actually needed for.

    What it must end on is a numbered frontier: the subset of open questions
    whose answers do not depend on another open question, each with a
    recommended answer, so a human replies by number instead of re-deriving the
    tree. Everything downstream of those waits for a later round, which is what
    keeps one comment from asking for a decision that the answer above it may
    make moot.

    The agent runs in the per-issue `issue-N` worktree under the same
    expectations the `question` stage sets -- the orchestrator parks on any
    commit or dirty tree -- with one exception the human has to unlock. Once
    they confirm on the thread that both sides understand the design the same
    way, the agreed design is written down in `plan_path` and committed there,
    alone: that commit is the stage's only artifact, and the orchestrator
    checks the branch against the base before publishing it, so the prompt
    states the same bound the check enforces. The path is passed in rather
    than spelled here because the owner that refuses to publish anything else
    is the owner that names it.
    """
    body = issue.body or _prompt_notes._NO_BODY
    convo = comments_text or _prompt_notes._NO_PRIOR_COMMENTS
    tracked = _prompt_context._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    return (
        f"You are opening an architecture discussion on GitHub issue "
        f"#{issue.number}: {issue.title!r}.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
        "Nobody has asked you to implement anything. This is a design "
        "conversation with the humans on the thread, and the only thing it "
        "produces is your written analysis.\n\n"
        "Research the repository yourself first. Do NOT ask a human for a "
        "fact you can read: use read-only commands (`git ls-files`, "
        "`git log`, `grep`, `cat`) to find the modules, contracts, and prior "
        "decisions this issue lands on, and cite the paths and commits you "
        "relied on so your reasoning can be checked.\n\n"
        "Then explore the design space out loud, as a tree rather than as a "
        "single answer. Start from what the issue leaves open, expand each "
        "branch into the concrete shapes it could take, and say what each one "
        "would commit this repository to. Include at least one unconventional "
        "option the existing code does not suggest, and say honestly why it "
        "might or might not fit. Name any research worth doing before the "
        "design is settled -- prior art to read, a measurement to take, a "
        "constraint to confirm -- and what its outcome would change.\n\n"
        "Keep it at the architecture level: boundaries and interfaces, who "
        "owns which state, failure and migration behavior, compatibility, and "
        "the trade-offs between them. Naming, formatting, and other "
        "implementation trivia belong to whoever implements this, not to "
        "this thread.\n\n"
        "End with a NUMBERED list of the questions that can be answered right "
        "now -- the frontier. A question earns a number only if its answer "
        "does not depend on another question you are also asking; hold "
        "everything downstream of an open question for a later round, and "
        "treat anything the conversation above has already settled as decided "
        "rather than asking it again. Give "
        "each numbered question your own recommended answer and one line of "
        "reasoning, so a human can agree or overrule by number.\n\n"
        "Until a human states explicitly on this thread that you and they "
        "understand the design the same way, you MUST NOT modify, create, "
        "delete, commit, or push any file, and you MUST NOT start "
        "implementing any part of this: nothing is settled and no work "
        "begins.\n\n"
        f"{_plan_publication_instruction(plan_path)}\n\n"
        f"{_prompt_notes._COMMIT_STYLE_NOTE}\n\n"
        f"{_prompt_notes._FOREGROUND_ONLY_NOTE}"
    )


def _plan_publication_instruction(plan_path: str) -> str:
    """The one write a confirmed discussion earns, and its exact bound.

    Both discussion prompts carry this verbatim because both can be the round
    the confirmation lands on: an opening prompt is also what a later round
    with no session to resume is given, and the humans may well have confirmed
    the design several rounds before that. The bound is stated as the check
    states it -- one path, nothing else, no push -- since an agent that
    commits a second file has its whole plan refused rather than trimmed.
    """
    return (
        "Once they have confirmed exactly that -- and only then -- write the "
        f"agreed design down in `{plan_path}` and COMMIT that file. It is "
        "what the implementation will be built from, so it carries the "
        "decisions the thread resolved and what each one rules out, the "
        "evidence and research behind them with the paths and commits you "
        "relied on, the alternatives you considered and why they lost, the "
        "risks and how each would show up, and the implementation plan that "
        "follows. Commit that ONE file and nothing else -- no code, no "
        "configuration, no second plan -- and do NOT push it or open a pull "
        "request: the orchestrator checks the branch against the base branch "
        "and publishes it for review itself. A commit that touches anything "
        "else publishes nothing and parks the issue for a human."
    )


def _build_discussion_followup_prompt(
    comments: list, plan_path: str,
) -> str:
    """Compose the resume prompt a discussion round sends its locked session.

    The humans replied to a numbered frontier, so what this round owes them is
    not another opening analysis but the same tree redrawn: their answers
    close the branches they chose, and closing those is what makes the
    questions underneath answerable for the first time. Asking for a fresh
    frontier is therefore the whole request -- a round that only acknowledged
    the reply would leave the conversation exactly where the last one did.

    This is also the prompt the confirmation itself arrives on, so it carries
    both halves of the contract and the boundary between them. An answered
    question is still not permission to build: only a reply that says the two
    sides understand the design the same way unlocks the one write this stage
    allows, and what that write may touch is stated as narrowly as the check
    that refuses everything else.
    """
    body = _SECTION_SEP.join(
        _prompt_context._quote_comment_line(comment) for comment in comments
    )
    quoted = _messages._as_blockquote(body)
    return (
        "The humans replied on the issue thread. Their answers settle the "
        "questions those answers cover; treat each as decided, even where you "
        "recommended otherwise.\n\n"
        f"Human reply:\n\n{quoted}\n\n"
        "Fold the answers back into the design tree you already have. Say "
        "briefly what each one rules out, check anything a settled branch "
        "newly makes worth confirming in the repository with read-only "
        "commands (`git ls-files`, `git log`, `grep`, `cat`), and expand the "
        "branches those answers have opened up.\n\n"
        "End with a NUMBERED list of the questions answerable right now given "
        "everything decided so far -- the new frontier. A question earns a "
        "number only if its answer does not depend on another question you "
        "are also asking, and a question the thread has already answered "
        "earns none at all. Give each your own recommended answer and one "
        "line of reasoning, so a human can agree or overrule by number. If "
        "nothing is left open, say so plainly and state the design the thread "
        "has converged on.\n\n"
        "Reminder: an answered question is not the confirmation to begin. "
        "Unless the reply above states explicitly that you and the humans "
        "understand the design the same way, you MUST NOT modify, create, "
        "delete, commit, or push any file, and you MUST NOT start "
        "implementing any part of this.\n\n"
        f"{_plan_publication_instruction(plan_path)}\n\n"
        f"{_prompt_notes._COMMIT_STYLE_NOTE}\n\n"
        f"{_prompt_notes._FOREGROUND_ONLY_NOTE}"
    )


def _build_pr_comment_followup(comments: list) -> str:
    """Compose a dev-fix prompt from new PR-side comments.

    The dev session has not seen any PR comment before (those live on a
    different surface than the issue thread it was fed at spawn time), so a
    short preamble is needed to frame the request -- otherwise a comment like
    "rename foo to bar" reads as freeform chatter without context.
    """
    body = _SECTION_SEP.join(
        _prompt_context._quote_comment_line(comment) for comment in comments
    )
    quoted = _messages._as_blockquote(body)
    return (
        "New comments arrived on the open PR for this issue. Address each item: "
        "COMMIT every repository change in your current worktree, and answer an "
        "item that asks only for report content in your updated report, with "
        "no commit for it. Do NOT push -- the orchestrator pushes, publishes "
        "your report, and re-runs the reviewer.\n\n"
        f"PR comments:\n\n{quoted}\n\n"
        f"{_prompt_notes._COMMIT_STYLE_NOTE}\n\n"
        f"{_prompt_notes._DEVELOPER_REPORT_NOTE}\n\n"
        "If a comment says a human published or updated the report on the pull "
        "request, read it there: when it is complete and current, end with the "
        "report-already-on-the-pull-request outcome instead of writing it "
        "again.\n\n"
        "If you genuinely disagree with a point, end your final message with a "
        "question for the human and leave that item un-fixed; the orchestrator "
        "will park the issue for human review.\n\n"
        "If the comments contain NO concrete, actionable change request -- e.g. "
        "a vague 'continue', 'ok', or 'ping' that names no specific defect -- "
        "and neither the branch nor your report has to change, make NO commit, "
        "emit no report outcome, and end your final message with a single line "
        "`ACK: <brief reason>`. The "
        "orchestrator will then return the PR to review-ready instead of "
        "parking it for a fix that is not warranted.\n\n"
        f"{_prompt_notes._FOREGROUND_ONLY_NOTE}"
    )


def _build_human_reply_followup(comments: list) -> str:
    """Compose the resume prompt a parked developer session receives when a
    human replies on the issue thread.

    The replies, one per paragraph, are the whole of the new task: the session
    already holds its stage's instructions in its transcript. The subject and
    report contracts are restated anyway, because that transcript may predate
    them or carry another stage's prompt -- and because this text is also what
    follows the respawn preamble when the resume rotates into a fresh session,
    which holds no transcript at all and is taught no subject contract by the
    preamble. A reply is often what lets the parked work finish, so the agent
    it reaches may well commit.
    """
    replies = "\n\n".join(
        _prompt_context._quote_comment_line(comment)
        for comment in comments if comment.body
    )
    return (
        f"{replies}\n\n{_prompt_notes._COMMIT_STYLE_NOTE}\n\n"
        f"{_prompt_notes._DEVELOPER_REPORT_NOTE}\n\n"
        f"{_prompt_notes._FOREGROUND_ONLY_NOTE}"
    )
