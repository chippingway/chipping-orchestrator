# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Refuse an unpublished recovery before evidence may authorize its retry.

Publication identity, an existing announcement, rollback, transfer integrity,
and checkout ownership are checked in that order. This preflight serves the
dormant replay coordinator and keeps every refusal ahead of the shared push.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    attempts,
    replay_checkout_parks as _replay_checkout_parks,
    replay_evidence as _replay_evidence,
    replay_publication_parks as _replay_publication_parks,
    replay_transfer_parks as _replay_transfer_parks,
    transfer_publication as _transfer_publication,
    transfer_values as _transfer_values,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)


def _refused_before_the_retry(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: _transfer_values._Handoff,
) -> bool | None:
    """The park this checkout owes before any push, or None where it owes one.

    Five refusals, in the order the evidence for them costs nothing to read.

    The first is not about the commit at all: whether the attempt was made for
    the publication this tick holds. It is asked of the RECORD rather than of
    the permit, because the permit is not on every road -- an issue carrying
    no verdict never had one, and it still reaches a finalize that posts a
    notice to this tick's pull request, files an audit event under this tick's
    stage, and drops the anchor.

    The second is the announcement mark, asked by PRESENCE and asked of every
    road here. It is written between a finish's notice and its relabel, so it
    stands only where a push had already landed and the pull request had
    already been told -- and this whole road is reached over a remote that is
    not standing on the checkout. Whichever head the mark names, then, the
    publication it describes is one the remote has lost: a rollback, or a
    checkpoint something took apart. A retry would overwrite the rollback
    under a lease the anchor satisfies and announce the same rebase a second
    time, which is the one outcome the mark exists to prevent.

    Then the three about the commit. A remote the record says already carried
    this replay has been rolled back by somebody, and the anchor a retry would
    lease against is the head they rolled it back to. A transfer record nobody
    can vouch for would reach the ordinary cumulative gate and send an
    adjudicated change into a second adjudication. And an attempt record that
    does not vouch for the checkout -- damaged, or whole and naming some other
    commit -- is the same refusal one field over: read as the window it
    resembles, it would fall through to the counts, and a strictly-ahead
    checkout would be measured and force-pushed on the strength of a claim
    nothing could check.
    """
    if _replay_evidence._made_for_another_publication(context, completed):
        return _replay_publication_parks._park_foreign_publication_recovery(context, completed)
    if attempts._carries_an_announcement(context.state):
        return _replay_checkout_parks._park_announced_recovery(context, completed)
    return _refused_by_the_records(context, completed, carried)


def _refused_by_the_records(
    context: _AutoRebaseRecoveryContext,
    completed: _AutoRebaseRecoverySnapshot,
    carried: _transfer_values._Handoff,
) -> bool | None:
    """The three refusals about the commit itself, or None where none holds.

    Split from the two above them only so each function answers a countable
    number of ways; the order across both is one order and is the property
    that matters.
    """
    if _transfer_publication._rolled_back_publication(context, completed.head, carried):
        return _replay_checkout_parks._park_rolled_back_recovery(context, completed)
    if carried == _transfer_values._Handoff.UNVOUCHED:
        return _replay_transfer_parks._park_unvouched_recovery(context, completed)
    if _replay_evidence._unclaimed_checkout(context, completed):
        return _replay_checkout_parks._park_unrecorded_recovery(context, completed)
    return None
