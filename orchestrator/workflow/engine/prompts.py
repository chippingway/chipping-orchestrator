# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The prompt builders the workflow stages share, and the notes folded in.

Each conversation-carrying builder opens on the same header: the issue body,
the thread text ``comments.py`` already trust-filtered, and the tracked-repository
block beside it. That shared opening is why an untrusted author's comment is
absent from the implement, review, documentation, decompose, question, and
discussion prompts alike -- one filtered read feeds all six -- and why the
placeholders for an empty body or an empty thread read the same in each. The
blank line those sections are joined on comes from ``comments.py`` too, so a
quoted thread and the prompt assembled around it break into paragraphs the same
way.

The notes appended below it are contracts the rest of the workflow enforces.
``_FOREGROUND_ONLY_NOTE`` goes on every prompt that can end in a commit: a
backgrounded build outlives no session, so its result is never observed and the
issue parks forever. ``_COMMIT_STYLE_NOTE`` goes on the subset of those whose
agent also writes a subject, since the repo's own `git log` is the style
authority and never a hardcoded type list. The conflict prompt is the one that
takes the first note without the second -- its agent finishes an in-progress
rebase, replaying subjects somebody else already wrote. The two discussion
prompts take both, even though most of their rounds commit nothing: the round
a human confirms the design on writes the plan and its subject, and which round
that is is not knowable when the prompt is built.

A prompt that promises a marker -- ``VERDICT:``, ``DOCS: NO_CHANGE``, ``ACK:``,
the fenced manifest -- spells out the exact literal its own reader then matches:
``completion_verdicts.py`` for the two that end a stage, ``messages.py`` for the
acknowledgement, the manifest parser for the last. Each of them says outright
that prose in the marker's place is parked rather than guessed at. The child
cap the decompose prompt states is read back off the validator that rejects
past it, for the same reason: a bound the agent is told and a bound it is
judged against must be one number.

A prompt with only one caller is built where that caller lives: ``drift.py``
composes the drift-resume prompt beside the route that sends it and borrows both
notes from here.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.workflow.engine import comments as _comments, messages as _messages
from orchestrator.workflow.engine.comments import _SECTION_SEP
from orchestrator.workflow.stages.decomposition.validation import _MAX_CHILDREN
from orchestrator.workflow.state import WorkflowLabel

_MAX_FILES_SHOWN = 20

_NO_BODY = "(no body)"

_NO_PRIOR_COMMENTS = "(no prior comments)"

_FOREGROUND_ONLY_NOTE = (
    "IMPORTANT: your session terminates the moment you finish responding -- "
    "nothing keeps running between turns, and a later resume starts a fresh "
    "process. NEVER start a background job (build, test run, Miri, server) "
    "and end your turn intending to check it later: the job dies with your "
    "session and its result will never be seen. Run all builds and tests in "
    "the foreground and wait for them to complete before you commit or reply."
)

_COMMIT_STYLE_NOTE = (
    "Before committing, run `git log --oneline -20` to see how recent commit "
    "subjects are formatted, and write your subject in the SAME "
    "repository-local style. Mirror whatever subject/prefix convention that "
    "history uses rather than assuming a fixed set of types -- it may be a "
    "`<type>: <subject>` form, or a project-specific prefix such as `event:` "
    "or `career:`; the repo's own recent history is the source of truth. Keep "
    "the subject a single short, imperative line.\n\n"
    "The commit message MUST be the subject line only -- no extended "
    "description / body and no `Co-Authored-By:` (or other) trailer. Use "
    "`git commit -m \"<subject>\"` with a single `-m`."
)

_CONTINUE_RETRY_PROMPT = (
    "Resuming after a session/usage limit or a silent session failure. "
    "Re-read the issue requirements and the conversation in your transcript, "
    "then CONTINUE the work already in progress and COMMIT any remaining "
    "changes in your current worktree. Do NOT push -- the orchestrator pushes "
    "and re-runs the reviewer."
)


def _build_implement_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    specs: list[_config_models.RepoSpec],
) -> str:
    body = issue.body or _NO_BODY
    convo = comments_text or _NO_PRIOR_COMMENTS
    tracked = _comments._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    return (
        f"You are the implementer for GitHub issue #{issue.number}: {issue.title!r}.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
        "Implement the change in the current working directory (a fresh git worktree on a "
        "new branch). When done, COMMIT your changes with a clear message. Do NOT push - "
        "the orchestrator pushes and opens the PR.\n\n"
        f"{_COMMIT_STYLE_NOTE}\n\n"
        f"{_FOREGROUND_ONLY_NOTE}\n\n"
        "If you cannot proceed because of missing information, leave the working tree "
        "uncommitted (no commits) and end your response with a clear question for the human."
    )


def _build_fresh_respawn_preamble(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    specs: list[_config_models.RepoSpec],
) -> str:
    """Re-grounding header prepended to a FRESH dev spawn that REPLACES a
    retired or poisoned session mid-issue (proactive rotation, silent-park
    fallback, or stale/overflow recovery).

    The previous session's in-memory reasoning is gone, but its committed work
    survives on the current branch, so the fresh agent is pointed at the branch
    as the source of truth and re-grounded in the issue requirements +
    conversation. Without this the rotation regresses into a context-starved
    spawn that could re-implement from scratch or ignore the original spec.
    The caller appends the stage-specific instruction (fix feedback, drift,
    conflict, ...) after this block.
    """
    body = issue.body or _NO_BODY
    convo = comments_text or _NO_PRIOR_COMMENTS
    tracked = _comments._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    return (
        f"You are resuming work on GitHub issue #{issue.number}: {issue.title!r}. "
        "A previous agent session worked on this issue and its commits are "
        "already on the current branch (your working directory); that session's "
        "history is NOT available to you. Before doing anything, re-ground "
        "yourself: inspect what has already been done with `git log --oneline` "
        "and `git diff` against the base branch, and continue from there -- do "
        "NOT restart the implementation from scratch.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
        "Your immediate task follows.\n"
        "----------------------------------------"
    )


def _build_review_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    specs: list[_config_models.RepoSpec],
    dev_backend: str = "agent",
) -> str:
    body = issue.body or _NO_BODY
    convo = comments_text or _NO_PRIOR_COMMENTS
    base_ref = f"{spec.remote_name}/{spec.base_branch}"
    tracked = _comments._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    return (
        f"You are an automated code reviewer for GitHub issue #{issue.number}: {issue.title!r}. "
        f"A separate {dev_backend} session has implemented this issue and committed to the current "
        f"branch. The base branch is `{base_ref}`.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
        "Inspect the change with:\n"
        f"  git log --oneline {base_ref}..HEAD\n"
        f"  git diff {base_ref}...HEAD\n\n"
        "Review the change against the issue requirements. Flag correctness bugs, missing "
        "tests, scope creep, obvious style issues, and anything that would block a human "
        "approver. Do NOT edit or commit anything -- you are a reviewer only.\n\n"
        "Your final message MUST end with exactly one of these markers, alone on its own line:\n"
        "  VERDICT: APPROVED\n"
        "  VERDICT: CHANGES_REQUESTED\n\n"
        "If CHANGES_REQUESTED, list the specific items above the verdict line as a numbered "
        "list so the implementer can address them one by one. If the change is acceptable as "
        "is, write VERDICT: APPROVED with a one-line justification above it."
    )


def _build_documentation_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    specs: list[_config_models.RepoSpec],
) -> str:
    """Prompt for the documentation pass that runs as the final-docs
    handoff between reviewer approval and `in_review`.

    Reuses the dev agent role -- the documentation pass commits to the same
    branch as the implementer, so it is operating as a developer and not a
    reviewer. No separate backend env var is introduced for this stage;
    the stage handler invokes the existing dev backend on the PR worktree.
    """
    body = issue.body or _NO_BODY
    convo = comments_text or _NO_PRIOR_COMMENTS
    base_ref = f"{spec.remote_name}/{spec.base_branch}"
    tracked = _comments._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    return (
        f"You are the documentation pass for GitHub issue #{issue.number}: "
        f"{issue.title!r}. A separate session has implemented this issue and "
        f"committed to the current branch. The base branch is `{base_ref}`.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
        "Inspect the change with:\n"
        f"  git log --oneline {base_ref}..HEAD\n"
        f"  git diff {base_ref}...HEAD\n\n"
        "Compare the branch diff against `README.md` and the `docs/` tree. "
        "If any user-facing description or architectural note needs to be "
        "updated to match the code that landed in this branch, UPDATE the "
        "relevant files and COMMIT the change in the current worktree. Do "
        "NOT push -- the orchestrator pushes once this stage finishes. Do "
        "NOT inspect or modify the `plans/` tree or roadmap entries: those "
        "are working notes owned by humans and are out of scope for the "
        "final-docs pass.\n\n"
        f"{_COMMIT_STYLE_NOTE}\n\n"
        "If the branch genuinely requires no documentation change, do NOT "
        "commit and end your final message with EXACTLY this marker, alone "
        "on its own line:\n\n"
        "  DOCS: NO_CHANGE\n\n"
        "Place a one-sentence justification on the line above the marker. "
        "The orchestrator will NOT accept ambiguous phrasing like "
        "'no changes needed' as success without the explicit marker; an "
        "agent message that neither commits nor emits the marker is parked "
        "for human review.\n\n"
        "If you genuinely cannot decide because of missing information, "
        "leave the worktree uncommitted, omit the marker, and end your "
        "final message with a question for the human; the orchestrator "
        "will park the issue for human review.\n\n"
        f"{_FOREGROUND_ONLY_NOTE}"
    )


def _build_fix_prompt(review_feedback: str) -> str:
    feedback = review_feedback.strip() or "(reviewer left no detail)"
    quoted = _messages._as_blockquote(feedback)
    return (
        "An automated reviewer requested changes on your implementation. Address each item "
        "below, then COMMIT the fix in your current worktree. Do NOT push -- the orchestrator "
        "pushes and re-runs the review.\n\n"
        f"Review feedback:\n\n{quoted}\n\n"
        f"{_COMMIT_STYLE_NOTE}\n\n"
        f"{_FOREGROUND_ONLY_NOTE}\n\n"
        "If you genuinely disagree with a point, end your final message with a question for "
        "the human and leave that item un-fixed; the orchestrator will park the issue for "
        "human review. Otherwise, fix all items (a single commit is fine)."
    )


def _build_conflict_resolution_prompt(
    base_ref: str, files: list[str]
) -> str:
    shown = files[:_MAX_FILES_SHOWN]
    files_md = "\n".join(f"- `{file_path}`" for file_path in shown)
    if len(files) > len(shown):
        elided = len(files) - len(shown)
        files_md = f"{files_md}\n- ... ({elided} more)"
    return (
        f"`git rebase {base_ref}` left {len(files)} conflicted "
        "file(s) in your worktree. Resolve each conflict and complete the "
        "rebase in your current worktree. Do NOT push -- the orchestrator "
        "pushes and re-runs the reviewer.\n\n"
        f"Conflicted paths:\n\n{files_md}\n\n"
        "Workflow: edit each file to a coherent resolution, `git add` it, "
        "then run `git rebase --continue`. Repeat until the rebase completes. "
        "If Git reports an empty commit because the change is already present, "
        "use `git rebase --skip`; use `git commit --allow-empty` only when "
        "an empty commit is intentional. Use `git rebase --abort` only as "
        "the escape hatch when you cannot make progress. "
        "Use `git status` to inspect the in-progress rebase.\n\n"
        "If you genuinely cannot resolve a conflict, end your final "
        "message with a question for the human and leave the worktree "
        "mid-rebase; the orchestrator will park the issue for human review.\n\n"
        f"{_FOREGROUND_ONLY_NOTE}"
    )


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
    body = issue.body or _NO_BODY
    convo = comments_text or _NO_PRIOR_COMMENTS
    tracked = _comments._build_tracked_repos_context(spec, specs)
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
        _comments._quote_comment_line(comment) for comment in comments
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
    body = issue.body or _NO_BODY
    convo = comments_text or _NO_PRIOR_COMMENTS
    tracked = _comments._build_tracked_repos_context(spec, specs)
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
        f"{_COMMIT_STYLE_NOTE}\n\n"
        f"{_FOREGROUND_ONLY_NOTE}"
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
        _comments._quote_comment_line(comment) for comment in comments
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
        f"{_COMMIT_STYLE_NOTE}\n\n"
        f"{_FOREGROUND_ONLY_NOTE}"
    )


def _build_pr_comment_followup(comments: list) -> str:
    """Compose a dev-fix prompt from new PR-side comments.

    The dev session has not seen any PR comment before (those live on a
    different surface than the issue thread it was fed at spawn time), so a
    short preamble is needed to frame the request -- otherwise a comment like
    "rename foo to bar" reads as freeform chatter without context.
    """
    body = _SECTION_SEP.join(
        _comments._quote_comment_line(comment) for comment in comments
    )
    quoted = _messages._as_blockquote(body)
    return (
        "New comments arrived on the open PR for this issue. Address each item, "
        "then COMMIT the fix in your current worktree. Do NOT push -- the "
        "orchestrator pushes and re-runs the reviewer.\n\n"
        f"PR comments:\n\n{quoted}\n\n"
        f"{_COMMIT_STYLE_NOTE}\n\n"
        "If you genuinely disagree with a point, end your final message with a "
        "question for the human and leave that item un-fixed; the orchestrator "
        "will park the issue for human review.\n\n"
        "If the comments contain NO concrete, actionable change request -- e.g. "
        "a vague 'continue', 'ok', or 'ping' that names no specific defect -- "
        "and the branch already satisfies them, make NO commit and end your "
        "final message with a single line `ACK: <brief reason>`. The "
        "orchestrator will then return the PR to review-ready instead of "
        "parking it for a fix that is not warranted.\n\n"
        f"{_FOREGROUND_ONLY_NOTE}"
    )


def _build_decompose_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    specs: list[_config_models.RepoSpec],
) -> str:
    body = issue.body or _NO_BODY
    convo = comments_text or _NO_PRIOR_COMMENTS
    tracked = _comments._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    return (
        f"You are the decomposer for GitHub issue #{issue.number}: {issue.title!r}.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
        "Decide whether this issue can be implemented in ONE coding-agent "
        "context window. If yes, return decision='single'. If no, propose a "
        "list of smaller child issues each one-shottable on its own.\n\n"
        "Sizing rule of thumb: if the change touches more than ~5 files or "
        "needs more than one logical commit, propose splitting; otherwise "
        "keep it as a single child. Use `git ls-files`, `wc -l`, or other "
        "read-only commands to inspect the codebase. You MUST NOT commit, "
        "push, or modify any file -- you are read-only.\n\n"
        "If you genuinely need a clarification, end your message with a "
        "question for the human and DO NOT emit a manifest. Otherwise, end "
        "your final message with EXACTLY ONE fenced JSON block in this "
        "format (and nothing else after it):\n\n"
        "```orchestrator-manifest\n"
        "{\n"
        "  \"decision\": \"split\",\n"
        "  \"rationale\": \"<<= 2 sentences why>\",\n"
        "  \"umbrella\": false,\n"
        "  \"children\": [\n"
        "    {\"title\": \"...\", \"body\": \"...\", \"depends_on\": []}\n"
        "  ]\n"
        "}\n"
        "```\n\n"
        "The block must be valid JSON parseable by `json.loads`. The "
        "`decision` value must be exactly the string `\"single\"` or "
        "`\"split\"` (no other values, no union syntax). On `\"single\"`, "
        "omit the `children` field and instead hand off the context you "
        "already gathered so the implementer does not re-derive it: add "
        "`\"affected_files\"` (a list of repo-relative paths you found "
        "relevant) and `\"notes\"` (<= 3 sentences of concrete "
        "implementation guidance). Both are optional but strongly "
        "encouraged on `\"single\"`.\n\n"
        "Rules for the children list (omit entirely on 'single'):\n"
        f"- At most {_MAX_CHILDREN} children.\n"
        "- `depends_on` is a list of 0-based indexes into THIS children "
        "array (not GitHub issue numbers; the orchestrator allocates those).\n"
        "- Self-dependencies and cycles are rejected.\n"
        "- Each child must be small enough to implement in one context "
        "(do not propose a child that itself needs decomposition).\n\n"
        "The optional `umbrella` boolean (default false) signals that the "
        "parent issue itself has NO implementation work of its own and exists "
        "only to aggregate the children. Set it to true when every line of "
        "the parent's intent is covered by the children you are creating; "
        "leave it false when the parent still needs its own coding pass after "
        "the children land. An umbrella parent auto-resolves to `done` once "
        "every child resolves; a non-umbrella parent re-enters implementation."
    )


def _single_manifest_text(
    manifest: dict, field_name: str, fallback: str = "",
) -> str:
    """Return one stripped optional text field with a safe fallback."""
    raw_value = manifest.get(field_name)
    text = raw_value.strip() if isinstance(raw_value, str) else ""
    return text or fallback


def _single_manifest_files(manifest: dict) -> list[str]:
    """Return non-empty string paths from optional single-decision context."""
    raw_files = manifest.get("affected_files")
    if not isinstance(raw_files, list):
        return []
    return [
        file_path.strip()
        for file_path in raw_files
        if isinstance(file_path, str) and file_path.strip()
    ]


def _build_single_decision_comment(manifest: dict) -> str:
    """Compose the `single`-decision comment posted on the parent issue.

    Beyond the decomposer's rationale, this surfaces the context the
    decomposer already gathered while sizing the issue -- the affected
    files and any implementation notes -- so the develop agent that picks
    the issue up in `implementing` starts from that groundwork instead of
    re-deriving it. The implementer reads the issue thread via
    `_recent_comments_text` at spawn, so anything included here reaches it.
    A comment (not a body edit) is deliberate: rewriting the issue body
    would shift the user-content hash and trip `_detect_user_content_change`
    into re-decomposing the issue on the next tick.

    Every field beyond `decision` is best-effort. `_parse_manifest` only
    validates the decision string for the single branch, so `rationale` /
    `affected_files` / `notes` may be any JSON value or missing; coerce
    non-strings / non-lists to empty rather than parking a valid single
    decision after the agent already ran.
    """
    rationale = _single_manifest_text(
        manifest, "rationale", "(no rationale provided)",
    )
    lines = [f":mag: decomposer says this fits one context: {rationale}"]

    files = _single_manifest_files(manifest)
    if files:
        rendered = "\n".join(f"- `{file_path}`" for file_path in files)
        lines.append(f"**Affected files:**\n{rendered}")

    notes = _single_manifest_text(manifest, "notes")
    if notes:
        lines.append(f"**Implementation notes:**\n{notes}")

    return _SECTION_SEP.join(lines)
