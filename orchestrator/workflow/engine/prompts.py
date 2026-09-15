# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Implementation, review, documentation, fixing, and conflict-resolution prompts.

Trust-filtered thread and repository context comes from prompt_context. Shared
placeholders and execution notes come from prompt_notes; every response marker
matches the parser that decides the corresponding workflow outcome. Conversation
and decomposition builders live beside these delivery-stage builders."""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.workflow.engine import (
    messages as _messages,
    prompt_context as _prompt_context,
    prompt_notes as _prompt_notes,
)

_MAX_FILES_SHOWN = 20


def _build_implement_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    specs: list[_config_models.RepoSpec],
) -> str:
    body = issue.body or _prompt_notes._NO_BODY
    convo = comments_text or _prompt_notes._NO_PRIOR_COMMENTS
    tracked = _prompt_context._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    return (
        f"You are the implementer for GitHub issue #{issue.number}: {issue.title!r}.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
        "Implement the change in the current working directory (a fresh git worktree on a "
        "new branch). When done, COMMIT your changes with a clear message. Do NOT push - "
        "the orchestrator pushes and opens the PR.\n\n"
        f"{_prompt_notes._COMMIT_STYLE_NOTE}\n\n"
        f"{_prompt_notes._DEVELOPER_REPORT_NOTE}\n\n"
        f"{_prompt_notes._FOREGROUND_ONLY_NOTE}\n\n"
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
    body = issue.body or _prompt_notes._NO_BODY
    convo = comments_text or _prompt_notes._NO_PRIOR_COMMENTS
    tracked = _prompt_context._build_tracked_repos_context(spec, specs)
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
        f"{_prompt_notes._RESPAWN_REPORT_NOTE}\n\n"
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
    body = issue.body or _prompt_notes._NO_BODY
    convo = comments_text or _prompt_notes._NO_PRIOR_COMMENTS
    base_ref = f"{spec.remote_name}/{spec.base_branch}"
    tracked = _prompt_context._build_tracked_repos_context(spec, specs)
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
    body = issue.body or _prompt_notes._NO_BODY
    convo = comments_text or _prompt_notes._NO_PRIOR_COMMENTS
    base_ref = f"{spec.remote_name}/{spec.base_branch}"
    tracked = _prompt_context._build_tracked_repos_context(spec, specs)
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
        f"{_prompt_notes._COMMIT_STYLE_NOTE}\n\n"
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
        f"{_prompt_notes._FOREGROUND_ONLY_NOTE}"
    )


def _build_fix_prompt(review_feedback: str) -> str:
    feedback = review_feedback.strip() or "(reviewer left no detail)"
    quoted = _messages._as_blockquote(feedback)
    return (
        "An automated reviewer requested changes on your implementation. Address each item "
        "below: COMMIT every repository change in your current worktree, and answer an item "
        "that asks only for report content -- a missing explanation, verification detail, or "
        "summary -- in your updated report, with no commit for it. Do NOT push -- the "
        "orchestrator pushes, publishes your report, and re-runs the review.\n\n"
        f"Review feedback:\n\n{quoted}\n\n"
        f"{_prompt_notes._COMMIT_STYLE_NOTE}\n\n"
        f"{_prompt_notes._DEVELOPER_REPORT_NOTE}\n\n"
        f"{_prompt_notes._FOREGROUND_ONLY_NOTE}\n\n"
        "If you genuinely disagree with a point, end your final message with a question for "
        "the human and leave that item un-fixed; the orchestrator will park the issue for "
        "human review. Otherwise, address all items (a single commit is fine where one is "
        "needed)."
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
        f"{_prompt_notes._FOREGROUND_ONLY_NOTE}"
    )
