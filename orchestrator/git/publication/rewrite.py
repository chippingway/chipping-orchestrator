# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The destructive half of a squash: reset, recommit, publish, roll back.

Every step here runs after the branch has already been rewound, so each
failure path restores the head it was rewound from before reporting -- the
agent's commits stay on the branch and a human decides what to do next. That
head is handed in rather than read: the plan pinned it while the branch was
intact, and the recovery beside this owner reads it off the record a squash
wrote before it ran.

The publish goes through the size gate's own push, because a squash is one of
the pushes onto a pull request the remote already carries: named against the
commit the squash produced, and pinned to the head the entry froze -- the same
pre-rebase SHA, checked against the head the publication was standing on
before any of this ran. A remote that moved underneath the rewrite rejects the
push instead of losing the update.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from orchestrator.config import settings as config
from orchestrator.git import commands
from orchestrator.git.publication import models, planning
from orchestrator.git.verification import probes as verification_probes

# The channel is named for the branch-publication domain rather than for this
# module's path: operators filter the rendered `orchestrator.branch_publication`
# prefix and attach handlers to it, so a squash reports where their filters
# already point whichever owner here is the one emitting.
log = logging.getLogger("orchestrator.branch_publication")

# What a push that never left this host is reported as when the pull request
# is already standing on the commit it would have sent.
_UNCONFIRMED_PUBLICATION = (
    "the pull request already carries `{squashed}` and the leased push that "
    "would have confirmed it did not go out; the branch is left standing on "
    "it rather than reset off work the remote has"
)


def _squash_failure(error: str) -> models._SquashOutcome:
    """Return the uniform failure result while leaving commits intact."""
    return models._SquashOutcome(error=error)


def _squash_commit_env() -> dict[str, str]:
    """Return the hardened agent identity used for the squash commit."""
    return {
        **os.environ,
        **commands._GIT_NO_PROMPT_ENV,
        "GIT_AUTHOR_NAME": config.AGENT_GIT_NAME,
        "GIT_AUTHOR_EMAIL": config.AGENT_GIT_EMAIL,
        "GIT_COMMITTER_NAME": config.AGENT_GIT_NAME,
        "GIT_COMMITTER_EMAIL": config.AGENT_GIT_EMAIL,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def _rollback_squash(
    gate,
    restored: str,
    reason: str,
    error: str,
    reported: models._SquashOutcome | None = None,
) -> models._SquashOutcome:
    """Restore the original branch after a post-reset failure or refusal.

    `restored` is the head the collapsed commits are still reachable from,
    which the caller holds and this owner could not read: a plan took it
    before the reset, or a record wrote it down before the process that made
    that plan died.

    `reported` is what the caller wants said about it, for the one road that
    restores the branch without a failure to park over: a publication the gate
    REFUSED has already worded its own notice, and a second one on top of it
    would describe a squash that did not fail. Left unset the answer is the
    failure below, which is what every rollback after a real one reports.

    The debt the reset just abandoned goes with it, and only once the reset
    has actually happened. The size gate approves the squashed commit before
    it is pushed and records it as one still owed a publication; a reset that
    LANDED puts the branch back on the pre-squash head, so that commit is not
    on this branch any more and only the reflog still has it. Left standing
    there, the reconciliation ahead of every handler finds an approval whose
    commit the checkout is not on and stops the tick, poll after poll, for a
    publication that is never coming.

    A reset that FAILED is the opposite state wearing the same failure: the
    branch may still be standing on the squashed commit, and the approval is
    the only record naming the one commit this issue may publish. Dropped
    there, the debt is gone durably while the work it is for is still at HEAD
    -- so the retry has nothing to ask for by id, and the next tick measures
    whatever the checkout became instead of republishing what was approved.
    So the two are ordered: the reset is proved first, and the record follows
    it rather than the intent.

    The reset takes the REF and the index and leaves the working tree alone,
    which is the whole difference between restoring a branch and destroying
    work. A squash is a collapse rather than an edit -- the commit it makes
    has the same tree as the head it replaces -- so on a checkout nobody
    touched the two modes land in exactly the same place. They part where
    somebody wrote to the worktree between the squash and the reading that
    refused it, which is the gate's FIRST refusal: a tree that is not provably
    clean. Taking the working tree too would throw that edit away to undo a
    squash it had nothing to do with, and it is the one repair a human cannot
    get back. Left where it is, it survives the restore as the uncommitted
    change it was, and the retry refuses on the same tree until it is settled.
    """
    rollback_result = commands._git_hardened(
        "reset", "--mixed", restored, cwd=gate.worktree,
    )
    if rollback_result.returncode != 0:
        log.error(
            "issue=#%s rollback to %s after %s failed; worktree may be "
            "in an inconsistent state and the approved commit's debt is "
            "left standing for it: %s",
            gate.issue.number,
            restored,
            reason,
            (rollback_result.stderr or "").strip(),
        )
        return reported or _squash_failure(error)
    _gated_rewrite()._forgets_the_rollback(gate, restored)
    return reported or _squash_failure(error)


def _create_squash_commit(
    worktree: Path, message: str,
) -> subprocess.CompletedProcess:
    """Create the orchestrator-owned commit with hooks and signing disabled."""
    return subprocess.run(
        [
            "git",
            "-c", "core.hooksPath=/dev/null",
            "-c", "core.fsmonitor=",
            "-c", "commit.gpgsign=false",
            "commit", "-m", message,
        ],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        env=_squash_commit_env(),
        check=False,
    )


def _gated_rewrite():
    """The gate a squash is entered on and publishes through.

    Reached from here by the composed entry point beside this owner too, so
    the hop out of this layer is spelled once. Lazily bound for the reason
    every other hop out of it is: the gate sits in the workflow layer above
    this package, and binding it at module load would make every git-side
    import pay for the stage tree it pulls in.
    """
    from orchestrator.workflow.stages.implementing import late_rewrite
    return late_rewrite


def _rewrite_squash(
    gate,
    branch: str,
    plan: planning._SquashPlan,
    entry,
) -> models._SquashOutcome:
    """Apply a prepared squash, then publish it through the size gate.

    The commit is made BEFORE the measurement because the commit is what gets
    measured: a squash collapses the approved commits into a new object, and
    it is that object -- not the head it replaces -- that the push would put
    on the pull request. Measuring the pre-squash head instead would gate one
    commit and publish another, which is the substitution the whole contract
    refuses.

    A held candidate is not a failure and is deliberately NOT rolled back. The
    gate has taken the issue to the adjudication and the squashed commit is
    what an authorized settlement publishes from this branch, so restoring the
    pre-squash head would leave the record naming a commit that no longer
    exists here.
    """
    collapsed = _gated_rewrite()._collapse_of(
        head=plan.original_head,
        base_sha=plan.base_sha,
        count=plan.count,
    )
    reset_result = commands._git_hardened(
        "reset", "--soft", plan.base_sha, cwd=gate.worktree,
    )
    if reset_result.returncode != 0:
        detail = (reset_result.stderr or "").strip()
        # Nothing was rewritten, so the record of what this rewrite was about
        # describes a collapse that did not happen. Left standing it would
        # send the next tick's recovery at a branch still carrying every
        # commit it names. The park the caller takes is what makes it durable.
        _gated_rewrite()._forgets_the_collapse(gate.state)
        return _squash_failure(f"reset --soft failed: {detail}")

    commit_result = _create_squash_commit(gate.worktree, plan.message)
    if commit_result.returncode != 0:
        detail = (commit_result.stderr or "").strip()
        return _rollback_squash(
            gate,
            collapsed.head,
            "squash commit",
            f"squash commit failed: {detail}",
        )

    new_sha = verification_probes._head_sha(gate.worktree)
    if not new_sha:
        return _rollback_squash(
            gate,
            collapsed.head,
            "post-commit head read",
            "could not read new HEAD after squash",
        )
    return _published_squash(gate, branch, entry, new_sha, collapsed)


def _published_squash(
    gate,
    branch: str,
    entry,
    new_sha: str,
    collapsed,
) -> models._SquashOutcome:
    """Measure the squashed commit, publish it, or leave it to be adjudicated.

    `collapsed` is the base the commits were collapsed onto and the head they
    were collapsed from, because the gate needs both ends of BOTH
    contributions to recognize a rewrite of a change a human already
    adjudicated. Neither is derivable here: a plan took the pair while the
    branch was still intact, or the pinned record wrote it down before the
    process that made that plan died, and both hand it in for the same reason.
    The pre-squash head is that pair's own rather than whatever the pull
    request is standing on: the two are checked against each other when the
    entry is frozen, but that check has a carve-out for a tip a durable record
    says this issue's own push put there, so the remote head is the head a
    push is LEASED against and only the pair says which commit was collapsed.

    Its count is what the handoff behind a landed publication announces, and
    it travels in the same record for the same reason: past the reset the
    commits it counts are off the branch.

    A push that lands does NOT end the collapse here, and the record of it is
    deliberately left standing: the count it holds is what the handoff behind
    this call still has to announce, and the notice, the watermarks, and the
    relabel are all ahead of it. The stage that finishes the handoff is what
    drops it, in the write it makes before the relabel -- so a tick that dies
    anywhere between here and there comes back to a record still standing over
    a branch the recovery reads again and answers the same way: the pull
    request already carries the commit, so the republication is the leased
    no-op it should be and the handoff finishes with the count it still holds.

    A hold is not one state, and only some of them leave the rewrite standing.
    Where the push landed, where the adjudication now owns the commit, or
    where something committed over the checkout, the squash is somebody's and
    the branch is left exactly as this call leaves it. Where the gate REFUSED
    instead -- a pull request a human closed mid-rewrite, a head somebody
    moved under it -- the squash is a local commit nobody measured and nobody
    published, and the branch goes back: left rewritten, the retry finds ONE
    commit, takes the nothing-to-squash road, and reports success without
    measuring or pushing anything at all.

    The refusal still reports `held`. The gate has already parked with the
    notice its own reading earned, and a squash-failed park on top of it would
    describe a failure that did not happen.

    A push that did not go out is rolled back with ONE exception, and it is
    the one where the remote is already standing on the commit. Such a push
    sends nothing, so a request that fails there is a transport failure over
    work the pull request has: reset, the checkout would come off a commit the
    remote carries and the record would go with it -- taking the count the
    handoff still owes a notice, and leaving the next tick a remote that moved
    for reasons nothing on the comment explains.

    Two readings say the remote is there and the ENTRY is the stronger of
    them, because it is a reading of the pull request taken this tick: a tip
    it froze equal to the commit about to be pushed is the pull request
    already carrying it. The entry only admits such a tip where a durable
    record accounts for it -- the approval that owes this commit a push, the
    generation that names it, the receipt dated to this attempt -- so it is
    the whole window a crash between a push and its receipt leaves, where the
    receipt itself is exactly what is missing. That receipt is asked beside
    it, for the road where nothing read the remote at all.

    Neither can fire on a fresh squash, and that is what leaves the designed
    rollback intact: the entry there was frozen before the commit existed, so
    it names the head this rewrite replaced and never the object it produced.
    The approval the gate wrote before the push, and the permission a transfer
    held, are records a reset is SUPPOSED to drop, so neither of them is asked
    here.
    """
    gated = _gated_rewrite()
    published = gated._publishes_rewrite(
        gate, branch, entry, new_sha,
        gated._Collapsed(head=collapsed.head, base_sha=collapsed.base_sha),
    )
    if published.held:
        if gated._rewrite_stands(gate, new_sha):
            return models._SquashOutcome(held=True)
        return _rollback_squash(
            gate,
            collapsed.head,
            "a publication the size gate refused",
            "the size gate refused this publication",
            models._SquashOutcome(held=True),
        )
    if not published.landed:
        if entry.published_sha == new_sha or gated._already_published(
            gate.state, collapsed.head, new_sha, entry.pr_number,
        ):
            return _squash_failure(_UNCONFIRMED_PUBLICATION.format(
                squashed=new_sha,
            ))
        return _rollback_squash(
            gate,
            collapsed.head,
            "force-push",
            "force-push with lease rejected (concurrent update on the "
            "remote, or lease violation); see orchestrator logs",
        )
    return models._SquashOutcome(
        success=True, sha=new_sha, count=collapsed.count,
    )
