# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settle the size verdict, approve accepted work, or route oversized work to adjudication.

Measured and unmeasured verdicts retire their answered parks, account for
route spends, and coordinate generation retirement with publication debt.
Routing records the unpublished candidate before its notice and relabel.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.workflow.engine import (
    comments as _comments,
)
from orchestrator.workflow.late_split import (
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_approval_state as _late_approval_state,
    late_authority as _authority,
    late_consent as _consent,
    late_measurement_state as _late_measurement_state,
    late_park_retirement as _late_park_retirement,
    late_park_state as _late_park_state,
    late_verdict_debt as _late_verdict_debt,
    late_verdict_retirement as _late_verdict_retirement,
)
from orchestrator.workflow.stages.implementing.late_approval_reading import LateApprovalBasis
from orchestrator.workflow.stages.implementing.late_gate_models import _HELD, _Gate, _GateVerdict
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_ROUTED_NOTICE = (
    ":triangular_ruler: this issue's committed implementation adds "
    "{additions} lines against a ceiling of {threshold}, so it is being "
    "adjudicated for its size before anything is published. Nothing has been "
    "pushed and no pull request carries it -- the commit `{candidate}` stays "
    "exactly where it is while `{label}` decides whether it ships as one "
    "change or becomes child issues."
)

# The same hold where a pull request already carries the work. What the notice
# may not repeat is the sentence above it: something HAS been pushed, and a
# reader told otherwise would go looking for a branch that is on the remote.
# What it says instead is the number the count is about -- everything the pull
# request would come to once this commit joined it -- and the head it is still
# standing on, so the diff a human opens to check the reading is the one the
# adjudication is about.
_ROUTED_ON_PUBLICATION_NOTICE = (
    ":triangular_ruler: pushing `{candidate}` would take this issue's pull "
    "request #{pull_request} to {additions} added lines against a ceiling of "
    "{threshold}, so it is being adjudicated for its size before that push. "
    "Nothing was pushed -- the pull request still stands on `{published}` and "
    "the commit stays exactly where it is while `{label}` decides whether it "
    "ships as one change or becomes child issues."
)

def _settled(gate: _Gate, generation: LateGeneration) -> bool:
    """What a measured candidate earns: adjudication, or the ordinary push.

    Strictly past the ceiling, which is the record's own comparison: a
    candidate exactly at the configured value publishes, so the trigger cannot
    move by one line when the threshold is retuned. That boundary is the same
    one for every candidate here, an adjudicated one included: a commit an
    exemption names and no operator authorization stands behind is measured
    like any other, and one that comes back at or below the ceiling publishes
    on the count exactly as it always did.

    An oversized one is held, and only WHERE differs. A candidate nothing has
    ruled on goes to the adjudication. One an exemption already names has been
    ruled on -- what it is missing is the human, not the verdict -- so sending
    it back would pay for a second adjudicator over an answered question and
    risk a `split` cutting children out of work somebody decided ships whole.
    It waits for the authorization instead, which `late_consent` owns: the
    park, the command that ends one, and the answer a command naming another
    commit earns. A count the ceiling lets through takes that park down on its
    way into the retirement's own durable write, because what the park waits
    for is a person and this reading says no person was ever needed:
    published under a record still saying a human holds the issue, the commit
    would have the source stage stop on its parked road every poll after. A
    candidate that command DID name publishes down the accepted road's own
    retirement rather than one of its own, so the generation is retired ahead
    of the effects it licenses exactly as it is for every other publication.

    A count in hand is what a measurement park was waiting for, so this is
    where one is retired -- here and at the unmeasured verdict beside it, and
    nowhere earlier. Retired on the way INTO the gate instead, a tick that
    went on to lose the reading again would leave an issue durably unparked
    with nothing measured and nothing said: the reading a human was told
    about is still the reading nobody has taken.

    The record of what that park SAID goes with the flag, and it goes here
    for the same reason: every step a reading can stop at is behind this line,
    so the member describes a refusal that is over. It is dropped before the
    record is settled on rather than after, because an oversized candidate's
    record survives the settlement to be adjudicated from -- and a step a
    human was told about, carried into an adjudication where nothing is
    refusing anything, is a sentence the announce-once guard would read as
    still standing on a thread whose park this very verdict retired.
    """
    _late_park_retirement._retire_spent_park(gate.state)
    settled = _late_measurement_state._measured(generation)
    if not settled.is_oversized:
        _late_park_retirement._retire_authorized_park(gate.state)
        return _accepted(gate, settled)
    if not _authority._unauthorized_exemption(gate, settled.candidate_sha):
        return _routed(gate, settled)
    if not _consent._authorizes_the_park(gate, settled):
        return True
    return _authorized(gate, settled)


def _accepted(gate: _Gate, generation: LateGeneration) -> bool:
    """Retire the generation a small candidate never needed, and publish.

    The debt it leaves is recorded as this gate's own READING, which is what
    makes spending it a repeat rather than a bypass: the count came back at or
    below the ceiling, so nobody's permission was involved and the tick that
    comes back after a crash owes nobody a question before it pushes. The
    owner granting an approval is the only one that can say that, which is why
    the basis is written here rather than inferred by whoever reads it.

    The record is dropped rather than left standing, and it has to be: a
    frozen candidate freezes this branch out of the ordinary base refresh, and
    a generation carried into the stages that close the issue is one a later
    guard reads as a live cycle a close should end.

    What outlives the drop is which cycle it was, which COMMIT is still owed
    a publication, and what the route that owes it has still to close. The
    cycle is what a close a poll observes inside this very window is adopted
    against, and what the next candidate on this issue mints its own cycle
    after, so no two attempts ever answer to the same number.

    The commit is the other half, and it rides the same write for the same
    reason: past the retirement nothing else on the issue names the work, and
    the push that carries it has not run yet. A tick that died in between
    would leave a branch with an unpublished commit on it and a record that
    has forgotten which one -- so a replacement host, which rebuilds the
    checkout from the base or the plan pull request, would find a head nothing
    contradicted and publish that instead. Recorded, the same host finishes
    the publication and a host without the commit parks for it.

    What the caller's route still OWES rides it too, and for the same window.
    The obligations were frozen with the pair -- the reviewer round a fix
    spends, the bookmarks a consumed batch clears, the head a finished docs
    pass produced -- and dropping them with the generation would leave the
    only tick that can pay this debt unable to close any of it: the push that
    licenses the caller's own tail fails, the caller parks, and the retry that
    lands the commit has no run behind it to re-derive a round from. Carried
    past the retirement, that retry closes exactly what the tick that approved
    the candidate would have.
    """
    log.info(
        "issue=#%d candidate %s adds %d lines against a ceiling of %d; "
        "publishing it as one change",
        gate.issue.number, generation.candidate_sha, generation.additions,
        generation.threshold,
    )
    _late_approval_state._approve(
        gate.state,
        generation.candidate_sha,
        _late_verdict_debt._frozen_lease(gate),
        LateApprovalBasis.READING,
    )
    return _late_verdict_retirement._retired(gate, generation, _late_state.read_late_spends(gate.state))


def _authorized(gate: _Gate, generation: LateGeneration) -> bool:
    """Retire the generation an operator authorized past the ceiling, and publish.

    The same close-safe retirement a small candidate earns, on the one road
    that reaches a publication without going through it. The count here really
    was this gate's own -- the pair frozen, the diff read, the ceiling
    compared -- so everything the retirement exists for is true of it: a
    generation left standing freezes this branch out of the ordinary base
    refresh for as long as the issue lives, and is read as a live cycle by the
    guard that ends one on a close.

    What the debt REST on is the difference, and it is the reason this is not
    `_accepted` with another argument. That road's approval says the ceiling
    let the commit through, so the tick that comes back after a crash owes
    nobody a question before it pushes. This one says a person did, which is a
    permission that has to still be readable when it is spent -- so the basis
    goes down as `AUTHORIZATION` and the readers that revalidate a debt an
    operator's gesture is behind can tell the two apart.

    True stops the publication, as it does everywhere else: a close ended this
    cycle inside the write, so nothing is pushed, opened, or handed on.
    """
    log.info(
        "issue=#%d publishes candidate %s at %d lines past a ceiling of %d "
        "on an operator's own authorization; retiring cycle %d ahead of it",
        gate.issue.number, generation.candidate_sha, generation.additions,
        generation.threshold, generation.cycle_id,
    )
    _late_approval_state._approve(
        gate.state,
        generation.candidate_sha,
        _late_verdict_debt._frozen_lease(gate),
        LateApprovalBasis.AUTHORIZATION,
    )
    return _late_verdict_retirement._retired(gate, generation, _late_state.read_late_spends(gate.state))


def _routed(gate: _Gate, generation: LateGeneration) -> bool:
    """Hand an oversized candidate to the adjudication, publishing nothing.

    The measurement is made durable first, because the label is what makes
    another handler read this issue: a tick that dies between the two leaves a
    live oversized generation under `workflow:implementing`, which the
    dispatcher's own relabel guard puts back where the adjudication left it.
    The reverse order would hand the coordinator an issue whose record cannot
    say what is being adjudicated.

    Nothing is pushed and no pull request is opened. The commit stays in the
    developer's worktree, which is where the adjudicator reads it and where a
    settlement that publishes it unsplit would publish it from.
    """
    log.warning(
        "issue=#%d candidate %s adds %d lines against a ceiling of %d; "
        "holding it unpublished and routing it to %s",
        gate.issue.number, generation.candidate_sha, generation.additions,
        generation.threshold, WorkflowLabel.DECOMPOSING,
    )
    # Whatever commit this issue was owed a publication for, it is not owed
    # one now: the branch carries a candidate under adjudication, and the
    # record naming it is what the coordinator reconciles from here. Left
    # standing, an approval this candidate was committed on top of would hold
    # the branch out of the base refresh for the whole adjudication and park
    # every later tick on a host that no longer has that commit.
    _late_approval_state._forget_approval(gate.state)
    _late_park_retirement._retire_superseded_park(gate.state)
    _late_verdict_debt._spent(gate)
    _late_park_state._persisted(gate, generation)
    _comments._post_issue_comment(
        gate.gh, gate.issue, gate.state, _routed_notice(generation),
    )
    gate.gh.write_pinned_state(gate.issue, gate.state)
    gate.gh.set_workflow_label(gate.issue, WorkflowLabel.DECOMPOSING)
    return True


def _unmeasured_verdict(
    gate: _Gate,
    recorded: LateGeneration,
    admitted: _GateVerdict = _HELD,
) -> _GateVerdict:
    """Publish a candidate this gate did not measure -- unless a close beat it.

    The three ways past the measurement, and they share the step that is easy
    to miss: a record may still be standing. The switch being off does not
    retire what an earlier tick froze, and an exemption names one commit
    rather than ending the generation that granted it -- so the retirement
    that has to land before the push runs here too, and with it the close
    protocol it carries. Held is the answer where a close ended the cycle: an
    issue nobody wants gets no branch, no pull request, and no relabel.

    An approval naming some OTHER commit is the same problem one field over,
    and it is dropped for the same reason: the debt it records is for a commit
    this publication is going past, and a record left over work nothing will
    push freezes the branch and parks every later tick asking for it back.

    What goes down in its place is the debt THIS publication is about, for the
    reason the measured road records one: a candidate that skipped the reading
    froze no generation either, so between here and the push there is
    committed work on the branch and nothing on the issue naming it.

    A measurement park still standing is retired here for the reason the
    measured road retires one: this commit is going out, so whatever an
    earlier reading could not answer about it is answered now. Carried past
    this, it reaches the stage the publication hands the issue to as a flag
    describing a question nobody is waiting on.

    The authorization park comes off too, and it comes off LATER -- past every
    refusal above, on the line the verdict is decided. This is the only road
    that ever publishes under one: the override an earlier tick recorded
    answers the park's own question before the gate's door is reached, so
    nothing here reads the thread and nothing else on the road would take the
    flag down. But what that park waits for is a PERSON, and no reading
    answers a person -- so a close that ended the cycle, or a record this
    publication is superseded by, has to leave the operator waiting exactly as
    it found them rather than unparking an issue nobody replied to.

    `admitted` is the answer its caller reached, handed in whole rather than
    as loose terms: every field on it is something only that caller knows, and
    what comes back is the same answer with the hold taken off. The default is
    the empty one, which is the road that proved no commit at all.

    `basis` on it says what ADMITTED the candidate, and only the answer that
    admitted it can say. Any road that re-asked here would be taking the proof
    a SECOND time, and a proof that succeeded at the gate and fails a moment
    later -- a store that stopped answering in between -- would record an
    operator's bypass as ordinary unmeasured debt, which the tick after a
    crash spends without asking anyone.

    `permitted_sha` is handed straight back rather than derived, because
    only the caller knows which of the roads past the measurement this is. A
    transfer's is the one road whose publication may MOVE a human's verdict,
    and the write past the push has to be able to tell it from every other
    road that publishes the very same commit -- an exemption already naming
    it, an approval owed a push for it, a receipt that already went out.

    `delivered_pr` is carried for the same reason and pins two things the seam
    behind this would otherwise resolve for itself: the lease its push is held
    to, which is that very commit, and the pull request its bookkeeping
    belongs to. Both are what the proof that admitted the candidate was ABOUT,
    and a seam that looked either up again could push over a tip that moved
    since or open a second pull request where this one closed since.
    """
    _late_park_retirement._retire_spent_park(gate.state)
    _late_verdict_debt._supersedes_approval(gate, admitted.candidate_sha)
    if _late_verdict_retirement._superseded(gate, recorded):
        return _HELD
    _late_park_retirement._retire_authorized_park(gate.state)
    _late_verdict_debt._owed_by_an_unmeasured_push(
        gate, admitted.candidate_sha, _late_verdict_debt._frozen_lease(gate), admitted.basis,
    )
    return replace(admitted, held=False)


def _routed_notice(generation: LateGeneration) -> str:
    """What the hold tells the thread, on the side of publication it is on.

    The record is what decides, rather than the caller: a generation carrying
    the publication group was entered on work the remote already has, and one
    without it was entered before anything went out. Read off the group as a
    whole, so a half-damaged one describes the hold it can actually vouch for
    instead of naming a pull request the record cannot show.
    """
    if not generation.has_publication_context:
        return _ROUTED_NOTICE.format(
            additions=generation.additions,
            threshold=generation.threshold,
            candidate=generation.candidate_sha,
            label=WorkflowLabel.DECOMPOSING,
        )
    return _ROUTED_ON_PUBLICATION_NOTICE.format(
        additions=generation.additions,
        threshold=generation.threshold,
        candidate=generation.candidate_sha,
        pull_request=generation.published_pr_number,
        published=generation.published_sha,
        label=WorkflowLabel.DECOMPOSING,
    )
