# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read pending rewrite permissions and their existing operator authorization.

Only an authorized outstanding permission names a recoverable rewrite.
A damaged claim cannot be overwritten as a grant, and a standing grant
must agree with the fingerprint taken by this reading.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.stages.implementing import (
    late_authority as _authority,
    late_gate_models as _late_gate_models,
)

_UNAUTHORIZED_EXEMPTION = (
    "no operator authorization stands behind the exemption for `{accepted}`"
)

_UNREADABLE_AUTHORIZATION = (
    "this issue already claims a transfer onto the commit it exempts and the "
    "record of it is not one this build can read"
)

_DISAGREEING_AUTHORIZATION = (
    "the permission standing here records `{recorded}` as the contribution it "
    "was granted over and this reading takes `{recomputed}`"
)


def _outstanding_rewrite(
    state: PinnedState, candidate_sha: str,
) -> _rewrite_values.LateRewrite | None:
    """The rewrite a standing permission still licenses for this commit.

    What a tick with no evidence of its own is answered from. A permission is
    written before the push and spent by the receipt behind it, so one left at
    `authorized` names a rewrite whose push has not been accounted for -- and
    the commit it names is exactly the one an approval is owed a push for.
    Handed back, the permit is re-asked over the terms it was granted on
    rather than assumed from the approval's bare object id.

    None for anything else: a comment carrying no permission, one this build
    cannot read whole, one already spent, and one naming some other commit.
    Each of those leaves the candidate to the ordinary cumulative gate, which
    is the answer a rewrite nobody can revalidate has to get.
    """
    authorization = _rewrite_reading.read_rewrite_authorization(state)
    if authorization is None or authorization.rewrite.to_sha != candidate_sha:
        return None
    if authorization.phase != _rewrite_values.LateRewritePhase.AUTHORIZED:
        return None
    return authorization.rewrite


def _licensed_by_a_permit(state: PinnedState) -> bool:
    """Whether this commit's debt rests on a permit rather than a reading.

    The gate skips the measurement for a commit an approval is owed a push
    for, because the approval is its own earlier decision brought back by a
    crash. That holds for every approval but one: a commit an approval names
    only because a TRANSFER let it past has never been measured and never been
    adjudicated -- what licensed it was a permit, and a permit is granted on
    terms that can stop being true between the grant and the recovery. A
    pull request repointed, an issue relabelled, a record hand-edited, or a
    contribution that no longer fingerprints alike each leave an approval
    standing over a rewrite nothing may publish unmeasured.

    So the bypass defers to the permit, which is re-asked in full over the
    record the grant left -- and where it refuses, the ordinary cumulative
    gate measures the rewrite like any other candidate.

    Asked of the PERMISSION rather than of the commit the record names, and
    that is what cross-binds it to the debt. An outstanding permission says a
    push is owed for the commit it produced, and the grant writes that
    permission and that debt in one write for one commit -- so an approval
    standing beside an outstanding permission is either the one it licensed or
    evidence that the two disagree, and neither may be spent on an object id.
    Compared against the commit the record names instead, a hand-edited target
    would make the permit invisible: the approval would look like any other
    and the rewrite nothing could revalidate would be pushed unmeasured.

    Only a record this build can vouch for ENTIRELY is recognized as spent,
    which is the record owner's own rule: a group announcing `published` over
    fields nothing else here understands, or bound to a commit this issue does
    not exempt, has not been shown to be over. A spent one licenses nothing
    outstanding, and that is what keeps the ordinary bypass intact -- a
    transfer that settled leaves its record behind for good, and reading that
    as a standing claim would send every later approval this issue earns back
    through a measurement.

    What ends the deferral is the receipt of the push the permission was
    granted for: that write carries the exemption over and moves the phase, so
    the record standing afterwards is spent and every later approval this
    issue earns is the ordinary one again. Until it lands the deferral holds,
    which costs a reading rather than a decision -- and where the permit
    refuses on the re-ask, the ordinary cumulative gate measures the rewrite
    like any other candidate.
    """
    return _rewrite_reading.outstanding_permission(state)


def _unauthorized_exemption(
    gate: _late_gate_models._Gate, rewrite: _rewrite_values.LateRewrite,
) -> str:
    """Why the exemption this would move licenses nothing, or "".

    An exemption is half a bypass: it says an ADJUDICATOR ruled the change one
    coherent whole, and the operator authorization beside it is what says a
    human agreed to publish past the ceiling. A commit only the exemption
    names is one the ordinary gate measures, so moving that exemption onto a
    rewrite would hand the rewritten commit a permission the accepted one
    never had -- and this owner's grant is the one road that skips the reading
    without any record naming the commit in advance.

    PROVED rather than parsed, which is why this is asked among the
    fingerprints rather than at the door. Every term of an authorization but
    the digest is the pinned comment agreeing with itself, and a hand edit
    arranges that as easily as a crash: a group naming the accepted commit
    over a base nobody froze, with a digest of nothing, reads back whole and
    would license this grant -- and past the grant an oversized change no
    human ever saw publishes on a rewrite the gate never measured. The digest
    is the one term the objects answer, so it is re-taken between the pair the
    record names and held to what the record says. Asked through the owner the
    GATE asks it through, so an authorization means the same thing on both
    roads past the measurement.

    The record an older binary left reaches it too: a `single` verdict wrote
    the exemption alone before a human's own decision was required at
    publication, and so does any comment whose authorization this build cannot
    read back whole.

    Refused, nothing moves and the rewritten commit is measured by the
    ordinary cumulative gate exactly as every other refusal here leaves it.
    """
    if _authority._publishes_on_an_exemption(gate, rewrite.from_sha):
        return ""
    return _UNAUTHORIZED_EXEMPTION.format(accepted=rewrite.from_sha)


def _unreadable_authorization(
    gate: _late_gate_models._Gate, rewrite: _rewrite_values.LateRewrite,
) -> str:
    """Why a claim already standing here forbids replacing it, or "".

    A grant writes the whole authorization group, so it does not add a record
    beside one -- it destroys whatever was there. Where that was a claim about
    the very commit this issue exempts and this build cannot read it back --
    a member missing, a field hand-edited, a kind or a phase from somewhere
    else -- overwriting it would repair evidence nobody checked, under the
    authority of a transfer this owner is in the middle of deciding.

    So it refuses, which costs the exemption nothing: the record stays exactly
    as it stands and the rewritten commit is measured by the ordinary gate
    until a human settles what is on the comment.

    A group describing some OTHER commit is not that claim and is replaced
    without ceremony: the exemption moved on since, so what is left names a
    commit nothing exempts and is not evidence for anything this issue still
    holds.
    """
    if not _rewrite_reading.claims_the_exemption(gate.state):
        return ""
    if _rewrite_reading.read_rewrite_authorization(gate.state) is None:
        return _UNREADABLE_AUTHORIZATION
    return ""


def _disagreeing_authorization(gate: _late_gate_models._Gate, fingerprint: str) -> str:
    """Why the digest a standing permission recorded is not this one, or "".

    The one field of an authorization that says what it was GRANTED over
    rather than what it is about, and the only one no other question here
    reaches: the ends are checked against the evidence, the publication
    against the entry, and the exemption against the record -- while the
    digest between them would otherwise be carried forward untested and
    written back as whatever this reading happened to take.

    That is a repair, and this owner may not make one. A permission whose
    digest disagrees with the contribution actually in front of it is either a
    record somebody edited or one taken under rules this build no longer
    reads the same way, and in both the honest answer is that nothing here
    knows which of the two digests the human ruled on. So the permit is
    refused, the record is left exactly as it stands, and the rewritten commit
    is measured by the ordinary cumulative gate.

    Asked only of a group claiming the commit this issue exempts, because that
    is the only one a grant would overwrite. One describing some other commit
    is replaced without ceremony and is evidence for nothing this issue still
    holds, so its digest is not a claim about this contribution either.

    A group that cannot be read whole is somebody else's refusal -- it comes
    first, and reaching here means the record proved out in every other field.
    """
    if not _rewrite_reading.claims_the_exemption(gate.state):
        return ""
    authorization = _rewrite_reading.read_rewrite_authorization(gate.state)
    if authorization is None or authorization.fingerprint == fingerprint:
        return ""
    return _DISAGREEING_AUTHORIZATION.format(
        recorded=authorization.fingerprint, recomputed=fingerprint,
    )
