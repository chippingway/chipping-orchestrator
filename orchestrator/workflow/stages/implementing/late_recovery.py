# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Route size-gate park recovery before another developer can run.

Repair the authorship ledger and restore a held authorization park before
reading replies. Measurement and restored-candidate recovery go through
`late_candidate_recovery`; authorization commands and their held watermarks
belong to `late_authorization_recovery`. The order prevents an unanswered
park from reaching the ordinary agent resume.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.implementing import (
    late_authorization_recovery as _late_authorization_recovery,
    late_authorship as _authorship,
    late_candidate_recovery as _late_candidate_recovery,
    late_rollback as _rollback,
)


def _recovers_a_late_park(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState
) -> bool:
    """Every park the size gate takes, answered before anything is spawned.

    A sentence of ours the write recording it never reached is repaired ahead
    of all three, because everything below reads the authorship ledger to tell
    our own prose from a human's: run after, the park's reading has already
    handed the tick back and the resume has already spawned a developer
    against our own notice.

    None of them is a park a human can talk their way out of, which is what
    puts them together and what puts them here. One is owed another READING,
    one another LOOK at the checkout, and one a DECISION nothing but a named
    command can be, and on all three the work in question is committed
    already -- so what they must never reach is the spawn below, which would
    buy a second developer run for an implementation the first one finished.
    """
    if _authorship._recovers_a_stranded_sentence(issue, state):
        gh.write_pinned_state(issue, state)
        return True
    if _rollback._restores_the_held_park(gh, issue, state):
        return True
    if _late_candidate_recovery._try_recover_late_measurement_park(gh, spec, issue, state):
        return True
    if _late_authorization_recovery._try_recover_unauthorized_exemption_park(gh, spec, issue, state):
        return True
    return _late_candidate_recovery._try_recover_moved_candidate_park(gh, spec, issue, state)
