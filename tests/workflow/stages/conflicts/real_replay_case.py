# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An adjudicated contribution measured and replayed over real repository objects."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator.git.measurement import (
    commits as _measurement_commits,
    fingerprint as _fingerprint,
)
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.workflow.late_split import (
    exemption as _exemption,
)
from orchestrator.workflow.stages.conflicts import (
    evidence as _evidence,
    models as _conflict_models,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_records as _late_records,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.authorization import _authorize
from tests.support.fakes import (
    FakeGitHubClient,
    FakeLabel,
    FakePR,
    FakePRRef,
    make_issue,
)
from tests.support.replay_repository import (
    TOPIC_BRANCH,
    ReplayRepositoryMixin,
)
from tests.workflow.observation_support import ObservedCloseCase

ISSUE_NUMBER = 9
PR_NUMBER = 77
STAGE = WorkflowLabel.RESOLVING_CONFLICT
FREEZE_BASE = "_freeze_base_commit"


class _RealReplayCase(ObservedCloseCase, ReplayRepositoryMixin):
    """One adjudicated commit, really replayed, really fingerprinted."""

    def setUp(self) -> None:
        super().setUp()
        # The transfer re-reads the issue before granting anything, and a
        # close another case latched process-wide is a refusal this one never
        # asked for.
        self._fresh_process()
        self.replay = self.build_replay()
        # The one reading in this fixture that leaves the host. Both the
        # permit and the measurement freeze the base branch from the remote,
        # which there is no token for here; the ancestry and the fingerprints
        # decided against it are the repository's own.
        self.enterContext(patch.object(
            _measurement_commits, FREEZE_BASE,
            MagicMock(return_value=FrozenCommit(sha=self.replay.replayed_base)),
        ))

    def _adjudicated(self, candidate: str):
        """The gate for an issue whose exemption names the replayed commit.

        The pinned comment is exactly what a settled `single` verdict leaves,
        with the digest taken over the objects rather than chosen: the pair
        the adjudication was measured between, and the real contribution
        between them.
        """
        github = FakeGitHubClient()
        issue = make_issue(ISSUE_NUMBER)
        issue.labels.append(FakeLabel(str(STAGE)))
        github.add_issue(issue)
        github.add_pr(FakePR(
            number=PR_NUMBER,
            head_branch=TOPIC_BRANCH,
            head=FakePRRef(sha=self.replay.accepted),
        ))
        github.seed_state(ISSUE_NUMBER, pr_number=PR_NUMBER)
        state = github.read_pinned_state(issue)
        contributes = self._contributes(
            self.replay.accepted_base, self.replay.accepted,
        )
        _exemption.record_exemption(state, self.replay.accepted)
        _exemption.record_semantic_identity(
            state,
            base_sha=self.replay.accepted_base,
            candidate_sha=self.replay.accepted,
            fingerprint=contributes,
        )
        _authorize(
            state, self.replay.accepted, self.replay.accepted_base, contributes,
        )
        github.write_pinned_state(issue, state)
        return _late_records._gate(
            github, self.replay.spec, issue, state, self.replay.worktree,
        )

    def _contributes(self, base: str, candidate: str) -> str:
        """What one pair really contributes, over the objects this host holds."""
        fingerprinted = _fingerprint._fingerprint_contribution(
            self.replay.worktree, base, candidate,
        )
        self.assertTrue(fingerprinted.is_fingerprinted)
        return fingerprinted.digest

    def _context(self, gate) -> _conflict_models._ConflictContext:
        """The tick this stage's own owners are handed."""
        return _conflict_models._ConflictContext(
            gate.gh, gate.spec, gate.issue, gate.state,
        )

    def _evidence(self, gate, candidate: str):
        """What the replay hands the gate, over the fork points git answers."""
        return _evidence._rewritten(
            self._context(gate),
            self.replay.worktree,
            _evidence._replayed(
                self.replay.spec, self.replay.worktree, self.replay.accepted,
            ),
            candidate,
            PR_NUMBER,
        )

    def _entered(self, gate, candidate: str) -> _late_gate_models._Entered:
        return _late_gate_models._Entered(
            head=self.replay.accepted,
            reconciling=True,
            candidate=candidate,
            rewrite=self._evidence(gate, candidate),
        )
