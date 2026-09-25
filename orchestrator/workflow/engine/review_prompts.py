# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The prompt a fresh reviewer is handed, the developer report inside it included.

The reviewer is the one agent whose prompt quotes a pull request's own content.
The developer report it reviews beside the diff is resolved and re-read by the
validating stage and quoted here whole -- between the issue and the commands
that inspect the branch -- because the thread excerpt above it is bounded and
covers the issue thread alone, and a reviewer left to fetch the pull request
reads whichever report it finds. Every marker it teaches is the one
`completion_verdicts` parses; it teaches none of the developer's report
outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.workflow.engine import (
    messages as _messages,
    prompt_context as _prompt_context,
    prompt_notes as _prompt_notes,
    review_subjects as _review_subjects,
)


@dataclass(frozen=True)
class ReviewHandover:
    """What a reviewer is told about the work beyond the issue itself.

    `dev_backend` names the session that implemented it; `subject` is what the
    validating stage resolved for this round, the report included. None is a
    reviewer handed no subject, which is told no report is recorded.
    """

    dev_backend: str = "agent"
    subject: _review_subjects.ReviewSubject | None = None


_NOTHING_HANDED = ReviewHandover()


def _build_review_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    specs: list[_config_models.RepoSpec],
    handover: ReviewHandover = _NOTHING_HANDED,
) -> str:
    """The fresh reviewer's prompt, over what the stage resolved for it.

    The handover's subject carries the developer report the reviewer is
    handed, quoted in full: the reviewer judges the report the pull request
    carries as well as the diff, and a reviewer left to fetch one reads
    whichever it finds. No subject, or one without a report, says no report is
    recorded.
    """
    body = issue.body or _prompt_notes._NO_BODY
    convo = comments_text or _prompt_notes._NO_PRIOR_COMMENTS
    base_ref = f"{spec.remote_name}/{spec.base_branch}"
    tracked = _prompt_context._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    return (
        f"You are an automated code reviewer for GitHub issue #{issue.number}: {issue.title!r}. "
        f"A separate {handover.dev_backend} session has implemented this issue and committed to the current "
        f"branch. The base branch is `{base_ref}`.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
        f"{_review_report_block(handover.subject)}\n\n"
        "Inspect the change with:\n"
        f"  git log --oneline {base_ref}..HEAD\n"
        f"  git diff {base_ref}...HEAD\n\n"
        "Review the change against the issue requirements, and the developer report "
        "against the change: a report that misstates the work, or leaves out what the "
        "requirements or earlier review asked it to explain, is a change to request like "
        "any other. Flag correctness bugs, missing "
        "tests, scope creep, obvious style issues, and anything that would block a human "
        "approver. Do NOT edit or commit anything -- you are a reviewer only.\n\n"
        "Your final message MUST end with exactly one of these markers, alone on its own line:\n"
        "  VERDICT: APPROVED\n"
        "  VERDICT: CHANGES_REQUESTED\n\n"
        "If CHANGES_REQUESTED, list the specific items above the verdict line as a numbered "
        "list so the implementer can address them one by one. If the change is acceptable as "
        "is, write VERDICT: APPROVED with a one-line justification above it."
    )


def _review_report_block(subject: _review_subjects.ReviewSubject | None) -> str:
    """The developer report a reviewer is handed, or the note that there is none.

    Quoted whole and never cut: the stage hands over only a report it re-read
    and held to its recorded digest, so the words below are that revision
    exactly. A report about another commit, or written against requirements
    the issue has moved past, is refused before any reviewer is spawned; what
    can still stand between the report and the thread the reviewer reads is a
    reply that bought this round, and the reviewer is told the issue has moved
    on rather than left to infer it from two hashes.
    """
    if subject is None or subject.report is None:
        return (
            "Developer report:\nNo developer report is recorded for this pull "
            "request; review the change against the issue alone."
        )
    report = subject.report
    notes = [_review_report_heading(report)]
    if (
        subject.requirements_revision
        and subject.requirements_revision != report.requirements_revision
    ):
        notes.append(
            "The issue has changed since this report was written; the issue "
            "body and conversation above are the current requirements.",
        )
    notes.append(_messages._as_blockquote(report.text))
    return "\n\n".join(notes)


def _review_report_heading(report: _review_subjects.ReviewReport) -> str:
    """What the quoted report is, where it was read, and what it is about."""
    location = report.location
    where = (
        "its description" if location.comment_id is None
        else f"comment {location.comment_id}"
    )
    revision = report.report_revision
    return (
        f"Developer report (revision {revision}, re-read in full by the "
        f"orchestrator from PR #{location.pr_number}, {where}; it reports on "
        f"commit `{report.source_sha}` against requirements revision "
        f"`{report.requirements_revision}`). It is the complete, current report "
        "for this pull request and supersedes every earlier report or agent "
        "message there, so review it as given here rather than fetching the "
        "pull request for another."
    )
