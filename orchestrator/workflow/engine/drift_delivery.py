# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The prompt a requirements edit is answered with, and its record.

One read of the thread answers both questions a resume asks it -- what the
developer is quoted, and what the issue may mark answered -- because they are
halves of one fact. Read twice, a stage quotes a comment that landed between
the reads and records a watermark below it, or records one above a comment it
never showed anybody; either way a human's words are delivered twice or not at
all.

Three things follow from freezing it, and they are the general rules for
issue-backed feedback rather than anything about a body edit. Context the
excerpt bound dropped reaches no agent, so the watermark stops below it and
the scan that owns that surface still delivers it. A reply written while the
agent is out is in neither the prompt nor the mark. And the requirements
revision recorded is the fingerprint of THAT read -- the baseline a later edit
is compared against -- so an edit arriving afterwards is still an edit.

Who settles the record is the road that disposes the run, since only it knows
whether an agent ever read the prompt through.

The text is also what a fresh respawn is re-grounded with, where the resume
turns into one -- a rotated, retired or poisoned session. That preamble quotes
a conversation of its own, and read live it would be a second reading of the
thread: newer than this record, and carrying to the agent a comment the
settlement would leave unread.

A resume on an OPEN PULL REQUEST quotes a second surface below the first, and
`_pr_drift_resume_prompt` freezes both into the one record. The two are read
apart because they are quoted apart: the thread through an excerpt that can
drop its head, the pull request's conversation entire. Only the comments that
reach the prompt are named as delivered -- an outsider's is kept as refused, so
the walk that carries a cursor may cross a comment no reader is owed without
crossing one the excerpt cut. Inline review comments and review summaries are
on neither surface and enter no prompt here, so nothing about them is recorded
and the round that reads them still delivers them.

What the record may be SETTLED from is narrower than what it names, and the
reason is that the two reads are a moment apart. GitHub numbers both surfaces
in one ascending space, and one cursor -- `pr_last_comment_id` -- spans both:
advancing it to an id claims every id below it on EITHER surface is delivered
or owed to nobody. A comment landing on the surface read first, after that
read, is in neither half of this record, and an id above it on the surface
read second would carry the shared cursor straight over it. Nothing built from
two readings can answer that; only a reading of both surfaces at one moment
can, and that reading is the caller's watermark carry. So the road that
settles this record writes the issue thread's own cursor and the requirements
revision, and leaves the shared one to the walk -- which crosses exactly what
this record names and stops at the first id it does not.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    drift as _drift,
    prompt_context as _prompt_context,
    prompt_delivery as _delivery,
)

# What a surface a prompt quotes ENTIRE is recorded under: no bound at all, so
# the record can name no omission the prompt did not make.
_UNBOUNDED_EXCERPT = None

# The heading the pull request's own comments are quoted under, so a developer
# reading one prompt can tell which surface a comment was written on.
_PR_CONVERSATION_HEADING = "Unread PR conversation comments:"

# The paragraph break the prompt builders assemble their sections with.
_SECTION_SEP = "\n\n"


@dataclass(frozen=True)
class _DriftPrompt:
    """The prompt one requirements edit is answered with, and its record.

    Both off ONE read, because they are halves of the same fact: `text` is
    what the developer is handed and `delivery` names the very comments that
    text is made of. Built apart -- a prompt rendered from one read and a
    watermark taken from another -- the tick quotes a comment it never records
    or records one it never quoted, and either way a human's words are
    delivered twice or not at all.

    `delivery` is settled by whoever disposes the run, and only for an outcome
    that counts it as delivered, so a shutdown kill, a live pause, or a launch
    nothing invoked leaves the edit exactly as unanswered as it was.
    """

    delivery: _delivery.PromptDeliverySnapshot
    text: str


def _drift_resume_prompt(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> _DriftPrompt:
    """Freeze what a dev resume is told about a requirements edit.

    The read is bounded exactly as the prompt quotes it, so the record says
    what the excerpt LEFT OUT as well as what it carried -- and what it left
    out holds the issue watermark below it, leaving that context for the road
    that delivers it rather than crossing it here.
    """
    delivery = _prompt_context._delivered_thread(gh, issue, state)
    return _DriftPrompt(
        delivery,
        _drift._build_user_content_change_prompt(issue, delivery.rendered_text),
    )


def _pr_drift_resume_prompt(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pr_conversation: list,
) -> _DriftPrompt:
    """Freeze what a resume on an open pull request is told about an edit.

    Two surfaces, one record. The bounded issue excerpt comes first and the
    pull request's unread conversation below it, and the record names exactly
    the comments that text is made of on each -- so the cursor each surface
    answers to advances over what a developer read there and stops below what
    it did not. Quoted from one read and settled from another, the resume
    would mark the thread read to a tip that includes the notice it posted
    getting there.

    `pr_conversation` is the caller's own read of the surface it owns, already
    stripped of this orchestrator's posts. It is handed over rather than read
    here because the cursor it was taken against is the caller's too, and a
    second read minutes later carries a comment the settlement never saw.

    No `issue_watermark_field` is named, so nothing settled from this record
    writes the cursor the two surfaces SHARE. That cursor spans a numbering
    this record covers at two different moments, and only the caller's merged
    walk reads both at one (see the module note above).
    """
    issue_side = _prompt_context._delivered_thread(gh, issue, state)
    appended = _delivered_pr_conversation(pr_conversation, state)
    quoted = _both_surfaces(issue_side, appended)
    return _DriftPrompt(
        _delivery.create_prompt_delivery_snapshot(
            entries=issue_side.entries + appended.entries,
            requirements_revision=issue_side.requirements_revision,
            rendered_text=quoted,
            state=state,
        ),
        _drift._build_user_content_change_prompt(issue, quoted),
    )


def _delivered_pr_conversation(
    pr_comments: list, state: PinnedState,
) -> _delivery.PromptDeliverySnapshot:
    """The record of the PR-conversation comments a prompt appends WHOLE.

    Uncapped, because every comment handed over is quoted: a record taken
    under a bound would name an omission the prompt never made, and the pull
    request's cursor would then stop below a comment the developer read and
    hand it back as fresh feedback on the next tick. The issue thread beside
    it is the bounded half, which is why the two are recorded apart.

    Our own posts are recognised by recorded id, so a notice this tick wrote
    is never read back as a reviewer's words. What the trust filter refuses
    stays as a refused entry rather than vanishing: nobody is owed an
    outsider's comment, so the walk that carries the cursor may cross it,
    while an entry nothing recorded would have stopped that walk there
    forever.
    """
    return _delivery.create_prompt_delivery_snapshot(
        pr_conversation_comments=pr_comments,
        max_chars=_UNBOUNDED_EXCERPT,
        retained_ids=frozenset(_comments._orchestrator_ids(state)),
        state=state,
    )


def _both_surfaces(
    issue_side: _delivery.PromptDeliverySnapshot,
    appended: _delivery.PromptDeliverySnapshot,
) -> str:
    """The conversation two surfaces make, in the order the prompt reads it.

    Rendered off the records themselves rather than off the comment lists, so
    the text cannot quote a comment the record left out or omit one it names.
    """
    lines = [
        entry.rendered_line
        for entry in appended.delivered_inputs(_delivery.SURFACE_PR_CONVERSATION)
    ]
    if not lines:
        return issue_side.rendered_text
    prefix = (
        f"{issue_side.rendered_text}{_SECTION_SEP}"
        if issue_side.rendered_text else ""
    )
    block = _SECTION_SEP.join(lines)
    return f"{prefix}{_PR_CONVERSATION_HEADING}{_SECTION_SEP}{block}"
