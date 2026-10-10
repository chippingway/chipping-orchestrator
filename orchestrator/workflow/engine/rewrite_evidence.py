# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence a landed automatic base rewrite's head is routed with.

A rebase whose push landed moves the pull request onto a head no verification
evidence was recorded for, and its finish (`rewrite_finish`) routes that head
to review between its checkpoint and its route. This owner is the evidence
policy for that step (`decides`), asked by the finish's evidence step
(`rewrite_finish_evidence`) for every head it routes, which records what the
decision requires before anything routes. It reads the landing the finish is
handed (`rewrite_finish_models`) and writes nothing itself; the one staging its
decision implies is `RewriteEvidence.stages`.

Evidence is carried only across a rewrite PROVED to change nothing it was
taken over. The landing carries both trees -- the one the rewrite replaced and
the one it published -- and both have to be the tree the current evidence
tested, under the verification context configured now. Then the carry-forward
decision (`verification_carry_forward`) proves the tested commit and the new
head still read as that tree, the source still published, and the pull
request on the new head, and it is held here to a review subject recorded
about the rewritten head itself. Never to the approved review of the head the
rewrite replaced: only an approval's own squash carries that, and a base
rewrite moves the head under a report about the old one, which the rewritten
head's report refresh answers before any reviewer is handed it. Its whole
binding is then proved (`verification_proof.binding_verdict`) -- the settled
report re-read at its location, the requirements, the branch and the checkout
-- and what it licenses keeps the tested commit and tree and names the source
it copied: explicit provenance, never a run relabelled.

A rewrite that moved the full tree or the context -- or one whose trees
nobody read -- invalidates the current evidence instead: it no longer answers
for the pull request, and goes into history whole as INVALIDATED. Equal trees
whose carry is refused invalidate nothing: the evidence still describes the
tree the rewritten head carries, and a fresh result that settles supersedes it.

Anything not carried needs a fresh result from the configured
`VERIFY_COMMANDS`, run by the verify runner (`git/verification/runner.py`) over
the issue's checkout. An empty configuration runs nothing, so it records no
local run and is never read as a pass: the head goes to the fresh reviewer,
which owes the evidence through its own declaration. So does a target binding
that is not available: a fresh run is evidence only of the review subject a
reviewer of the rewritten head was handed (`review_subject`, the applicable
record for a run this orchestrator executes) and the settled report it names,
on the publication that report was settled to, moved to the rewritten head.
The whole binding is proved before anything runs, so a subject still about
the head the rewrite replaced -- the refresh not yet settled, or no reviewer
handed it -- runs nothing. A pull request or report nobody could read is
reported in the proof's own verdict, so its HOLD reaches the caller. Nor does
a head that no longer stands on the base tip its replay was made onto
(`rewrite_evidence_proof.standing_refusal`): a remote base moved since it was
counted HOLDS, and a base rewound or repointed under it, or no recorded tip to
hold it to, DEFERS.

After the run its own record is held to the binding planned for it: the
commit and tree the runner read as its baseline, and the context it minted,
have to be the rewritten head, the tree the landing read for it, and the
configuration proved before it ran. A checkout that stood elsewhere as the run
began -- and back by the time anything is read again -- or a baseline the
runner never read is a run of something else, whatever it passed or failed.
Then the issue and its pinned comment are read afresh and the whole binding
proved again over them (`rewrite_evidence_proof.proves_again`): the pull
request still on the rewritten head, the remote branch and the checkout
standing there, the configuration still the one the commands ran under, the
review subject and the settled report still the ones bound, and the issue's
requirements unchanged. Anything that moved, or that nobody could read again,
makes the result MOVED, eligible for nothing. Only then is it classified: a run `verification_local_runs` binds is
FRESH, carrying exactly the commands, exit statuses, and outputs that ran; a
passing run that binds nothing records nothing and leaves the evidence to the
reviewer; and every other run is FAILED, the run kept whole so its failing
command and output stay actionable.

Every decision -- a carry, a route that runs nothing, and a run's -- is held,
once it is written, to the last word the finish's evidence step takes behind
all its requests (`rewrite_finish_captured.stands_before_the_route`): the
landing, the base, the requirements, and the configuration read once more.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator import config
from orchestrator.git.verification import models as _verify_models, runner as _verify_runner
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
    verification_carry_forward as _carry_forward,
    verification_local_runs as _local_runs,
    verification_proof as _proof,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_evidence_models import RewriteEvidence, RewriteEvidenceRoute
from orchestrator.workflow.engine.rewrite_evidence_proof import proves_again, standing_refusal
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

log = logging.getLogger("orchestrator.workflow")

# The commands and the per-command timeout one run is handed, read once.
_Configuration = tuple[tuple[str, ...], int]

_DEFER = _evidence_models.ReportEvidenceVerdict.DEFER

_UNCONFIGURED = _evidence_models.ReportEvidence(
    _DEFER, "no VERIFY_COMMANDS are configured, so nothing ran and nothing passed",
)

_UNBOUND = _evidence_models.ReportEvidence(
    _DEFER, "no review_subject about the rewritten head and its settled report is recorded",
)

_PRECEDING = _evidence_models.ReportEvidence(
    _DEFER, "the review the carried evidence answers for is not about the rewritten head",
)

_UNBINDABLE = _evidence_models.ReportEvidence(
    _DEFER, "the passing run binds no evidence the pull request could carry",
)

_ELSEWHERE = _evidence_models.ReportEvidence(
    _DEFER, "the run did not test the rewritten head and its tree under the configuration proved for it",
)


def decides(finish: LandedFinish) -> RewriteEvidence:
    """The evidence `finish`'s landed head is routed with; nothing is written.

    Asked of a landing the finish accounts for, after its push landed and
    before anything routes it. A carry where the rewrite is proved equivalent
    to what the current evidence tested, and otherwise a fresh run of the
    configured commands, or the reviewer's responsibility where none can be
    bound. The base the head was replayed onto, and everything else that can
    move, is held to once the decision is written
    (`rewrite_finish_captured.stands_before_the_route`).
    """
    reading = _proof.ProofReading(finish.gh, finish.spec, finish.issue, finish.state)
    invalidates = invalidates_current(finish)
    carried = None
    if _settlement.read_current_evidence(finish.state) is not None and not invalidates:
        carried = _carried(reading, finish.head)
    decided = carried or _verified(reading, finish, invalidates)
    log.info(
        "issue=#%d decided %s evidence for the base rewrite's head %.8s, "
        "invalidating the current evidence: %s; %s",
        finish.issue.number, decided.route.value, finish.head, decided.invalidates,
        decided.reason or "nothing refused",
    )
    return decided


def invalidates_current(finish: LandedFinish) -> bool:
    """Whether the rewrite moved the full tree or the context the current evidence was taken under.

    Equivalence has to be shown rather than assumed: the tree the rewrite
    replaced, the tree it published, and the tree the evidence tested all
    read, and are one, under the context configured now. False where there is
    no current evidence to invalidate. Asked again by the finish as it stages
    its write -- behind the commands a decision ran, and of a decision an
    earlier finish made durable -- since the configuration can move in
    between.
    """
    current = _settlement.read_current_evidence(finish.state)
    if current is None:
        return False
    candidate = finish.landed.candidate
    trees = {candidate.original_tree, candidate.checkout.tree, current.binding.tested_tree}
    context = current.binding.context_revision == _proof.configured_context_revision()
    return not (context and candidate.checkout.tree and len(trees) == 1)


def _carried(reading: _proof.ProofReading, head: str) -> RewriteEvidence | None:
    """The current evidence carried onto `head`, or None where no carry is proved.

    The carry-forward decision answers only for a review subject about
    `head` or the approval's unchanged one; the second is refused here, and
    the first proved whole.
    """
    decided = _carry_forward.carry_forward_decision(reading, head)
    if not isinstance(decided, _carry_forward.CarryForward):
        return None
    about = _review_subjects.ReviewSubject.commit_recorded_in(decided.subject)
    found = _proof.binding_verdict(reading, decided.binding) if about == head else _PRECEDING
    if found.proved:
        return RewriteEvidence(RewriteEvidenceRoute.CARRIED, carry=decided)
    log.info(
        "issue=#%d carries no verification evidence to the rewritten head %s: %s",
        reading.issue.number, head, found.refusal,
    )
    return None


def _verified(reading: _proof.ProofReading, finish: LandedFinish, invalidates: bool) -> RewriteEvidence:
    """A fresh run of the configured commands on the rewritten head, and what it came to.

    The configuration is read once, so the binding proved before the run is
    minted under exactly the commands and timeout the runner is handed. A
    head that no longer stands on the base it was counted against runs
    nothing (`rewrite_evidence_proof.standing_refusal`).
    """
    configured = (tuple(config.VERIFY_COMMANDS), config.VERIFY_TIMEOUT)
    planned = _planned(reading.state, finish, configured)
    found = planned
    if isinstance(planned, _records.EvidenceBinding):
        found = _proof.binding_verdict(reading, planned)
    if found.proved:
        found = standing_refusal(finish) or found
    if not found.proved:
        return RewriteEvidence(RewriteEvidenceRoute.REVIEWER, invalidates, refusal=found)
    run = _verify_runner._run_verify_commands(
        _worktree_paths._worktree_path(finish.spec, finish.issue.number), *configured,
    )
    return _ran(finish, planned, run, invalidates)


def _planned(
    state: PinnedState, finish: LandedFinish, configured: _Configuration,
) -> _records.EvidenceBinding | _evidence_models.ReportEvidence:
    """The binding a passing run of the rewritten head would be, or why there is none.

    The review subject a reviewer of the rewritten head was handed and the
    settled report's publication moved to that head and those requirements,
    as a reviewer's own account is bound (`stages/validating/review_claims.py`);
    the run's commit and tree are the rewritten head and the tree the landing
    read for it, which the proof reads again.
    """
    if not configured[0]:
        return _UNCONFIGURED
    recorded = state.get(_review_subjects.REVIEW_SUBJECT)
    settled = _report_settlement.read_current_report(state)
    requirements = _review_subjects.ReviewSubject.requirements_recorded_in(recorded)
    about = _review_subjects.ReviewSubject.commit_recorded_in(recorded)
    if settled is None or not requirements or about != finish.head:
        return _UNBOUND
    return _records.EvidenceBinding(
        target=_records.EvidenceTarget(
            replace(settled.subject, source_sha=finish.head, requirements_revision=requirements), recorded,
        ),
        source=EvidenceSource.ORCHESTRATOR_EXECUTED,
        tested_sha=finish.head,
        tested_tree=finish.landed.candidate.checkout.tree,
        context_revision=_verify_models._context_revision(*configured),
    )


def _ran(
    finish: LandedFinish,
    planned: _records.EvidenceBinding,
    run: _verify_models.VerifyResult,
    invalidates: bool,
) -> RewriteEvidence:
    """What `run` of the rewritten head comes to once everything it is bound to is read again.

    The run's own baseline first: the commit, tree, and context it recorded
    have to be the ones `planned` names, since a run of anything else -- a
    checkout elsewhere as it began, or a baseline it never read -- says
    nothing about the rewritten head, a failure included, and the readings
    behind it cannot tell. Then `planned` is proved again over the issue and
    its pinned comment read afresh (`rewrite_evidence_proof`), so a failure
    on a head nobody stands on any more is no failure of the rewritten head
    either, and the base the head stands on read again, so a run the base
    moved under is recorded as nothing at all. Where the baseline is
    `planned`'s, so is the binding a passing run earns.
    """
    bound = _local_runs.local_run_evidence(run, planned.target)
    baseline = (run.commit, run.tree_identity, run.context_revision)
    if baseline == (planned.tested_sha, planned.tested_tree, planned.context_revision):
        found = proves_again(finish, planned)
    else:
        found = _ELSEWHERE
    if found.proved:
        found = standing_refusal(finish) or found
    if not found.proved:
        return RewriteEvidence(RewriteEvidenceRoute.MOVED, invalidates, refusal=found, run=run)
    if bound is not None:
        return RewriteEvidence(RewriteEvidenceRoute.FRESH, invalidates, run=run, fresh=bound)
    if run.status == _verify_models.VERIFY_STATUS_OK:
        return RewriteEvidence(RewriteEvidenceRoute.REVIEWER, invalidates, refusal=_UNBINDABLE, run=run)
    return RewriteEvidence(RewriteEvidenceRoute.FAILED, invalidates, run=run)
