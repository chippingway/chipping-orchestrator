# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Activity and continuation gates around artifact maintenance.

Every unreadable guard refuses action. A claim protects a running issue,
checkout activity protects recent work, and continuation stops a bounded pass."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

from orchestrator.git.worktrees import (
    activity_evidence as _activity_evidence,
    candidates as _candidates,
    maintenance_results as _maintenance_results,
    models as _models,
)

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


def _activity_reason(
    artifacts: _candidates.IssueArtifacts,
) -> tuple[_maintenance_results.MaintenanceReason | None, str]:
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
