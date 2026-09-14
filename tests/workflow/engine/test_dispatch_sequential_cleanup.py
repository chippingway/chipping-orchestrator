# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The freshness the path with no worker hand-off has to take for itself.

`parallel_limit == 1` dispatches on the caller thread, straight off the objects
the enumeration yielded. On the two labels where the CLOSE decides which
handler runs, a reading that old decides it wrongly in both directions. An
owner closed after the poll reaches the stage its label names -- spawning the
decomposer, or walking a dependency graph and activating children, on an issue
a human just ended. An owner reopened after the poll is swept as closed, and a
snapshot no consumer holds is deleted out from under a live cycle, because the
sweep's own re-read of the close would be re-reading the very object that
classified it.
"""
from __future__ import annotations

import importlib
import unittest
from unittest.mock import Mock, patch

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.skills import catalog
from orchestrator.workflow.engine import stage_targets as _stage_targets, tick
from orchestrator.workflow.late_split import obligations as _obligations, phases as _late_phases, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_UMBRELLA
from tests.workflow.git_owners import seam_patch

_OWNER_NUMBER = 41

_WORKFLOW_LOG = "orchestrator.workflow"

_CYCLE_ID = 3

_GENERATION = 1

# The one commit this owner preserved, and the ref its own identity puts that
# commit under -- spelled out rather than derived, since what the sweep does
# is re-derive it and refuse anything else.
_CANDIDATE_SHA = "c0ffee0000000000000000000000000000000001"

_OWNER_REF = "refs/orchestrator/late-split/issue-41/cycle-3/gen-1"

_REFRESH_BASE = "_refresh_base_and_worktrees"

# The handler an OPEN issue on this label reaches, which is the one a stale
# reading would send a closed owner to.
_UMBRELLA_TARGET = _stage_targets._STAGE_HANDLER_TARGETS[LABEL_UMBRELLA]


def _intercepted(target: tuple[str, str], reached: Mock):
    """Hold the handler one target names, on the module that owns it."""
    return patch.object(
        importlib.import_module(target[0]), target[1], reached,
    )


class _PolledOneReadingBehind:
    """A repo whose enumeration is one reading behind the issue itself.

    What a human closing or reopening an owner right after a tick listed it
    leaves: the object the poll yielded says what it said then, and every read
    taken since says otherwise. Everything but the enumeration is the client
    underneath.
    """

    def __init__(self, github: FakeGitHubClient, polled) -> None:
        self._github = github
        self._polled = polled

    def list_pollable_issues(self):
        """Answer this tick's enumeration with the stale reading."""
        return [self._polled]

    def __getattr__(self, name):
        """Everything a tick asks that is not the enumeration."""
        return getattr(self._github, name)


class SequentialTickRefetchTest(unittest.TestCase):
    """The sequential path classifies and refetches before it sweeps."""

    def test_a_reopen_after_enumeration_keeps_the_ref(self) -> None:
        # The reading that routed the issue is what says a close was
        # OBSERVED, so the cycle ends whatever the refetch then says -- but
        # the refetch is what decides how far this pass goes, and an issue
        # somebody has just reopened gets nothing external done to it and no
        # terminal. The mark is what hands it to the dispatcher's own guard.
        github = self._owner_holding_a_ref()
        deleted = Mock()

        with patch.object(_snapshot_refs, "delete_snapshot_ref", deleted), self.assertLogs(_WORKFLOW_LOG):
            self._sequential_tick(github)

        deleted.assert_not_called()
        self.assertTrue(github.pinned_data(_OWNER_NUMBER)["late_cancelled"])
        self.assertEqual(github.label_history, [])
        self.assertEqual(github.posted_comments, [])

    def test_a_still_closed_owner_is_swept_as_before(self) -> None:
        # The refetch decides on what it reads rather than on having read: an
        # owner still closed when it is looked at again is the ordinary
        # cleanup pass, and this path must not have stopped taking it.
        github = self._owner_holding_a_ref(reopened=False)
        deleted = Mock(return_value=_snapshot_refs.SnapshotOutcome.DELETED)

        with patch.object(_snapshot_refs, "delete_snapshot_ref", deleted):
            self._sequential_tick(github)

        self.assertEqual(
            deleted.call_args.kwargs,
            {"ref": _OWNER_REF, "sha": _CANDIDATE_SHA},
        )

    def test_a_close_after_the_poll_reaches_the_sweep(self) -> None:
        # The other direction, and the one where being late costs an agent
        # rather than a ref: the poll listed the owner while it was open, and
        # the handler its label names is the decomposer or the dependency
        # walk. Refetched, the close it was ended with is what routes it.
        github = self._owner_holding_a_ref(reopened=False)
        deleted = Mock(return_value=_snapshot_refs.SnapshotOutcome.DELETED)
        stage = Mock()

        with patch.object(_snapshot_refs, "delete_snapshot_ref", deleted), _intercepted(_UMBRELLA_TARGET, stage):
            self._sequential_tick(github, polled_closed=False)

        stage.assert_not_called()
        self.assertEqual(
            deleted.call_args.kwargs,
            {"ref": _OWNER_REF, "sha": _CANDIDATE_SHA},
        )

    def _owner_holding_a_ref(
        self, *, reopened: bool = True,
    ) -> FakeGitHubClient:
        """A closed owner whose ledger still holds one snapshot ref."""
        github = FakeGitHubClient()
        github.add_issue(make_issue(
            _OWNER_NUMBER, label=LABEL_UMBRELLA, closed=not reopened,
        ))
        state = github.read_pinned_state(github.get_issue(_OWNER_NUMBER))
        _late_state.write_late_generation(state, LateGeneration(
            cycle_id=_CYCLE_ID,
            generation=_GENERATION,
            root_issue=_OWNER_NUMBER,
            current_issue=_OWNER_NUMBER,
            candidate_sha=_CANDIDATE_SHA,
            phase=_late_phases.LatePhase.SNAPSHOTTING,
            obligations=_obligations.LateObligations().with_resource(_obligations.LateResource(
                kind=_obligations.LateResourceKind.SNAPSHOT_REF,
                target=_OWNER_REF,
                resource_state=_obligations.LateResourceState.RETAINED,
            )),
        ))
        github.seed_state(_OWNER_NUMBER, **state.data)
        return github

    def _sequential_tick(
        self, github: FakeGitHubClient, *, polled_closed: bool = True,
    ) -> None:
        """One `scheduler=None` tick, enumerating the owner as it was."""
        polled = make_issue(
            _OWNER_NUMBER, label=LABEL_UMBRELLA, closed=polled_closed,
        )
        with (
            seam_patch(_REFRESH_BASE, Mock()),
            patch.object(catalog, "_emit_repo_skill_catalog", Mock()),
        ):
            tick.tick(_PolledOneReadingBehind(github, polled), _TEST_SPEC)


if __name__ == "__main__":
    unittest.main()
