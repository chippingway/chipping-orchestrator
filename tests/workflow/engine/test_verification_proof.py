# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Nothing is published or declared current until the whole world is proved.

Each case moves exactly one thing the evidence is bound to and asserts the same
outcomes: no artifact reached the pull request, the transaction is still owed,
the refusal logged is the one that move earns, and the tick is held only where
a reading could not be taken. A move that a route behind the guard answers -- a
push, a drift resume, a fresh reviewer, fresher evidence -- stands down
instead, so the stage behind it still runs.

The settlement proves the pull request and the requirements once more after the
post, since a push can land while the artifact is being written: evidence is
then left owed rather than declared current over a head nobody verified.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_records as _report_records,
    report_settlement_state as _report_settlement,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import verification_evidence_test_support as support, verification_world_fixture as _world
from tests.workflow.fixtures import _TEST_SPEC

_ABSENT_CHECKOUT = Path("/nonexistent/orchestrator/issue-7")

_LATER_DIGEST = "22b2e1d2c3b4a5968778695a4b3c2d1e0ff0e1d2c3b4a5968778695a4b3c2d1e"

_LEVEL = "INFO"

# Every move, what it is, whether a tick meeting it holds (True) or stands down
# (False), and the refusal it is logged under -- so each is refused for its own
# move rather than for whichever reading happened to fail first.
_REFUSALS = (
    (
        "the pull request moved",
        lambda case: setattr(case.pull_request.head, "sha", support.REBASED_SHA),
        False, "moved off the recorded commit",
    ),
    (
        "the remote branch moved",
        lambda case: setattr(case.world, "remote", _world.standing_on(support.REBASED_SHA)),
        False, "not standing on the recorded commit",
    ),
    (
        "the checkout is elsewhere",
        lambda case: setattr(case.world, "path", _ABSENT_CHECKOUT),
        False, "not on this host",
    ),
    (
        "the tested commit carries another tree",
        lambda case: case.world.trees.update({support.TESTED_SHA: support.REBASED_TREE}),
        False, "does not carry the tested tree",
    ),
    (
        "the tested commit is unreadable",
        lambda case: case.world.trees.pop(support.TESTED_SHA),
        False, "tested commit cannot be read",
    ),
    (
        "the configuration moved",
        lambda case: case.enterContext(
            patch.object(config, "VERIFY_COMMANDS", ("uv run pytest -x",)),
        ),
        False, "verification configuration moved",
    ),
    (
        "the requirements were edited",
        lambda case: setattr(case.issue, "body", "Also cover an empty configuration."),
        False, "requirements moved",
    ),
    (
        "a developer report is owed",
        lambda case: case.persists(_report_records.PENDING_REPORT, {"receipt": "r"}),
        False, "would describe is still owed",
    ),
    (
        "a later report settled",
        lambda case: case.settles_a_later_report(),
        False, "not about the report the pull request carries",
    ),
    (
        "the branch would not fetch",
        lambda case: setattr(case.world, "fetched", 1),
        True, "could not be fetched",
    ),
    (
        "the divergence would not read",
        lambda case: setattr(case.world, "remote", _world.unreadable_divergence()),
        True, "would not say how it stands",
    ),
    (
        "the pull request would not read",
        lambda case: case.enterContext(patch.object(
            case.gh, "get_pr", side_effect=RuntimeError("GitHub did not answer"),
        )),
        True, "the recorded pull request could not be read",
    ),
)


class UnprovedEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """One moved fact holds or stands down, and publishes nothing either way."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.pending = self.record()

    def persists(self, key: str, recorded: object) -> None:
        """Write one pinned field, as another route's write would."""
        self.state.set(key, recorded)
        self.gh.write_pinned_state(self.issue, self.state)

    def settles_a_later_report(self) -> None:
        """Settle a second developer report revision over the first."""
        current = _report_settlement.read_current_report(self.state)
        _report_settlement.record_current_report(
            self.state, _report_records.CurrentReport(
                subject=current.subject,
                report_revision=2,
                content_revision=_LATER_DIGEST,
                location=current.location,
                mode=current.mode,
            ),
        )
        self.gh.write_pinned_state(self.issue, self.state)

    def test_every_moved_fact_refuses_the_evidence(self) -> None:
        for moved, moves, holds, refusal in _REFUSALS:
            with self.subTest(moved=moved):
                self.setUp()
                moves(self)

                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertIs(self.reconcile(), holds)
                    self.assertIn(refusal, support.logged_refusal(logged))

                self.assertEqual(self.artifacts(), [])
                self.assertEqual(
                    _record_state.read_pending_evidence(self.state), self.pending,
                )
                self.assertIsNone(_settlement.read_current_evidence(self.state))

    def test_a_subject_about_another_tree(self) -> None:
        # A subject naming a head the tested tree is not -- evidence answering
        # for a review of different content -- never becomes current.
        target = self.binding().target
        subject = dict(target.subject, sha=support.REBASED_SHA)
        pending = self.record(self.binding(
            target=_records.EvidenceTarget(target.publication, subject),
        ))

        with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
            self.assertFalse(self.reconcile())
            self.assertIn(
                "review subject's head does not carry", support.logged_refusal(logged),
            )

        self.assertEqual(self.artifacts(), [])
        self.assertEqual(_record_state.read_pending_evidence(self.state), pending)


class MovedDuringPublicationTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A head that moves while the artifact is written leaves the evidence owed."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.pending = self.record()
        self.posts = self.gh._post_verification_artifact

    def posts_then_pushes(self, pull_request, body: str):
        """Land the artifact, then let a push move the head before the settlement."""
        landed = self.posts(pull_request, body)
        self.moves_the_head(support.REBASED_SHA)
        return landed

    def test_a_push_during_the_post(self) -> None:
        with patch.object(
            self.gh, "_post_verification_artifact", self.posts_then_pushes,
        ), self.assertLogs(support.WORKFLOW_LOG, _LEVEL):
            self.assertFalse(self.reconcile())

        persisted = self.gh.read_pinned_state(self.issue)
        self.assertEqual(
            [found.target_head for found in self.artifacts()], [support.TESTED_SHA],
        )
        self.assertIsNone(_settlement.read_current_evidence(persisted))
        self.assertEqual(_record_state.read_pending_evidence(persisted), self.pending)
        # The artifact is ours on the ledger even though it never settled.
        self.assertEqual(len(persisted.get(support.LEDGER)), 1)


class CurrentEvidenceVerdictTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A reader relying on current evidence proves it against the world first."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def verdict(self) -> _evidence_models.ReportEvidence:
        """What a reader asking now is told about the current evidence."""
        with self.seams():
            return _proof.current_evidence_verdict(
                self.gh, _TEST_SPEC, self.issue, self.state,
            )

    def test_current_evidence_stands_until_moved(self) -> None:
        absent = self.verdict()
        self.record()
        self.reconcile()

        standing = self.verdict()
        self.moves_the_head(support.REBASED_SHA)
        moved = self.verdict()

        self.assertEqual(
            [reading.verdict for reading in (absent, standing, moved)],
            [
                _evidence_models.ReportEvidenceVerdict.DEFER,
                _evidence_models.ReportEvidenceVerdict.PROVED,
                _evidence_models.ReportEvidenceVerdict.DEFER,
            ],
        )
        self.assertIs(standing.pull_request, self.pull_request)


if __name__ == "__main__":
    unittest.main()
