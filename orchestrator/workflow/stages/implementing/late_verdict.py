# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a measured candidate earns, and what the record owes on the way.

Three endings and the retirement they share. A candidate at or below the
ceiling publishes, one past it is held under the adjudication label, and a
record the publication is going past is dropped -- durably, before the effects
it licenses, because the write that ends a generation has to land ahead of the
label that hands the issue on.

Which leaves a gap the same write has to fill. Between a retirement and the
push it licenses there is committed work on the branch and, without this,
nothing on the issue saying which commit it is -- so the commit a publication
is owed goes down beside the retirement and is spent by the handoff that
carries it. An adjudication takes it back off: a candidate being decomposed is
one nobody is publishing yet.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.workflow.engine import (
    comments as _comments,
    observations as _observations,
    retiring_cycles as _retiring_cycles,
    usage as _usage,
)
from orchestrator.workflow.late_split import (
    endings as _endings,
    events as _events,
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration, LatePhase
from orchestrator.workflow.stages.implementing import (
    late_authority as _authority,
    late_consent as _consent,
    late_parks as _parks,
    late_records as _records,
)
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

def _settled(gate: _records._Gate, generation: LateGeneration) -> bool:
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
    _parks._retire_spent_park(gate.state)
    settled = _parks._measured(generation)
    if not settled.is_oversized:
        _parks._retire_authorized_park(gate.state)
        return _accepted(gate, settled)
    if not _authority._unauthorized_exemption(gate, settled.candidate_sha):
        return _routed(gate, settled)
    if not _consent._authorizes_the_park(gate, settled):
        return True
    return _authorized(gate, settled)


def _accepted(gate: _records._Gate, generation: LateGeneration) -> bool:
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
    _parks._approve(
        gate.state,
        generation.candidate_sha,
        _frozen_lease(gate),
        _parks.LateApprovalBasis.READING,
    )
    return _retired(gate, generation, _late_state.read_late_spends(gate.state))


def _authorized(gate: _records._Gate, generation: LateGeneration) -> bool:
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
    _parks._approve(
        gate.state,
        generation.candidate_sha,
        _frozen_lease(gate),
        _parks.LateApprovalBasis.AUTHORIZATION,
    )
    return _retired(gate, generation, _late_state.read_late_spends(gate.state))


def _frozen_lease(gate: _records._Gate) -> str:
    """The head an approval on the published side is pinned to.

    The retirement below takes the generation -- and the head it froze -- off
    the record, and the push it licenses has not run yet. If that push fails,
    the retry has an approved commit and no reason to measure again, so
    without this the only head left to pin to is whatever the pull request has
    become since: a head somebody moved in between would be adopted as the
    lease and force-overwritten. Carried past the retirement, the retry pins
    to what was frozen and git refuses instead.

    Empty for a call taken before anything was published, which is what makes
    the implementing seam's push take its own reading of the remote exactly as
    it always did.
    """
    if gate.entry is None:
        return ""
    return gate.entry.published_sha


def _supersedes_approval(gate: _records._Gate, candidate_sha: str) -> None:
    """Drop an approval this publication is going past.

    An approval names one commit and says that commit is owed a push. A tick
    publishing a DIFFERENT one has moved past the debt rather than paid it: a
    developer resumed on a human's guidance committed again, or an exemption
    one step over named some other commit, and the branch will not carry the
    approved commit as its tip. Left standing it would freeze this branch out
    of the ordinary base refresh for as long as the issue lives and park every
    later tick asking for a checkout back for work nobody is going to push.

    An approval naming the commit in hand is left exactly where it is: it is
    still owed, and the handoff that carries it is what spends it -- so a
    publication that parks instead comes back to a record that still says
    which commit the issue is waiting on.
    """
    approved = _parks._approved_commit(gate.state)
    if not approved or approved == candidate_sha:
        return
    log.info(
        "issue=#%d is publishing %s and no longer owes a push for approved "
        "commit %s; dropping it rather than holding the branch for work "
        "nothing is going to publish",
        gate.issue.number, candidate_sha or "a candidate it did not name",
        approved,
    )
    _parks._forget_approval(gate.state)


def _superseded(gate: _records._Gate, recorded: LateGeneration) -> bool:
    """Drop a record this publication is going past, and publish without it.

    Two roads reach it and they are the same fact. With the switch off a fresh
    candidate does not enter the gate, so the record it supersedes describes a
    commit nothing is going to publish. And an exemption is the same shape one
    step over: the commit an authorized settlement accepted publishes without being
    measured, so a generation recorded over some OTHER candidate is a record
    about work this issue has moved past.

    Leaving either would freeze the branch out of the ordinary base refresh
    for as long as the issue lives, and carry a live-looking cycle into the
    stages that close the issue -- where the guard that ends one on a close
    reads it as still running. An issue that never entered the gate has
    nothing to drop and is left exactly as it was.

    True is a close that ended the cycle instead, which the caller reads the
    same way `_accepted` does: nothing is published.
    """
    if not recorded.is_present:
        return False
    log.info(
        "issue=#%d is publishing past recorded candidate %s without measuring "
        "it; retiring cycle %d rather than leaving it over work nobody is "
        "publishing",
        gate.issue.number, recorded.candidate_sha, recorded.cycle_id,
    )
    return _retired(gate, recorded)


def _retired(
    gate: _records._Gate, generation: LateGeneration, owed: tuple = (),
) -> bool:
    """Drop this generation durably, BEFORE the publication it licenses.

    The write is the point, and it is one the caller cannot defer. What
    follows a retirement is `_on_commits`, which pushes a branch, opens a pull
    request, and moves the label to `workflow:validating` -- and the pinned
    write that would have carried the retirement comes after all of it. A tick
    that died in that window would leave a published pull request under
    `validating` over a generation that still says `measuring`: the branch
    frozen out of the base refresh for good, and a close on that issue read by
    the cancellation guard as a live cycle to end.

    So the record is dropped first and the effects follow it. The cost is one
    pinned write per candidate that publishes; what it buys is that no window
    exists in which the issue has moved on and its record has not.

    True is the answer that stops the publication: a close ended this cycle
    instead, so nothing may be pushed, opened, or handed to review on an issue
    nobody wants. It is asked in the two places a retirement can lose one. The
    latch is one -- a poll observed the close and could hand the reading to no
    worker, so no request of this tick's would show it. The retirement WRITE
    is the other and the subtler: it takes the cycle identity off the record,
    and everything that decides what a close is worth reads that identity, so
    a poll landing inside it finds an issue with nothing to end and drops the
    observation. The window advertises the cycle for exactly as long as the
    write runs, and what it saw is decided as it closes -- under the lock that
    closes it, so no interval is left for a reading to arrive unreported.

    A reading the window caught is answered by putting the generation BACK.
    It is still in this call's own memory, which is what makes that possible:
    it goes back exactly as it was and is cancelled from there, so what the
    ending reads is the cycle that actually ran rather than a refusal with no
    record under it. There is nothing to take back either -- the retirement
    runs ahead of every effect it licenses, so nothing has been published.
    """
    if _cancelled(gate, generation):
        return True
    retiring = _retiring_cycles.retiring(
        gate.spec.slug, gate.issue.number, generation.cycle_id,
    )
    with retiring.held():
        _late_state.clear_late_generation(gate.state)
        _endings.record_retired_cycle(gate.state, generation.cycle_id)
        # What an APPROVAL still owes its route, put back inside the same
        # write that dropped the generation carrying it. Empty for every
        # other retirement: a superseded or adjudicated generation's
        # obligations belong to a candidate nothing is going to publish.
        _late_state.write_late_spends(gate.state, owed)
        gate.gh.write_pinned_state(gate.issue, gate.state)
    if not retiring.observed:
        return False
    log.warning(
        "repo=%s issue=#%d was observed closed inside the write retiring "
        "cycle %d; putting it back so the cancellation has something to end",
        gate.spec.slug, gate.issue.number, generation.cycle_id,
    )
    _marked(gate, generation)
    return True


def _cancelled(gate: _records._Gate, generation: LateGeneration) -> bool:
    """End this cycle where a close is already latched against the issue.

    Asked before the retirement rather than after, because the retirement is
    what makes the reading unanswerable: once the identity is off the record
    there is no cycle for the ending to be entered from, and the receipt a
    poll left on the thread has nothing to be adopted against.

    The mark is durable before it is reported, and it is the same mark the
    adjudication's own barriers write -- the cleanup that settles a cancelled
    cycle reads this record and cannot tell which barrier put it there.
    """
    if not generation.is_present or generation.cancelled:
        return False
    if not _observations.close_observed(gate.spec.slug, gate.issue.number):
        return False
    log.warning(
        "repo=%s issue=#%d was observed closed as its measured candidate was "
        "about to publish; ending cycle %d rather than pushing a branch and "
        "opening a pull request on an issue nobody wants",
        gate.spec.slug, gate.issue.number, generation.cycle_id,
    )
    _marked(gate, generation)
    return True


def _marked(gate: _records._Gate, generation: LateGeneration) -> None:
    """Record this cycle cancelled, then report it, in that order.

    Nothing is owed a publication on a cancelled cycle, so the commit an
    approval had recorded goes with it -- including one this very call is
    reinstating a generation over. Left standing it would freeze the branch
    out of the base refresh for as long as the issue lives and park a later
    tick asking for a checkout back for work nobody is going to push.
    """
    cancelled = replace(
        generation.cancel(_usage._now_iso()),
        phase=LatePhase.CANCELLING,
        owner_check_pending=False,
    )
    _parks._forget_approval(gate.state)
    _late_state.write_late_generation(gate.state, cancelled)
    _endings.clear_retired_cycle(gate.state)
    gate.gh.write_pinned_state(gate.issue, gate.state)
    _parks._emit(
        gate, cancelled,
        _events.LateEvent(family=_events.LateEventFamily.CANCELLATION),
    )


def _routed(gate: _records._Gate, generation: LateGeneration) -> bool:
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
    _parks._forget_approval(gate.state)
    _parks._retire_superseded_park(gate.state)
    _spent(gate)
    _parks._persisted(gate, generation)
    _comments._post_issue_comment(
        gate.gh, gate.issue, gate.state, _routed_notice(generation),
    )
    gate.gh.write_pinned_state(gate.issue, gate.state)
    gate.gh.set_workflow_label(gate.issue, WorkflowLabel.DECOMPOSING)
    return True


def _unmeasured_verdict(
    gate: _records._Gate,
    recorded: LateGeneration,
    admitted: _records._GateVerdict = _records._HELD,
) -> _records._GateVerdict:
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
    _parks._retire_spent_park(gate.state)
    _supersedes_approval(gate, admitted.candidate_sha)
    if _superseded(gate, recorded):
        return _records._HELD
    _parks._retire_authorized_park(gate.state)
    _owed_by_an_unmeasured_push(
        gate, admitted.candidate_sha, _frozen_lease(gate), admitted.basis,
    )
    return replace(admitted, held=False)


def _owed_by_an_unmeasured_push(
    gate: _records._Gate, candidate_sha: str, lease: str, basis: str = "",
) -> None:
    """Name the commit an unmeasured publication owes a push for, durably.

    The measured road records this beside its retirement, and a candidate that
    skipped the reading owes it just as much: nothing was frozen for it, so
    past this call the only account of the work is the commit on the branch.
    A tick that died between here and the push comes back to an issue with no
    generation, no debt, and a pull request that may or may not have received
    it -- and the stage below runs from there, spawning an agent over work
    nobody can say is unpublished.

    Recorded, the reconciliation ahead of every handler finds the debt first,
    republishes the same commit against the same head, and closes what the
    route owed in the receipt's own write -- so the stage behind it runs over
    the world the dead tick would have handed it.

    What the route still owes rides the same write, because the recovery has
    no run behind it to re-derive a reviewer round, a consumed fix batch, or a
    docs receipt from. The debt and the obligations are spent together by the
    push that pays them.

    A debt this issue ALREADY carries for the commit is left exactly as it
    is. It was granted by an earlier tick against a head that tick froze, and
    the head read now is precisely the move its lease exists to refuse -- so
    re-leasing it here would repair a half-written approval by pinning it to
    the present, which is the one substitution the refusal behind it forbids.
    An approval naming some other commit is gone by this point, dropped by the
    supersession a line above.

    Written only where the push will MOVE the publication. A pull request
    already standing on the commit has nothing to receive, so there is no
    window to survive -- and a debt written there would be paid by a
    republication that closes a round the tick which really published it
    already closed. A call taken before anything was published names no head
    at all, and the initial publication owns that window itself.

    The lease is handed IN rather than read off the entry, because the entry
    is not the only road to one. Where the switch keeps a candidate out of the
    gate nothing freezes a publication, and the head the push is pinned to is
    the CALLER's own reading of the remote -- so the debt is recorded against
    that instead. What the switch decides is the measurement; the account of
    what a push is putting where is not its to turn off.
    """
    if _stages_unmeasured_debt(gate, candidate_sha, lease, basis):
        gate.gh.write_pinned_state(gate.issue, gate.state)


def _stages_unmeasured_debt(
    gate: _records._Gate, candidate_sha: str, lease: str, basis: str = "",
) -> bool:
    """Put the debt an unmeasured push owes in memory, and say whether it did.

    The rule above without the write, so an owner that has its OWN write to
    make can carry the debt out on it rather than one behind it. The two are
    not interchangeable orderings of the same thing: a record that LICENSES a
    rewritten commit to publish is the account of what the branch carries, and
    the debt is the account of where it has still to go -- split
    across two writes, a process dying between them comes back to a branch the
    record explains and no debt naming the push it is still owed, and the
    reconciliation that would have finished it never runs.

    Answering rather than writing is also what keeps the caller's write
    honest: an owner that staged nothing has nothing of this to make durable
    and says so, instead of spending a request on a comment it did not change.

    What the debt RESTS on is handed DOWN from the answer that admitted the
    candidate rather than re-derived here, and that difference is the whole of
    it. A commit an exemption and an authorization both vouch for leaves a
    debt that may be spent only while that authorization can still be read --
    but proving one is a git reading, and a second reading is a second chance
    to fail. Re-asked here, a store that stopped answering between the gate's
    proof and this write would record an operator's bypass as ordinary
    unmeasured debt, and the tick after a crash would spend it without asking
    anyone. Handed down, the record says what the gate actually decided on.

    A road that carried nothing records the ordinary unmeasured basis, and so
    does a value from outside this build's own vocabulary: what a caller
    cannot name is not a claim the record may carry. That is every other road
    here -- a rewrite permit, a supersession the switch let past, a receipt
    the remote already carries -- each a record this workflow made for itself
    and re-derives on the next tick.
    """
    if _parks._approved_commit(gate.state) == candidate_sha:
        return False
    if not lease or lease == candidate_sha:
        return False
    log.info(
        "issue=#%d is publishing unmeasured candidate %s onto a pull request "
        "standing at %s; recording the debt before the push that pays it",
        gate.issue.number, candidate_sha, lease,
    )
    admitted = _parks.LateApprovalBasis.UNMEASURED
    if basis in tuple(_parks.LateApprovalBasis):
        admitted = _parks.LateApprovalBasis(basis)
    _parks._approve(gate.state, candidate_sha, lease, admitted)
    _late_state.write_late_spends(gate.state, gate.spends.fields)
    return True


def _spent(gate: _records._Gate) -> None:
    """Close the route bookkeeping this hold's caller will never get to.

    Written here rather than by the caller because of what comes next: the
    relabel below hands the issue to the adjudication, and a caller that
    counted afterwards would lose the count to any crash in that window --
    with nothing going back for it, since an authorized settlement publishes the
    accepted commit and the resumed stage finds nothing left to push.

    Only the ROUTED hold spends. A reading nobody could take also stops the
    tick with a generation on the pinned comment, and that one is a park: the
    developer's work is still pending and its round is not spent.
    """
    _records._spend(gate.state, gate.spends)


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
