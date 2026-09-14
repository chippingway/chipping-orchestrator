# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Maintenance outcomes and the artifacts left on the local host and remote."""
from __future__ import annotations

from collections.abc import Sequence

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import (
    branch_probes,
    discovery,
    maintenance,
    remote_inventory as _remote_inventory,
)
from orchestrator.git.worktrees.candidates import MaintenanceCandidate
from orchestrator.git.worktrees.maintenance_results import MaintenanceResult
from tests.git.worktrees import maintenance_guard_support as _guard_support


class _MaintenanceAssertions:
    """Assertions shared by maintenance cases using a real git host."""

    @property
    def only_branch(self) -> tuple[str, ...]:
        """This issue's one branch, as a listing of what a host still holds."""
        return (self.branch,)

    def discovered(
        self, specs: Sequence[_config_models.RepoSpec] | None = None,
    ) -> tuple[MaintenanceCandidate, ...]:
        """Every candidate the discovery finds on this host and its remote."""
        return discovery._maintenance_candidates(
            specs or (self.spec,),
        ).candidates

    def only_candidate(self, specs=None) -> MaintenanceCandidate:
        """The single candidate this host and its remote hold between them."""
        found = self.discovered(specs)
        self.assertEqual(len(found), 1, f"expected one candidate, got {found}")
        return found[0]

    def swept(
        self,
        candidates: Sequence[MaintenanceCandidate] | None = None,
        *,
        claimed=_guard_support._never_claimed,
        going=_guard_support._going_on,
    ) -> tuple[MaintenanceResult, ...]:
        """Run one maintenance pass over what the discovery found."""
        return maintenance._maintained_candidates(
            self.gh,
            self.discovered() if candidates is None else candidates,
            claimed=claimed,
            going=going,
        )

    def only_result(self, **options) -> MaintenanceResult:
        """The single answer a pass over this host's one candidate gives."""
        swept = self.swept(**options)
        self.assertEqual(len(swept), 1, f"expected one candidate, got {swept}")
        return swept[0]

    def local_branches(self) -> tuple[str, ...]:
        """Every orchestrator-owned branch the clone still carries."""
        return branch_probes._local_orchestrator_branches(self.clone) or ()

    def remote_branches(self) -> tuple[str, ...]:
        """Every orchestrator-owned branch the remote still carries."""
        return _remote_inventory._remote_orchestrator_branches(self.spec) or ()
