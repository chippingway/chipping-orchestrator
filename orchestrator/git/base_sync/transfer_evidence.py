# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reconstruct a clean rebase's contribution and declared publication evidence.

A frozen base and whole semantic identity name both ends of the rewrite.
Recovery requires its pending record to vouch for the actual checkout
before asking the size gate to grant a fresh transfer.
"""
from __future__ import annotations

from orchestrator.git.base_sync import transfer_values as _transfer_values
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
    _PendingRewrite,
)
from orchestrator.git.base_sync.state import log
from orchestrator.git.measurement import commits as measurement_commits


def _rewritten_by_the_rebase(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext,
    before_sha: str,
    after_sha: str,
    publication: _PendingRewrite | None = None,
):
    """What this rebase replaced, as the evidence a transfer is granted on.

    Assembled here because this is the one place both halves of the claim are
    in hand at once. The pair the contribution came FROM is the one the
    adjudication already recorded -- the commit a human ruled on and the base
    it was measured over -- and it is the only pair a verdict may be moved off
    and the only one a later reader re-derives the equality from. The pair it
    went TO is this rebase's own: the head the replay left, which moves with
    the next commit, and the base the branch now sits over, which is what the
    remote says its base branch is at.

    Nothing is decided here. Whether the two pairs are one contribution is the
    gate's question, asked over fingerprints taken from the objects
    themselves, and every other term this hands over is re-asked there against
    the publication the gate froze for itself.

    The base is frozen from what the REMOTE says the branch is at rather than
    read off the local ref the rebase named, and that is the whole of what
    keeps the pair honest. `refs/remotes/<remote>/<base>` lives in the object
    store the issue's agent writes to and any worktree sharing it can repoint
    -- after this tick's fetch, at that. A replay onto a ref carrying work the
    remote does not have fingerprints as the little that sits on top of it,
    while the pull request against the real base carries that work and this
    change together, and the permit would wave the pair through unmeasured.
    Read from the remote, the forged base is simply a different contribution
    and the ordinary cumulative gate measures it -- which costs one
    authenticated read on the rare tick an exempt issue is rebased.

    Empty where either half cannot be shown, and that is a claim withheld
    rather than a refusal reported. A comment with no semantic record -- an
    issue that never earned an exemption, one written before the record
    existed, one whose fingerprint could not be taken -- has no accepted pair
    to name, and a base the remote would not name, or one this host does not
    hold even after a fetch, is no commit to read a contribution over. In both
    the rebase goes to the ordinary cumulative gate and is measured like any
    other candidate.

    The PUBLICATION is the caller's where it hands one in, and that is the
    difference between the tick that makes the rewrite and the tick that comes
    back to it. The publisher is making the rewrite now, so the pull request
    and the stage it is entered on are the ones it is looking at. A recovery
    is not: taking them from the issue as it reads on the tick AFTER a crash
    would compare today with today, and a relabel or a repoint made while the
    process was down would pass as the terms the dead tick made its rewrite
    under -- which is exactly what the permit's publication checks exist to
    catch.

    The pre-rebase anchor goes down as the LEASE rather than as the commit
    that was replaced, and the two are deliberately kept apart. It is the head
    the pull request is standing on and the head the force-push behind this is
    pinned to; that it is also the commit the exemption names is what the
    equality of the two contributions proves, and not something this owner may
    assert by spelling one field from the other.
    """
    # Lazy import: the exemption record and the rewrite vocabulary sit in the
    # workflow layer above this package, so binding them at module load would
    # make every git-side import pay for the stage tree they pull in.
    from orchestrator.workflow.late_split import (
        exemption_reading as _exemption_reading,
        rewrite_values as _rewrite_values,
    )
    identity = _exemption_reading.read_semantic_identity(context.state)
    if identity is None:
        return None
    replayed_onto = measurement_commits._freeze_base_commit(
        context.spec, context.worktree,
    )
    if not replayed_onto.is_frozen:
        return None
    made_against = publication or _PendingRewrite(
        sha=after_sha, pr_number=context.pr_number, stage=context.label,
    )
    return _rewrite_values.LateRewrite(
        kind=_rewrite_values.LateRewriteKind.AUTO_CLEAN_REBASE,
        from_sha=identity.candidate_sha,
        from_base_sha=identity.base_sha,
        to_sha=after_sha,
        to_base_sha=replayed_onto.sha,
        pr_number=made_against.pr_number,
        source_stage=made_against.stage,
        lease=before_sha,
    )


def _reconstructed(
    context: _AutoRebaseRecoveryContext,
    local_head: str,
    carried: _transfer_values._Handoff,
):
    """The evidence a recovery hands the gate where the grant never landed.

    The one window the record cannot answer for itself. An interrupted tick
    rebased and died before the write that would have said what the replay
    replaced, so the reissued push reaches the gate with nothing on the
    comment naming a rewrite -- and the ordinary cumulative gate measures a
    change a human already ruled on past the same ceiling, with a pull request
    open over the work.

    Assembled from exactly the readings the interrupted tick would have taken:
    the pair the adjudication recorded, the head the checkout is standing on,
    the base the REMOTE names, the pinned anchor as the lease, and the pull
    request and stage that tick recorded making its rewrite against. Those
    last two are the dead tick's own rather than this one's, and they have to
    be: the permit checks them against the publication it freezes for itself,
    so terms taken from the issue as it reads now would compare today with
    today and adopt a relabel or a repoint made while the process was down.

    Nothing at all is assembled where the record names some OTHER commit, or
    where the terms it was made under cannot be read back: evidence made up to
    fill either gap is the one thing this owner may not offer the permit, and
    a publication taken from the issue as it reads on the tick after a crash
    is exactly that.

    A record carrying the terms and no head is assembled for, and it is the
    one place the head in hand is not the record's own claim. That is the
    window between git returning and the write that names what it produced:
    the terms went down with the anchor, so which publication the attempt was
    for is known, and the head is offered to the permit to be proved by what
    it contributes against the pair a human ruled on. The permit refusing is
    what that road is held by -- nothing here asserts the checkout is the
    replay, it hands over the claim for checking.

    None for every other handoff, each for its own reason: a permission still
    outstanding IS the evidence and is re-asked over the terms the grant was
    taken on, a spent one describes a transfer that is over, one nobody can
    vouch for may not be replaced by a claim this owner made up, and an issue
    carrying no verdict has nothing to carry.
    """
    if carried != _transfer_values._Handoff.UNRECORDED:
        return None
    if not _vouches_for_the_checkout(context.pending_rewrite, local_head):
        return None
    rewrite = _rewritten_by_the_rebase(
        context, context.pending_pre_rebase_sha, local_head,
        publication=context.pending_rewrite,
    )
    if rewrite is not None:
        log.info(
            "issue=#%d auto-rebase recovery: the interrupted tick left %s on "
            "the branch and no permission for it; re-deriving what the replay "
            "of %s contributes so the gate rules on the transfer it would have",
            context.issue.number, local_head[:8], rewrite.from_sha[:8],
        )
    return rewrite


def _vouches_for_the_checkout(
    recorded: _PendingRewrite, local_head: str,
) -> bool:
    """Whether this record may be the terms the head in hand is decided on.

    Two records may, and they are the two ends of one write. A record naming
    this exact commit is the ordinary one: the attempt got past `git rebase`
    and said what it produced. A record carrying the terms and no head at all
    is the window before that write, where nothing on the comment names any
    commit -- and the terms are still the dead tick's own, which is the whole
    of what the permit needs them for.

    Nothing else does. A record naming another commit says out loud that this
    checkout is not its work, and one whose terms cannot be read cannot say
    which publication anything was for.
    """
    if recorded.sha:
        return recorded.names(local_head)
    return recorded.is_declared
