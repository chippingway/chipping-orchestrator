# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Prove the transfer checkout, lease, open owner, and remote-backed rewritten base.

The owner is re-read after the close latch and must retain its stage and
controls. A clean checkout names the rewritten commit, and the remote
base must contain the base used for its contribution.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.git.measurement import (
    commits as _measurement_commits,
)
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.github import labels as _labels
from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.late_split import (
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


# The revision a checkout's own head is named by.
_HEAD = "HEAD"

# The state a GitHub issue has to report for a transfer to be granted.
_OPEN = "open"

_UNPROVABLE_TREE = (
    "the worktree is not provably clean, so the contribution it would be "
    "fingerprinted over is not the one a push would publish"
)

_MOVED_CHECKOUT = (
    "the rewrite produced `{rewritten}` and the checkout stands on `{head}`"
)

_UNPROVABLE_LEASE = (
    "the head this push is leased against (`{lease}`) is not a commit this "
    "host holds"
)

_UNREADABLE_OWNER = "this issue could not be read again"

_CLOSED_OWNER = "this issue is {state} rather than open"

_CONTROLLED_OWNER = "this issue carries `{control}`"

_RELABELLED_OWNER = (
    "the rewrite was entered from `{frozen}` and this issue is on `{read}` now"
)

_LATCHED_CLOSE = (
    "a poll observed this issue closed and nothing has settled the reading"
)

# What a freeze that established nothing is reported as where it named no
# failure of its own, so the line an operator reads always says something.
_UNNAMED_BASE = "the remote named nothing"

_UNFROZEN_BASE = (
    "the commit the remote says `{branch}` is at could not be frozen, so "
    "nothing here can say which base the rewritten contribution is read over "
    "({failure})"
)

_FOREIGN_BASE = (
    "the rewritten contribution is read over `{base}`, which this host does "
    "not show `{branch}` carrying as of `{tip}`"
)


def _unproven_checkout(
    gate: _late_gate_models._Gate, rewrite: _rewrite_values.LateRewrite,
) -> str:
    """Why the checkout is not provably the rewritten commit, or "".

    Both halves, because a transfer is a claim about what the checkout will
    publish. A tree carrying anything loose is one whose contribution is not
    the contribution a push would send, and a `git status` that established
    nothing names no paths -- which is what a clean tree names too. And a head
    that is not the rewritten commit, or one this host cannot peel, is a
    checkout the rewrite's own before-and-after says nothing about.
    """
    if not _worktree_status._worktree_status(gate.worktree).is_clean:
        return _UNPROVABLE_TREE
    proved = _measurement_commits._prove_candidate_commit(
        gate.worktree, _HEAD,
    )
    if proved.is_frozen and proved.sha == rewrite.to_sha:
        return ""
    return _MOVED_CHECKOUT.format(
        rewritten=rewrite.to_sha, head=proved.sha or "an unreadable head",
    )


def _unproven_lease(
    gate: _late_gate_models._Gate, rewrite: _rewrite_values.LateRewrite,
) -> str:
    """Why the head this push is leased against is not one to lease on, or "".

    The one end of the evidence nothing else here reads as an OBJECT. The
    checkout proves the rewritten commit, and the two fingerprints prove both
    ends of both contributions by reading every byte they name -- but the
    lease is compared as an id and never asked for, and it is deliberately
    allowed to differ from the accepted commit, so nothing else would catch a
    whole-looking object id this repository does not hold.

    That gap matters because of what the lease IS: the head the pull request
    was standing on, which this branch was on before the rewrite collapsed it.
    An id the remote reports and this host cannot peel is a fetch that brought
    nothing back or work made somewhere else -- so the agreement between the
    entry and the record is two readings of a commit neither of them can
    produce, and a permit resting on it would skip the measurement on evidence
    nobody can check.

    Proved rather than looked up, for the reason every other commit in this
    domain is: git resolves a full object id to itself whether or not the
    store has ever seen it, so only peeling tells the two apart.
    """
    proved = _measurement_commits._prove_candidate_commit(
        gate.worktree, rewrite.lease,
    )
    if proved.is_frozen:
        return ""
    return _UNPROVABLE_LEASE.format(lease=rewrite.lease)


def _unconfirmed_owner(
    gate: _late_gate_models._Gate, rewrite: _rewrite_values.LateRewrite,
) -> str:
    """Why this issue is not the one the rewrite was made on, or "".

    The issue in hand was fetched when the tick began and a squash-on-approval
    runs minutes later, so the snapshot says nothing about whether anybody
    still wants this work or has taken it somewhere else. A transfer is the
    one answer here that carries a human's verdict forward without re-asking a
    human anything, so the issue is re-read for it rather than assumed -- and
    the latch is asked first, because a close a poll observed while this
    worker holds the issue is one no request of this tick's would ever show.

    The three things asked of that read are one question: is this still the
    issue the rewrite was entered on. Its STATE, since a closed one wants none
    of it. Its CONTROL labels, since `paused` and `backlog` are how an
    operator says stop and a transfer that pushed past one would be the
    orchestrator carrying on where it was told not to. And its WORKFLOW label,
    against the stage the rewrite recorded -- the entry read that stage off
    the issue the tick opened with, so a relabel during the rewrite is
    invisible to every reading but this one, and a permit granted under it
    would publish onto a pull request whose stage no longer owns the branch.

    Fails closed twice over, like every other owner read in this domain: an
    exception is unreadable -- the fetch and every attribute behind it, since
    a fetched issue is lazy -- and so is a state that is neither of the two
    GitHub reports, which would otherwise default to open and grant a permit
    on a read that established nothing.
    """
    if _observations.close_observed(gate.spec.slug, gate.issue.number):
        return _LATCHED_CLOSE
    try:
        return _moved_issue(
            gate.gh.get_issue(gate.issue.number), rewrite.source_stage,
        )
    except Exception:
        log.warning(
            "issue=#%d could not be re-read before carrying its exemption "
            "onto a rewritten commit", gate.issue.number, exc_info=True,
        )
    return _UNREADABLE_OWNER


def _moved_issue(fetched: Issue, source_stage: WorkflowLabel | None) -> str:
    """Why this reading is not the open, unpaused issue that stage owns.

    Read off the FETCHED issue rather than the one the tick opened with, which
    is the whole point of taking it: the state, the control labels, and the
    workflow label are three things a human moves while an agent runs, and the
    snapshot in hand is as old as the run that has just finished.
    """
    owner_state = getattr(fetched, "state", "")
    if owner_state != _OPEN:
        return _CLOSED_OWNER.format(state=owner_state or "unreadable")
    controlled = _labels.hard_skip_control_label(fetched)
    if controlled:
        return _CONTROLLED_OWNER.format(control=controlled)
    stage = _labels.workflow_label(fetched)
    if stage != source_stage:
        return _RELABELLED_OWNER.format(frozen=source_stage, read=stage)
    return ""


def _unproven_base(
    gate: _late_gate_models._Gate, rewrite: _rewrite_values.LateRewrite,
) -> str:
    """Why the base the rewrite was read over is not the branch's, or "".

    The one end of the evidence the digests cannot prove for themselves, and
    the reason is what equality of the two fingerprints actually says: the
    rewritten pair contributes what the accepted pair did. Over WHICH base it
    contributes it is the caller's claim, and a rewrite that moves the base --
    which is what a rebase is -- is free to name one that is not the branch's
    at all. A base carrying work the remote does not have subtracts that work
    from the rewritten contribution, so the pair fingerprints to the digest a
    human ruled on while the object it names carries that change AND the bulk
    the forged base swallowed. Granted, the exemption moves onto it and the
    gate publishes it without a reading.

    That claim is not the caller's to make good either, and it is not enough
    that the caller read the base off `refs/remotes/<remote>/<base>`. That ref
    lives in the object store the issue's agent writes to and any worktree
    sharing it can repoint -- after this tick's fetch, at that -- so a fork
    point taken against it and the branch the remote really carries are two
    different answers whenever something in that checkout wants them to be.

    So the base branch is frozen from the REMOTE, the way every other reading
    that has to mean something off this host freezes it, and the recorded base
    is held to being a commit that tip's history contains. Reachability rather
    than equality, because the base moves on its own: a rebase replays onto
    the tip it fetched a moment ago and a squash collapses over the fork point
    the branch has had for days, and both are commits the branch really
    carries. What is not one is a commit nobody but this host has ever seen.

    Asked of the REWRITTEN pair alone. The accepted pair's base is the one the
    adjudication froze, and it is proved where it is used: the record either
    fingerprints to the digest it recorded over its own pair or refuses, which
    no reading of the base branch could add to.

    A tip this host cannot establish refuses like everything else here, and
    what it costs is the transfer rather than the decision -- the exemption
    stays where it is and the ordinary cumulative gate measures the rewritten
    commit. So does a base this store cannot read, since a commit nothing can
    walk has not been shown to be on the branch whatever it is really named.

    One authenticated read, on a tick that has an exemption to carry and a
    rewrite claiming to carry it. A caller that froze the same branch for
    itself pays it twice, and it is asked here anyway: what a permit may not
    do is take the base a rewrite was measured over from the rewrite.
    """
    frozen = _measurement_commits._freeze_base_commit(gate.spec, gate.worktree)
    if not frozen.is_frozen:
        return _UNFROZEN_BASE.format(
            branch=gate.spec.base_branch,
            failure=frozen.failure or _UNNAMED_BASE,
        )
    if _verification_probes._commit_contains(
        gate.worktree, rewrite.to_base_sha, frozen.sha,
    ):
        return ""
    return _FOREIGN_BASE.format(
        base=rewrite.to_base_sha,
        branch=gate.spec.base_branch,
        tip=frozen.sha,
    )
