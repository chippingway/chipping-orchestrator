# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Activity, writer-claim, and continuation gates around artifact maintenance.

Every unreadable guard refuses action. A claim protects a running issue, the
issue's writer claim keeps every other orchestrator writer on this host off it
from the first reading through the teardown, checkout activity protects recent
work, and continuation stops a bounded pass."""
from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Callable, Iterator

from orchestrator.git.worktrees import (
    activity_evidence as _activity_evidence,
    candidates as _candidates,
    maintenance_results as _maintenance_results,
    models as _models,
)
from orchestrator.github.client import GitHubClient
from orchestrator.scheduler import writer_claims as _writer_claims

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


def _claim_reason(
    artifacts: _candidates.IssueArtifacts, claimed: ActivityGuard,
) -> _maintenance_results.MaintenanceReason | None:
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
        return _maintenance_results.MaintenanceReason.CLAIM_UNREADABLE
    return _maintenance_results.MaintenanceReason.ACTIVE_CLAIM if active else None


@contextlib.contextmanager
def _issue_claim(
    gh: GitHubClient, artifacts: _candidates.IssueArtifacts,
) -> Iterator[bool]:
    """Hold this candidate's issue writer claim for the body, or say it was not held.

    The claim every dispatch path and the base refresh take for the issue,
    on the one key in the one namespace, so a pass contends with them, and
    with another poller's pass, exactly as two dispatches do. Imported rather
    than injected, unlike the guards above: the claim is a host record under
    `WORKTREES_DIR` rather than a reading of the process this pass runs
    beside, and every holder on the host meets on the same file whoever
    asks.

    Taken without waiting, and `False` is answered the same way whatever
    refused it -- a holder elsewhere, a writer of this process's own, a
    namespace nothing can be locked in, or a repository whose id would not
    read to key the claim on: the candidate is left exactly as it stands,
    with nothing about the issue read. The refusal is said on the claim
    owner's own line, and a key that could not be read is said here.
    """
    try:
        repo_id = gh.repo_id
    except Exception:
        log.warning(
            "issue=#%d repo=%s writer claim could not be keyed: the repository "
            "id would not read; leaving its artifacts alone",
            artifacts.issue_number, artifacts.spec.slug, exc_info=True,
        )
        repo_id = None
    if repo_id is None:
        yield False
        return
    with _writer_claims.issue_writer(
        repo_id, artifacts.issue_number, repo_name=artifacts.spec.slug,
    ) as held:
        yield held


def _activity_reason(
    artifacts: _candidates.IssueArtifacts,
) -> tuple[_maintenance_results.MaintenanceReason | None, str]:
    """Whether this candidate's checkouts have been left alone long enough.

    Asked of the checkout the candidate holds, since it is a tree somebody may
    still be standing in. A branch has no tree to be disturbed, so a candidate
    with no checkout has nothing to ask.

    Asked last, because a modification time is only worth reading about a tree
    that has already been established as this issue's own.
    """
    since = time.time() - _QUIET_PERIOD_SECONDS
    for worktree in artifacts.worktrees:
        quiet = _activity_evidence._quiet_checkout(worktree, since)
        if quiet is _models.ProbeAnswer.REFUTED:
            return _maintenance_results.MaintenanceReason.RECENT_ACTIVITY, str(worktree)
        if quiet is _models.ProbeAnswer.UNREADABLE:
            return _maintenance_results.MaintenanceReason.ACTIVITY_UNREADABLE, str(worktree)
    return None, ""


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
