# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hand an unpublished auto-rebase replay to the late generation that adjudicates it.

A clean auto rebase whose candidate the size gate hands to an adjudication
leaves two owners claiming one branch: the attempt (`git/base_sync/attempts.py`)
still anchors a replay nothing has published, and the live late generation
froze that same replay as its candidate. Each holds the other's road -- the
dispatcher holds the adjudication behind the anchor, and the generation
freezes the refresh that would end the attempt -- so this owner moves the
replay to the generation, durably, where the two provably describe the same
work.

The proof is of the pinned record alone and never of a checkout. The attempt
has to read back whole (`attempt_records`): the anchor a whole commit, the
terms it was made under, and the replay it recorded, with no announcement a
finish left for a push that landed. The generation has to be one late
adjudication itself would act on for this issue -- a record that passes the
late domain's own gate (`late_split/validation.py`), names this issue as the
one it is about, and freezes both its candidate and its measurement base --
live and measured past its ceiling, with its publication group whole. A
replay handed to anything less would be retired from the attempt into an
owner adjudication refuses, with nobody left to publish it. Then the two have
to agree on all four facts the replay is: the candidate is the replay, the
pull request is the attempt's, the head that pull request was frozen standing
on is the anchor the push is leased against, and the stage it was entered
from is the attempt's own.
Evidence short of that is INCOMPLETE and evidence of other work UNRELATED,
and both are left exactly as they stand for the recovery that answers them.

A proved pair is handed over in one guarded write (`report_commits`, as the
rewrite finish writes): the generation's publication group takes over the
replay (`late_auto_rebase_replay_sha`) and the whole attempt is retired,
decided on both records as they were read. The attempt is never retired
without the generation carrying the replay, and the frozen pair, the
measurement, and the publication group are left as the comment spells them.
A repeated handoff finds no attempt and a generation that already owns its
candidate, and writes nothing. A write sent and never confirmed may or may
not have landed: only the comment read again says which, and the handoff
asked over that reading answers OWNED or proves the pair afresh.

Ownership licenses no push. What the generation's settlement owes the replay
is the publication every authorized `single` makes -- under the operator's
authorization of that exact candidate, leased to the head the generation
froze -- and the report debt the replay leaves, recorded behind that push
(`stages/decomposition/late_replay_debt.py`).
"""
from __future__ import annotations

import logging
from enum import StrEnum
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    attempts as _attempts,
    state as _base_sync_state,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pinned_commit_models as _commit_models, report_commits as _commits
from orchestrator.workflow.late_split import (
    formats as _formats,
    keys as _late_keys,
    payloads as _payloads,
    state as _late_state,
    validation as _late_validation,
)
from orchestrator.workflow.late_split.models import LateGeneration

log = logging.getLogger("orchestrator.workflow")

_ANCHOR = _base_sync_state._PENDING_PUSH_SHA


class TakeoverOutcome(StrEnum):
    """What one handoff came to, and so whether the attempt or the generation owns the replay.

    TAKEN_OVER landed the generation's ownership and the attempt's retirement
    together; OWNED found that already done. ABSENT is no attempt standing, or
    no generation recorded to hand one to. INCOMPLETE and UNRELATED are an
    attempt left standing for its recovery: one side cannot show what the
    proof needs, or the two describe different work. REFUSED is a proved
    handoff whose write was refused with nothing written. UNCONFIRMED is one
    whose write went out and was never confirmed, so whether it landed is
    unknown until the comment is read again.
    """

    TAKEN_OVER = "taken_over"
    OWNED = "owned"
    ABSENT = "absent"
    INCOMPLETE = "incomplete"
    UNRELATED = "unrelated"
    REFUSED = "refused"
    UNCONFIRMED = "unconfirmed"


# The write that hands the replay over: it owns the attempt and the one late key
# that records the takeover, and is decided on both records it was proved on.
_TAKEOVER = _commits.ReportWrite(
    owned=frozenset((*_attempts._ATTEMPT_KEYS, _late_keys.AUTO_REBASE_REPLAY_SHA)),
    decided_on=frozenset((*_attempts._ATTEMPT_KEYS, *_late_keys.LATE_STATE_KEYS)),
)

# What a handoff whose write was refused, or never confirmed, is answered as.
_UNLANDED = MappingProxyType({
    _commit_models.CommitStatus.REFUSED: TakeoverOutcome.REFUSED,
    _commit_models.CommitStatus.UNCONFIRMED: TakeoverOutcome.UNCONFIRMED,
})


def takes_over(gh: GitHubClient, issue: Issue, state: PinnedState) -> TakeoverOutcome:
    """Hand the replay the pinned attempt made to the live generation adjudicating it, where the two prove one.

    `state` is the issue's pinned state as the caller holds it; the write is a
    guarded commit over the reading it was last synced with, and lands over
    `state` only where it lands at all.
    """
    proved, refusal = _proof(state, issue.number)
    if refusal:
        log.warning(
            "issue=#%d leaves its auto-rebase attempt standing rather than handing it to the late "
            "generation: %s (%s)", issue.number, refusal, proved.value,
        )
    if proved is not TakeoverOutcome.TAKEN_OVER:
        return proved
    return _hands_over(gh, issue, state)


def _hands_over(gh: GitHubClient, issue: Issue, state: PinnedState) -> TakeoverOutcome:
    """Land a proved handoff: the generation takes the replay over and the attempt is retired, in one write."""
    commit = _commits.ReportCommit(gh, issue, state)
    staged = commit.staging()
    replay = _late_state.read_late_generation(state).candidate_sha
    _late_state.record_replay_takeover(staged, replay)
    _attempts._clears_the_attempt(staged)
    unlanded = _UNLANDED.get(commit.lands(staged, _TAKEOVER).status)
    if unlanded is not None:
        log.warning(
            "issue=#%d the write handing the auto-rebase replay %.8s to its late generation came back %s; "
            "a refusal wrote nothing, and an unconfirmed write is known only once the comment is read again",
            issue.number, replay, unlanded.value,
        )
        return unlanded
    log.info(
        "issue=#%d handed the unpublished auto-rebase replay %.8s to late cycle %s; the attempt is retired",
        issue.number, replay, state.get(_late_keys.CYCLE_ID),
    )
    return TakeoverOutcome.TAKEN_OVER


def _proof(state: PinnedState, issue_number: int) -> tuple[TakeoverOutcome, str]:
    """What the pinned record proves about handing its attempt over, and why a proof that failed did."""
    generation = _late_state.read_late_generation(state)
    if not state.get(_ANCHOR):
        owner = not _unadjudicable(generation, issue_number)
        owned = owner and generation.publication.replayed_as(generation.candidate_sha)
        return TakeoverOutcome.OWNED if owned else TakeoverOutcome.ABSENT, ""
    if not generation.is_present:
        return TakeoverOutcome.ABSENT, ""
    incomplete = _incomplete(state, generation, issue_number)
    if incomplete:
        return TakeoverOutcome.INCOMPLETE, incomplete
    unrelated = _unrelated(state, generation)
    if unrelated:
        return TakeoverOutcome.UNRELATED, unrelated
    return TakeoverOutcome.TAKEN_OVER, ""


def _incomplete(state: PinnedState, generation: LateGeneration, issue_number: int) -> str:
    """Why either record cannot show what a handoff is proved on, or "" where both can.

    The attempt has to name its lease as a whole commit and its replay whole,
    since one still in flight names no replay and a damaged one names nothing
    anybody may act on. The generation has to be what publishes the replay
    and resumes the stage after it (`_unadjudicable`), with its whole
    publication group.
    """
    recorded = _attempt_records._pending_rewrite(state)
    unadjudicable = _unadjudicable(generation, issue_number)
    refusals = (
        (not _payloads.as_hex(state.get(_ANCHOR), _formats.COMMIT_LENGTHS), "its anchor is not a whole commit"),
        (not recorded.is_recorded, "its record of the replay is not whole"),
        (bool(unadjudicable), unadjudicable),
        (not generation.publication.is_complete, "the late generation names no whole publication"),
    )
    return next((reason for refused, reason in refusals if refused), "")


def _unrelated(state: PinnedState, generation: LateGeneration) -> str:
    """Why two whole records describe different work, or "" where they describe one replay.

    An announcement is a finish's mark for a push that already landed, so its
    attempt is no unpublished replay for an adjudication to own.
    """
    recorded = _attempt_records._pending_rewrite(state)
    publication = generation.publication
    refusals = (
        (_attempts._carries_an_announcement(state), "a finish announced the attempt's landing"),
        (recorded.sha != generation.candidate_sha, "the replay is not the generation's candidate"),
        (recorded.pr_number != publication.published_pr_number, "the attempt was made for another pull request"),
        (state.get(_ANCHOR) != publication.published_sha, "the generation froze another head than the anchor"),
        (recorded.stage != publication.source_stage, "the attempt was made from another stage"),
    )
    return next((reason for refused, reason in refusals if refused), "")


def _unadjudicable(generation: LateGeneration, issue_number: int) -> str:
    """Why `generation` is no live adjudication of this issue a replay could be owned by, or "".

    Held first to what late adjudication itself refuses a record for
    (`stages/decomposition/late_evidence.py`): the late domain's own gate --
    every identity a record is correlated by and every field in its shape --
    both frozen commits, and the issue it names being this one. A replay
    handed to a record adjudication refuses would leave the attempt retired
    and nobody to publish it. Then it has to be live and measured past its
    ceiling: cancelled, restarting, unmeasured, under the ceiling, or already
    cut into children, it is no owner a replay could be published by.
    """
    try:
        _late_validation.check_generation(generation)
    except _formats.InvalidLateValue as refused:
        return f"the late generation is not a record adjudication accepts ({refused})"
    if not (generation.candidate_sha and generation.base_sha):
        return "the late generation froze no candidate and measurement base"
    if generation.current_issue != issue_number:
        return f"the late generation was recorded against issue #{generation.current_issue}"
    ended = generation.cancelled or generation.restart_pending or generation.split_has_settled
    if ended or not generation.is_oversized:
        return "the late generation is not a live measured adjudication"
    return ""
