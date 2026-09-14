# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Decide whether a relabelled or unmoved replay attempt can be cleared.

The recovery asks these questions before comparing or publishing.
An untouched anchor can be dropped; a recorded replay, announcement, or
unspent transfer requires reconciliation without silently losing its record.
"""
from __future__ import annotations

from orchestrator.git.base_sync import (
    attempts,
    replay_checkout_parks as _replay_checkout_parks,
    replay_publication_parks as _replay_publication_parks,
    snapshot,
    transfer_values as _transfer_values,
    transfers,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.verification import probes as verification_probes

# The two handoffs that say a grant is still standing over a commit the branch
# does not have: one this build reads as owed a push, and one it cannot read
# at all. A settled transfer is neither -- it is never cleared, so an issue
# that earned one would never look unstarted again.
_UNSPENT_TRANSFERS = frozenset((
    _transfer_values._Handoff.OUTSTANDING, _transfer_values._Handoff.UNVOUCHED,
))


def _answers_an_ineligible_label(
    context: _AutoRebaseRecoveryContext,
) -> bool:
    """Answer an anchor found under a label the base refresh does not drive.

    Nothing is fetched and nothing is compared, because nothing under this
    label is coming back to do either. So the road is a clear or a park, and
    what decides between them is whether the attempt left anything a clear
    would strand.

    An anchor over a checkout still standing ON it strands nothing. Git never
    moved the branch, no replay exists, and no permission was granted, so the
    anchor is a promise to come back that nobody is coming back for: dropping
    it costs the issue nothing, and leaving it pinned would strand a flag no
    later tick under this label ever reads.

    Everything else parks with every record intact. A rebase the tick
    RECORDED, or a permission granted for a push that never landed, is state
    the clear cannot honour: it would drop the one field naming what the
    branch would go back to while leaving the verdict, the debt, and the
    replay standing without it. A finish's announcement mark is the same
    refusal from the far end of the route, and it is asked by PRESENCE and on
    its own: the mark is written past a notice and an audit event, so it is
    the only evidence a publication was already announced -- and a comment
    carrying it and nothing else beside the anchor is exactly the partial
    record a clear would erase, leaving the next finish free to announce the
    same rebase a second time. A checkout that has MOVED off the anchor under
    the terms alone is the same refusal one reading over: that is the window
    between `git rebase` returning and the write that names what it produced,
    and the terms on their own cannot tell it from an attempt that never
    started. Cleared there, the replay stays on the branch with nothing on the
    comment naming it, and the issue this route hands on is one no reader can
    tell from an issue with nothing in flight -- so another handler or a
    decomposition tick is free to start over on a change a human already ruled
    on.

    The head is read locally, which costs no fetch and no request. A reading
    that could not be taken is no evidence the branch is where the attempt
    left it, so it parks with everything else this route cannot prove.
    """
    if context.pending_rewrite.left_a_replay:
        return _replay_publication_parks._park_stranded_recovery(context)
    if attempts._carries_an_announcement(context.state):
        return _replay_publication_parks._park_stranded_recovery(context)
    if transfers._left_mid_transfer(context.state):
        return _replay_publication_parks._park_stranded_recovery(context)
    if verification_probes._head_sha(
        context.worktree,
    ) != context.pending_pre_rebase_sha:
        return _replay_publication_parks._park_stranded_recovery(context)
    return snapshot._clear_ineligible_recovery(context)


def _finish_an_unmoved_head(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Answer a checkout standing exactly where the attempt anchored it.

    Two states look identical from HEAD alone, and only one of them is the
    shortcut. An attempt that pinned its anchor and got no further left
    nothing else behind: no record of a replay, no permission it never spent,
    and a tree git has not touched. Dropping the anchor there costs nothing --
    the normal rebase flow picks the branch up on this same tick and does the
    work again.

    The other is an attempt that got a long way and was UNDONE. A reset that
    landed and whose park write did not, or somebody's own `git reset`, puts
    the branch back on the anchor with the record of the replay, the
    permission granted for it, and the debt beside it all still standing.
    Dropping the anchor there throws away the only thing that brings a
    recovery back, leaves the transfer state for the next grant to trip over,
    and hands the branch straight to a fresh rebase -- which force-pushes a
    commit no adjudication has seen over the one the pull request carries.

    So the shortcut is for the unstarted attempt only, and everything else is
    finished as the rollback it is: the reset is re-run onto the head the
    branch is already on, which is what lets the abandoned debt and the
    permission the replay will never spend go with it, and the issue parks for
    a human to say what undid it.
    """
    if _unstarted_attempt(context, recovery_snapshot):
        return snapshot._clear_unchanged_recovery(context)
    return _replay_checkout_parks._park_undone_recovery(context, recovery_snapshot)


def _unstarted_attempt(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Whether this attempt left nothing behind but the anchor it pinned.

    Three things say it did leave something. A record of the replay it
    produced, whether whole or in pieces, is an attempt that reached the write
    after `git rebase` -- and a reset that put the branch back before its own
    park write leaves exactly that. A mark that a finish announced ANYTHING
    says the same from the far end of the route, and it is asked by presence
    rather than against the head in hand: no finish ever announces the anchor,
    so a mark naming it is a checkpoint something took apart rather than an
    absence, and read as one it would hand the branch to a fresh rebase over a
    publication that has already gone out. A permission this build reads as
    outstanding, or one it cannot vouch for at all, is a grant that was never
    spent on a commit the branch no longer has.

    A SETTLED permission is not one of them: a transfer that finished is never
    cleared, so every issue that ever earned one would fail this test for the
    rest of its life.

    The TREE is nobody's question here, and deliberately. A checkout carrying
    uncommitted work is one the clean-tree gate ahead of every rebase already
    refuses, so a shortcut taken over one hands the branch to a flow that
    stands down on the same tick -- and where the dirt came from a reset this
    attempt took, the record it left is the first test above.

    Costs no git and no request, which is what lets the ordinary unstarted
    attempt -- the whole reason this shortcut exists -- pay nothing for it.
    """
    if context.pending_rewrite.left_a_replay:
        return False
    if attempts._carries_an_announcement(context.state):
        return False
    carried = transfers._carried_by(context, recovery_snapshot.head)
    return carried not in _UNSPENT_TRANSFERS
