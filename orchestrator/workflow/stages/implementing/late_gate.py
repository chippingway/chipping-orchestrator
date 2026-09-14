# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read and decide one committed candidate through the late size gate.

The candidate must still be the commit its caller named. Publication
receipts and existing permissions answer before a fresh or resumed count,
and the verdict carries the basis that admitted the publication.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models, settings as config
from orchestrator.git.measurement import (
    models as _measurement,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_delivery as _delivery,
    late_freeze as _freeze,
    late_gate_permission as _late_gate_permission,
    late_parks as _parks,
    late_reading as _reading,
    late_records as _records,
    late_transfer as _transfer,
    late_verdict as _verdict_owner,
)
from orchestrator.workflow.stages.implementing.late_gate_models import _HELD, _REFUSED, _Gate, _GateVerdict
from orchestrator.workflow.stages.implementing.models import _AgentWork, _RecoveredWork

log = logging.getLogger("orchestrator.workflow")

# Why a candidate skips the measurement, spelled as the log line reads it.
# What a checkout standing somewhere other than the commit its caller named
# is reported and parked as.
_MOVED_OFF_THE_CALLER = (
    "the commit handed to it was `{named}` and its checkout stands on "
    "`{head}`"
)


_MOVED_OFF_THE_CALLER_PARK = (
    "{mentions} this stage read `{named}` as the commit it was about to "
    "publish, and the checkout it would publish from stands on `{head}`. "
    "Something committed over the worktree between the two readings, so the "
    "two are not one candidate -- measured and pushed as it stands, this "
    "issue would put `{head}` on the pull request while recording `{named}` "
    "as what it published. Nothing was pushed and nothing was recorded. "
    "Reconcile the worktree with what landed and the next tick reads it "
    "afresh."
)

def _holds_committed_work(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    work: _AgentWork,
) -> _GateVerdict:
    """Whether the size gate keeps this committed candidate unpublished.

    `held` is the whole of what this tick did with the candidate: it is either
    parked on a reading nobody could take or handed to the late coordinator,
    and on both the caller publishes nothing. Not held means the candidate is
    this repository's to publish exactly as it always was -- small, already
    adjudicated, or never measured because the switch is off -- and the SHA
    beside it is the commit that earned that, which is what the push is then
    named against.

    A record already carrying a measurement for the commit in hand is acted on
    rather than re-taken, once it is proved to be a whole one this host can
    still show. The threshold on it is the one that generation was frozen
    under, so a setting retuned between two ticks cannot re-judge a candidate
    mid-flight, and a crash between the count and the label costs a label
    write rather than another reading of the same diff.
    """
    recovering = isinstance(work, _RecoveredWork)
    return _holds_candidate(_Gate(
        gh=gh, spec=spec, issue=issue, state=state, worktree=work.worktree,
        reconciling=recovering,
        # Every recovery here answers a reading this gate itself recorded --
        # a late park a human replied to, an approval whose push never went
        # out, a frozen pair a crash stranded -- so the switch has nothing
        # left to say about any of them.
        answering=recovering,
        # And each of them proved the checkout on that reading's own commit
        # before handing it over, so the head this owner reads is held to it:
        # the worktree is writable in between, and a commit landing there is
        # a candidate no reading covers.
        candidate=work.candidate_sha if recovering else "",
    ))


def _holds_candidate(gate: _Gate) -> _GateVerdict:
    """The size question one committed candidate answers, whatever asked it.

    The order of the questions rather than the seam that reaches them, which
    is what lets the gate stand in front of the initial publication and in
    front of a push onto a pull request the remote already carries without
    either seam re-deriving the contract. Every difference between the two is
    in the subject it is handed: the publication the call was entered on, the
    checkout, and whether a developer ran.

    A park a previous reading left is deliberately NOT cleared on the way in.
    Entering the gate is not answering the question it was taken for, and the
    two owners past here that do answer it retire it themselves -- so a tick
    that re-read the pair and missed again leaves the park exactly as it
    found it, rather than durably unparking an issue whose reading still has
    not happened.

    A publication receipt group this build cannot read WHOLE is refused here,
    ahead of every question below, because every road out of this call ends in
    the write that puts a fresh group down -- and the road that answers first
    is the one an install with `DECOMPOSE=off` and no caller-named candidate
    takes, which never reaches the candidate question the rest of the proof
    hangs off. Asked of the record and of no candidate, it costs nothing on an
    ordinary tick and holds before anything is measured, pushed or written.
    """
    if _delivery._holds_a_damaged_receipt(gate):
        return _HELD
    recorded = _records._entered(
        gate, _late_state.read_late_generation(gate.state),
    )
    candidate = _freeze._candidate_commit(gate, recorded)
    if candidate is None:
        return _verdict_owner._unmeasured_verdict(gate, recorded)
    if not candidate.is_frozen:
        return _unnameable(gate, recorded, candidate)
    if _moved_off_the_caller(gate, recorded, candidate.sha):
        return _HELD
    return _decided(gate, recorded, candidate.sha)


def _decided(
    gate: _Gate, recorded: LateGeneration, candidate_sha: str,
) -> _GateVerdict:
    """What one proved candidate earns, once the checkout is its caller's.

    The two answers past the proof, in the order the record decides them: a
    commit this workflow has already ruled on publishes without a reading, and
    everything else is measured -- the recorded count acted on where there is
    one, a fresh pair frozen and counted where there is not.

    Between them sits the one commit that is neither yet: a REWRITE of a
    change a human already ruled on. It is asked second because every question
    ahead of it is a record read off the pinned comment and this one spends
    two fingerprints and a fresh owner read, and because a commit the record
    already calls decided has nothing left to earn. Refused, the candidate
    falls through to the measurement exactly as it always did.

    A caller that may publish on the permit and on NOTHING else is answered
    one function over, and answered there ALONE rather than after the three
    records below have had their say. That is the vouched-replay crash
    recovery -- dormant, since no production selector reaches it yet -- and
    every other road to publishing is the wrong answer for it: the reading it
    would otherwise fall back to measures a commit an interrupted push is
    already leased for, and the reasons that skip a reading say the candidate
    may publish without saying a verdict may move onto it -- so the switch
    being off would let the push out with no permit behind it, the route would
    finish with the exemption still on the commit a human ruled on, and the
    permission would stand outstanding for ever.

    The delivery proof is taken ONCE, at the top and for every candidate,
    because the road past the measurement that rests on it -- a commit this
    stage's own receipt names -- may not take a second reading of its own: a
    second answer is a second chance to disagree with a decision already made.
    It costs no request unless the receipt names the candidate in hand, and
    none at all on a call that froze a publication of its own.

    A proof that FAILED holds the tick rather than falling through to the
    measurement, and it is asked before anything else acts on the candidate.
    The commit is one the record says this stage already pushed, so a count
    under the ceiling does not make republishing safe -- it force-pushes a
    branch nothing here could confirm and opens a second pull request over
    work the first may already carry. `late_delivery` owns which candidates
    that covers and what the park says.

    The permit's answer is kept APART from the other three rather than folded
    into the one reason, because the two license different things. All four
    say the candidate may publish without a reading; only the permit says a
    human's verdict may move onto it once that publication lands. A refusal
    that fell through to the measurement, and a count the ceiling then let
    through, publish the same commit under an answer nothing vouched for --
    so the write past the push is handed this commit and not the record, and
    a permit that refused rotates nothing however readable the permission
    beside it still is.

    What ADMITTED the candidate travels with it, because this is the only
    place that knows and because a second answer taken later is a second
    chance to fail: proving an operator's authorization is a git reading, and
    a store that stopped answering between the proof here and the write that
    records the debt would leave that bypass looking like ordinary unmeasured
    debt -- which the tick after a crash spends without asking anyone. One
    answer here is a human's; every other road past the measurement is this
    workflow's own record, and each of those already answers for itself.

    A commit an exemption names and no authorization stands behind is none of
    those answers, so it falls through to the ordinary measurement like any
    other candidate -- which is the whole of what the compatibility costs.
    What an oversized reading of one earns is decided where every other
    reading is settled, by `late_verdict`: a hold for the person the exemption
    cannot show rather than a second adjudication, which `late_consent` owns
    along with the command that ends it.
    """
    delivered = _delivery._delivered_before_the_relabel(gate, candidate_sha)
    if _delivery._holds_an_unprovable_receipt(gate, candidate_sha, delivered):
        return _HELD
    if gate.permit_only:
        return _permitted_only(gate, recorded, candidate_sha, delivered)
    decided = _late_gate_permission._needs_no_measuring(gate, recorded, candidate_sha, delivered)
    permitted = decided or _transfer._carried_over(gate, candidate_sha)
    if permitted:
        log.info(
            "issue=#%d candidate %s %s; publishing it without a reading",
            gate.issue.number, candidate_sha, permitted,
        )
        return _verdict_owner._unmeasured_verdict(
            gate, recorded, _GateVerdict(
                held=True,
                candidate_sha=candidate_sha,
                permitted_sha="" if decided else candidate_sha,
                basis=_late_gate_permission._admitted_by(decided),
                delivered_pr=delivered.number,
            ),
        )
    answered = (
        recorded.candidate_sha == candidate_sha
        and recorded.additions is not None
    )
    held = (
        _reading._reconciled_measurement(gate, recorded) if answered
        else _reading._freshly_measured(gate, recorded, candidate_sha)
    )
    return _held_or_published(candidate_sha, held)


def _permitted_only(
    gate: _Gate,
    recorded: LateGeneration,
    candidate_sha: str,
    delivered,
) -> _GateVerdict:
    """What a candidate may publish on where a permit is the only licence.

    One question and no fallbacks. The caller is finishing a publication
    rather than deciding one -- the push it was leased for is already owed --
    so what it needs to know is whether the permission may be spent, and every
    other answer this gate can give is about something else.

    That is why the three records that skip a reading are not asked here, and
    the switch is not either. Each of them says a candidate may PUBLISH
    without a count; none of them says a human's verdict may move onto it, and
    the write past the push turns on the second. Let through on one of them,
    the recovery would push, finish its route with the exemption still on the
    commit the adjudication accepted, and leave the permission standing
    outstanding with nothing left to spend it.

    The delivery proof above is still taken, because it is the one answer that
    is not about licensing: a commit the record says this stage already pushed
    and this host cannot confirm holds the tick whatever a permit says.

    A refusal is handed back rather than parked or routed: nothing was
    measured, nothing was decided, and the caller owns what it means where it
    stands.
    """
    permitted = _transfer._carried_over(gate, candidate_sha)
    if not permitted:
        log.warning(
            "issue=#%d candidate %s earned no permit and its caller may "
            "publish it on nothing else; refusing rather than measuring a "
            "commit an interrupted push is already leased for",
            gate.issue.number, candidate_sha,
        )
        return _REFUSED
    log.info(
        "issue=#%d candidate %s %s; publishing it on that permit alone",
        gate.issue.number, candidate_sha, permitted,
    )
    return _verdict_owner._unmeasured_verdict(
        gate, recorded, _GateVerdict(
            held=True,
            candidate_sha=candidate_sha,
            permitted_sha=candidate_sha,
            basis=_late_gate_permission._admitted_by(""),
            delivered_pr=delivered.number,
        ),
    )


def _held_or_published(
    candidate_sha: str, held: bool,
) -> _GateVerdict:
    """One reading's answer as the verdict its caller publishes or holds by.

    The SHA travels with the go-ahead because the caller's next step is a
    push, and a push that named nothing would publish whatever the checkout
    points at when it runs.
    """
    if held:
        return _HELD
    return _GateVerdict(held=False, candidate_sha=candidate_sha)


def _moved_off_the_caller(
    gate: _Gate, recorded: LateGeneration, candidate_sha: str,
) -> bool:
    """Refuse a checkout that is not the commit its caller named.

    The caller read a head for itself -- the commit its docs pass made, the
    one its squash collapsed to, the resolution it just committed -- and this
    owner proves the checkout's head again, because everything past here is a
    claim about one object id and a caller's word is not a proof. Between the
    two reads the worktree is writable, so a commit landing in that window is
    a DIFFERENT candidate: measured here, pushed here, and recorded here,
    while the caller goes on to stamp the id it read as the one it published.

    So the two are made one decision. Asked before anything is persisted or
    pushed, because that is the whole point: a refusal after the freeze leaves
    a record about the wrong commit, and one after the push leaves the wrong
    commit on the pull request.

    A recovery names one for the same reason a run does, and proves it for a
    sharper one: no developer ran, so the reading that licensed the recovery
    is about a commit a previous tick recorded, and a head that moved between
    that proof and this one is not a fresh candidate to measure in its place.
    It is a commit an operator's authorization does not cover, published on
    its own count while the record names another.

    Silent where the caller named nothing -- a bounce over a checkout it did
    not just write -- and where the two agree, which is every ordinary tick.
    """
    if not gate.candidate or gate.candidate == candidate_sha:
        return False
    log.error(
        "issue=#%d was handed %s to publish and its checkout stands on %s; "
        "refusing to measure a candidate its caller never read",
        gate.issue.number, gate.candidate, candidate_sha,
    )
    return _parks._parked(
        gate, _records._named(gate, recorded, candidate_sha),
        _MOVED_OFF_THE_CALLER.format(
            named=gate.candidate, head=candidate_sha,
        ),
        _MOVED_OFF_THE_CALLER_PARK.format(
            mentions=config.HITL_MENTIONS,
            named=gate.candidate,
            head=candidate_sha,
        ),
    )


def _unnameable(
    gate: _Gate,
    recorded: LateGeneration,
    candidate: _measurement.FrozenCommit,
) -> _GateVerdict:
    """Park a candidate nobody could freeze, under the id it did name.

    A reading can fail with an id in hand, and the commonest one does: a
    revision that resolved and would not peel -- an object a prune took, or
    work made on a host this one is not -- comes back carrying the id it
    resolved to. That id is the only record of which commit the attempt was
    about, so it goes down with the park rather than being reported and
    dropped. Recorded, the retry asks for that exact object, the pre-tick base
    refresh holds the branch still around it, and the reconciliation ahead of
    the next spawn proves it before anything runs. Reported and dropped, none
    of those three has anything to act on: the branch is rebased under the
    park and the next reading proves whatever the checkout points at by then,
    which is how base or somebody else's work is measured and published as
    this issue's implementation.

    A revision that would not resolve at all names nothing, and there the park
    itself is the record: no pair was frozen, so nothing may be reconciled
    against one and the retry says so rather than taking a first reading of a
    head it cannot tie to this issue.
    """
    named = _records._named(gate, recorded, candidate.sha)
    if named.candidate_sha and named.candidate_sha != recorded.candidate_sha:
        _parks._persisted(gate, named)
    _parks._unmeasured(gate, named, candidate.failure, candidate.detail)
    return _HELD
