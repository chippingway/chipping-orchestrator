# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared prompt placeholders, foreground-run instructions, and commit and report contracts.

Foreground instructions spell out the one-shot execution model and the AGY
asynchronous-command contract (waiting within the current response via tools
like `manage_task` while `RUNNING`). The developer report contract is spelled
from the marker vocabulary its parser reads, so every developer prompt teaches
exactly the outcomes `report_outcomes` accepts."""
from __future__ import annotations

from orchestrator.workflow.engine import report_outcome_models as _report_models

_NO_BODY = "(no body)"

_NO_PRIOR_COMMENTS = "(no prior comments)"

_DEVELOPER_REPORT_CHAR_BUDGET = 4000

_FOREGROUND_ONLY_NOTE = (
    "IMPORTANT: your session terminates the moment you finish responding -- "
    "nothing keeps running between turns, and a later resume starts a fresh "
    "process. NEVER start a background job (build, test run, Miri, server) "
    "and end your turn intending to check it later: the job dies with your "
    "session and its result will never be seen. Run all builds and tests in "
    "the foreground and wait for them to complete before you commit or reply. "
    "For asynchronous commands (such as in AGY sessions), you must use "
    "supported wait/status tools such as `manage_task` within the current "
    "response: a `RUNNING` status requires continued polling or waiting, and "
    "ending the response to await a notification terminates AGY and cancels "
    "the command."
)

# The history this note sends an agent to read already carries the ` (#N)`
# references publication appended to it, so "mirror the style" has to exclude
# them explicitly: an agent copying one has only the issue number to reach for,
# and the subject would land naming the issue and the pull request both.
_COMMIT_STYLE_NOTE = (
    "Before committing, run `git log --oneline -20` to see how recent commit "
    "subjects are formatted, and write your subject in the SAME "
    "repository-local style. Mirror whatever subject/prefix convention that "
    "history uses rather than assuming a fixed set of types -- it may be a "
    "`<type>: <subject>` form, or a project-specific prefix such as `event:` "
    "or `career:`; the repo's own recent history is the source of truth. Keep "
    "the subject a single short, imperative line.\n\n"
    "Mirror the descriptive part of that style only. A trailing ` (#N)` on a "
    "subject in that history is publication metadata the orchestrator "
    "appended when it published the change, not a convention to copy: write "
    "no numeric suffix of your own, and never end the subject with the number "
    "of the issue you are working on. The orchestrator supplies the pull "
    "request reference.\n\n"
    "The commit message MUST be the subject line only -- no extended "
    "description / body and no `Co-Authored-By:` (or other) trailer. Use "
    "`git commit -m \"<subject>\"` with a single `-m`."
)

# Every developer prompt carries this whole, resumes included: a resumed
# session's transcript may predate the contract or hold another stage's prompt.
_DEVELOPER_REPORT_NOTE = (
    "Developer report: you write it, and the orchestrator publishes it. "
    "Whenever this task ends in finished work -- with a new commit or without "
    "one -- your final message MUST end with a concise, complete, current "
    "completion report for this issue. Keep the report body at or below "
    f"{_DEVELOPER_REPORT_CHAR_BUDGET:,} characters. Make it self-contained, "
    "but describe the final branch state rather than the journey: do not repeat "
    "the issue body, preserve a history of review rounds or earlier reports, "
    "enumerate every touched file, or list every individual test. Include only "
    "what the branch changes and why, the verification performed and its "
    "outcome, and unresolved risks or decisions a reviewer must weigh. Write "
    "the complete current report rather than only the latest delta, because it "
    "supersedes every earlier report. Publishing it on the pull request is "
    "routine orchestrator work that needs no permission: do NOT post or edit "
    "the report yourself, and do NOT ask a human whether or how to publish "
    "it. Never create an empty commit, or any change made only to carry a "
    "report -- a report that needs no repository change is delivered with no "
    "commit at all. The one finished reply without a report is an `ACK:` "
    "line, where this prompt offers one.\n\n"
    "End with EXACTLY one of these two report outcomes:\n\n"
    "1. Report ready for publication. Put the complete report between these "
    "two lines, each alone on its own line and outside any code fence, with "
    "nothing after the closing line:\n\n"
    f"  {_report_models._REPORT_READY_MARKER}\n"
    "  <complete report>\n"
    f"  {_report_models._REPORT_END_MARKER}\n\n"
    "2. Report already on the pull request. Use this ONLY when a complete, "
    "current report is already published on this issue's pull request -- for "
    "example one a human posted or edited -- and you read it during this run. "
    "End with this single line, outside any code fence:\n\n"
    f"  {_report_models._REPORT_VERIFIED_MARKER} <location> <revision>\n\n"
    f"<location> is `{_report_models._PULL_REQUEST_URL_SHAPE}` for the pull "
    "request description, or that URL followed by "
    f"`{_report_models._COMMENT_ANCHOR_SHAPE}` for a comment on it. <revision> "
    f"is `{_report_models._REVISION_PREFIX}` followed by the 64 lowercase hex "
    "digits of the SHA-256 of that report's text exactly as GitHub returns "
    "it. The orchestrator re-reads the location and accepts the outcome only "
    "while its text still matches.\n\n"
    "No other line of your message may start with "
    f"`{_report_models._REPORT_MARKER_PREFIX}`, and a report outcome never "
    "shares a message with an `ACK:` line. A report outcome means the work is "
    "finished: if you have a question, disagree with a request, or could not "
    "finish, emit neither outcome and end with your question for the human "
    "instead."
)

# A fresh respawn's preamble precedes every stage's task, including ones that
# end on a marker of their own, so it defers the outcome to the task below.
_RESPAWN_REPORT_NOTE = (
    "Wherever the task below asks for your completion report, write one concise "
    "report about the final state of the whole branch, the previous session's "
    "commits included. You write the report and the orchestrator publishes it as "
    "routine work: there is no permission to ask for, nothing of yours to push "
    "or post, and no empty commit to make just to carry it. End with the exact "
    "report outcome that task describes -- the "
    f"`{_report_models._REPORT_READY_MARKER}` ... "
    f"`{_report_models._REPORT_END_MARKER}` block or the "
    f"`{_report_models._REPORT_VERIFIED_MARKER} <location> <revision>` line."
)

_CONTINUE_RETRY_PROMPT = (
    "Resuming after a session/usage limit, execution failure "
    "(`agent_execution_failed`), or a silent session failure. "
    "Re-read the issue requirements and the conversation in your transcript, "
    "then CONTINUE the work already in progress and COMMIT any remaining "
    "changes in your current worktree. Do NOT push -- the orchestrator pushes "
    "and re-runs the reviewer."
)

# The style note rides along for the same reason the report contract does, and
# one more: a developer resume can rotate into a FRESH session, where the only
# text ahead of this is the respawn preamble. That preamble teaches no subject
# contract, so a retry asking a brand-new agent to COMMIT would otherwise reach
# it with nothing said about what its subject may carry.
_DEVELOPER_CONTINUE_RETRY_PROMPT = (
    f"{_CONTINUE_RETRY_PROMPT}\n\n{_COMMIT_STYLE_NOTE}\n\n"
    f"{_DEVELOPER_REPORT_NOTE}\n\n{_FOREGROUND_ONLY_NOTE}"
)
