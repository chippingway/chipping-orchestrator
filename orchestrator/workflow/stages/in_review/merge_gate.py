# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The last answer a tick can reach: whether to tell a human the PR is ready.

The orchestrator never merges from here and never routes a conflict from here.
An unmergeable PR -- branch protection, a real conflict, a base that moved --
parks awaiting a human, because every automatic answer to it would be a guess
about what the human wants merged.

A mergeable PR earns one ping per head SHA, and each of the gates in front of
that ping protects the same claim. The ping says "ready for review/merge", so
it may only fire for a head this orchestrator reviewed and documented (the
final-docs marker) or that GitHub itself carries an APPROVED review for, and
never over a standing CHANGES_REQUESTED veto. `ready_ping_sha` keys the
de-duplication on the head that was pinged, so a new commit re-pings once
evidence answers for it, and a repeated tick on the same head stays silent.

The last gate is the readiness proof, taken at the ping itself, and either
route to the ping has to pass it: a docs marker and a GitHub approval each say
who vouched for the head, and neither says the head was verified. So the
issue's current verification evidence is proved whole again through the proof
every reader about to rely on it takes
(`verification_proof.current_evidence_verdict`): still the latest revision,
its handoff describing it, its artifact re-read on the pull request and still
the one that settled, the pull request open in the configured repository on
its branch and standing on the head the evidence answers for, the branch
fetched and level with that head, the tested commit and that head both
reading as the tested tree, the configured verification context, the
applicable review subject, the settled developer report re-read at its
location, and the issue's requirements read afresh. The head the evidence
answers for has to be the head the ping names. Current is not passing, so the
artifact is then held to what an approval rests on: every command it carries
exiting 0, at least one of them, with every configured `VERIFY_COMMANDS`
command among them (`approved_evidence._artifact_refusal`) -- an artifact
recording that nothing ran is never passing, whatever the configuration. And
behind every one of those requests, the subject the approval covered is read
last (`review_coverage._approval_holds`), and behind that the pull request
once more, its state and its head together, by the terminals' own reading --
a merge or close leaves the head where it was, so the head alone would not see
one. The requests the gate makes before the ping are time in which a human can
edit the report, the issue, or the evidence's artifact, push to the branch, or
merge or close the pull request; any of those that the proof finds pings
nobody.

A refusal the proof demonstrates withholds the ping and writes nothing: the
next tick's hand-back, drift check, or the ping over a new head answers what
moved, and a refusal none of those answers leaves the issue in review without
a ping until something does. A reading nobody could take -- a request that
failed, or one that raised -- holds the ping the same way, and so does a pull
request found merged or closed, which the next tick's terminals answer; none
of them is ever read as readiness. The ping's own writes are held to the
records the proof was read over, the pointer among them, as guarded commits
over a fresh reading, and its publication is `ready_ping`'s: armed before it
is posted, found again on the thread rather than posted twice, and recorded
behind the post -- and a ping armed and never found on the thread is a new
post, which takes the whole proof again before it goes out. Those writes guard
the pinned comment and nothing else, and are requests of their own, so the
proof is taken once more behind them -- behind the arming and the
settlement's preparation, the last thing asked before the post -- and a push,
an edit, or an artifact deleted while they were written still pings nobody.
The park the gate takes is held to the report records and the pointer too,
since it writes the state in hand.

Both writes this stage makes to a thread are bounded by the same fact: the
feedback scan that decided this tick ran several GitHub round-trips ago, and a
human may have written since. So the unmergeable park is a BOUNDED one -- it
records the thread read only as far as the ledger can vouch for, never at the
id of the notice it just posted, which would sit above their reply and take it
with it. And the ping, which is no park at all, ratchets nothing: it is
filtered by the id ledger and its hidden marker on the next read, so no mark
has to move for it, and a mark that did move would be moving over exactly that
unread reply.
"""
from __future__ import annotations

import logging
from functools import partial
from typing import Any

from orchestrator import config
from orchestrator.workflow.engine import (
    guards as _guards,
    report_evidence_models as _evidence_models,
    terminal_reading as _terminal_reading,
    verification_proof as _proof,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.in_review import (
    models as _models,
    ready_ping as _ready_ping,
    watermarks as _watermarks,
)
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
)

log = logging.getLogger("orchestrator.workflow")

_UNREAD_PROOF = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD,
    "a reading the readiness proof rests on raised rather than answering",
)

_ANOTHER_HEAD = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.DEFER,
    "the current evidence answers for another head than the one the ping would name",
)

_UNREAD_ARTIFACT = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD,
    "the current evidence's artifact could not be re-read for what it passed",
)

# What the subject the approval covered, read last behind every request of the
# proof, answers where it could not be read, and where it no longer holds.
_UNREAD_LAST = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.HOLD,
    "the evidence, report, issue, or pull request read last before the ping could not be read",
)

_MOVED_LAST = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.DEFER,
    "the approval no longer holds over the evidence, report, requirements, or head read last before the ping",
)

# What the pull request read last answers where it is still open, and where it
# has merged or closed since the proof read it.
_OPEN = "open"

_ENDED_LAST = _evidence_models.ReportEvidence(
    _evidence_models.ReportEvidenceVerdict.ENDED,
    "the pull request read last before the ping has merged or closed",
)

# The docs verdicts a final-docs pass stamps on the head it checked.
_DOCS_VERDICTS = frozenset(("updated", "no_change"))


def _head_is_approved(ctx: _models._InReviewContext, head_sha: str) -> bool:
    """True when `head_sha` earned the reviewer-approved final-docs handoff or
    carries a real GitHub APPROVED review.

    The final-docs pass records the exact head it checked after reviewer
    approval; if a later push changes the PR head, the docs marker no longer
    matches and the issue must bounce back through validating/documenting before
    it can ping again. A real GitHub APPROVED review on the current head is the
    fallback for manually-driven review flows -- probed only when the final-docs
    marker did not already qualify the head, to avoid a redundant API call.
    Either only qualifies the head: the ping still waits on the readiness
    proof (`_still_ready`), which neither route stands in for.
    """
    documented = bool(head_sha) and ctx.state.get("docs_checked_sha") == head_sha
    if documented and ctx.state.get("docs_verdict") in _DOCS_VERDICTS:
        return True
    return ctx.gh.pr_is_approved(ctx.pr, head_sha=head_sha)


def _handle_mergeable_gate(ctx: _models._InReviewContext) -> None:
    """Manual-merge-only mergeability gate. An unmergeable PR parks awaiting
    human regardless of approval state -- the orchestrator never routes from
    here to `resolving_conflict` and never calls `gh.merge_pr`. A mergeable PR
    earns a one-shot HITL ping per head SHA when either the agent-approved
    final-docs handoff covers that head OR GitHub carries a real APPROVED
    review on that head, no standing CHANGES_REQUESTED veto exists, and the
    issue's current verification evidence proves current and passing for that
    head at the ping itself (`_still_ready`).
    """
    pr = ctx.pr
    pr_number = ctx.pr_number
    mergeable = ctx.gh.pr_is_mergeable(pr)
    if mergeable is None:
        return  # GitHub still computing; try next tick
    if not mergeable:
        # The mergeability request is time another road can settle a later
        # report in, or point the issue at another pull request, and the park
        # below writes the state in hand whole: over a comment that moved, it
        # would put the replaced report or pointer back.
        if not _review_comment._records_in_hand(
            ctx.gh, ctx.issue, ctx.state, "park its pull request as unmergeable",
        ):
            return
        # Bounded, because this refusal is not decided between two adjacent
        # steps: the feedback scan that let the tick get here ran several
        # GitHub round-trips ago, and a reply written since is numbered below
        # the notice this park posts. Stamped at that notice id, the reply
        # would be under BOTH cursors the next scan reads -- the delivery
        # cursor this park set and the issue-side watermark carried over it --
        # and no later poll could go back for it.
        _guards._park_awaiting_human(
            ctx.gh, ctx.issue, ctx.state,
            f"{config.HITL_MENTIONS} PR #{pr_number} is not mergeable "
            "(branch protection, conflicts, or out-of-date base); "
            "manual merge needed.",
            reason="unmergeable",
            bounded=True,
        )
        ctx.state.set("park_reason", "unmergeable")
        _watermarks._bump_in_review_watermarks(ctx)
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    # mergeable: humans drive the merge. The ping advertises the PR as "ready
    # for review/merge", so it must only fire for a head the orchestrator has
    # reviewer-approved and documented (or one a human/bot formally approved in
    # GitHub), carrying no standing human veto, AND over current passing
    # verification evidence for it; otherwise we would invite a manual merge
    # over a stale, rejected, or unverified commit.
    head_sha = pr.head.sha
    if ctx.gh.pr_has_changes_requested(pr, head_sha=head_sha):
        return
    if not _head_is_approved(ctx, head_sha):
        return
    # Ping HITL handles once per head SHA so the human knows the PR is ready.
    # De-duplication is keyed on `ready_ping_sha` (the head we pinged for); a
    # new commit pushed onto the branch shifts pr.head.sha and re-pings once
    # evidence answers for it, while repeated ticks on the same head stay
    # silent and prove nothing. Deliberately do NOT set `awaiting_human` -- the
    # handler must still react to PR comments / external merge / a later
    # unmergeable transition.
    #
    # Deliberately NOT calling `_bump_in_review_watermarks` here. The ping is
    # not a park: it leaves `awaiting_human` false and owes the thread no
    # "everything below here is read" claim. It IS an issue comment, and its
    # settlement records it in `orchestrator_comment_ids`, so the next tick's
    # id-set filter drops it without any watermark having to move -- as the
    # hidden marker does for one whose record never landed. Moving one would
    # only risk crossing a human comment that landed between the earlier
    # feedback scan and this point -- the next tick's `comments_after` would
    # skip it and the dev would never see the feedback.
    if ctx.state.get("ready_ping_sha") != head_sha:
        _pings_ready(ctx, head_sha)


def _pings_ready(ctx: _models._InReviewContext, head_sha: str) -> None:
    """Ping a human that `head_sha` is ready, while the readiness proof still covers it.

    A ping an earlier tick armed over the head is looked for on the thread
    first, and settled where it landed (`ready_ping.recovers`): that is a
    record of what was already said, and posts nothing. Anything else is a
    new post -- a first attempt, or an armed one the thread reads without --
    and takes the whole readiness proof first (`_still_ready`): refused,
    unread, or ended, nobody is pinged and nothing is written, and the next
    tick's hand-back, drift check, terminals, or ping over the new head
    answers it. Passed, the proof is handed to the publication, which takes
    it once more behind its arming and its settlement's preparation,
    immediately ahead of the post: those checkpoints guard the pinned comment
    alone, and a push or an artifact deleted while they are written is
    nothing they would see.
    """
    if _ready_ping.recovers(ctx, head_sha) or not _still_ready(ctx, head_sha):
        return
    _ready_ping.publishes(ctx, head_sha, partial(_still_ready, ctx, head_sha))


def _still_ready(ctx: _models._InReviewContext, head_sha: str) -> bool:
    """Whether everything the ping claims still stands, proved at the ping itself.

    The hand-back ahead of the feedback scan asked the approval too, but it
    read the pinned records and the report alone, and the mergeability and
    review requests since then are round-trips in which a human can edit or
    delete the report, the issue, or the evidence's artifact, or push the
    pull request off the head those requests approved -- and the ping is the
    one claim here that what stands was reviewed and verified. So the whole
    readiness proof is taken (`_proves_ready`). The pinned comment is held to
    the report, evidence, approval, and pull-request records in hand by the
    ping's own guarded writes, each over a fresh reading
    (`ready_ping._DECIDED_ON`): a record that reads otherwise was moved by no
    write of this tick's, and refuses the write.

    Only PROVED pings. A refusal the proof demonstrates and a reading nobody
    could take both withhold the ping and write nothing, and are logged
    apart: the first is the work moved past what was verified, the second --
    a pull request found merged or closed among them, which the next tick's
    terminals answer -- proves nothing either way and is asked again by the
    next tick. A git that could not be started, or a request that failed
    outright, is a reading nobody could take too; every reading the proof
    takes only reads, so nothing of it is left half-written.
    """
    try:
        readiness = _proves_ready(ctx, head_sha)
    except Exception:
        log.exception("issue=#%d a reading behind its ready ping raised", ctx.issue.number)
        readiness = _UNREAD_PROOF
    if readiness.proved:
        return True
    unread = readiness.holds or readiness.ended
    log.info(
        "issue=#%d %s its ready ping over %.8s: %s",
        ctx.issue.number, "holds" if unread else "withholds", head_sha, readiness.refusal,
    )
    return False


def _proves_ready(ctx: _models._InReviewContext, head_sha: str) -> _evidence_models.ReportEvidence:
    """Prove the current evidence current and passing for `head_sha`, and the approval holding last; PROVED or why not.

    The issue is read afresh for its requirements, since the one in hand was
    fetched before the feedback scan. An issue recording no current evidence
    is refused by the proof itself, whichever route qualified the head, and
    so is evidence answering for another head than the one the ping names.
    """
    issue = ctx.gh.get_issue(ctx.issue.number)
    reading = _proof.ProofReading(ctx.gh, ctx.spec, issue, ctx.state)
    proof = _proof.current_evidence_verdict(reading)
    if not proof.proved:
        return proof
    current = _settlement.read_current_evidence(ctx.state)
    if current.binding.target.target_head != head_sha:
        return _ANOTHER_HEAD
    refused = _passes(ctx, proof.pull_request, current)
    return refused or _holds_last(ctx, head_sha) or proof


def _passes(
    ctx: _models._InReviewContext, pull_request: Any, current: _records.CurrentEvidence,
) -> _evidence_models.ReportEvidence | None:
    """Refuse or hold evidence proved current that an approval may not rest on, or None.

    The proof holds the record's pass flag to the artifact's commands, but
    current is not passing: the artifact, re-read on `pull_request` -- the
    one the proof read -- has to carry every command exiting 0, at least one
    of them, with every configured `VERIFY_COMMANDS` command among them
    (`approved_evidence._artifact_refusal`).
    """
    refused = _approved_evidence._artifact_refusal(ctx.gh, pull_request, current)
    if refused is None:
        return _UNREAD_ARTIFACT
    if refused:
        return _evidence_models.ReportEvidence(_evidence_models.ReportEvidenceVerdict.DEFER, refused)
    return None


def _holds_last(ctx: _models._InReviewContext, head_sha: str) -> _evidence_models.ReportEvidence | None:
    """Refuse or hold the ping on the final reading behind the proof's requests, or None.

    The check every road about to move an approval on asks last
    (`review_coverage._approval_holds`): the evidence claim the approval
    records, the report it covers, the requirements over the issue read
    afresh, and the pull request read afresh standing on `head_sha`. That
    pull-request reading asks after its head alone, and a merge or close
    keeps the head where it was, so the pull request is read once more
    behind it, by the terminals' own reading
    (`terminal_reading._linked_pull_request`), the last request of the
    proof: one found merged or closed holds for the terminal the next tick
    answers, one nobody could read holds too, and one standing anywhere but
    `head_sha` -- a push behind the reading before it -- refuses.
    """
    holds = _review_coverage._approval_holds(ctx.gh, ctx.issue, ctx.state, head_sha)
    if holds is None:
        return _UNREAD_LAST
    if not holds:
        return _MOVED_LAST
    linked = _terminal_reading._linked_pull_request(
        ctx.gh, ctx.issue, ctx.state, "reading the pull request last before a ready ping",
    )
    if not linked.was_read:
        return _UNREAD_LAST
    if linked.state != _OPEN:
        return _ENDED_LAST
    return None if linked.head == head_sha else _MOVED_LAST
