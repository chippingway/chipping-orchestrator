# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reconcile and apply late-candidate pull-request holds with durable original bodies.

The issue preserves the pull-request identity, head, and description before
editing it. Unknown holds and displaced descriptions are never overwritten;
a moved head is reported while the recorded hold remains anchored.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_hold_reading as _late_hold_reading,
    late_hold_release as _late_hold_release,
    late_hold_text as _late_hold_text,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _HeldPr,
    _HeldPrHold,
)

log = logging.getLogger("orchestrator.workflow")


def _reconcile_hold(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    generation: LateGeneration,
) -> _HeldPrHold:
    """Bring this generation's hold on any reusable pull request up to date.

    Answers three ways. Nothing to hold -- no pull request this generation can
    name, one it may not mark, or one that is no longer open -- leaves the
    generation exactly as it arrived and lets the caller spawn. A reconciled
    hold reports `held`. A pull request that could not be read, whose
    provenance could not be established, that already wears a hold nothing
    preserved a body for, or that refused the edit reports `failed`, and the
    caller parks without spawning.

    The pull request is fetched ONCE and everything is decided about that one
    snapshot -- what it may be, its state, the head it stands on, and the body
    preserved from it -- because a head is a mutable thing. Past the
    discussion handoff a plan is told from an implementation by the commit its
    head is on, so a tick that classified one read and then edited another
    could preserve and overwrite a description a human pushed in between.

    A hold left on a pull request this record has since moved off is settled
    BEFORE any of that, because the notice has to end up where the candidate
    is: a generation re-measured past its own push is adjudicating the change
    on the published pull request, and a "do not merge" standing on the plan
    one instead marks nothing while leaving the change a human could merge
    unmarked. The old hold is released first and the new one taken after --
    never both at once, since the record holds one identity and one preserved
    body, and taking the second before restoring the first would destroy the
    only copy of a description there is.
    """
    settled = _late_hold_release._settled_stale_hold(gh, issue, generation)
    if settled is None:
        return _late_hold_reading._refused(generation)
    return _reconciled_target(gh, issue, state, settled)


def _reconciled_target(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    generation: LateGeneration,
) -> _HeldPrHold:
    """Reconcile the hold on whichever pull request this record now names.

    Reached with the hold's slot free of anything stale, so the pull request
    chosen here is the one the record means and there is no second one to
    settle first.
    """
    pr_number = _late_hold_reading._hold_subject(state, generation)
    if pr_number is None:
        return _HeldPrHold(generation=generation)
    held_pr = _late_hold_reading._readable_held_pr(gh, issue, pr_number)
    if held_pr is None:
        return _late_hold_reading._refused(generation)
    if not _late_hold_reading._may_be_held(gh, issue, state, generation, held_pr):
        return _HeldPrHold(generation=generation)
    if held_pr.pr_state != _late_hold_release._OPEN_PR_STATE:
        log.info(
            "issue=#%d PR #%d is not open; leaving the frozen candidate and "
            "any recorded hold exactly as they are",
            issue.number, pr_number,
        )
        return _HeldPrHold(generation=generation)
    return _reconciled_hold(gh, issue, state, generation, held_pr)


def _reconciled_hold(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    generation: LateGeneration,
    held_pr: _HeldPr,
) -> _HeldPrHold:
    """Decide what an open pull request needs: a retry, refusal, or hold.

    The middle one is the crash window the persist-first order leaves no room
    for: a body already carrying a hold that this issue preserved no original
    for was held by something else -- an older cycle, another binary -- and
    capturing it would record the hold text as somebody's description,
    destroying the only copy of it. A human settles that; this refuses it.
    """
    if (
        generation.plan_pr_number == held_pr.number
        and generation.plan_pr_body is not None
    ):
        _report_moved_head(issue, generation, held_pr)
        return _applied_hold(gh, issue, generation, held_pr)
    if _late_hold_text._HOLD_PREFIX in held_pr.body:
        log.error(
            "issue=#%d PR #%d already carries a late hold this issue "
            "preserved no body for; refusing to overwrite it",
            issue.number, held_pr.number,
        )
        return _late_hold_reading._refused(generation)
    return _taken_hold(gh, issue, state, generation, held_pr)


def _report_moved_head(
    issue: Issue, generation: LateGeneration, held_pr: _HeldPr,
) -> None:
    """Say when the change under this hold is not the one it was taken on.

    Said and nothing more. What the notice is for is stopping a human from
    merging while an adjudication is open, and that is as true of a branch
    somebody has pushed to as of the one the hold was written over -- so the
    hold stands, the retry re-applies the same body it would have anyway, and
    the recorded head is left as the reading it was rather than being restamped
    to whatever the pull request has become. What movement costs is settled
    where the evidence is: the gate refuses to re-enter a publication over it,
    and the settlement refuses to publish or supersede against one that moved.

    Nothing is said for a hold recorded without a head. That can only be a
    record an older binary wrote -- a head this one cannot name refuses the
    capture rather than being recorded absent -- and the pull request under
    such a record has moved or not moved against a reading nobody took.
    """
    if not generation.plan_pr_head:
        return
    if generation.plan_pr_head == held_pr.head_sha:
        return
    log.info(
        "issue=#%d PR #%d has moved from %s to %s under this cycle's hold; "
        "the hold stands and the recorded reading is kept",
        issue.number, held_pr.number, generation.plan_pr_head,
        held_pr.head_sha or "an unreadable head",
    )


def _taken_hold(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    generation: LateGeneration,
    held_pr: _HeldPr,
) -> _HeldPrHold:
    """Record the identity, the head, and the body, then apply the hold.

    All three go down in one write, and the head goes with them because it is
    the only thing that says which change wore the notice: the same pull
    request stands on a different commit the moment somebody pushes, and a
    later tick reading only the identity could not tell the two apart. What is
    NOT written is the published head one field over -- the gate froze that
    one and a settlement pushes against it, so a hold that re-stamped it from
    its own reading would move the evidence under the verdict.

    A head this reading could not name refuses the hold before anything is
    touched, rather than being recorded as absent. The write drops an empty
    one, so the record it would leave is an identity and a body with no head
    between them -- a notice on a change no later tick could show it was
    written over -- and the description would already have been replaced by
    the time anything noticed. Two of three is not this record.

    A write that does not land is a hold that may not be taken. The preserved
    body is the only copy of the description the edit is about to replace, so
    editing on the strength of a record nobody kept would destroy it. Nothing
    is edited and the caller parks.

    Whether it CAN land is asked before anything is written, and asked about
    the whole of what follows rather than about this write alone. A body that
    fits the comment exactly is the worst case, not the safe one: the write
    that STARTS the run comes next and has no safe failure of its own, since
    parking is another write of the same oversized comment. So the run record
    that write would make -- built from the spec this issue is locked to,
    which is an operator's command line and bounded by nothing here -- is
    measured beside the preserved body, and a description too long to hold
    with it is refused while nothing has been touched and a park is still
    small enough to land.
    """
    if not held_pr.head_sha:
        log.error(
            "issue=#%d PR #%d names no head this reading could use; "
            "refusing to hold a description it could record no head for",
            issue.number, held_pr.number,
        )
        return _late_hold_reading._refused(generation)
    holding = replace(
        generation,
        plan_pr_number=held_pr.number,
        plan_pr_head=held_pr.head_sha,
        plan_pr_body=held_pr.body,
    )
    prospective = PinnedState(data=dict(state.data))
    _late_state.write_late_generation(prospective, holding)
    if not _late_session._holdable(prospective.data, holding):
        log.error(
            "issue=#%d cannot preserve the body of PR #%d and still "
            "record the run; refusing to hold it",
            issue.number, held_pr.number,
        )
        return _late_hold_reading._refused(generation)
    _late_state.write_late_generation(state, holding)
    try:
        gh.write_pinned_state(issue, state)
    except Exception:
        log.exception(
            "issue=#%d could not preserve the body of PR #%d; refusing "
            "to hold it", issue.number, held_pr.number,
        )
        return _late_hold_reading._refused(generation)
    return _applied_hold(gh, issue, holding, held_pr)


def _applied_hold(
    gh: GitHubClient,
    issue: Issue,
    generation: LateGeneration,
    held_pr: _HeldPr,
) -> _HeldPrHold:
    """Write the hold over a body this issue wrote or preserved, and no other.

    The one place the retry is made idempotent, and the one place a crash is
    told apart from a human. Three bodies can be on the pull request when this
    runs, and each answers differently:

    * this cycle's hold, VERBATIM -- the edit already landed, so the retry
      does nothing rather than editing a second time. Verbatim and not "wears
      the marker", because a sentence somebody changed inside the notice is
      their edit, and calling it held is what would have the release put the
      preserved copy back over their words;
    * the description recorded beside the identity -- exactly what a crash
      between the persist and the edit leaves behind, and the first
      application besides;
    * the same hold in the spelling an earlier binary used, which is the
      upgrade case: the notice is ours and stands, so it is rewritten in the
      current spelling by the very edit that would have applied a fresh one;
    * anything else -- a human writing over the notice. That body is theirs,
      the preserved copy is no longer a description of it, and the release
      beside this one already refuses to overwrite it.

    A generation that advanced needs no case of its own: the hold is keyed to
    the cycle and quotes nothing that moves inside one, so a re-measured
    candidate leaves its pull request wearing the same body this reconstructs.
    """
    if held_pr.body == _late_hold_text._hold_body(generation):
        return _HeldPrHold(generation=generation, held=True)
    if not _late_hold_text._wears_our_hold(generation, held_pr.body) and (
        held_pr.body != generation.plan_pr_body
    ):
        log.warning(
            "issue=#%d PR #%d carries a description this issue did not "
            "displace; leaving it alone and reporting the hold displaced",
            issue.number, held_pr.number,
        )
        return _HeldPrHold(
            generation=generation,
            displaced=held_pr.pr_state == _late_hold_release._OPEN_PR_STATE,
        )
    try:
        gh.edit_pr_body(held_pr.pull_request, _late_hold_text._hold_body(generation))
    except Exception:
        log.exception(
            "issue=#%d could not hold PR #%d",
            issue.number, held_pr.number,
        )
        return _late_hold_reading._refused(generation)
    return _HeldPrHold(generation=generation, held=True)
