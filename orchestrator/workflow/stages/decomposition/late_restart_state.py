# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist restart identities and project the fresh cycle onto retained issue usage.

The retired cycle keeps thread attribution and lifetime spending while
dropping its sessions, publications, candidates, and children.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from github.Issue import Issue

from orchestrator.github import (
    client as _client,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import (
    run_ledger as _run_ledger,
)
from orchestrator.workflow.late_split import (
    events as _events,
    lineage as _lineage,
    restart as _restart,
    state as _late_state,
    telemetry as _telemetry,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")


# What survives the projection. Each is a fact about the ISSUE rather than
# about the attempt that just ended, and the group is a whitelist so a key a
# later stage adds is dropped by a restart rather than inherited by one.
#
# The pinned comment's own id is deliberately not here: it is not a field at
# all. The projection rewrites the payload of the comment it was read from, so
# the fresh cycle goes back into the comment every reader already knows.
_RETAINED_KEYS = (
    # The bounded id list every "is this comment ours" reading is taken
    # against. Comments are append-only, so the thread a restarted issue wakes
    # up on is the one the cancelled cycle left -- and a drift baseline or a
    # validating handoff that could no longer recognize the orchestrator's own
    # comments would read them as a human's.
    "orchestrator_comment_ids",
    # What the issue has already cost. These counters are cumulative per ISSUE
    # by construction -- the receipt a terminal posts reports what the whole
    # issue spent, not what one cycle did -- so zeroing them would under-report
    # every attempt after the first.
    "issue_agent_runs",
    "issue_total_tokens",
    "issue_total_cost_usd",
    "issue_cost_sources",
    # What the issue may spend and what it has spent of it, named by the
    # ledger owner rather than copied here, so a field that group grows is
    # kept by this projection without a second edit. A lifetime ceiling a
    # restart handed back would be no lifetime ceiling at all -- a cancelled
    # cycle would be the way to buy another one -- and the allowance travels
    # beside the count for the same reason the receipt's counters do: dropping
    # the ceiling an issue was granted while keeping its spend parks it on the
    # first run of the fresh cycle.
    *_run_ledger.PROJECTED_KEYS,
)


def _identified(
    issue: Issue, state: _pinned_state.PinnedState, generation: LateGeneration,
) -> LateGeneration:
    """This cycle carrying the identity every record of it is correlated by.

    Two of the four identities a record is joined on are re-derived before
    anything is written, and neither is the cycle: that one is the record's
    own, it is what the marker is minted from, and it is the one thing a
    restart may not invent.

    The current issue is THIS issue, always. The pinned comment was read off
    it, so a field naming another one is damage rather than a reading about
    somebody else's issue -- and honoring it would carry that number into the
    projection and into both sinks, filing a fresh cycle and its telemetry
    under an issue this pass is not about.

    The root is kept where the record is this issue's own and re-derived
    otherwise, which is both repairs at once. A record that could not name its
    own issue is one whose remaining lineage claims nothing vouches for; a
    root of no issue at all is a record the telemetry contract refuses
    outright, so the restart would run to completion and say nothing about
    itself on either sink. What it is re-derived from is the ancestry beside
    it -- a fact about the split this issue was CUT from rather than about the
    cycle it ran -- and an owner with no ancestry is the root of its own
    lineage. That is the same chain a cancellation rebuilds a dropped identity
    from.
    """
    ancestry = _lineage.read_late_ancestry(state)
    own_root = (
        generation.root_issue
        if generation.current_issue == issue.number
        else 0
    )
    return replace(
        generation,
        current_issue=issue.number,
        root_issue=own_root or ancestry.root_issue or issue.number,
    )


def _retired(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
) -> None:
    """Retire the marker, leaving the fresh cycle the restart was for.

    Last, and only once both effects have reconciled, because this write is
    what takes the record out of every reading that brought the tick back
    here: the marker is gone, the cancellation is gone, and the issue is an
    ordinary one on an ordinary label from the next tick.

    What it projects is the domain's own answer -- the cycle minted, the issue
    and root it belongs to, and the cycle it succeeds -- laid over a pinned
    comment stripped back to what is true about the issue rather than about
    the attempt.

    Where the issue now IS comes off the marker rather than off the issue. The
    label was applied a moment ago and a client's cached labels survive the
    write that changes them, so reading it back here would say the state the
    issue was in BEFORE the restart -- which for the ordinary entry is no
    state at all, putting `None` in the line an operator reads and in the
    `stage` both sinks file the reconciled record under. The marker named the
    target before either effect ran and is the same value the write carried.
    """
    target = generation.restart_target
    fresh = _restart.retire_restart(generation)
    _projected(state, fresh)
    gh.write_pinned_state(issue, state)
    log.warning(
        "issue=#%d is restarted as late-split cycle %d after cycle %s; every "
        "record of that cycle is dropped and the issue starts over on %r",
        issue.number,
        fresh.cycle_id,
        fresh.restart_predecessor,
        target,
    )
    _telemetry.emit_late_event(
        gh,
        _events.LateEvent(
            family=_events.LateEventFamily.RESTART,
            restart_step=_events.LateRestartStep.RECONCILED,
        ),
        fresh,
        stage=stage_name(target),
    )


def _projected(
    state: _pinned_state.PinnedState, fresh: LateGeneration,
) -> None:
    """Rewrite this pinned comment as the fresh cycle's whole durable state.

    A whitelist rather than a list of drops. Every stage shares this comment
    and each adds keys of its own, so a projection that named what to delete
    would carry whatever the deleting was not written for -- a park nobody
    set, a pull request nobody opened, a watermark over a thread the fresh
    cycle has not read. What is kept is named instead, and the identity of the
    comment itself is kept by rewriting the payload in place rather than by
    minting a second one no reader would find.
    """
    kept = {
        key: state.data[key] for key in _RETAINED_KEYS if key in state.data
    }
    state.data.clear()
    state.data.update(kept)
    _late_state.write_late_generation(state, fresh)


def _persisted(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: LateGeneration,
) -> None:
    """Make one step of this transaction durable before the next one acts."""
    _late_state.write_late_generation(state, generation)
    gh.write_pinned_state(issue, state)
