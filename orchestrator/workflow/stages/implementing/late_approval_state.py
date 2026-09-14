# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Write publication approval coordinates together and retain their existing basis.

An approval already naming the candidate keeps its known, unknown, or
legacy basis. Clearing the approval also clears route spends, since those
steps are owed only by that publication.
"""
from __future__ import annotations

from orchestrator.github import (
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    state as _late_state,
)
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    state as _state,
)


def _approve(
    state: _pinned_state.PinnedState,
    candidate_sha: str,
    lease: str,
    basis: _late_approval_reading.LateApprovalBasis | str | None,
) -> None:
    """Record the commit a publication is owed, what pins it, and its grounds.

    The three are written together because they are spent together and mean
    nothing apart: a lease with no approval names a head nobody owes a push
    for, an approval whose lease was dropped is the one that force-pushes over
    whatever the pull request has become, and one whose basis was dropped is a
    debt a later tick has to GUESS the provenance of -- which is the guess
    that publishes an adjudication's debt as though this gate had counted it.

    The basis is handed in rather than derived, because the owner granting an
    approval is the only one that knows: the records standing around it are
    the same on every road, and a reader can tell them apart only if the
    writer said so.

    `None` is a caller that has an approval to re-record and NO grounds to
    record for it, which is the shape an older build left. It goes down as an
    absence rather than as a value, because the two say opposite things to the
    reader: a basis names a decision, while an absence hands the question to
    the exemption beside it -- and a caller inventing one here would answer a
    question it was never in a position to.

    A bare string is the third of those and is written back unchanged: a
    caller carrying forward a basis this build cannot read is preserving the
    record's own claim to grounds it cannot name, which the readers fail
    closed on. Turned into either of the two above it would become a decision
    nobody made or an absence the exemption answers for.
    """
    state.set(_state._APPROVED_SHA, candidate_sha)
    state.set(_state._APPROVED_LEASE, lease or None)
    state.set(_state._APPROVED_BASIS, None if basis is None else str(basis))


def _owes_a_publication(
    state: _pinned_state.PinnedState, candidate_sha: str,
) -> None:
    """Record that this commit is owed a push, on whatever grounds it has.

    The write for a caller holding one commit and no lease, which is the
    implementing seam: nothing froze a publication head there because there is
    no pull request yet, and the push that opens one reads the remote for
    itself. The gate's own debt writer declines for exactly that reason, so
    this seam mints its own -- and it has two callers, since the publication
    that normally does it is skipped whenever the checkout stopped being the
    commit that was approved.

    The grounds are CARRIED where an approval already stands for this very
    commit, since nothing about a checkout that moved changes what the
    publication was allowed on -- and an approval that never said what it
    rested on is carried as saying nothing, not upgraded. An older build wrote
    exactly that shape, and what a reader owes it is the exemption beside it
    rather than a claim this write invented: turned into `unmeasured` here, a
    legacy record would stop being read as unknown and become debt this
    workflow owns, which is a bypass nobody would ever revalidate.

    Where no approval stands for the commit, the grounds are the record's.
    The exemption CLAIM decides -- presence, not readability, since a field a
    hand edit truncated still says an adjudication happened and only fails to
    say which commit -- so a comment carrying one leaves the adjudication's
    debt, to be revalidated like every other debt a human's gesture is behind.
    A comment carrying none leaves `unmeasured`, which is what every road
    reaching here on such an issue is: a receipt the remote already carries, a
    permit, a candidate the switch kept out of the gate -- records this
    workflow made for itself and re-derives on the next tick, so each answers
    for its own bypass.

    The whole group goes down either way rather than the commit alone. A
    commit with a lease left over from some other attempt beside it is the
    pair disagreeing with itself, which the reconciliation ahead of the next
    handler reads as damage.
    """
    if _late_approval_reading._approved_commit(state) == candidate_sha:
        _approve(state, candidate_sha, "", _standing_basis(state))
        return
    _approve(state, candidate_sha, "", _minted_basis(state))


def _minted_basis(state: _pinned_state.PinnedState) -> _late_approval_reading.LateApprovalBasis:
    """What a debt this seam mints for a commit no approval names rests on.

    Read off the exemption CLAIM rather than off the commit it names, and
    conservatively: an issue that never entered an adjudication carries no
    such field, while one whose field is unreadable carries the claim that one
    happened and no way to say what it was about. Read alike, the second is
    how an adjudication's publication debt comes to be recorded as this
    workflow's own -- the one write a later reader spends without asking
    anybody.

    What the conservative answer costs is a measurement on an issue whose
    adjudication is long over and whose candidate this gate really did admit
    for itself. What the other answer costs is the bypass.
    """
    if state.carries(_exemption_reading.LATE_EXEMPT_SHA):
        return _late_approval_reading.LateApprovalBasis.ADJUDICATION
    return _late_approval_reading.LateApprovalBasis.UNMEASURED


def _standing_basis(
    state: _pinned_state.PinnedState,
) -> _late_approval_reading.LateApprovalBasis | str | None:
    """What the standing approval rests on, exactly as the record holds it.

    The debt a caller re-records is the one that was already there -- the same
    commit, now the head the pull request stands on -- so what it rests on is
    whatever granted it. Carried forward rather than re-decided, since nothing
    about a checkout that stopped being what went out changes the grounds a
    publication was allowed on.

    None where the record never said, which is the shape an older build left
    and the one the exemption beside it answers for. Answered `unmeasured`
    instead, an unknown would be promoted to a decision nobody made: the
    reader would stop falling back, and a legacy `late_approved_sha` standing
    over the very commit an exemption names would read as debt this workflow
    owns and be spent without anybody being asked.

    A value this build cannot read is handed back VERBATIM rather than as
    either of those. It is neither a decision nor an absence -- it is a record
    claiming grounds it cannot name -- and the readers fail closed on exactly
    that shape. Rewritten as an absence here, one carry-forward would launder
    the damage into the legacy road and the next tick would spend the debt
    without asking anyone.
    """
    standing = _late_approval_reading._approved_basis(state)
    if standing:
        return _late_approval_reading.LateApprovalBasis(standing)
    if _late_approval_reading._unreadable_basis(state):
        return state.get(_state._APPROVED_BASIS)
    return None


def _forget_approval(state: _pinned_state.PinnedState) -> None:
    """Drop a debt that is paid, superseded, or being adjudicated instead.

    What the route still owed goes with it. Those obligations outlive the
    generation that froze them only so the tick that finally lands this commit
    can close them; past that push there is nothing left to close, and a group
    left standing would be restored by the next approval on this issue and
    applied to a round it was never owed for.
    """
    for key in _late_approval_reading._APPROVAL_KEYS:
        state.set(key, None)
    _late_state.write_late_spends(state, ())
