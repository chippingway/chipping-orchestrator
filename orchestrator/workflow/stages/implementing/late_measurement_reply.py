# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reserve trusted bare-continue replies for an active measurement park.

The current reason and wait must agree before a thread read can answer
this park. Mixed feedback stays with its stage; only a batch consisting
entirely of bare continue commands belongs to measurement recovery.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github import (
    client as _client,
    comments as _github_comments,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import (
    messages as _messages,
)
from orchestrator.workflow.stages.implementing import (
    late_measurement_state as _late_measurement_state,
    state as _state,
)


def _answers_the_measurement_park(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState,
) -> list:
    """The bare continues a human has written on a measurement park, if any.

    Empty for everything else, and each exclusion is its own answer. An issue
    parked for another reason is not this park's to retry; a thread with
    nothing new on it is a human who has not replied yet; and a reply carrying
    real words is guidance, which belongs to the ordinary resume that feeds it
    to the developer rather than to a reading taken behind their back.

    A bare `/orchestrator continue` is the one reply that means "the step you
    could not take, take again": the failure was a reading rather than a
    question, so what it earns is the same pair measured once more and no
    agent at all.

    Which batch that is, the reader below decides -- so the two roads that
    would otherwise spend one of these answer the same question off the same
    shape of read, and a command landing between two of them is deferred to
    the poll that can act on it rather than consumed by one that cannot.
    """
    if state.get(_state._PARK_REASON) != _late_measurement_state.PARK_MEASUREMENT_FAILED:
        return []
    if not state.get(_state._AWAITING_HUMAN):
        return []
    replies = _github_comments.filter_trusted(
        gh.comments_after(issue, state.get(_state._LAST_ACTION_COMMENT_ID)),
    )
    return replies if _reserved_for_the_measurement_park(replies, state) else []


def _reserved_for_the_measurement_park(replies: list, state) -> bool:
    """Whether this batch is one only this park's own road may consume.

    Every road that reads a parked thread reads it again after the road above
    it handed the tick back, and the time in between is time an operator can
    write in. A bare continue landing there is in a later road's batch and in
    nobody else's, and both of the roads behind this one would SPEND it: the
    parked-continue classifier reads a command on a park that is not a session
    failure as one carrying no answer, refuses it, and consumes the thread
    past its own refusal; the generic resume reads it as guidance, pays for a
    developer to answer it, and consumes it too. Either way the operator's
    retry is gone and the reading they asked for is one nothing will ever
    take.

    So while this park stands, a batch this road would act on belongs to it,
    and the two behind it hand the whole TICK back rather than sparing the one
    reply. A watermark is one number and neither of them is the last thing to
    move it: the run a resume starts parks, and that park stamps the thread
    read to the notice it posts, which lands above the command and takes it.
    Deferred entire, nothing is lost -- the next poll reads the same batch and
    re-measures the pair on it.

    ALL of them, which is this park's own rule rather than the last-reply one
    the authorization command is read by. A reading is retried by a reply that
    asks for nothing else; a batch carrying real words is guidance, and the
    ordinary resume feeding it to the developer is exactly what it is owed.

    Asked only while the park is standing, and only of a batch read the way
    this owner reads one. A comment of ours above the watermark is in that
    read, so it is in this one: reserved off a narrower batch, a tick would
    defer what the road it deferred to then refuses, and the two would hand
    the same thread back and forth forever.
    """
    if state.get(_state._PARK_REASON) != _late_measurement_state.PARK_MEASUREMENT_FAILED:
        return False
    if not state.get(_state._AWAITING_HUMAN):
        return False
    if not _messages._parse_orchestrator_continue(replies):
        return False
    return all(
        _messages._is_bare_orchestrator_continue(reply) for reply in replies
    )
