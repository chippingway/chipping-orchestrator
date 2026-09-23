# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The prompt an issue-backed requirements edit is answered with, and its record.

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
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    drift as _drift,
    prompt_context as _prompt_context,
    prompt_delivery as _delivery,
)


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
