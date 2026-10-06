# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned reviewer's verdict, persisted and its evidence reconciled, then acted on or parked where that is owed.

Every live reviewer round that returns a verdict hands it here: the round
(`reviewer._dispatch_reviewer_result`) calls `disposes_of_the_verdict` with
the decision it parsed, and the validating handler's recovery asks
`finishes_the_verdict` of a verdict an earlier tick left waiting
(`review_resume`). `disposes_of_the_verdict` takes a returned run from the
top: its preparation (`prepares_the_verdict`) hands back the verdict ready to
be acted on, or nothing, and the disposition acts on it or parks it.
`finishes_the_verdict` takes the verdict a later tick finds waiting,
where `waiting_verdict_ready` answers it may be acted on now -- from the pinned
comment alone, since the process keeps nothing between ticks -- beside a run
its caller rebuilds of the round that returned it. That run has to be of the
verdict's own round and subject, and has to name the pull request that subject
is on, each read as the record spells it rather than as Python compares it: the
record, not the run, says what was decided about what, and a verdict carried
out through another round's run, or on another pull request, would post, push,
or squash where nobody reviewed. A change request is then
handed over from the record alone, in the checkout the issue's developer
resumes in; an approval goes on in that run's checkout and pull request.

A verdict is persisted only while the whole subject the reviewer was handed --
head, requirements, and report -- still stands. A verdict of a subject that
moved while the reviewer ran is about work that is not there: an approval
would hand it on, and a change request would pay a developer to answer a
review of words the pull request no longer carries. So is one returned beside
verification evidence another road recorded or settled meanwhile: its
transaction was minted, and a reuse named the evidence it was handed, over the
records that replaced. The run is recorded over whatever settled meanwhile --
the pinned comment read again once the subject has been resolved, since that
resolution is requests of its own -- and the next tick's reviewer is handed
the subject as it stands, or refused.

The run's own records -- its usage, session, and returned subject -- are
staged here, over that last reading, rather than by the caller: a usage total
another road folded meanwhile is added to, not written back over, however the
records it was read against stand. A verdict of the subject that stands is
persisted before anything is published (`review_verdicts`): the round,
verdict, subject, the feedback a change request hands on, and the evidence the
verdict relies on go down in ONE guarded commit beside those records and the
reply the round settled, with the reviewer-reported transaction its commands
were minted as (`review_claims`) recorded in that same commit
(`review_writes.lands_the_verdict`). From there nothing asks the reviewer
again. The transaction is published through the dispatcher's own
reconciliation (`verification_transaction`), which retries a post GitHub
refuses or never confirms on every later tick, so a retry reruns no reviewer,
folds no usage twice, and spends no round. A commit refused -- a record the
verdict stands on moved after the last reading, a comment that will not read
or was replaced -- writes, publishes, and acts on nothing, and so does one
GitHub took and never confirmed: what it may have left, the verdict and its
transaction, is what a later tick's reconciliation and recovery
(`review_resume`) finish, with no second reviewer, fold, charge, or round. A
verdict that cannot be persisted is persisted and published nowhere, and the
answer says why (`Prepared.unrecorded`, in the words the park that answers it
spells): a record that would not read back as written -- words UTF-8 cannot
carry, say -- or a comment with no room for the verdict or its transaction,
measured once more of the very candidate its commit sends. A disposition nothing
durable backs is one a second reviewer would answer again, and evidence dropped
for room would leave what the reviewer reported, a failed check included, off
the pull request. The disposition parks it under `reviewer_unrecorded` over the
run's records staged here (`review_parks.parks_unrecorded`), acting on nothing.

The feedback that record carries -- the words a change request posts on the
pull request and hands its developer, in that tick or from the record on a
later one -- is the reviewer's findings as a human is shown them
(`review_findings`), formatted only once the declaration has been read off the
run's own message (`review_claims`), which nothing here rewrites. So the
evidence is the declaration exactly as written, every command, status, and
output carried whole by the transaction's artifact, while the feedback sets
it aside, keeping each check not shown passing as the diagnostic a developer
acts on (`VerdictInHand.returned_by`). Findings the formatting leaves nothing
of read as a sentence saying so, never as the raw message their declaration
sits in. Formatting decides nothing: the claim, its refusal, and the
approval's proof read the declaration, never the findings. A record persisted
before that formatting still carries the declaration raw: a later tick's
handoff formats only the words it posts and hands on (`review_handoffs`), and
the record is held, compared, and dropped as written.

Neither verdict is ready until the evidence it relies on has settled: a change
request handed to a developer moves the head and an approval squashes it, and
either leaves a transaction about the old head that can never settle. A
publication that holds or stands down leaves the verdict waiting and the
transaction owed, for the reconciliation ahead of a later tick to publish --
held to its subject on every tick it waits
(`review_coverage._verdict_still_stands`), and dropped once that subject is
proved to have moved, since no settlement makes it a review of the work there
now. A transaction that can never settle -- retired, superseded by a later
revision, or bound to a verification context that has since moved -- drops the
verdict for a fresh reviewer instead of waiting forever. So does a reuse of
evidence a later revision has superseded since, whichever the verdict: the
reviewer judged the branch beside evidence that is no longer the pull
request's current evidence. Nor is a verdict ready on its evidence alone: the
verdict's own write, a publication, or a later tick's reads are long enough
for a push or a later report, so it is held once more to its subject, the
comment read again last, and its claim judged over that reading -- a
settlement of the very evidence it claims readies it, and a later revision
superseding that evidence drops it.

Every write here -- the verdict's own, the run's where its subject moved, and
each drop -- is a guarded commit (`review_writes`) captured over the comment
read again just before it (`review_comment._records_stand`): a report or
evidence another road settled meanwhile is kept, and so is anything else it
wrote that no verdict stands on -- a round a reply bought, the thread it read
through -- save, where the report records and the verdict stand, a field this
tick changed too, which its own write says. What another road writes between
that reading and the commit is kept the same way, while one moving a record the
write was decided on -- the report's, `pr_number`, the verdict, the evidence --
refuses it with nothing written. A drop names the verdict held
(`review_verdicts.drops_the_verdict`), so one another road put in its place is
that road's to finish. A comment or subject that will not read writes nothing,
and the verdict waits.

A change request stands without evidence -- a reviewer may find a bug without
running anything -- so a declaration that earned none is ready too, carrying
the refusal that says why (`VerdictInHand.refusal`) for an approval, which
cannot rest on it.

Either entry acts only on a verdict just proved carried on the pinned comment,
its subject standing, and its evidence settled -- never on one a caller hands
over unproved. A change request goes to the one developer it owes
(`review_handoffs`), behind its feedback posted and anchored -- through the
decision it was returned as in that tick, and from the record on a later one,
where one a tick already handed resumes where that handoff stopped without
posting again. An approval reaches the approval arc only through the proof of
the evidence its record names (`unverified_approvals`): a proof nobody could
read holds it for a later tick, and a refusal -- or a declaration that earned
no evidence at all -- parks it under `reviewer_unverified` (`review_parks`).
The proof is requests long enough for a push or a later revision, and a refusal
over either is a fresh reviewer's to answer rather than a human's, so a refused
approval is held to its subject and its claim once more first, measured from
the comment as its readiness was proved, and only one still standing on them
parks. Every disposition retires the verdict in the write it makes: the
approval arc in whichever write its road makes -- save where the subject behind
its verify gate would not read, which that write keeps the verdict through --
and each park in its own. A change request keeps it, marked handed, until the
writes behind the developer's launch drop it. A disposition that ends its tick
writing nothing leaves the verdict for a later tick to finish.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    review_findings as _findings,
    verification_records as _records,
    verification_transaction as _transaction,
)
from orchestrator.workflow.stages.implementing import late_records as _late_records
from orchestrator.workflow.stages.validating import (
    review_claims as _claims,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_handoffs as _handoffs,
    review_parks as _parks,
    review_verdicts as _verdicts,
    review_writes as _review_writes,
    unverified_approvals as _unverified,
)
from orchestrator.workflow.stages.validating.models import _ReviewerDecision, _ReviewerRun
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


@dataclass(frozen=True)
class VerdictInHand:
    """A verdict and the evidence it relies on, as the tick it returned in persisted it.

    `refusal` says why a declaration earned no evidence, for the park an
    approval without any takes; "" where it earned some or was never asked.
    `pending` is the transaction a published claim names, which that tick
    recorded and publishes itself.
    """

    decision: _ReviewerDecision
    claim: _verdicts.EvidenceClaim | None = None
    refusal: str = ""
    pending: _records.PendingEvidence | None = None

    @classmethod
    def returned_by(cls, decision: _ReviewerDecision, claimed: _claims.ClaimedEvidence) -> VerdictInHand:
        """The verdict a live round returned as `decision`, its findings concise, beside what `claimed` earned.

        `claimed` was read off the run's own message, which nothing here
        rewrites, so the evidence is the declaration exactly as the reviewer
        wrote it -- every command, status, and output the transaction carries
        whole. The feedback is formatted only behind that reading
        (`review_findings`): the reviewer's words with the declaration set
        aside, save each check not shown passing, kept as the diagnostic a
        developer acts on. The raw feedback is chosen first -- the body above
        the VERDICT line, or the whole message where nothing stands there --
        and formatting never answers empty, so findings it left nothing of
        read as a sentence saying so and never fall back to the raw message
        their declaration sits in. The claim, its refusal, and its
        transaction are `claimed`'s as they stand: formatting decides nothing.
        """
        concise = replace(decision, body=_findings._concise_findings(decision.feedback))
        return cls(concise, claimed.claim, claimed.refusal, claimed.pending)

    @classmethod
    def replayed(cls, run: _ReviewerRun, returned: _verdicts.ReturnedVerdict) -> VerdictInHand | None:
        """The verdict a tick left waiting as `returned`, in hand again over `run`; None where `run` is not its own.

        `run` has to be of the very round and subject the record names, on the
        pull request that subject is on, each read as the record spells it
        before it is compared: the record `run` would be persisted as has to
        read back whole, as exactly the one waiting (`ReturnedVerdict.
        reads_back`), and its pull request has to be the subject's as a whole
        number (`ReviewSubject.is_on_pull_request`). Python's `==` calls a
        round `False` the round `0` and a report revision `True` the revision
        `1`, and a verdict carried out through such a run would act on, and
        write, values no record spells. The waiting record keeps no copy of
        why a declaration earned no evidence, so an approval relying on none
        is refused in the words its proof has for all of them.
        """
        rebuilt = replace(returned, round_n=run.round_n, subject=run.subject.recorded())
        own = rebuilt.reads_back() and rebuilt == returned
        if not (own and run.subject.is_on_pull_request(run.pr_number)):
            return None
        return cls(_ReviewerDecision(run, returned.verdict, returned.feedback), returned.evidence)

    def returned(self) -> _verdicts.ReturnedVerdict:
        """The record this verdict is persisted as, ahead of any handoff."""
        decision = self.decision
        return _verdicts.ReturnedVerdict(
            round_n=decision.run.round_n,
            verdict=decision.verdict,
            subject=decision.run.subject.recorded(),
            feedback=decision.feedback if decision.verdict == _verdicts.CHANGES_REQUESTED else "",
            evidence=self.claim,
        )

    def _persists(
        self, gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
    ) -> Prepared:
        """Persist the verdict with its transaction in one guarded commit, then publish it; the verdict once ready.

        Measured together at the verdict's handoff: the transaction's
        settlement lands while the verdict still waits, and a change request's
        handoff behind both. The claim and its transaction were minted
        together over records that still stand, so a record that reads back
        refused past that is one the comment has no room for -- asked again of
        the candidate the commit sends (`review_writes.lands_the_verdict`). A
        commit otherwise refused, or never confirmed, publishes nothing. The
        publication goes through the dispatcher's own reconciliation, which
        holds the tick over a reading nobody could take, and otherwise settles
        the evidence, retires it, or stands down with it still owed; what this
        tick wrote, the settlement included, is what the verdict is held
        against from there.
        """
        returned = self.returned()
        unrecorded = _parks.UNREADABLE
        if returned.reads_back():
            landed = _review_writes.lands_the_verdict(gh, issue, state, returned, self.pending)
            if landed is False:
                return Prepared()
            unrecorded = "" if landed else _parks.NO_ROOM
        if unrecorded:
            log.warning(
                "issue=#%d could not persist its reviewer's verdict (%s); writing "
                "and publishing nothing", issue.number, unrecorded,
            )
            return Prepared(unrecorded=unrecorded)
        if self.pending is not None and _transaction._reconciles_pending_evidence(
            gh, spec, issue, WorkflowLabel.VALIDATING, state,
        ):
            log.info(
                "issue=#%d holds its reviewer's verdict until the verification "
                "evidence it declared is confirmed on PR #%s", issue.number, self.decision.run.pr_number,
            )
            return Prepared()
        ready = _ready(gh, issue, state, returned, dict(state.data))
        return Prepared(self if ready else None)

    def _acts(
        self, gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
    ) -> None:
        """Carry out this verdict, just proved carried, standing, and settled over the comment as `state` carries it.

        A change request goes to its developer through the decision in hand
        (`review_handoffs.hands_the_request_over`). An
        approval goes to its proof and the approval arc over a gate built on
        its run's checkout (`unverified_approvals.approves`): a proof nobody
        could read holds it, and a refusal parks it -- as a declaration that
        earned no evidence does, with no proof asked. The proof's requests are
        long enough for a push or a later revision, and a refusal over either
        is a review of work nobody is asking about, so the refused approval is
        held to its subject and its claim once more first (`_ready`), measured
        from the comment as its readiness was proved, and only one still
        standing on them parks.
        """
        run = self.decision.run
        if self.decision.verdict == _verdicts.CHANGES_REQUESTED:
            _handoffs.hands_the_request_over(gh, spec, issue, state, self.decision)
            return
        if self.refusal:
            _parks.parks_unverified(gh, issue, state, run, self.refusal)
            return
        proved_over = dict(state.data)
        gate = _late_records._gate(gh, spec, issue, state, run.wt)
        refusal = _unverified.approves(gate, run)
        if refusal is None:
            log.info(
                "issue=#%d could not confirm the evidence its reviewer's approval "
                "relies on; holding the approval for a later tick", issue.number,
            )
        elif refusal and _ready(gh, issue, state, self.returned(), proved_over):
            _parks.parks_unverified(gh, issue, state, run, refusal)


@dataclass(frozen=True)
class Prepared:
    """What preparing one returned verdict leaves its caller.

    `ready` is the verdict persisted, relying on settled evidence or on none,
    and proved to stand -- subject and records -- behind the last request this
    tick made: the one thing a caller may act on, holding it to its subject
    again, against the state handed back beside it, around whatever requests
    it makes. None where this tick has nothing to act on -- the verdict waits
    on its evidence, was dropped, or was never persisted over a subject that
    moved, a reading nobody could take, or a run off its subject's pull
    request. `unrecorded` says why the verdict could not be persisted at all
    (`review_parks.UNREADABLE`, `review_parks.NO_ROOM`), "" where it was or was
    never asked: nothing was written or published, and the park that answers
    it is the caller's write.
    """

    ready: VerdictInHand | None = None
    unrecorded: str = ""


def disposes_of_the_verdict(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    decision: _ReviewerDecision,
) -> None:
    """Persist a returned reviewer's verdict and publish its evidence, then act on it or park it where that is owed now.

    `state` is as `prepares_the_verdict` takes it. A verdict the preparation
    could not persist parks over the run's records it staged; one it hands
    back ready is acted on over the comment as that preparation last read or
    wrote it; anything else was refused, held, or dropped there, and this tick
    does nothing more.
    """
    prepared = prepares_the_verdict(gh, spec, issue, state, decision)
    if prepared.unrecorded:
        _parks.parks_unrecorded(gh, issue, state, decision.run, prepared.unrecorded)
    elif prepared.ready is not None:
        prepared.ready._acts(gh, spec, issue, state)


def prepares_the_verdict(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    decision: _ReviewerDecision,
) -> Prepared:
    """Persist a returned reviewer's verdict and publish its evidence; the verdict ready to be acted on, if any.

    `state` carries whatever the round staged ahead of the run and nothing of
    its return, which is staged here. The evidence is minted first, since
    reading the reviewed tree is a request of its own, out of the run's
    message as the reviewer wrote it; the feedback the verdict is persisted
    with is formatted only behind that (`VerdictInHand.returned_by`). Then the
    subject is held to what stands, which is requests of its own too, long
    enough for another road to settle a later report the state in hand does
    not carry, so the comment is read again against what the run was resolved
    over, carrying whatever moved -- the last requests before the write that
    persists the verdict: a write composed over the older records would put
    them back over the newer, and the verdict it persists would be handed on
    as though nothing had. A comment or a subject that will not read writes
    nothing: no verdict is persisted over a reading nobody took. Nor does a
    run that does not name, as a whole number, the pull request its subject
    names (`ReviewSubject.is_on_pull_request`): its feedback, its fix, or its
    approval would go to another pull request than the one reviewed, so it is
    refused before anything is minted, written, or published.
    """
    run = decision.run
    if not run.subject.is_on_pull_request(run.pr_number):
        log.warning(
            "issue=#%d its reviewer run names PR #%s where the subject it "
            "reviewed is on PR #%s; acting on nothing", issue.number,
            run.pr_number, run.subject.pr_number,
        )
        return Prepared()
    claimed = _claims.claimed_evidence(issue, state, run)
    stands = _review_coverage._verdict_still_stands(gh, issue, state, run.subject.recorded(), run.resolved_over)
    if stands is None:
        return Prepared()
    _review_writes.stages_the_return(state, run)
    evidence_moved = _review_comment._moved(state.data, run.resolved_over, _review_comment._EVIDENCE_RECORDS)
    if run.subject_moved or not stands or evidence_moved:
        _review_writes.lands(gh, issue, state, _review_writes.RETURN)
        return Prepared()
    return VerdictInHand.returned_by(decision, claimed)._persists(gh, spec, issue, state)


def waiting_verdict_ready(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
) -> _verdicts.ReturnedVerdict | None:
    """The verdict this issue has waiting, where it may be acted on now; None where none may.

    For a later tick, over the pinned comment alone: the record names the
    subject its reviewer was handed and the evidence it relies on, and the
    comment as `state` was read is what it is held against. None where no
    verdict waits, where it waits on evidence still owed or on a reading
    nobody could take, and where it was dropped (`_ready`).
    """
    waiting = _verdicts.read_returned_verdict(state)
    if waiting is None:
        return None
    read = dict(state.data)
    return waiting if _ready(gh, issue, state, waiting, read) else None


def finishes_the_verdict(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _ReviewerRun,
) -> None:
    """Act on the verdict this issue has waiting, where it is ready now, in `run`'s checkout and pull request.

    `run` is what the caller rebuilt of the round that returned the verdict,
    and the verdict is acted on only where the pinned comment has waiting one
    of exactly that round and that subject -- a change request as its handoff
    last wrote it, handed or not -- and where the pull request `run` would
    post and push to is the one that subject names, each read as the record
    spells it (`VerdictInHand.replayed`); anything else acts on nothing and
    writes nothing. Past that, only once `waiting_verdict_ready`
    finds the verdict ready, over the comment as that last read or wrote it: a
    change request is handed over from the record, in the checkout the issue's
    developer resumes in (`review_handoffs.hands_the_waiting_request_over`),
    and an approval goes to its proof and the approval arc in `run`'s checkout.
    """
    waiting = _verdicts.read_returned_verdict(state)
    if waiting is None:
        return
    in_hand = VerdictInHand.replayed(run, waiting)
    if in_hand is None:
        log.warning(
            "issue=#%d its waiting reviewer verdict was not returned in the "
            "round, over the subject, or on the pull request of the run in "
            "hand; acting on nothing", issue.number,
        )
        return
    if waiting_verdict_ready(gh, issue, state) != waiting:
        return
    if waiting.verdict == _verdicts.CHANGES_REQUESTED:
        _handoffs.hands_the_waiting_request_over(gh, spec, issue, state)
    else:
        in_hand._acts(gh, spec, issue, state)


def _ready(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    held: _verdicts.ReturnedVerdict,
    resolved_over: dict,
) -> bool:
    """Whether the persisted verdict `held` may be acted on now: still carried, standing, and its evidence settled.

    Only the verdict the pinned comment carries, as the state in hand read or
    wrote it last -- `resolved_over`: one another road dropped or replaced
    since -- a reply that bought a fresh round, a recovery that finished it --
    is no verdict this tick may act on, nor drop over whatever took its place.
    Whatever requests came since the comment was last read -- the verdict's
    own write, a publication, the reads a later tick took before asking, an
    approval's proof -- are long enough for a push or a later report, so the
    verdict is held to its subject once more first: a later report settling,
    a push, or report records that moved since `resolved_over` are a subject
    nobody reviewed, which a fresh reviewer handed them answers. A comment or
    a subject that will not read writes nothing, and the verdict waits for a
    later tick to resolve again rather than being dropped as stale over a
    reading nobody could take. The comment that reads last carries whatever
    evidence another road recorded or settled meanwhile, and the verdict's
    claim is judged over it without a request of its own: a settlement of the
    very evidence it claims readies it; a transaction still owed holds it,
    written nowhere, for the reconciliation ahead of the next tick to publish;
    and evidence that can never be relied on -- superseded by a later
    revision, retired, or under a verification context that has since moved
    -- drops it, whichever the verdict. Every drop is a guarded commit over
    that reading (`review_writes.DROP`), whatever else another road wrote
    there kept, and drops only this verdict: one another road put in its place
    is that road's, and the state already carries it as the comment does. A
    record the drop was decided on that moves under the commit -- a verdict
    put in this one's place, evidence recorded or settled -- refuses it, and
    the verdict waits for a later tick to decide again.
    """
    if _verdicts.read_returned_verdict(state) != held:
        log.info(
            "issue=#%d its pinned comment no longer carries the reviewer "
            "verdict this tick holds; acting on nothing", issue.number,
        )
        return False
    stands = _review_coverage._verdict_still_stands(gh, issue, state, held.subject, resolved_over)
    if stands is None:
        return False
    claim = held.evidence
    standing = _claims.ClaimStanding.SETTLED if claim is None else _claims.claim_standing(state, claim)
    if not stands:
        log.info(
            "issue=#%d the subject its reviewer's verdict is about moved "
            "before it was acted on; dropping the verdict", issue.number,
        )
    elif standing is _claims.ClaimStanding.OWED:
        log.info(
            "issue=#%d holds its reviewer's verdict until the verification "
            "evidence it declared is published", issue.number,
        )
        return False
    elif standing is _claims.ClaimStanding.LOST:
        log.info(
            "issue=#%d drops its reviewer's verdict: the verification evidence it "
            "declared can no longer be published or relied on", issue.number,
        )
    if stands and standing is _claims.ClaimStanding.SETTLED:
        return True
    if _verdicts.drops_the_verdict(state, only=held):
        _review_writes.lands(gh, issue, state, _review_writes.DROP)
    return False
