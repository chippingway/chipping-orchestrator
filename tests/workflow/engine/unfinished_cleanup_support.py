# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One closed owner whose cleanup ran and left the ending owed.

The deferral cases next door are about a pass nothing could hand the reading
to, or one that broke before it marked anything. These are about the pass that
looks most finished and is not: it ran every step of the ending and the remote
would not let it complete one -- a delete refused, a terminal declined -- so
the observation it was carrying is still the only thing that routes the owner
back, and the label it was reached under may not be there any more.
"""
from __future__ import annotations

from unittest.mock import Mock, patch

from orchestrator.config import settings as config
from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.workflow.stages.decomposition import (
    late_close_reading as _late_close_reading,
)
from tests.support.fakes import FakeLabel
from tests.workflow.engine.cleanup_deferral_support import (
    OWNER_NUMBER,
    DeferralCase,
)

# The request-budget knob deciding which ticks enumerate closed issues at all.
_SWEEP_CADENCE_ATTR = "CLOSED_ISSUE_SWEEP_EVERY_N_TICKS"

# What GitHub declining the one write that ends a cleanup looks like here.
_REFUSED_LABEL = RuntimeError("label rejected")

_UMBRELLA_FLAG = "umbrella"

# What a read whose request failed outright looks like from here.
_UNREADABLE = ConnectionError("github unreachable")


def refusing() -> Mock:
    """A remote that will not drop the ref, so the obligation stays owed."""
    return Mock(return_value=_snapshot_refs.SnapshotOutcome.REFUSED)


def cleanup_settled(github, spec, issue_number: int) -> bool:
    """Ask the seam itself whether a cleanup's reading may be handed back.

    Driven directly for the one answer no whole tick can stage: what the
    question does when the request behind it never lands.
    """
    return _late_close_reading._cleanup_settled(github, spec, issue_number)


class UnfinishedCleanupCase(DeferralCase):
    """The closed owner, plus what a case about an unfinished ending reads."""

    def _label(self) -> str:
        """The one workflow label the owner currently carries."""
        return self.github.workflow_label(self.github.get_issue(OWNER_NUMBER))

    def _resources(self) -> dict:
        """What the owner's ledger now says about each obligation."""
        recorded = self.github.pinned_data(OWNER_NUMBER).get("late_resources")
        return {
            entry["target"]: entry["state"] for entry in recorded or []
        }

    def _relabelled(self, label: str) -> None:
        """What this cycle's own decomposer writes as its ordinary outcome.

        A run spawned before the close finishes after it, so the label the
        ending was reached under is not the one it is finished under -- and
        neither label a decomposition outcome names is one the closed sweep
        queries.
        """
        self.github.get_issue(OWNER_NUMBER).labels = [FakeLabel(label)]

    def _forget_umbrella(self) -> None:
        """Take the flag off, leaving an adjudication that never converted.

        Which is a split cancelled before it created a single child, and the
        other half of what the record answers about where such an owner
        belongs when its label has been moved.
        """
        recorded = dict(self.github.pinned_data(OWNER_NUMBER))
        recorded.pop(_UMBRELLA_FLAG, None)
        self.github.seed_state(OWNER_NUMBER, **recorded)

    def _refusing_the_label(self):
        """GitHub declining the one write that ends this owner's cleanup."""
        return patch.object(
            self.github, "set_workflow_label", side_effect=_REFUSED_LABEL,
        )

    def _unreadable(self):
        """The refetch that question opens with, failing the way an outage
        fails: a request that answered nothing about the ending."""
        return patch.object(
            self.github, "get_issue", side_effect=_UNREADABLE,
        )

    def _every_tick_sweeps(self) -> None:
        """Pin the closed-issue sweep to every tick, whatever is configured.

        The cadence resolves from the environment, so a case about the label
        a later process finds a closed owner BY would otherwise be asserting
        about the operator's shell rather than about the label.
        """
        pinned = patch.object(config, _SWEEP_CADENCE_ATTR, 1)
        pinned.start()
        self.addCleanup(pinned.stop)
