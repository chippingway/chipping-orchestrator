# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether an approval relies on verification evidence that passed and is current.

An approval reaches the approval arc -- the verify gate, the approval record,
the squash -- only when the evidence it relies on passed and is the evidence
the pull request carries now. Either way it relies on it, that is one question,
and the owner that answers it answers it again for every road that acts on the
approval later (`approved_evidence`): the claim has to name this issue's
CURRENT evidence exactly -- the same receipt, revision, and digest -- and that
evidence has to prove current again
(`verification_proof.current_evidence_verdict`): still the latest revision
spent, its handoff and artifact standing, and the whole binding about this very
subject.

What an approval relies on is what its own record says. The approval proved
is the one the pinned comment has waiting, and only where that is the one the
run returned -- of its round and subject, the same verdict the arc retires
(`handoff._Held`) -- and the claim proved is the one that record names, never
one handed in beside it: any other would carry the approval on evidence it
was never persisted relying on, or on evidence where it recorded none.

The evidence also has to be the repository's own verification: every
configured `VERIFY_COMMANDS` command among its commands, exactly as configured,
exiting 0 (`review_claims.covers_the_configuration`). A reviewer that ran
something else, however green, did not run what the repository requires of a
change, so an approval resting on it is refused like one resting on nothing.

The claim's own `passed` and `covers` are the verdict's copy of what the
evidence said when the reviewer returned, and a copy is never what an approval
rests on: they refuse the approval early where they already say no, and
otherwise the evidence answers for itself. Its pass flag is the one the proof
holds to the artifact, and its commands are the artifact's, re-read at the
comment it settled as and held to the record again -- a record whose flags say
more than the pull request shows is no approval.

Commands the reviewer ran therefore count only once their transaction has
SETTLED: posted on the pull request and made current by the reconciliation.
Recorded is not enough. A transaction still owed is a publication that stood
down, and an approval over evidence nobody could publish would carry the pull
request to `documenting` with nothing on it saying anything ran. A reuse is
held to the same record, since it is only as good as the evidence it names.

Anything short of that refuses the approval, with the words the disposition
parks it under `reviewer_unverified` with (`review_parks.parks_unverified`),
and an approval it proves reaches the approval arc (`approves`); a proof that
could not be read is no refusal, and holds the verdict for a later tick to ask
again. Last, the pinned comment is read again: whatever another road wrote
while all of that was read is carried onto the state in hand, so no write
behind this puts the older records back, and report, pull-request, verdict, or
evidence records moved there refuse the approval, which no longer rests on
what the proof was taken over.

Nothing here parks, and no live reviewer round asks it: the dormant
disposition service is its one caller to be (`review_disposition`), so live
reviewer results never pass through it.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.validating import (
    approval as _approval,
    approved_evidence as _approved_evidence,
    handoff as _handoff,
    models as _models,
    review_comment as _review_comment,
    review_verdicts as _verdicts,
)

# Why an approval relying on no claim at all is refused. Which of the refusals
# its declaration earned -- nothing declared, another commit named, a run that
# did not complete -- is the returning tick's to say: the waiting record keeps
# no copy, so a later tick names only what is true of all of them.
_NO_EVIDENCE = "nothing it declared earned verification evidence"

_RECORDS_MOVED = "the records on the pinned comment moved while it was proved"

# Why a run whose approval the pinned comment no longer has waiting is refused:
# there is no record to prove, and a verdict another road put in its place is
# not this proof's to act on.
_NOT_WAITING = "the pinned comment has no approval of its round and subject waiting"


def approves(gate, run: _models._ReviewerRun) -> str | None:
    """Hand the approval `run` returned to the arc where the evidence it records proves valid; why not where not.

    As `approval_refusal` answers: "" where the approval arc took it, over
    the gate built on `run`'s checkout, None where the proof could not be
    read, and otherwise the refusal the caller parks the approval for. The
    proof's last reading carried whatever the comment changed onto the state
    in hand, which stages nothing of its own here, so the arc is measured from
    that state: measured from an older reading, a move that reading carried
    would read as this tick's own.
    """
    refusal = approval_refusal(gate.gh, gate.spec, gate.issue, gate.state, run)
    if refusal == "":
        branch = _naming._resolve_branch_name(gate.state, gate.spec, gate.issue.number)
        _approval._finalize_validating_approval(gate, run.measured_over(gate.state.data), branch)
    return refusal


def approval_refusal(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
) -> str | None:
    """Why the approval `run` returned may not be acted on; "" where it may, None to hold.

    The approval is the one `state` has waiting where that is `run`'s, and
    the claim proved is the evidence its record names; where no approval of
    `run`'s round and subject waits, there is nothing to prove, and the
    refusal says so -- the park that answers it holds only that approval,
    so it posts and writes nothing over whatever waits instead. `state` is
    the pinned comment as the caller last read or wrote it, with nothing
    staged beside it.
    """
    waiting = _handoff._Held.of_the_approval(state, run).verdict
    refusal = _recorded_refusal(waiting)
    if refusal:
        return refusal
    refusal = _approved_evidence.refusal(gh, spec, issue, state, waiting.evidence)
    return _held_to_the_comment(gh, issue, state) if refusal == "" else refusal


def _held_to_the_comment(gh: GitHubClient, issue: Issue, state: PinnedState) -> str | None:
    """Whether the comment still carries the records the approval was proved over; None unread.

    The proof and the artifact's reread are requests long enough for another
    road to settle a later report or evidence revision, repoint the issue, or
    replace the verdict, which is on the comment and nowhere in hand -- and the
    approval arc writes the state in hand, which would put the older records
    back over it. So the comment is read again, and whatever it changed is
    carried onto the state in hand (`review_comment._records_stand`); report,
    pull-request, verdict, or evidence records among it refuse the approval.
    """
    read = dict(state.data)
    reread = _review_comment._records_stand(gh, issue, state, read, persisted=True)
    if reread is None:
        return None
    if reread.stood and not _review_comment._moved(reread.read, read, _review_comment._EVIDENCE_RECORDS):
        return ""
    return f"{_approved_evidence.MOVED}: {_RECORDS_MOVED}"


def _recorded_refusal(waiting: _verdicts.ReturnedVerdict | None) -> str:
    """Why the waiting record alone -- before anything is read -- refuses the approval, or ""."""
    if waiting is None:
        return _NOT_WAITING
    claim = waiting.evidence
    if claim is None:
        return _NO_EVIDENCE
    if not claim.passed:
        return _approved_evidence.FAILED
    if not claim.covers:
        return _approved_evidence.uncovered()
    return ""
