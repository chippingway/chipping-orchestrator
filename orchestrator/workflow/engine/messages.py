# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an agent's last message says apart from the marker that ends its
stage, and the one form the orchestrator quotes that message back in.

The read side is a drift acknowledgement and the two commands an operator
writes. The acknowledgement takes the LAST `ACK:` match, the convention the
`completion_verdicts` owner reads its own markers under, so one quoted from a
template earlier in a long message loses to the concluding line.
`/orchestrator continue` is the first of the two a human writes, so it also
owns the refusal posted when that command arrives without the guidance the
park is actually waiting on.

`/orchestrator authorize-oversized <commit>` is the second, and only its
SYNTAX is here. What it means -- which candidate it may publish, what has to be
proved before it does, and what the record it earns says -- is the late-split
stage owner's, because that is the only place the frozen pair and the
measurement it names exist. Read from the WHOLE comment and nowhere else: it
bypasses the one gate that stops unreviewed bulk reaching a pull request, so a
line of it inside a paragraph is prose that mentions the command rather than a
gesture anybody made, and prose about an oversized candidate is guidance the
developer is resumed against. The argument is captured as whatever was written
rather than as a commit, because a malformed one is a command this workflow
owes an answer to and not a line it never saw.

The write side is `_as_blockquote`, the one form every agent output an issue
carries is quoted in -- a verdict body, a park's last message, the stderr the
`agent_diagnostics` owner beside this one renders when there was no usable
message at all.
"""
from __future__ import annotations

import re

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments

_DRIFT_ACK_RE = re.compile(r"^\s*ACK:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

_CONTINUE_PARK_REASONS = frozenset(("agent_silent", "agent_timeout"))

_ORCHESTRATOR_CONTINUE_RE = re.compile(
    r"^[ \t]*/orchestrator[ \t]+continue[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

# The command that publishes one oversized candidate a human has read, as a
# whole line. Anchored at both ends like the continue above it, and matched
# against the whole comment by the reader below, so a park notice spelling it
# out inside a sentence is never read back as somebody's authorization.
_AUTHORIZE_OVERSIZED_RE = re.compile(
    r"^[ \t]*/orchestrator[ \t]+authorize-oversized"
    r"(?P<candidate>[ \t]+[^\r\n]*?)?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

_CONTINUE_NEEDS_GUIDANCE_MSG = (
    f"{config.HITL_MENTIONS} `/orchestrator continue` needs your actual "
    "guidance here: this park is waiting on a real answer (an agent question, "
    "or a worktree it could not finish), not a generic continue. Reply with "
    "the specific change to make, or relabel the issue, to proceed."
)


def _as_blockquote(text: str) -> str:
    """Render `text` as a Markdown blockquote (each line prefixed with `> `)."""
    prefixed = text.replace("\n", "\n> ")
    return f"> {prefixed}"


def _drift_ack_reason(last_message: str) -> str | None:
    """Return the dev's ACK justification if `last_message` carries the
    explicit `ACK: ...` marker, or None when no marker is present.

    Takes the LAST match (the convention `completion_verdicts` reads its
    markers under) so a stray reference earlier in the message loses to the
    concluding line.
    """
    if not last_message:
        return None
    matches = list(_DRIFT_ACK_RE.finditer(last_message))
    if not matches:
        return None
    return matches[-1].group(1).strip() or None


def _parse_orchestrator_continue(comments: list) -> list:
    """Return the comments whose body contains an exact-line
    `/orchestrator continue` operator command."""
    return [
        comment
        for comment in comments
        if _ORCHESTRATOR_CONTINUE_RE.search(comment.body or "")
    ]


def _is_bare_orchestrator_continue(comment) -> bool:
    """True when the comment's ENTIRE body is the command line and nothing
    else -- a content-free nudge whose consumption drops no guidance."""
    return (
        _ORCHESTRATOR_CONTINUE_RE.fullmatch((comment.body or "").strip())
        is not None
    )


def _authorized_oversized_candidate(comment) -> str | None:
    """The commit an operator's whole-comment authorization names, or None.

    None is "this comment is not that command", which is what every caller
    branches on: the drift hash leaves the command out of the requirements it
    counts, and the late stage reads the argument out of it. A command with
    nothing after it answers with the empty string rather than None -- it is
    still a command, and one nobody could act on is owed the same answer a
    misspelled commit is.

    The whole comment or nothing. What this licenses is a bypass of the size
    gate, so a line of it under a paragraph is text that mentions the command
    rather than a decision somebody made -- and that paragraph is guidance,
    which resumes the developer against it.
    """
    written = (getattr(comment, "body", "") or "").strip()
    found = _AUTHORIZE_OVERSIZED_RE.fullmatch(written)
    if found is None:
        return None
    return (found.group("candidate") or "").strip()


def _continue_command_action(new_comments: list, park_reason) -> str:
    """Classify an operator `/orchestrator continue` on a parked dev-session
    stage (`implementing` / `documenting` / `validating` / `resolving_conflict`)
    whose park carries no preserved feedback batch to replay -- the counterpart
    to `fixing`'s richer `_handle_continue_command`, which can reconstruct an
    in_review batch.

    `new_comments` is the fresh trusted issue-thread comments since the last
    consumed watermark. Returns:

      * ``"retry"``       -- a retryable session-failure park
        (`agent_silent` / `agent_timeout`) whose fresh comments are ALL bare
        continues: retry the parked dev flow intentionally, without feeding
        the bare command to the dev as guidance.
      * ``"refuse"``      -- a park that needs real guidance (a genuine agent
        question, a dirty worktree, a diverged branch, ...) whose fresh
        comments are ALL bare continues: the command carries no answer, so
        refuse and stay parked.
      * ``"passthrough"`` -- no continue command is present, or the command
        arrived alongside genuine guidance: the caller's normal
        resume / drift path handles the comments (and feeds that guidance to
        the dev).
    """
    if not _parse_orchestrator_continue(new_comments):
        return "passthrough"
    if not all(
        _is_bare_orchestrator_continue(comment) for comment in new_comments
    ):
        return "passthrough"
    if park_reason in _CONTINUE_PARK_REASONS:
        return "retry"
    return "refuse"


def _refuse_parked_continue(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Consume a content-free `/orchestrator continue` and post a refusal on a
    park that needs real human guidance, leaving the issue parked.

    Shared by the dev-parking stages (`implementing`, `documenting`,
    `validating`, `resolving_conflict`): a bare continue on a non-retryable
    park carries no answer, so post a single note and advance the
    issue watermark past BOTH the command and the refusal (so neither re-fires
    next tick and the refusal is not re-posted every poll). `awaiting_human`
    stays set. Mutates in-memory state only; the caller writes pinned state.
    """
    _comments._post_issue_comment(gh, issue, state, _CONTINUE_NEEDS_GUIDANCE_MSG)
    latest = gh.latest_comment_id(issue)
    if latest is not None:
        state.set("last_action_comment_id", latest)
