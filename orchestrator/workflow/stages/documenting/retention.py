# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the verification evidence an approval rests on outlives a docs pass that changed nothing.

A clean `DOCS: NO_CHANGE` -- no commit, nothing recovered ahead of the remote --
leaves the pull request on the head the approval moved here, so the evidence
that approval rests on may go on answering for it. May, not does: the pass is
an agent run, long enough for a push, a configuration change, an issue edit, a
report edited at its location, or the artifact deleted or edited on the pull
request, and the opening's reading (`handoff._hands_back_what_validating_owes`)
saw none of it. So before the completion is handed the verdict, the current
evidence is proved whole again, through the proof every reader about to rely
on it takes (`verification_proof.current_evidence_verdict`): still the latest
revision, its handoff describing it, its artifact re-read on the pull request
and still the one that settled, the pull request open on its branch and
standing on the head the evidence answers for, the branch fetched and level
with that head, the tested commit and that head both reading as the tested
tree, the configured verification context, the applicable review subject --
for evidence an equivalent-tree approval squash carried, the approved review
of the commit that was tested -- the settled developer report as re-read at
its location, and the issue's requirements, read afresh. Current is not
passing, so the evidence is then held to what an approval may rest on: every
command its artifact carries exiting 0, the configured `VERIFY_COMMANDS` among
them (`_proved`). Each of those readings is a request long enough for the issue
to be edited or the pull request pushed to behind the one that proved it, so
the last word is the check every road about to move an approval on takes
(`review_coverage._approval_holds`): the requirements over the issue read
afresh, and the pull request read afresh standing on the head, behind every
other request -- and behind that the terminals' own reading of the pull request
(`terminal_reading._linked_pull_request`), since a merge or close leaves its
head where it was: found over, it holds, and standing on another head -- a push
behind the check before it -- it refuses. The completion's watermark walk is a
request of the pull request too, so it is taken ahead of all of this
(`handoff._in_review_watermark`), and that last reading is the last request
anything the pass writes is decided behind; a thread that walk could not read,
or any reading of the proof that raises rather than answering, holds the pass
like any reading nobody could take. The pass committed nothing, so the
checkout that proof finds level with the evidence's head is the one the pass
was handed and found needing no docs.

Proved, nothing is written to the evidence: the record, its tested commit, its
artifact, and the report's source stay exactly as the approval and its squash
left them, the completion names it as the evidence the unchanged head rests on
(`final_completion._completes_unchanged`), and it lands decided as well on
every record that proof read (`UNCHANGED`), so a hand edit of any of them under
the tick refuses it.

A proof that refuses is the evidence proved to no longer answer for the pull
request. The unchanged-doc handoff is withheld -- no verdict, no notice, no
`in_review` -- and the evidence is invalidated by `validating`'s own
retirement (`squash_evidence._invalidates`): the current record goes into
history as invalidated, the approval it answers for is written null, which no
reader takes for an approval, and the issue goes back to `validating` for a
fresh reviewer, behind a write that landed (`_INVALIDATION`). A write refused
or never confirmed stops there with nothing relabelled, and the next tick's
opening hands back the approval that no longer stands, or asks again. Evidence
that is missing, or a record that will not read, is no evidence either, and
never counts as passing: the proof refuses it, and it takes the same road --
a record that will not read cleared, nothing to index.

A reading nobody could take proves nothing either way -- the pull request, its
thread, the branch, the report's location, the issue, the lookup of a commit
id, or the tree of a commit the repository holds -- and neither does a pull
request found over, by the proof or by that last reading, which the next
tick's terminals answer. Nothing is
announced, stamped, retired, or relabelled; what the tick staged -- the run's
usage and session, the launch record a finished pass drops -- lands alone
(`_HELD`), and the next tick runs the pass again, as it does behind any clean
no-change whose completion did not land.

A NO_CHANGE over recovered commits never reaches here: it is a publication,
which moves the head.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.engine import (
    comments as _comments,
    report_commits as _commits,
    report_evidence_models as _evidence_models,
    terminal_reading as _terminal_reading,
    verification_durable as _durable,
    verification_proof as _proof,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.documenting import handoff as _handoff, models as _models
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    review_coverage as _review_coverage,
    squash_evidence as _squash_evidence,
    state as _validating_state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The requirements baseline the settled report is held to beside the subject.
_BASELINE = "user_content_hash"

# Every record the proof reads off the pinned comment: those the evidence is
# bound through, the report debt among them (`verification_durable`), the
# approval's claim on that evidence, the requirements baseline, the round a
# reply bought and how far into the thread it reached, which stand in for that
# baseline as the requirements the report is held to
# (`review_report._outran_the_drift_check`), and the ledger of this
# orchestrator's own comments, which the requirements are read without.
_READ = (
    *_durable._BOUND_RECORDS,
    _approved_evidence.APPROVED_EVIDENCE,
    _BASELINE,
    _validating_state._REVIEWER_OWES_A_ROUND,
    _validating_state._ROUND_BOUGHT_THROUGH,
    _comments._ORCH_COMMENT_IDS,
)

# The completion of a pass that changed nothing over evidence proved to still
# answer for its head: the final-docs completion, decided as well on every
# record that proof read.
UNCHANGED = _handoff._COMPLETION.deciding_on(*_READ)

# What a proof that refused lands beside what the tick staged: the evidence
# invalidated, the approval it answers for retired, and a squash handoff over
# it dropped -- decided on what the completion would have been.
_INVALIDATION = _commits.ReportWrite(
    owned=frozenset(_squash_evidence.INVALIDATES), decided_on=UNCHANGED.decided_on,
)

# What a proof nobody could take lands: nothing of its own, only what the tick staged.
_HELD = _commits.ReportWrite(owned=frozenset(), decided_on=UNCHANGED.decided_on)

# Why a pass is held over the completion's watermark walk that did not answer.
_UNWALKED = "the pull request's threads could not be read for the completion's watermark"

_UNREAD_PROOF = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD,
    "a reading the evidence proof rests on raised rather than answering",
)

_UNREAD_ISSUE = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD,
    "the issue could not be read again for its requirements",
)

_UNREAD_ARTIFACT = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD,
    "the current evidence's artifact could not be re-read for what it passed",
)

# What the final reading behind every request of the proof answers where it
# could not be taken, and where the approval no longer holds over it.
_UNREAD_LAST = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD,
    "the evidence, report, issue, or pull request read last before the completion could not be read",
)

_MOVED_LAST = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.DEFER,
    "the approval no longer holds over the evidence, report, requirements, or head read last before the completion",
)

# What the pull request read last answers where it is still open, and where it
# has merged or closed since the proof read it.
_OPEN = "open"

_ENDED_LAST = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.ENDED,
    "the pull request read last before the completion has merged or closed",
)


def _retains(ctx: _models._DocumentingContext, checked: str) -> bool:
    """Whether the unchanged pass over `checked` may complete; False where this tick is already handled.

    The completion's watermark walk is taken first
    (`handoff._in_review_watermark`): it requests the pull request and its
    threads, and a push behind a request the proof came before is one the
    proof never saw. A thread it could not read holds like any reading nobody
    could take, and what it reached is staged only behind a proof.

    True only over evidence proved to still answer for `checked`. Otherwise
    the completion is withheld: a walk or proof nobody could take, or a pull
    request found over, lands what the tick staged and nothing else, and a
    refusal -- evidence missing or unreadable among them -- invalidates what
    is there and hands the issue back to `validating`, relabelling only behind
    a write that landed.
    """
    try:
        walked = _handoff._in_review_watermark(ctx.gh, ctx.issue, ctx.state)
    except Exception:
        log.exception(
            "issue=#%d could not walk the pull request's threads behind its unchanged docs pass", ctx.issue.number,
        )
        _holds(ctx, checked, _UNWALKED)
        return False
    proof = _proved(ctx, checked)
    if proof.proved:
        if walked is not None:
            ctx.state.set(_handoff._PR_LAST_COMMENT_ID, walked)
        return True
    if proof.holds or proof.ended:
        _holds(ctx, checked, proof.refusal)
        return False
    commit = _commits.ReportCommit(ctx.gh, ctx.issue, ctx.state)
    retired = _squash_evidence._invalidates(ctx.state)
    log.warning(
        "issue=#%d its verification evidence no longer answers for %s: %s; %s, retiring the approval it answers "
        "for, and handing the issue back to `%s` in place of the unchanged-doc handoff",
        ctx.issue.number, checked, proof.refusal,
        "invalidating it" if retired else "no record to invalidate or no room to", WorkflowLabel.VALIDATING,
    )
    if not _handoff._stops(ctx, commit.lands(ctx.state, _INVALIDATION), "relabelling"):
        ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    return False


def _holds(ctx: _models._DocumentingContext, checked: str, refusal: str) -> None:
    """Hold the unchanged pass over `checked` for `refusal`: what the tick staged lands alone, through a checkpoint.

    The run's usage and session, and the launch record a finished pass
    drops, land as a write over the reading the tick last confirmed, so the
    next tick runs the pass again rather than taking the park a launch whose
    outcome nothing recorded earns. Nothing is announced, stamped, retired,
    or relabelled.
    """
    log.info(
        "issue=#%d holds its unchanged docs pass over %s: %s; announcing, retiring, and relabelling nothing",
        ctx.issue.number, checked, refusal,
    )
    commit = _commits.ReportCommit(ctx.gh, ctx.issue, ctx.state)
    _handoff._stops(ctx, commit.lands(ctx.state, _HELD), "relabelling")


def _proved(ctx: _models._DocumentingContext, checked: str) -> _evidence_models.ReportEvidence:
    """The whole proof (`_whole_proof`), or a hold where one of its readings raised rather than answered.

    A git that could not be started, or a request that failed outright,
    proves nothing either way, like any reading nobody could take: the pass
    holds through its checkpoint rather than leaving the tick with the run it
    finished unrecorded. Every reading the proof takes only reads, so nothing
    of it is left half-written.
    """
    try:
        return _whole_proof(ctx, checked)
    except Exception:
        log.exception("issue=#%d a reading behind its unchanged docs pass raised", ctx.issue.number)
        return _UNREAD_PROOF


def _whole_proof(ctx: _models._DocumentingContext, checked: str) -> _evidence_models.ReportEvidence:
    """The whole proof of the current evidence, held to what an approval rests on and read last; a refusal, or PROVED.

    It refuses an issue that records no evidence it can read. The issue is
    read afresh for its requirements, since the one in hand was fetched before
    the pass ran. Current is not passing: the proof holds the record's pass
    flag to the artifact's commands, whichever way that flag reads, so
    evidence proved current is then held to what the approval needed of it
    (`approved_evidence._artifact_refusal`) -- its artifact, re-read on the
    pull request the proof read, still the one that settled, every command
    exiting 0, and every configured `VERIFY_COMMANDS` command among them. An
    approval with no evidence claim was never held to that by the opening,
    and a failed or uncovering run is no evidence a pass may be completed
    over. Every one of those readings is a request long enough for the issue
    to be edited or the pull request pushed to behind the reading that proved
    it, so the last word is the one every road about to move an approval on
    takes (`_holds_last`).
    """
    try:
        issue = ctx.gh.get_issue(ctx.issue.number)
    except Exception:
        log.exception("issue=#%d could not be read again behind its unchanged docs pass", ctx.issue.number)
        return _UNREAD_ISSUE
    reading = _proof.ProofReading(ctx.gh, ctx.spec, issue, ctx.state)
    proof = _proof.current_evidence_verdict(reading)
    if not proof.proved:
        return proof
    refused = _approved_evidence._artifact_refusal(
        ctx.gh, proof.pull_request, _settlement.read_current_evidence(ctx.state),
    )
    if refused is None:
        return _UNREAD_ARTIFACT
    if refused:
        return _evidence_models.ReportEvidence(_evidence_models.ReportEvidenceVerdict.DEFER, refused)
    return _holds_last(ctx, checked) or proof


def _holds_last(ctx: _models._DocumentingContext, checked: str) -> _evidence_models.ReportEvidence | None:
    """Refuse or hold the completion on the final reading behind the proof's requests, or None.

    The check every road about to move an approval on asks last
    (`review_coverage._approval_holds`): the evidence the approval rests on,
    on the records and its artifact; the report it covers; the requirements,
    over the issue read afresh; and the pull request, read afresh, standing on
    `checked`. One that has moved refuses, and one nobody could read holds.
    That pull-request reading asks after its head alone, and a merge or close
    keeps the head where it was, so the pull request is read once more behind
    it, by the terminals' own reading (`terminal_reading._linked_pull_request`),
    the last request before the completion: one found over holds for the
    terminal the next tick answers, one nobody could read holds too, and one
    standing anywhere but `checked` -- a push behind the reading before it --
    refuses.
    """
    holds = _review_coverage._approval_holds(ctx.gh, ctx.issue, ctx.state, checked)
    if holds is None:
        return _UNREAD_LAST
    if not holds:
        return _MOVED_LAST
    linked = _terminal_reading._linked_pull_request(
        ctx.gh, ctx.issue, ctx.state, "reading the pull request last behind an unchanged docs pass",
    )
    if not linked.was_read:
        return _UNREAD_LAST
    if linked.state != _OPEN:
        return _ENDED_LAST
    return None if linked.head == checked else _MOVED_LAST
