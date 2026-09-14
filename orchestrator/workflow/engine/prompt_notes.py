# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared prompt placeholders, foreground-run instructions, and commit contracts."""
from __future__ import annotations

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
