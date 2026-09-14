# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read the whole publication approval and its bounded permission basis.

A candidate, optional lease, and basis form one claim. Damaged or legacy
bases remain distinguishable from a known approval, and operator-backed
bases are named explicitly rather than inferred from adjacent records.
"""
from __future__ import annotations

from enum import StrEnum

from orchestrator.github import (
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
)
from orchestrator.workflow.stages.implementing import (
    state as _state,
)


class LateApprovalBasis(StrEnum):
    """What one approval on this issue rests on, said by the owner granting it.

    A bounded vocabulary rather than a flag, because the readers ask different
    questions of it and a boolean would have to be renamed the first time a
    third road approved anything.

    `READING` is this gate's own count coming back at or below the ceiling.
    `UNMEASURED` is a publication that skipped the count on a record this
    workflow made for itself and can re-derive: a rewrite permit, a
    switched-off candidate, a receipt already on the remote. Each of those
    answers for its own bypass on the next tick, so nothing about the debt
    they leave has to be revalidated before it is spent.

    The other two are the ones an operator's authorization stands behind, and
    they are apart from `READING` for exactly that reason: an approval is
    spent by the tick that comes back after a crash, and one that RESTS on an
    authorization may only be spent while that authorization can still be
    read. `ADJUDICATION` is the publication debt an authorized settlement
    records beside the exemption it writes. `AUTHORIZATION` is the debt a
    candidate past the ceiling earns when an operator authorizes it at the
    gate itself -- the count behind it was this gate's own, so recording it as
    a reading would be true and useless: what let it through was the human,
    and a record damaged before the push would have it publish unmeasured.

    A value from anywhere else, and an approval an older binary wrote with no
    basis at all, read back as no basis -- and what a reader does with that is
    fall back to the exemption, which is the only evidence such a record left.
    """

    READING = "reading"
    UNMEASURED = "unmeasured"
    ADJUDICATION = "adjudication"
    AUTHORIZATION = "authorization"


# The two an operator's gesture is behind, which may be spent only while that
# gesture can still be read. Named as a group because that is the question a
# reader has of the basis -- whether a debt has to be revalidated, rather than
# which owner granted it -- so the membership is stated once here instead of
# being re-derived by each of them, and it is the whole of what the two share.
AUTHORIZED_BASES = frozenset((
    LateApprovalBasis.ADJUDICATION,
    LateApprovalBasis.AUTHORIZATION,
))


# Everything one standing debt goes down as, taken as one group: the commit a
# push is owed for, the head that push is pinned to, and the grounds the debt
# rests on. Spelled once so the reader that refuses a half-written group and
# the write that ends one cannot come to disagree about what the group is.
_APPROVAL_KEYS = (
    _state._APPROVED_SHA, _state._APPROVED_LEASE, _state._APPROVED_BASIS,
)


def _approved_commit(state: _pinned_state.PinnedState) -> str:
    """The commit an approval owes a publication for, or "" where none does.

    Published for every owner that has to know a commit is already DECIDED.
    An approval -- the retirement a small candidate earns, the exemption a
    `single` verdict records -- drops the generation that named the commit
    and licenses a push that has not run yet, so between the two this is what
    says which commit the issue is still waiting on. Read fail-closed like
    every other late commit field: only a whole object id is one, so a
    hand-edited value is no approval rather than an unmeasured publication.
    """
    return _payloads.as_hex(
        state.get(_state._APPROVED_SHA), _formats.COMMIT_LENGTHS,
    ) or ""


def _approved_lease(state: _pinned_state.PinnedState) -> str:
    """The head a published approval was frozen against, or "" where none was.

    The other half of an approval taken on the published side, and the half
    the retry after a failed push cannot re-derive: the generation that froze
    the pull request's head was retired by the write that approved the
    commit, and re-reading the pull request answers with wherever it has
    moved to since. Read fail-closed like every other late commit field.

    Empty is the ordinary answer and means a pre-publication approval -- what
    every implementing-seam approval is -- whose push correctly takes its own
    reading of the remote.
    """
    return _payloads.as_hex(
        state.get(_state._APPROVED_LEASE), _formats.COMMIT_LENGTHS,
    ) or ""


def _approved_basis(state: _pinned_state.PinnedState) -> str:
    """What the standing approval rests on, or "" where the record cannot say.

    Read fail-closed like every other late field: only a value this build's
    own vocabulary carries reads back, so a hand edit and a spelling from
    somewhere else are both "no basis" rather than a basis nothing checked.

    "" is also what an approval an older binary wrote reads back as, which
    carried no basis at all -- and a reader that acts on the two ALIKE is the
    one thing this may not be used for. `_unreadable_basis` beside it is what
    tells them apart, because only the absent one earns the compatibility.
    """
    written = state.get(_state._APPROVED_BASIS)
    if written in tuple(LateApprovalBasis):
        return str(written)
    return ""


def _unreadable_basis(state: _pinned_state.PinnedState) -> bool:
    """Whether the record CARRIES a basis this build cannot read.

    Presence and truth asked together, because the answer is the gap between
    them, and it is a gap a reader has to act on differently at each end. An
    approval an older binary wrote carries no field at all: there the
    exemption beside it is the only evidence there ever was, and reading it is
    the compatibility this domain owes live issues. One whose field a hand
    edit or a half-written crash left unreadable is the opposite record -- it
    CLAIMS grounds and cannot say which -- and reading that as the absence
    above hands a bypass to the one shape an attacker or an accident reaches
    by touching the single field the fallback turns on.

    So this is what the readers key the fail-closed road on, and the absence
    keeps the fallback to itself. `None` is asked beside the key because the
    payload is JSON and a field can be present and null, which is an older
    binary's value or a hand edit and is an absence either way.
    """
    if not state.carries(_state._APPROVED_BASIS):
        return False
    if state.get(_state._APPROVED_BASIS) is None:
        return False
    return not _approved_basis(state)


def _unreadable_approval(state: _pinned_state.PinnedState) -> bool:
    """Whether this comment CLAIMS a debt it cannot show whole.

    Presence rather than truth, and the question a caller asks before it acts
    on a debt having been PAID. The readers above answer "nothing owed" for a
    group a hand edit or a half-written crash left unreadable exactly as
    readily as for one the write that pays a debt blanked -- which is the
    right answer for a road deciding whether to spend an approval, and the
    wrong one for a road deciding whether the write that should have settled a
    publication landed at all. Read as the absence, a group standing over a
    commit nobody can name would pass as a debt somebody paid.

    Three shapes count, and each is the group disagreeing with itself. A
    member carrying something beside a commit this build cannot read is one:
    the debt names no commit and the record is still claiming one. A lease
    present that is not a commit is another, since the head a published
    approval was frozen against is what its retry is pinned to and a value
    nothing can read is no pin. And a basis the record carries and cannot name
    is the third, on the terms `_unreadable_basis` beside it already states.

    False for the ordinary comment, which carries a group of nulls: the write
    that ends a debt blanks these fields rather than removing them, so all
    three absent is the record nobody wrote.
    """
    if all(state.get(key) is None for key in _APPROVAL_KEYS):
        return False
    if not _approved_commit(state):
        return True
    leased = state.get(_state._APPROVED_LEASE) is not None
    if leased and not _approved_lease(state):
        return True
    return _unreadable_basis(state)
