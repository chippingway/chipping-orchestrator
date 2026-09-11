# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The bounded pass that spends a classification on a finished issue's artifacts.

The one place in this domain that deletes something nobody asked it to delete.
Everything under it is a reading -- the discovery in ``discovery``, the
classification in ``eligibility``, the fail-closed probes in ``evidence``,
``claims``, and ``commit_claims`` -- and this module is where those readings
are turned into three mutations and one answer per candidate.

What it does NOT touch is as much of its contract as what it does. No workflow
label is written, no pinned state, no comment, and no agent session is started
or stopped: an issue that has ended keeps every record of how it ended, and a
host tidying its own disk must not be able to change what GitHub says happened.
The artifacts are the whole of what this pass owns.

Every gate in front of the mutation fails closed, and they are asked cheapest
first. Whether something is running for this issue right now is asked of an
injected guard, because the answer lives in the process the pass runs beside --
the scheduler holding a claim, a worker mid-tick -- and this layer may not
reach up into the workflow to find it. Then the classification, which is where
the issue's own ending, the pull requests still standing on the branches, and
every reading of the artifacts are established. Then, last and only for a
candidate everything else cleared, whether the checkout has been touched
lately: a tree nobody proved is not one whose modification time says anything.

The mutations are ordered by what git allows and by what a failed pass has to
leave behind. The checkout goes first because a branch checked out somewhere
cannot be deleted. Each branch is then taken on the remote before the clone,
so a remote delete that fails leaves the local ref standing -- and a local ref
is what makes the candidate discoverable again, where a remote-only artifact
would be found only by the next listing of the remote. A pass that stops leaves
everything it had not reached exactly where it was; nothing is written down,
because the discovery that found the candidate once finds what is left of it
again. That is what makes an interrupted pass cost nothing to resume and a
repeated one report the parts already gone as done.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from types import MappingProxyType

from orchestrator.git.worktrees import eligibility, evidence, models as _models, reclaim
from orchestrator.github.client import GitHubClient

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so every artifact this pass takes or
# refuses to take reports where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

# Whether anything is currently running for one repository's issue, asked as
# the scheduler's own question is spelled: the repository slug and the issue
# number, and nothing about the artifacts. Injected rather than imported
# because the answer belongs to the process this pass runs beside, and this
# layer may not reach up into the workflow that owns it.
ActivityGuard = Callable[[str, int], bool]

# Whether this pass may still act at all, asked with nothing in hand: it is
# about the process rather than about a candidate. Injected for the same reason
# the activity guard is -- what ends a pass early is a signal this layer never
# sees and a hold it did not take.
#
# Asked twice per candidate, and both places are boundaries a pass can stop on
# without leaving a teardown half spent: before the candidate is looked at, and
# again as the last thing before the first mutation. The second is what makes
# the first worth anything, since everything expensive happens in between --
# the issue, the pull requests, the remote, every reading the deletions are
# pinned to -- and a signal that landed in the middle of all that would
# otherwise be answered by going ahead and deleting.
ContinuationGuard = Callable[[], bool]

# How long a checkout is left alone after the last thing that touched it. An
# hour is longer than any tick and any agent run's gap between writes, and
# short enough that a host finishing its day's work has its disk back the same
# day. It is a constant rather than a setting because it is a safety margin
# around a deletion, not a knob an operator tunes: what a shorter one buys is
# the chance to delete a tree somebody is standing in.
_QUIET_PERIOD_SECONDS = 3600

# Which outcome each reason is, fixed here so the two fields of a result
# cannot disagree. A retention is the pass declining to act, a failure is a
# step that ran and was refused, and the one reason that cleans is the one
# that reached the end of the teardown.
_OUTCOMES = MappingProxyType({
    _models.MaintenanceReason.RECLAIMED: _models.MaintenanceOutcome.CLEANED,
    _models.MaintenanceReason.UNPROVEN: _models.MaintenanceOutcome.RETAINED,
    _models.MaintenanceReason.RECENT_ACTIVITY: _models.MaintenanceOutcome.RETAINED,
    _models.MaintenanceReason.ACTIVITY_UNREADABLE: _models.MaintenanceOutcome.RETAINED,
    _models.MaintenanceReason.ACTIVE_CLAIM: _models.MaintenanceOutcome.RETAINED,
    _models.MaintenanceReason.CLAIM_UNREADABLE: _models.MaintenanceOutcome.RETAINED,
    _models.MaintenanceReason.TIP_MOVED: _models.MaintenanceOutcome.RETAINED,
    _models.MaintenanceReason.TIP_UNREADABLE: _models.MaintenanceOutcome.RETAINED,
    _models.MaintenanceReason.BRANCH_CHECKED_OUT: _models.MaintenanceOutcome.RETAINED,
    _models.MaintenanceReason.WORKTREE_REMOVAL_FAILED: _models.MaintenanceOutcome.FAILED,
    _models.MaintenanceReason.REMOTE_DELETE_FAILED: _models.MaintenanceOutcome.FAILED,
    _models.MaintenanceReason.LOCAL_DELETE_FAILED: _models.MaintenanceOutcome.FAILED,
})


def _answered(
    candidate: _models.MaintenanceCandidate,
    reason: _models.MaintenanceReason,
    subject: str = "",
    retentions: tuple[_models.Retention, ...] = (),
) -> _models.MaintenanceResult:
    """One candidate's answer, with the outcome its reason fixes."""
    return _models.MaintenanceResult(
        candidate=candidate,
        outcome=_OUTCOMES[reason],
        reason=reason,
        subject=subject,
        retentions=retentions,
    )


def _claim_reason(
    artifacts: _models.IssueArtifacts, claimed: ActivityGuard,
) -> _models.MaintenanceReason | None:
    """Whether something is running for this issue, or could not be asked.

    First of the gates, because it is the only one that costs nothing and the
    only one whose answer can change under the pass: an issue a worker picks up
    while the classification is being taken is one whose artifacts are about to
    be written in.

    The boundary is total. The guard belongs to the caller, so what it does
    when it fails is not something this module can know -- and an exception out
    of one candidate's guard would otherwise end the pass for every candidate
    behind it.
    """
    try:
        active = claimed(artifacts.spec.slug, artifacts.issue_number)
    except Exception:
        log.warning(
            "issue=#%d could not be asked whether anything is running for it; "
            "leaving its artifacts alone",
            artifacts.issue_number, exc_info=True,
        )
        return _models.MaintenanceReason.CLAIM_UNREADABLE
    return _models.MaintenanceReason.ACTIVE_CLAIM if active else None


def _activity_reason(
    artifacts: _models.IssueArtifacts,
) -> tuple[_models.MaintenanceReason | None, str]:
    """Whether this candidate's checkouts have been left alone long enough.

    Asked of every checkout the issue holds, since an issue that was in flight
    when slug namespacing landed can be sitting in two of them and either one
    is a tree somebody may still be standing in. A branch has no tree to be
    disturbed, so a candidate with no checkout has nothing to ask.

    Asked last, because a modification time is only worth reading about a tree
    that has already been established as this issue's own.
    """
    since = time.time() - _QUIET_PERIOD_SECONDS
    for worktree in artifacts.worktrees:
        quiet = evidence._quiet_checkout(worktree, since)
        if quiet is _models.ProbeAnswer.REFUTED:
            return _models.MaintenanceReason.RECENT_ACTIVITY, str(worktree)
        if quiet is _models.ProbeAnswer.UNREADABLE:
            return _models.MaintenanceReason.ACTIVITY_UNREADABLE, str(worktree)
    return None, ""


def _kept_subject(verdict: _models.ArtifactVerdict) -> str:
    """The artifact the first reason a classification kept this candidate for names."""
    return verdict.retentions[0].subject if verdict.retentions else ""


def _cleared_tips(proven: tuple[_models.ProvenTip, ...]) -> dict[str, str]:
    """The commit each cleared artifact was standing on, by the artifact's name.

    Keyed the way a proof spells its subject -- a branch by name, a checkout by
    path -- so a teardown looking one up names the artifact exactly as the
    classification did rather than deriving a second spelling of it.
    """
    return {tip.subject: tip.sha for tip in proven}


def _checkout_stop(
    worktree: Path, proven: str | None,
) -> _models.MaintenanceReason | None:
    """Whether the checkout is still standing on the commit that was cleared.

    The last reading before the tree comes down, and it is about the commit
    rather than the tree: a linked worktree holds its HEAD and reflog on its
    own, so removing it takes whatever that HEAD names -- and between the proof
    and here, an agent committing moves it to something nobody cleared.

    A candidate with no proof for its checkout is refused rather than removed.
    An eligible verdict always carries one, so reaching this means the two
    halves disagree, and the only safe reading of that is that nothing was
    established.
    """
    tip = evidence._checkout_tip(worktree)
    if proven is None or tip.answer is not _models.ProbeAnswer.CONFIRMED:
        return _models.MaintenanceReason.TIP_UNREADABLE
    if tip.sha != proven:
        return _models.MaintenanceReason.TIP_MOVED
    return None


def _take_checkouts(
    candidate: _models.MaintenanceCandidate, cleared: dict[str, str],
) -> _models.MaintenanceResult | None:
    """Take every checkout of this candidate down, or say where the pass stops.

    None is the step being done -- every tree removed, or none of them there in
    the first place -- and a result is the pass ending on one of them. They all
    run before any branch because git refuses to delete a branch a worktree
    still has checked out, so a pass that took the branches first would leave
    the trees standing and the branches beside them undeletable.

    Both layouts are taken, in the order the scan reported them. An issue that
    was in flight when slug namespacing landed can be sitting in the flat
    checkout it started in and the per-repository one the next tick made, and a
    pass that took only one of them would report the issue cleaned with a tree
    still on disk that nothing would ever discover again.
    """
    for worktree in candidate.artifacts.worktrees:
        stopped = _take_checkout(candidate, worktree, cleared)
        if stopped is not None:
            return stopped
    return None


def _take_checkout(
    candidate: _models.MaintenanceCandidate,
    worktree: Path,
    cleared: dict[str, str],
) -> _models.MaintenanceResult | None:
    """Take one checkout down, or say why the pass stops on it."""
    stopped = _checkout_stop(worktree, cleared.get(str(worktree)))
    if stopped is not None:
        return _answered(candidate, stopped, str(worktree))
    removed = reclaim._remove_recognized_worktree(
        candidate.artifacts.spec, worktree,
    )
    if removed:
        return None
    return _answered(
        candidate, _models.MaintenanceReason.WORKTREE_REMOVAL_FAILED, str(worktree),
    )


def _take_remote_branch(
    candidate: _models.MaintenanceCandidate, branch: str, proven: str,
) -> _models.MaintenanceResult | None:
    """Take one branch off the remote, or say why the pass stops here.

    The remote is asked what it carries before the delete is sent, so the three
    answers stay apart: a branch that is not there is a step already done -- the
    ordinary shape of a merged pull request's head -- a branch at another commit
    is a push nobody here cleared, and a reading that failed is not permission
    to delete anything.

    The delete itself is leased to the same commit, so the answer above is not
    what the deletion rests on: between this read and that push the branch can
    move again, and the remote is what refuses it then.
    """
    spec = candidate.artifacts.spec
    published = evidence._published_tip(spec, branch)
    if published.answer is _models.ProbeAnswer.UNREADABLE:
        return _answered(candidate, _models.MaintenanceReason.TIP_UNREADABLE, branch)
    if published.answer is _models.ProbeAnswer.REFUTED:
        return None
    if published.sha != proven:
        return _answered(candidate, _models.MaintenanceReason.TIP_MOVED, branch)
    if reclaim._delete_remote_branch_at(spec, branch, proven):
        return None
    return _answered(candidate, _models.MaintenanceReason.REMOTE_DELETE_FAILED, branch)


def _take_local_branch(
    candidate: _models.MaintenanceCandidate, branch: str, proven: str,
) -> _models.MaintenanceResult | None:
    """Take one branch out of the clone, or say why the pass stops here.

    Reached only once the remote's copy is gone, which is what keeps a failed
    pass discoverable: the local ref is the cheapest thing the next discovery
    finds, so it is the last artifact of a candidate to go.

    A branch the clone no longer has is a step already done. Anything else is
    put to the pinned delete, which refuses the branch that has moved -- the
    reading here only decides whether there is a deletion to attempt at all.
    """
    spec = candidate.artifacts.spec
    tip = evidence._local_branch_tip(spec, branch)
    if tip.answer is _models.ProbeAnswer.REFUTED:
        return None
    if tip.answer is _models.ProbeAnswer.UNREADABLE:
        return _answered(candidate, _models.MaintenanceReason.TIP_UNREADABLE, branch)
    if tip.sha != proven:
        return _answered(candidate, _models.MaintenanceReason.TIP_MOVED, branch)
    if reclaim._delete_local_ref_at(spec, branch, proven):
        return None
    return _answered(candidate, _models.MaintenanceReason.LOCAL_DELETE_FAILED, branch)


def _take_branches(
    candidate: _models.MaintenanceCandidate, cleared: dict[str, str],
) -> _models.MaintenanceResult | None:
    """Take every cleared branch of this candidate, in the order it was named.

    Each branch goes remote-side first and then locally, rather than every
    remote and then every local, so a candidate carrying both layouts leaves
    one whole branch behind rather than two half-taken ones when a pass stops.

    A branch nothing cleared ENDS the pass rather than being passed over. It
    is a branch the discovery named and the classification found on neither
    host, so nothing about it was established -- and a name that is gone at one
    reading can be back at the next, pushed by a run this pass never saw. The
    candidate is kept, which costs one more pass of an artifact that has really
    gone: the next discovery does not name it, and that pass reports the rest
    cleaned.

    Which branches some tree of this clone is still standing on is read once
    here, after every checkout of this candidate has come down and before any
    branch goes. It is read at all because the plumbing delete does not ask:
    `branch -D` refuses a branch a worktree is on and `update-ref -d` takes it
    without a word, leaving that tree holding a HEAD nothing resolves. The
    trees that can be on it are not only this candidate's -- an operator's own
    `worktree add` is on the branch just as squarely, and so is a checkout this
    scan could not attribute.

    The first stop ends the candidate. What is left is exactly what the next
    discovery finds, and going on past a refusal would spend deletions on a
    host that has just said it is not in the state anybody read.
    """
    standing = evidence._checked_out_branches(candidate.artifacts.spec)
    for branch in candidate.artifacts.branches:
        stopped = _take_branch(candidate, branch, cleared, standing)
        if stopped is not None:
            return stopped
    return None


def _take_branch(
    candidate: _models.MaintenanceCandidate,
    branch: str,
    cleared: dict[str, str],
    standing: frozenset[str] | None,
) -> _models.MaintenanceResult | None:
    """Take one branch off both hosts, or say why the pass stops on it.

    A listing that could not be taken keeps the branch, as every unread
    question here does: without it nothing establishes that no tree is standing
    on the ref about to be deleted.
    """
    proven = cleared.get(branch)
    if proven is None:
        return _answered(candidate, _models.MaintenanceReason.TIP_UNREADABLE, branch)
    if standing is None:
        return _answered(candidate, _models.MaintenanceReason.TIP_UNREADABLE, branch)
    if branch in standing:
        return _answered(
            candidate, _models.MaintenanceReason.BRANCH_CHECKED_OUT, branch,
        )
    return (
        _take_remote_branch(candidate, branch, proven)
        or _take_local_branch(candidate, branch, proven)
    )


def _reclaimed(
    candidate: _models.MaintenanceCandidate, proven: tuple[_models.ProvenTip, ...],
) -> _models.MaintenanceResult:
    """Run the whole teardown for one cleared candidate, and say where it got to."""
    cleared = _cleared_tips(proven)
    stopped = (
        _take_checkouts(candidate, cleared)
        or _take_branches(candidate, cleared)
    )
    return stopped or _answered(candidate, _models.MaintenanceReason.RECLAIMED)


def _maintained_candidate(
    gh: GitHubClient,
    candidate: _models.MaintenanceCandidate,
    *,
    claimed: ActivityGuard,
    going: ContinuationGuard,
) -> _models.MaintenanceResult | None:
    """Decide about one candidate, and act on it if everything clears it.

    The classification is taken here rather than handed in, because what it
    reads is what the mutations are pinned to: a verdict taken a tick earlier
    would clear commits the artifacts have since left, and the teardown would
    then be spending a proof about branches that no longer exist.

    `None` is the pass being stopped between the readings and the teardown, and
    it is a different answer from every other one here: the others are what
    this candidate IS, and this one is that nothing was decided about it. The
    reading is taken last, immediately before the first mutation, because the
    readings above it are where the seconds go -- an issue, its pull requests,
    what the remote carries -- and a stop that arrived during them may not be
    answered by deleting anyway.

    Once past it the candidate is taken as ONE unit rather than checked again
    between its artifacts. A teardown is a checkout removal and two pinned ref
    deletes, each already leased to a commit and each idempotent; stopping in
    the middle of them would trade a state this vocabulary can report for one
    it cannot, and buy microseconds of earlier exit for it.
    """
    artifacts = candidate.artifacts
    active = _claim_reason(artifacts, claimed)
    if active is not None:
        return _answered(candidate, active, f"#{artifacts.issue_number}")
    verdict = eligibility._classify_artifacts(gh, artifacts)
    if not verdict.eligible:
        return _answered(
            candidate,
            _models.MaintenanceReason.UNPROVEN,
            _kept_subject(verdict),
            verdict.retentions,
        )
    quiet, disturbed = _activity_reason(artifacts)
    if quiet is not None:
        return _answered(candidate, quiet, disturbed)
    if _stopped(going):
        return None
    return _reclaimed(candidate, verdict.proven)


def _stopped(going: ContinuationGuard) -> bool:
    """Whether the pass may no longer act, with an unread answer meaning no.

    Fails closed like every gate in front of a deletion here, and behind a
    total boundary for the reason every injected question carries one: the
    predicate is the caller's, so what it does when it fails is not something
    this module can weigh against the mutations behind it.
    """
    try:
        return not going()
    except Exception:
        log.warning(
            "could not be asked whether the maintenance pass may go on; "
            "stopping it here", exc_info=True,
        )
        return True


def _maintained_candidates(
    gh: GitHubClient,
    candidates: Iterable[_models.MaintenanceCandidate],
    *,
    claimed: ActivityGuard,
    going: ContinuationGuard,
) -> tuple[_models.MaintenanceResult, ...]:
    """Run the pass over every candidate of ONE repository, in its order.

    One client for the lot, so the caller is what splits a discovery spanning
    several repositories: the client is authenticated against one repository,
    and asking it about another's issue number would answer about whatever
    issue happens to carry that number there -- and then delete branches on the
    strength of it.

    Every candidate this pass DECIDED about gets a result, the untouched ones
    included: a caller holding only what was cleaned cannot tell a candidate
    this pass kept from one it never reached, and the second is what a pass
    that died half way through looks like. The candidates behind a stop are
    the ones it decided nothing about, and they get none -- so the answer is
    the prefix it reached, in the order the discovery named them.

    Whether it may still act is asked before EACH candidate rather than once
    for the repository, because what a caller is being asked is not a property
    of the artifacts: a process that has begun stopping has no standing to
    spend the quiet it was granted a moment ago, and one asked a repository at
    a time would spend the whole of the repository it was already inside. The
    candidate itself asks once more before it acts, and answers `None` when
    that reading is what stopped it -- so a stop arriving DURING the readings
    ends the pass here rather than being noticed one candidate later.

    A candidate the pass stops before has no answer at all, which is exactly
    what an interrupted pass has always looked like from here.
    """
    answers: list[_models.MaintenanceResult] = []
    for candidate in candidates:
        answered = None if _stopped(going) else _maintained_candidate(
            gh, candidate, claimed=claimed, going=going,
        )
        if answered is None:
            log.info(
                "issue=#%d artifacts left alone: this pass may no longer act",
                candidate.artifacts.issue_number,
            )
            break
        answers.append(answered)
    return tuple(answers)
