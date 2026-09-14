# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a recovery proves about a recorded pair before it acts on one.

The refusals the paths with no developer behind them are held to. A tick
answering a reading a previous one recorded cannot take the checkout on trust:
the worktree has to be there, both recorded commits readable in it, and the
head actually ON the candidate -- because nothing here produced the work, so
anything else in the checkout is not this issue's answer to substitute in.

The head is what every one of these proves, never the object on its own. An
object store outlives the branch that put a commit in it: a worktree rebuilt
from the base or reset onto it, on the very host that made the commit, still
holds the object while standing somewhere else entirely. So "is it here" is a
question that answers yes about a checkout carrying none of the work -- which
reads downstream as a branch with nothing to publish, and buys a second
developer run for an implementation that is already written.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models, settings as config
from orchestrator.git.measurement import (
    commits as _measurement_commits,
    models as _measurement_models,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_freeze as _freeze,
    late_parks as _parks,
    late_records as _records,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_HEAD = "HEAD"

_MISSING_CANDIDATE_PARK = (
    "{mentions} the committed implementation this issue recorded (`{candidate}"
    "`) is not on this host: its worktree is gone, so the exact commit that "
    "was frozen cannot be measured or published from here. Nothing was re-run "
    "and nothing was published -- the recorded commit is the evidence, and "
    "whatever a fresh checkout would contain is not it. Restore the worktree "
    "at that commit and reply `/orchestrator continue`, or close the issue if "
    "the work is gone for good."
)

_MISSING_CHECKOUT_PARK = (
    "{mentions} the worktree this issue's committed implementation lives in "
    "is gone, and no commit was ever frozen for it -- the reading that would "
    "have recorded one is the step that failed. So there is nothing here to "
    "measure and nothing to publish, and nothing was re-run. Restore the "
    "checkout carrying the work and reply `/orchestrator continue`, or close "
    "the issue if the work is gone for good."
)

_UNPUBLISHED_COMMIT_PARK = (
    "{mentions} this issue is waiting to publish the commit its size gate "
    "approved (`{approved}`), and its worktree is on `{head}` -- so nothing "
    "was published and no developer was started. The approved commit is the "
    "evidence: what a rebuilt or reset checkout stands on is the base or the "
    "plan pull request rather than the implementation, and a fresh run would "
    "answer with different work. Put the worktree back on `{approved}` and it "
    "publishes by itself on the next tick, with nothing re-run and no agent "
    "spawned; or reply with the change you want made and the developer is "
    "resumed against it."
)

_UNNAMED_CANDIDATE_PARK = (
    "{mentions} no commit was ever frozen for this issue -- the reading that "
    "would have recorded which one its committed implementation is is the "
    "step that failed -- so there is no pair here to re-measure and nothing "
    "was re-run. A first reading of whatever the checkout points at now is "
    "not the reading you asked for: a rebased, reset, or rebuilt worktree "
    "stands on the base, and publishing that would open a pull request over "
    "work nobody wrote. Reply with the change you want made and the developer "
    "is resumed against it, or close the issue if the work is gone."
)

_MOVED_HEAD_PARK = (
    "{mentions} this issue's worktree is no longer on the commit that was "
    "frozen for it (`{recorded}`), so there is nothing here to re-measure: a "
    "retry reads the exact pair that was recorded, and whatever the checkout "
    "points at now is not it. Nothing was re-run and nothing was published. "
    "Put the worktree back on that commit and reply `/orchestrator continue`, "
    "or reply with the change to make and the developer is resumed against it."
)

def _holds_missing_candidate(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    worktree: Path,
) -> bool:
    """Say the recorded candidate is not on this host, and stay parked.

    The answer a trusted continue earns where the checkout the commit lives in
    is gone. It is still late-measurement reconciliation and it still owns the
    tick: handing it to the generic parked-continue classifier would refuse
    the command as one carrying no guidance -- which is the wrong thing to
    tell an operator whose command is exactly the right one, and which
    consumes their reply against a question nobody asked.

    What it may not do is re-run the developer. The recorded commit is the
    evidence, a fresh run would produce different work, and the way back is
    the worktree -- so the park says so and is retried by the next continue.

    What it says depends on whether a commit was ever frozen. A refusal taken
    before the first freeze -- the candidate would not prove, so there was
    nothing to record -- reaches the same park through the same retry, and a
    sentence naming a commit that was recorded would be describing a record
    the issue does not carry. The identity is minted for the report either
    way, so the failure is on both sinks in both cases rather than refused for
    a generation the sinks cannot correlate.
    """
    gate = _records._gate(gh, spec, issue, state, worktree)
    recorded = _late_state.read_late_generation(state)
    return _parks._parked(
        gate,
        _records._reportable(gate, recorded),
        _measurement_models.MeasurementFailure.CANDIDATE_ABSENT,
        _missing_candidate_park(recorded),
    )


def _missing_candidate_park(recorded: LateGeneration) -> str:
    """What a checkout that is gone is worth telling a human, either way."""
    if recorded.candidate_sha:
        return _MISSING_CANDIDATE_PARK.format(
            mentions=config.HITL_MENTIONS, candidate=recorded.candidate_sha,
        )
    return _MISSING_CHECKOUT_PARK.format(mentions=config.HITL_MENTIONS)


def _holds_moved_candidate(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    worktree: Path,
) -> bool:
    """Refuse a no-agent retry whose checkout is not the recorded commit.

    What a trusted bare continue buys is a re-reading of the EXACT pair that
    was recorded, and nothing else: no agent ran, so a head that is somewhere
    else is not work this workflow produced. Measuring it would answer the
    size question about a commit nobody froze, and publishing it -- which is
    what the switch being off would do -- would push a branch no reading
    covers.

    A park that named NO commit is refused for the same reason and more
    flatly: there is no pair to re-read, so what a retry would take is a
    FIRST reading, of whatever the checkout points at by then. Nothing ties
    that head to this issue -- a rebase, a reset, a rebuilt worktree all leave
    one -- so a base with no work on it, or somebody else's, would be measured
    and published as this implementation. The way on from there is the
    developer, which is what guidance buys; a bare continue is answered by
    saying no reading exists to take again.

    The comparison is by NAME rather than by proof, because "is the checkout
    still on it" and "can this host read it" are two questions and only the
    first is this one's. A head naming the recorded commit is handed on even
    where the object cannot be peeled, so the refusal that follows says the
    object is missing rather than that the checkout moved.

    The ordinary disposition is deliberately not held to any of this. There a
    head that moved past the record IS a developer who was resumed and
    committed again, and a fresh candidate is exactly the right reading of it.
    """
    recorded = _late_state.read_late_generation(state)
    head = _measurement_commits._prove_candidate_commit(worktree, _HEAD)
    if recorded.candidate_sha and head.sha == recorded.candidate_sha:
        return False
    log.error(
        "issue=#%d was asked to re-measure recorded candidate %r, but its "
        "worktree is on %s; parking rather than reading a pair nobody froze",
        issue.number, recorded.candidate_sha, head.sha or head.failure,
    )
    gate = _records._gate(gh, spec, issue, state, worktree)
    return _parks._parked(
        gate, _records._reportable(gate, recorded),
        _measurement_models.MeasurementFailure.CANDIDATE_UNREADABLE,
        _moved_head_park(recorded),
    )


def _moved_head_park(recorded: LateGeneration) -> str:
    """What a retry that cannot read its own pair is worth telling a human.

    Which sentence depends on whether a commit was ever named. A park that
    froze one asks for the checkout back on it, and the next bare continue
    re-reads exactly that pair. A park that froze none has no pair to promise,
    so it may not name one and may not offer that retry: what it asks for is
    guidance, which resumes the developer over work judged the ordinary way.
    """
    if recorded.candidate_sha:
        return _MOVED_HEAD_PARK.format(
            mentions=config.HITL_MENTIONS,
            recorded=recorded.candidate_sha,
        )
    return _UNNAMED_CANDIDATE_PARK.format(mentions=config.HITL_MENTIONS)


def _holds_absent_candidate(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    worktree: Path,
) -> bool:
    """Park a recorded candidate whose object this checkout cannot show.

    The pre-spawn question, and the one window that needs it: a tick that
    persisted the frozen pair and died before counting it leaves a record with
    no park beside it, so nothing stops the next tick from treating the issue
    as ordinary work. On the host that froze it that is harmless -- the
    commits are there and the gate measures them again. On another one the
    checkout is rebuilt at base, the recorded commit is nowhere, and the
    ordinary flow would pay for a SECOND developer against an issue whose
    first one already finished.

    So the object is proved before anything spawns, and a host that does not
    hold it parks rather than starting over. What the park asks for is the
    worktree, not another run: the recorded commit is the evidence, and a
    fresh one would be different work.
    """
    recorded = _late_state.read_late_generation(state)
    proved = _measurement_commits._prove_candidate_commit(
        worktree, recorded.candidate_sha,
    )
    if proved.is_frozen:
        return False
    log.error(
        "issue=#%d records candidate %s, which this host cannot read; "
        "parking rather than starting a second developer over it",
        issue.number, recorded.candidate_sha,
    )
    gate = _records._gate(gh, spec, issue, state, worktree)
    return _parks._parked(
        gate, _records._reportable(gate, recorded), proved.failure,
        _missing_candidate_park(recorded),
    )


def _holds_absent_base(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    worktree: Path,
) -> bool:
    """Park a recorded base whose object this checkout cannot show.

    The other end of the pre-spawn proof, and it fails differently from the
    candidate: the candidate is what a publication would push, and the base is
    what the count is taken against. A host holding one and not the other can
    neither measure the pair nor defend a verdict over it, and asking the
    remote for a base instead would answer with wherever the branch has moved
    to -- measuring a different pair under the same generation.

    False where no base is recorded at all. A freeze that got as far as the
    candidate and no further has nothing to prove here, and the reconciliation
    behind this takes a fresh one.

    A record too damaged to act on, or one recorded against another issue,
    parks here rather than having its base retried, and the proof that says so
    is the reused pair's own. It matters most on this road: nothing has
    checked the record yet -- the gate that would is behind the spawn this
    call exists to come before -- and the retry is durable, so a record
    adopted here would be publishable under this issue's identity as soon as
    the base came back.
    """
    recorded = _late_state.read_late_generation(state)
    if not recorded.base_sha:
        return False
    gate = _records._gate(gh, spec, issue, state, worktree)
    return _freeze._refrozen_base(gate, recorded) is None


def _holds_unpublished_commit(
    gh: GitHubClient, issue: Issue, state: PinnedState, worktree: Path,
) -> bool:
    """Prove the commit this issue owes a publication is here, or park.

    The last window the recorded pair cannot cover, and the one every
    approval opens. Anything that lets a candidate publish drops the record
    that named it -- the retirement a small candidate earns, and the
    exemption an authorized settlement writes -- and the push comes after
    that write. A tick that died in between leaves committed work on the
    branch with nothing on the issue waiting for anything, so the ordinary
    flow runs: on a replacement host the checkout is rebuilt from the base or
    the plan pull request, and the head it lands on is published as the
    implementation or handed to a second developer over work the first one
    already finished.

    The approved commit is what closes it, and the proof is taken AFTER the
    checkout has been restored rather than before. That order is what tells
    the two hosts apart: a branch whose commit was already pushed carries it
    back with it and passes, while one whose commit never left the dead host
    cannot -- and only the second is a park.

    What is proved is the HEAD, not the object. Holding the commit says only
    that the store was never pruned, and the store outlives the branch: a
    worktree rebuilt from the base or from the plan pull request on the very
    host that made the commit still has the object sitting in the shared
    object store it was fetched into. Asking for the object there answers yes
    while the checkout stands on something else entirely -- and a branch with
    no commits ahead of base reads as an issue with nothing to publish, so the
    tick would go on to buy a second developer run for an implementation that
    is already written.

    What the park asks for is the worktree, never another run. Nothing here
    produced the commit, a fresh run would produce different work, and the
    recovery that answers it is the checkout coming back: it is the same park
    the handoff takes on a checkout that moved, and the same quiet
    republication settles it -- while a human who wants the work changed
    instead replies with guidance, exactly as they would to that one.
    """
    approved = _payloads.as_hex(
        state.get(_state._APPROVED_SHA), _formats.COMMIT_LENGTHS,
    )
    if not approved:
        return False
    head = _measurement_commits._prove_candidate_commit(worktree, _HEAD)
    if head.is_frozen and head.sha == approved:
        return False
    log.error(
        "issue=#%d owes a publication for approved commit %s and its "
        "worktree is on %s; parking rather than publishing or re-running "
        "over a checkout that is not the one the gate approved",
        issue.number, approved, head.sha or head.failure,
    )
    _guards._park_awaiting_human(
        gh, issue, state,
        _UNPUBLISHED_COMMIT_PARK.format(
            mentions=config.HITL_MENTIONS,
            approved=approved,
            head=head.sha or "an unreadable head",
        ),
        reason=_state._CANDIDATE_MOVED,
    )
    state.set(_state._PARK_REASON, _state._CANDIDATE_MOVED)
    return True
