# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The parks on either side of an auto-rebase replay handed to its late generation.

A park stands for one of three owners. The attempt's own road takes the
`auto_base_rebase_*` reasons, and the handoff (`rewrite_takeover`) retires
such a park with the attempt, since nothing is left to come back for the
reply it asks for -- spending, in the same write, the replies that only asked
for that retry (`rewrite_replies`). The late domain takes every reason spelled
under its `late_` prefix, the size gate's and the adjudication's alike, and
shares the spent spawn budget's `retry_cap` with every stage; the
adjudication answers those on its own road. Every other park is somebody
else's question.

Nothing on `workflow:decomposing` answers somebody else's question: the label
is the adjudication's, and its verdict would take the park's flags over with
one of its own. So such a park survives every step that brings a replay to
an adjudication. The size gate's route keeps it where an auto-rebase anchor
is pinned (`stages/implementing/late_park_retirement.py`) -- the recovery a
stage's park let through with no reply spent -- the handoff leaves it, and
the dispatcher holds the adjudication behind it (`holds_the_adjudication`)
until a human replies past its notice. The adjudication then reads that reply
as it reads any reply on a park it does not own: guidance answers the park
and resumes the developer, and a bare `/orchestrator continue` lets the
adjudication run.

The attempt's notice outlives its park. It still stands on the thread asking
for a reply once the handoff has taken the park down, and a tick lost after
that write -- before the adjudication first reads the thread -- leaves the
human to answer it with nobody left to recognize the answer as a retry. So,
up to that first reading and with no park standing, a reply that only asks
for the retry can be answering nothing else: the same hold records it read
for the attempt before the adjudication is reached, in a guarded write of its
own, and a write that did not land holds the tick. Past that reading the
adjudication's own parks and baseline say what a reply answers.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    report_commits as _commits,
    retry_values as _retry_values,
    rewrite_replies as _rewrite_replies,
)
from orchestrator.workflow.late_split import keys as _late_keys, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration

log = logging.getLogger("orchestrator.workflow")

# Every park the late domain takes is spelled under this prefix, and the spent
# spawn budget's is the one it shares with every other stage.
_LATE_PREFIX = "late_"

_PARK = (_base_sync_state._AWAITING_HUMAN, _base_sync_state._PARK_REASON)

# The write that spends a retry the attempt's notice drew after its handoff:
# the two marks a retry is recorded read on, decided on the generation that
# took the replay over and on no park standing.
_SPENT_RETRY = _commits.ReportWrite(
    owned=frozenset(_rewrite_replies.REPLY_FIELDS),
    decided_on=frozenset((*_late_keys.LATE_STATE_KEYS, *_PARK)),
)


def stands_for_another_owner(state: PinnedState) -> bool:
    """Whether the park standing on `state` is neither the attempt's own nor the late domain's."""
    if not state.get(_base_sync_state._AWAITING_HUMAN):
        return False
    reason = str(state.get(_base_sync_state._PARK_REASON) or "")
    owned = reason.startswith(_LATE_PREFIX) or reason == _retry_values.PARK_RETRY_CAP
    return not owned and reason not in _base_sync_state._AUTO_REBASE_PARK_REASONS


def retires_its_park(gh: GitHubClient, issue: Issue, staged: PinnedState) -> bool:
    """Retire the park the attempt's road left, and stage the retry it was answered with read; whether a park stood.

    The replies are the ones past the watermark the park's notice moved, read
    before the park goes down.
    """
    answering = _rewrite_replies.AttemptReplies.past(staged)
    if not _attempts._retires_its_park(staged):
        return False
    _rewrite_replies.records_the_retry(gh, issue, staged, answering)
    return True


def holds_the_adjudication(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool:
    """Whether the adjudication of a replay this issue's generation took over is held this tick.

    Behind somebody else's park until a human replies past its notice: the
    reply is the answer, and the adjudication reads it. Otherwise a retry the
    attempt's notice drew past the handoff is spent first, and only a write of
    it that did not land holds the tick.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.publication.replayed_as(generation.candidate_sha):
        return False
    if stands_for_another_owner(state):
        return _waits_for_a_reply(gh, issue, state)
    return _spends_a_late_retry(gh, issue, state, generation)


def _waits_for_a_reply(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool:
    """Whether nobody has replied past the notice of the park another owner left; logged where nobody has."""
    if _rewrite_replies.replied_past_the_watermark(gh, issue, state):
        return False
    log.warning(
        "issue=#%d took its auto-rebase replay over beside a %r park nothing on its label answers; "
        "holding the adjudication until a human replies to it",
        issue.number, state.get(_base_sync_state._PARK_REASON),
    )
    return True


def _spends_a_late_retry(gh: GitHubClient, issue: Issue, state: PinnedState, generation: LateGeneration) -> bool:
    """Record read a retry the attempt's notice drew after the handoff; whether a write of it failed to land.

    Only before the adjudication's first reading of the thread -- its baseline
    unrecorded -- and with no park standing, where that notice is the only
    question on the thread a bare retry could answer.
    """
    if state.get(_base_sync_state._AWAITING_HUMAN) or generation.title_body_hash is not None:
        return False
    commit = _commits.ReportCommit(gh, issue, state)
    staged = commit.staging()
    _rewrite_replies.records_the_retry(gh, issue, staged, _rewrite_replies.AttemptReplies.past(staged))
    if staged.data == state.data:
        return False
    status = commit.lands(staged, _SPENT_RETRY).status
    log.info(
        "issue=#%d records a retry of its taken-over auto-rebase replay read ahead of the adjudication: %s",
        issue.number, status.value,
    )
    return status is not _commit_models.CommitStatus.COMMITTED
