# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the refresh may touch a discovered worktree at all, asked in order.

The refresh walks a directory of checkouts knowing nothing about any of them,
so before a rewrite can be considered something has to say which directories
name an issue, whether that issue still reads, and whether anything on it
holds its branch still. Those answers live together because they are one kind
of answer -- a refusal that ends the sync before any rewrite is attempted --
and because the order they are asked in is a property of its own: an
operator's hard-skip comes first, then every record that costs no read of the
checkout, then the read-only conversation stages and the parks they leave
behind, and last the one gate that does pay for a read, so an issue some
cheaper answer already froze never pays for it.

Which records freeze a branch, and what ends each freeze, is the `frozen`
owner's. What is added here is where in that order each is asked and -- for
the two no write ever ends -- whether the stage that still has to act on the
commit holds the issue.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator.git.base_sync import frozen as _frozen
from orchestrator.git.base_sync.state import (
    _AUTO_REBASE_PARK_REASONS,
    _PENDING_PUSH_SHA,
    _PR_REFRESH_DETOUR_LABELS,
    log,
)
from orchestrator.github import (
    client as _client,
    labels as _labels,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.state import WorkflowLabel

_READ_ONLY_STAGE_LABELS: tuple[str, ...] = (
    str(WorkflowLabel.QUESTION), str(WorkflowLabel.DISCUSSION),
)

# The stages that still have to ACT on a commit their own records name: the
# size gate under `implementing`, and the adjudication that writes an
# exemption a relabel has not carried out of `decomposing` yet. Past them the
# issue belongs to review, where a pushed branch is kept in step with base by
# the PR-aware sync rather than by holding it still.
_DECIDED_STAGE_LABELS: tuple[str, ...] = (
    str(WorkflowLabel.IMPLEMENTING), str(WorkflowLabel.DECOMPOSING),
)


def _issue_worktree_number(worktree: Path) -> int | None:
    """Return an issue number only for a valid issue worktree directory."""
    if not worktree.is_dir() or not worktree.name.startswith("issue-"):
        return None
    try:
        return int(worktree.name[len("issue-"):])
    except ValueError:
        return None


def _base_sync_issue(
    gh: _client.GitHubClient, issue_number: int,
) -> Issue | None:
    """Return the issue for a worktree, or None when it is not retrievable."""
    try:
        return gh.get_issue(issue_number)
    except Exception:  # noqa: BLE001 - an unretrievable issue is skipped, not raised through
        log.debug(
            "issue=#%d not retrievable; skipping base sync", issue_number,
        )
        return None


def _issue_skips_base_sync(
    issue: Issue,
    issue_number: int,
    state: _pinned_state.PinnedState,
    worktree: Path,
) -> bool:
    """Apply dispatcher hard-skips and the conversation stage gate.

    Neither conversation stage builds anything in its checkout, so the tree
    under one of their labels is something to read rather than work in
    progress: an inspection target an unsafe park left for an operator, and --
    in the discussion stage, which keeps its tree on every exit short of the
    terminal that finishes the issue -- the tree the next round opens on.
    Rebasing `origin/<base>` over either would rewrite the state someone was
    parked to look at.

    The discussion stage does push, once: the plan its humans confirmed, on the
    branch and at the SHA its own check read. That is the sharper reason to
    stand down rather than a reason not to. A rebase between that reading and
    the push would move the branch off the commit that was validated, and the
    same rebase after publication would move it off the tip the PR is open
    against and the record vouches for.

    The label answers that only while the stage still holds the issue, so the
    park is consulted beside it. An operator's relabel takes the label away a
    full tick before the implementing guard reads the recorded round tip and
    rules on the branch, and this refresh runs first in that tick: a rebase in
    the gap moves the tip off the anchor and the guard convicts a branch
    nobody touched. Its refusal then asks for a reset back to that same
    anchor, which only hands the next tick the same rebase to redo. The
    checkout therefore stays frozen until the guard's own write clears the
    park, from which tick on the branch syncs normally again.

    The records that freeze a branch on their own, the two parks that freeze
    one with no record behind them, and the two that freeze only while the
    checkout still stands on the commit they name are all the `frozen`
    owner's; what belongs here is where in the order they are asked, and --
    for the last two -- whether the stage that has to act on that commit still
    has the issue.
    A discussion round or publication left in flight freezes the branch on the
    same terms and without any park at all. Those records are written before
    the thing they describe, so a tick that died mid-round leaves one standing
    with `awaiting_human` false -- and the commit it died holding is on the
    branch. Rebasing over it moves the tip off the anchor its own stage will
    measure it against, and on a PR-backed issue the PR-aware route would push
    that rewrite over a plan PR the publication may already have opened.

    Clearing the park does not end the freeze, because the guard replaces it
    with `read_only_baseline_sha` -- the tip it certified, which the dev run
    is measured against until that run commits something. A rebase would move
    the branch off that SHA while the inherited commits it names are still
    there, and the spawn path would then read them as a dev run whose
    publication was interrupted and push them without an agent ever running.
    The baseline is retired the moment there is committed work to publish, so
    this holds for the ticks the dev spends answering rather than building.

    The accepted commit is asked LAST, because it is the only gate here that
    costs a read of the checkout: an exemption on an issue some cheaper answer
    already froze never pays for it.
    """
    skip_label = _labels.hard_skip_control_label(issue)
    if skip_label is not None:
        log.debug(
            "issue=#%d has %r; skipping base sync",
            issue_number,
            skip_label,
        )
        return True
    if _state_holds_the_branch(issue_number, state):
        return True
    park_reason = state.get("park_reason") if state.get("awaiting_human") else None
    for stage_label in _READ_ONLY_STAGE_LABELS:
        if _labels.issue_has_label(issue, stage_label):
            log.debug(
                "issue=#%d has %r label; skipping base sync (read-only stage)",
                issue_number,
                stage_label,
            )
            return True
        if isinstance(park_reason, str) and park_reason.startswith(f"{stage_label}_"):
            log.debug(
                "issue=#%d carries an unconsumed %r park; skipping base sync",
                issue_number,
                park_reason,
            )
            return True
    return _stands_on_an_unhanded_commit(
        issue, worktree, issue_number, state,
    )


def _stands_on_an_unhanded_commit(
    issue: Issue,
    worktree: Path,
    issue_number: int,
    state: _pinned_state.PinnedState,
) -> bool:
    """Whether a commit this issue still owes a step holds its branch still.

    The records that name a COMMIT rather than a step are the `frozen`
    owner's, and so is the reading that asks the checkout for one. What
    belongs here is the half that owner cannot ask: whether the stage which
    has to act on the commit still has the issue.

    Neither of those records is ended by a write -- an exemption is never
    cleared at all, and a publication record is overwritten rather than spent
    -- so on their own they take a branch out of the base refresh for the rest
    of its issue's life. Past the handoff that is exactly wrong: the commit is
    on the remote with a pull request over it, and keeping that in step with
    base is the PR-aware sync's own job, which is the only route that can move
    it without stranding the reviewer's SHA. So the freeze lasts as long as
    the stage that reads these records does -- the gate that must not
    re-measure an accepted commit, and the handoff that has to find the pushed
    one where it left it when its relabel did not land -- and ends with the
    label that hands the issue on.
    """
    if not any(
        _labels.issue_has_label(issue, stage_label)
        for stage_label in _DECIDED_STAGE_LABELS
    ):
        return False
    return _frozen._stands_on_a_decided_commit(worktree, issue_number, state)


def _state_holds_the_branch(
    issue_number: int, state: _pinned_state.PinnedState,
) -> bool:
    """Whether the pinned comment alone holds this branch still.

    The answers that cost no read of the checkout, together because they are
    the same kind of answer: an unspent record some stage wrote before the
    thing it describes, and the two parks that are waiting on this branch's
    own commit. Those are parks rather than records because neither can leave
    one -- a size refusal that came before any commit could be named has none
    to write, and a timeout's watermark names the tip the run started at
    rather than anything it produced -- and a branch rebased under either
    leaves its recovery with nothing it can be answered from.
    """
    held = _frozen._held_records(state)
    if held:
        log.debug(
            "issue=#%d holds unspent read-only state (%s); skipping base sync",
            issue_number, ", ".join(held),
        )
        return True
    if _frozen._awaits_a_commit_of_its_own(state):
        log.debug(
            "issue=#%d is parked on %r, which is waiting on a commit of this "
            "branch's own; skipping base sync until it is answered",
            issue_number, state.get("park_reason"),
        )
        return True
    return False


def _recovery_holds_dispatch(
    issue: Issue,
    label: str | None,
    state: _pinned_state.PinnedState,
    worktree: Path,
) -> bool:
    """Whether an unfinished auto-rebase attempt holds this issue's handler.

    The anchor is this refresh's to answer, and the refresh answers it ahead
    of every handler -- but only on a tick that REACHES it. A pull request
    that would not read, a base lag that would not count, an issue that would
    not fetch: each returns before the recovery runs and leaves the anchor
    exactly where it was. The handler behind the dispatcher then runs over a
    checkout standing on a replay no push has published -- a reviewer spawned
    on `validating`, a developer resumed on `fixing` -- which is precisely the
    agent an interrupted rebase must not cost. So the dispatcher defers while
    the anchor stands, and the next tick's refresh gets the recovery back.

    Only while the refresh CAN get it back, because every other hold is a
    deadlock. Three shapes are released by something other than the refresh,
    and each of them lets the handler run:

    * A label the refresh does not drive. The refresh answers an anchor there
      without reading any pull request -- a clear, or the stranded park -- so
      there is nothing transient for a hold to wait out.
    * An issue the refresh skips outright, for any of the freezes above. Those
      are records the dispatcher's own reconciliation answers, and it is
      behind this question; held here, the record that keeps the refresh away
      is never answered and the anchor is never reached.
    * A park some STAGE left. The refresh leaves such a park intact rather than
      rebasing past it, and only the handler that wrote it can take it down.

    A park the refresh left is held like any other tick, since every stage
    handler short-circuits on one anyway and the reply that releases it is the
    refresh's own to recognize.

    Asked of the label the dispatcher resolved rather than read again, so the
    handler this holds back and the stage this reads are the same one.
    """
    if not state.get(_PENDING_PUSH_SHA):
        return False
    if label not in _PR_REFRESH_DETOUR_LABELS:
        return False
    if state.get("awaiting_human") and (
        state.get("park_reason") not in _AUTO_REBASE_PARK_REASONS
    ):
        return False
    return not _issue_skips_base_sync(
        issue, int(issue.number), state, worktree,
    )
