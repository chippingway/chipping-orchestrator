# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The hold and the pull request a candidate owes before it is handed on.

Two reconciliations, run in that order, and the second is the one a search by
branch and open state cannot make. The hold comes off the pull request this
generation marked, and the pull request the issue RECORDS is settled against
the measured commit, so what the handoff names is a change that commit is
actually in.

Two roads out of the gate reach this owner: the settlement a decision to
publish an oversized candidate unsplit licenses, and the handoff of a candidate
a remeasurement put back under the ceiling without any adjudication at all.
Neither may hand the issue on with a "do not merge" notice nobody will reclaim,
or with `pr_number` naming a change the candidate is not in -- the retirement a
moment later reads a record about SIZE and knows nothing about either.

The hold is RESTORED rather than rewritten: the held pull request gets back the
description this generation replaced, and what happens to it afterwards is the
ordinary publication's -- that one reuses it and rewrites its body when the
push lands on it, and leaves it alone when it does not.

Which reconciliation the pull request gets splits on the side of publication
the candidate was measured on. A candidate nothing had published is SEARCHED
for by commit, because nothing on the record names where it went. One measured
against a pull request the remote already carries is PROVED instead: the entry
the gate froze names that pull request and the head it was standing on, neither
can be re-derived, and a check that fails refuses rather than dropping what it
could not confirm.
"""
from __future__ import annotations

import logging

from orchestrator.git.worktrees import naming as _naming
from orchestrator.github import pull_requests as _pull_requests
from orchestrator.workflow.late_split import payloads as _payloads
from orchestrator.workflow.late_split.models import LateFailure
from orchestrator.workflow.stages.decomposition import (
    late_hold as _late_hold,
    late_outcome as _late_outcome,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_proof as _late_proof,
    late_publication as _late_publication,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.implementing import (
    late_parks as _gate_parks,
)

log = logging.getLogger("orchestrator.workflow")

# Whichever pull request this issue currently records, and the one state in
# which keeping it is safe. Shared with every other stage that reads it, which
# is why what it names has to be true by the time this hands the issue on.
_PR_NUMBER = "pr_number"

_OPEN_PR_STATE = "open"

_RELEASE_FAILED_PARK = (
    "this issue's committed candidate was adjudicated as one coherent change, "
    "but the hold on its pull request could not be taken off -- so nothing "
    "was handed on for publication and the pull request still reads as held. "
    "Settle the pull request, then the next tick retries the same release "
    "against the same recorded description."
)

_LOOKUP_FAILED_PARK = (
    "this issue's committed candidate was adjudicated as one coherent change, "
    "but GitHub could not be asked which pull request already carries it -- "
    "so it was not handed on for publication. Publishing on that answer could "
    "open a second pull request for a commit that is already on one. The next "
    "tick asks again, against the same frozen commit, without re-running any "
    "agent."
)

_RECORDED_PR_UNREADABLE_PARK = (
    "this issue's committed candidate was adjudicated as one coherent change, "
    "but the pull request this issue records could not be read -- so it was "
    "not handed on for publication. A merged one carried into the "
    "implementing stage ends the issue on a change the candidate is not in. "
    "The next tick asks again, against the same frozen commit, without "
    "re-running any agent."
)

_DAMAGED_RECEIPT_PARK = (
    "this issue's committed candidate was adjudicated as one coherent change, "
    "and the publication receipt group on the pinned comment does not read "
    "back whole: `{field}` is missing or is not a value this build can read. "
    "The three members are one write -- the commit that reached the remote, "
    "the head it replaced, and the pull request it went onto -- so a group "
    "missing one, or carrying a value nothing here can use, is a record no "
    "tick produced. Publishing the accepted candidate would put a fresh group "
    "down over it and destroy the only evidence of what this stage last "
    "pushed, so nothing was pushed and nothing was handed on. Repair all "
    "three members -- or remove all three, if nothing was ever published from "
    "this branch -- and the next tick asks again against the same frozen "
    "commit."
)


_FOREIGN_REPOSITORY_PARK = (
    "this issue's committed candidate was adjudicated as one coherent change, "
    "but pull request #{number} -- the one it was measured against -- has its "
    "head in `{read}` rather than in `{expected}`. A fork carries this "
    "repository's ref names over its commits, so nothing about the branch or "
    "the head tells that pull request from a publication this issue made: "
    "settling against it would push this repository's branch while handing "
    "the reviewer somebody else's change. Repair the pinned comment, then the "
    "next tick asks again against the same frozen commit."
)


_FOREIGN_BRANCH_PARK = (
    "this issue's committed candidate was adjudicated as one coherent change, "
    "but pull request #{number} -- the one it was measured against -- is open "
    "on `{read}` rather than on `{expected}`, which is the branch this issue "
    "would push. The number and the branch are separate fields on the pinned "
    "comment and these two do not describe the same publication, so nothing "
    "was handed on: publishing would grow a branch that pull request never "
    "carried while recording its number as the change the candidate is in. "
    "Repair the pinned comment, then the next tick asks again against the "
    "same frozen commit."
)


_SETTLED_PUBLICATION_PARK = (
    "this issue's committed candidate was adjudicated as one coherent change, "
    "but pull request #{number} -- the one it was measured against -- is "
    "{state} rather than open, so it was not handed on for publication. The "
    "reading that accepted it is a claim about what THAT pull request would "
    "come to, and there is nowhere for the commit to land any more: pushing "
    "would grow a branch whose pull request a human has already settled, or "
    "open a second one for a change that was adjudicated against the first. "
    "Reopen it, or close this issue, and the next tick asks again."
)


def _released_hold(context: _LateContext) -> bool:
    """Give the held pull request its description back, or park unpublished.

    Run before anything else this reconciliation does, so a release that fails
    leaves the generation exactly as it arrived: live, oversized, and carrying
    the same recorded verdict, which is what makes the retry free.
    """
    release = _late_hold._release_hold(
        context.gh, context.issue, context.generation,
    )
    context.generation = release.generation
    if not release.failed:
        return True
    _late_outcome._emit_failure(context, LateFailure.PLAN_PR_HOLD_FAILED)
    _late_parks._park(
        context, _RELEASE_FAILED_PARK, reason=_late_park_state.PARK_HOLD_FAILED,
    )
    return False


def _reconciled_pr(context: _LateContext) -> bool:
    """Point this issue at the pull request the MEASURED commit is on.

    A generation entered on the PUBLISHED side is not searched for at all:
    the record already names the pull request the work is on and the head it
    was standing on when the reading was taken, and neither can be re-derived.
    What that one owes is a proof rather than a lookup, and it is asked one
    function over.

    The exact-commit half, and the one a search by branch and open state
    cannot do. `pr_number` is whatever the issue recorded when it entered the
    gate -- most often the plan pull request a design discussion opened -- and
    what it names by the time a verdict is settled may be neither the change
    being published nor a change at all: a human can merge or close it, and a
    publication that pushed and died before recording its number leaves the
    accepted commit sitting on a pull request nothing points at.

    Handing either of those on is not cosmetic. `implementing` asks its
    recorded pull request first, and a MERGED one that is no longer the plan
    ends the issue as `done` -- with the adjudicated candidate never
    published; a commit already on a pull request nobody records is published
    a second time, since the ordinary reuse looks for an OPEN one on the
    branch and finds none.

    So the commit is what the pull request is found by, in any state. One that
    carries it is recorded, whatever state it is in, because that is the pull
    request this candidate landed on. Nothing carrying it leaves the recorded
    number alone -- the commit is simply not published yet, and an open plan
    PR is exactly what the ordinary publication reuses -- unless the recorded
    one is settled, which is the pointer that would end the issue.
    """
    if context.generation.has_publication_context:
        return _reconciled_publication(context)
    carrying = context.gh.find_pr_for_commit(
        branch=_naming._resolve_branch_name(
            context.state, context.spec, context.issue.number,
        ),
        base=context.spec.base_branch,
        head_sha=context.generation.candidate_sha,
    )
    if carrying is _pull_requests.PR_LOOKUP_UNREADABLE:
        return _late_proof._unreconciled(context, _LOOKUP_FAILED_PARK)
    if carrying is None:
        return _dropped_settled_pr(context)
    log.info(
        "issue=#%d candidate %s is already on PR #%d; recording it rather "
        "than publishing it again",
        context.issue.number, context.generation.candidate_sha,
        carrying.number,
    )
    context.state.set(_PR_NUMBER, carrying.number)
    return True


def _reconciled_publication(context: _LateContext) -> bool:
    """Prove the publication this candidate was measured against is still it.

    The pre-publication road searches for a pull request because it does not
    know of one. This road knows: the entry the gate froze names the pull
    request the work is already on and the head it was standing on, and the
    verdict a human reached is a claim about what THAT pull request would come
    to with the candidate in it. So the two are checked rather than looked up,
    and a check that fails refuses instead of dropping what it could not
    confirm.

    A settled pull request is a refusal here where the pre-publication road
    drops it, and the asymmetry is the point: there, a merged or closed number
    is a stale pointer at a change the candidate is not in, and losing it
    costs nothing because the publication opens the pull request this work
    needs. Here it IS the change -- the branch is on the remote and a human
    settled the pull request carrying it -- so dropping the number would push
    onto that branch and open a second pull request for a change adjudicated
    against the first.

    A head that moved is the same refusal one field over, and the owner that
    tells it apart from this settlement's own landed push is asked for it.

    The REF is checked beside it, because a head alone is not a publication:
    a commit is the tip of a ref in a repository. The number and the branch
    are separate fields on one pinned comment and this road pushes the branch
    it resolves for itself, and a fork carries this repository's ref names
    over its commits -- so a pull request standing at the frozen head in
    somebody else's copy, or on a ref this issue never publishes to, would
    pass every check above while the push grew a branch that pull request
    never carried and the handoff named it as the change the candidate is in.

    The number is recorded on the way out for the reason the road above
    records one: the publication asks its recorded pull request first, and the
    one this issue entered the gate with may not be the one it was measured
    against.
    """
    if not _reconciled_receipt(context):
        return False
    generation = context.generation
    number = generation.published_pr_number
    reading = _late_publication._read_publication(
        context.gh, context.issue, number,
    )
    if reading.refused:
        return _late_proof._unreconciled(context, _RECORDED_PR_UNREADABLE_PARK)
    settled = reading.state
    if settled != _late_publication.OPEN:
        log.error(
            "issue=#%d was adjudicated against PR #%d, which is %s; refusing "
            "to publish the accepted candidate onto a settled publication",
            context.issue.number, number, settled,
        )
        return _late_proof._unreconciled(
            context,
            _SETTLED_PUBLICATION_PARK.format(number=number, state=settled),
        )
    # Short-circuited, so a ref that already refused parks once: the head
    # comparison is only about a publication this push would actually touch.
    standing = (
        _reconciled_ref(context, reading, number)
        and _late_proof._reconciled_head(context, reading.head, number)
    )
    if not standing:
        return False
    context.state.set(_PR_NUMBER, number)
    return True


def _reconciled_receipt(context: _LateContext) -> bool:
    """Prove the record this settlement's own push will write over is sound.

    Asked before the remote is read, because it costs nothing and because what
    it protects is the write rather than the reading: this road reaches the
    transport directly, and the receipt its push leaves puts a fresh group
    down over whatever was there. A group this build cannot read whole is the
    one record that write destroys rather than corrects -- so it is refused
    here, where the size gate's own door refuses it for every road that goes
    through the gate.

    The park leaves everything: the verdict, the exemption, the approval and
    the damaged group all stand for the retry once a human has repaired the
    record.
    """
    damaged = _gate_parks._damaged_receipt(context.state)
    if not damaged:
        return True
    log.error(
        "issue=#%d carries a publication receipt group this build cannot "
        "read whole (`%s`); refusing to publish the accepted candidate over "
        "a record that claims a publication it cannot name",
        context.issue.number, damaged,
    )
    return _late_proof._unreconciled(
        context, _DAMAGED_RECEIPT_PARK.format(field=damaged),
    )


def _reconciled_ref(
    context: _LateContext,
    reading: _late_publication._PublicationReading,
    number: int,
) -> bool:
    """Prove the publication is the ref this settlement will actually push.

    Asked before the head, because it is what makes the head mean anything: a
    commit is the tip of a ref in a repository, and a pull request standing at
    the frozen SHA anywhere else is somebody else's publication that happens
    to agree.

    The REPOSITORY comes first. A fork carries this repository's ref names
    over its commits, so one agrees on the branch and the head together while
    naming a ref no push of this issue's has ever touched.

    Refused rather than preferred either way -- neither field is evidence the
    other is wrong -- and the record is left exactly as it stands for the
    human who reconciles it.
    """
    if not context.gh.is_own_repository(reading.head_repo):
        log.error(
            "issue=#%d was adjudicated against PR #%d, whose head is in %r "
            "rather than in %r; refusing to publish the accepted candidate "
            "onto a publication this issue never made",
            context.issue.number, number, reading.head_repo,
            context.gh.repo_slug,
        )
        return _late_proof._unreconciled(
            context,
            _FOREIGN_REPOSITORY_PARK.format(
                number=number,
                read=reading.head_repo,
                expected=context.gh.repo_slug,
            ),
        )
    return _reconciled_branch(context, reading.head_branch, number)


def _reconciled_branch(
    context: _LateContext, observed: str | None, number: int,
) -> bool:
    """Prove the publication is open on the branch this settlement will push.

    Compared against the branch the SEAM resolves rather than against anything
    read back, since the question is where the push behind this verdict will
    actually land.
    """
    branch = _naming._resolve_branch_name(
        context.state, context.spec, context.issue.number,
    )
    if observed == branch:
        return True
    log.error(
        "issue=#%d was adjudicated against PR #%d, which is open on %r rather "
        "than on %r; refusing to publish the accepted candidate onto a "
        "publication the push would not touch",
        context.issue.number, number, observed, branch,
    )
    return _late_proof._unreconciled(
        context,
        _FOREIGN_BRANCH_PARK.format(
            number=number, read=observed, expected=branch,
        ),
    )


def _dropped_settled_pr(context: _LateContext) -> bool:
    """Stop recording a pull request this candidate cannot publish onto.

    Reached only when nothing carries the measured commit, so what the issue
    records is about some other change. An OPEN one is left exactly where it
    is: that is the pull request the ordinary publication reuses. A
    merged or closed one is dropped, because carrying it into `implementing`
    is what lets the merged-PR terminal end the issue on a change the
    adjudicated candidate is not in.

    A read that failed is neither answer, and it parks: publishing on the
    strength of it is the one thing this exists to prevent.
    """
    pr_number = _payloads.as_identity(context.state.get(_PR_NUMBER))
    if pr_number is None:
        return True
    try:
        settled = context.gh.pr_state(
            context.gh.get_pr(pr_number),
        ) != _OPEN_PR_STATE
    except Exception:
        log.exception(
            "issue=#%d could not read recorded PR #%d before publishing the "
            "accepted candidate", context.issue.number, pr_number,
        )
        return _late_proof._unreconciled(
            context, _RECORDED_PR_UNREADABLE_PARK,
        )
    if settled:
        log.info(
            "issue=#%d recorded PR #%d is settled and does not carry the "
            "accepted candidate; dropping it from the handoff",
            context.issue.number, pr_number,
        )
        context.state.set(_PR_NUMBER, None)
    return True
