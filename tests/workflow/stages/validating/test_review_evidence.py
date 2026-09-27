# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification evidence a reviewer round is handed, and what its approval relies on.

A reviewer is handed the evidence current for exactly the subject it reviews,
quoted whole with the revision a reuse names, and nothing about another
subject. Commands it ran are published as reviewer-reported evidence before its
verdict is acted on, whatever the local configuration says -- an empty one
runs nothing and proves nothing. An approval reaches the approval arc only on
evidence that passed and still vouches for it; anything else parks for a human
before the verify gate, the approval record, or the squash is reached.
"""
from __future__ import annotations

import unittest

from orchestrator import config
from orchestrator.git.verification import models as _verify_models
from orchestrator.github.verification_evidence import EvidenceSource
from tests.workflow import published_reports as _published_reports
from tests.workflow.fixtures import LABEL_DOCUMENTING, ROLE_DEVELOPER, ROLE_REVIEWER
from tests.workflow.repo_values import _FAKE_TREE_SHA
from tests.workflow.stages.validating import (
    review_evidence_readings as _read,
    review_evidence_test_support as _world,
    settled_evidence_support as _settled,
)

HEAD = _world.HEAD

# A head the pull request is not standing on.
OTHER_HEAD = "a" * len(HEAD)

# A declaration that never closes its block, which the reader refuses whole.
UNCLOSED = f"VERIFICATION: RUN {HEAD}\nCOMMAND: {_world.SUITE}\nEXIT: 0\n\nVERDICT: APPROVED"

UNDECLARED = "LGTM\n\nVERDICT: APPROVED"

LATER_REPORT = "Covered the empty configuration as well; the suite passes."

REUSE_MOVED = "no longer this issue's current evidence"

DOCUMENTING = (_world.ISSUE, LABEL_DOCUMENTING)


class _EditsTheArtifactFirst:
    """A reviewer run during which a human edits the current evidence's artifact.

    Answers as the reviewer that reuses that evidence, which it was handed
    intact before the edit.
    """

    def __init__(self, case, current) -> None:
        self._case = case
        self._current = current

    def __call__(self, *_args, **_kwargs):
        artifact = next(
            posted for posted in self._case.pull_request.issue_comments
            if posted.id == self._current.comment_id
        )
        artifact.body = artifact.body.replace(_world.SUITE_OUTPUT, "13 passed")
        return self._case.reviewer(_world.declared_reuse(self._current.content_revision))


class DeclaredRunTest(_world.ReviewEvidenceWorld, unittest.TestCase):
    """Commands a reviewer ran are published before its approval is acted on."""

    def test_the_run_is_published_first(self) -> None:
        # No verification commands are configured, so the local gate runs
        # nothing and the reviewer's run is the only evidence there is: it is
        # published as the reviewer's, bound to the head and tree it reviewed
        # under the empty context, and the approval goes on only behind it.
        with _world.configured():
            ran = self.dispatched(self.reviewer(_world.declared_run()))

        artifact = _read.artifacts(self)[-1]
        self.assertEqual(
            (
                artifact.source,
                (artifact.tested_sha, artifact.tested_tree, artifact.target_head),
                artifact.context_revision,
                [(command.command, command.exit_status) for command in artifact.commands],
                len(_read.artifacts(self)),
            ),
            (
                EvidenceSource.REVIEWER_REPORTED,
                (HEAD, _FAKE_TREE_SHA, HEAD),
                _verify_models._context_revision((), config.VERIFY_TIMEOUT),
                [(_world.SUITE, 0)],
                1,
            ),
        )
        current = _read.current_evidence(self)
        self.assertEqual(
            (current.passed, current.content_revision, ran[_world.RUN_AGENT].call_count),
            (True, artifact.content_revision, 1),
        )
        self.assertEqual(
            (self.pinned()[_world.RETURNED_VERDICT], self.pinned()[_world.PENDING_EVIDENCE]),
            (None, None),
            "the verdict is dropped once disposed of, and the published run settled",
        )
        self.assertEqual(self.github.label_history[-1], DOCUMENTING)
        posted = _read.pr_comments(self)
        self.assertLess(
            posted.index(_read.pr_comments(self, _world.ARTIFACT_HEADING)[0]),
            posted.index(_read.pr_comments(self, _world.APPROVAL_NOTICE)[0]),
            "the evidence goes out before the approval",
        )


class UnverifiedApprovalTest(_world.ReviewEvidenceWorld, unittest.TestCase):
    """An approval relying on no valid evidence never reaches the approval arc."""

    def test_each_purported_approval_parks(self) -> None:
        # Nothing the reviewer declared, a run of another commit, a block left
        # open, and a run whose command failed: none reaches the verify gate,
        # the approval record, or `documenting`. The failed run is still
        # evidence, of a failure, and is published as such.
        for name, message, published in (
            ("no declaration", UNDECLARED, 0),
            ("another commit", _world.declared_run(OTHER_HEAD), 0),
            ("an unclosed block", UNCLOSED, 0),
            ("a failed command", _world.declared_run(exit_status=1), 1),
        ):
            with self.subTest(name):
                self.seeds()
                with _world.configured():
                    ran = self.dispatched(self.reviewer(message))

                self.assertEqual(
                    self._parked(ran), (True, _world.REASON_UNVERIFIED, None, None, 0),
                )
                self.assertEqual(self._left_behind(), (published, False, [], 1))

    def test_a_retry_runs_a_fresh_reviewer(self) -> None:
        # The reviewer owes the evidence, so the operator's retry on the park
        # buys a reviewer round rather than a developer run, and that round's
        # approval with its evidence is acted on.
        self.dispatched(self.reviewer(UNDECLARED))
        _read.replies(self, "/orchestrator continue")

        ran = self.dispatched(self.reviewer(_world.declared_run()))

        self.assertEqual(
            (
                _read.spawns(self, ROLE_REVIEWER),
                _read.spawns(self, ROLE_DEVELOPER),
                ran[_world.RUN_AGENT].call_args.args[0],
                self.github.label_history[-1],
            ),
            (2, 0, config.REVIEW_AGENT, DOCUMENTING),
        )

    def _left_behind(self) -> tuple:
        """The artifacts, the label, the approval notice, and the park notice a tick left."""
        return (
            len(_read.artifacts(self)),
            DOCUMENTING in self.github.label_history,
            _read.pr_comments(self, _world.APPROVAL_NOTICE),
            _read.issue_notices(self, _world.UNVERIFIED_NOTICE),
        )

    def _parked(self, ran) -> tuple:
        """The park flags, the approval and verdict records, and verify runs a tick left."""
        pinned = self.pinned()
        return (
            pinned[_world.AWAITING_HUMAN],
            pinned[_world.PARK_REASON],
            pinned.get(_world.APPROVED_SUBJECT),
            pinned[_world.RETURNED_VERDICT],
            ran[_world.VERIFY].call_count,
        )


class HandedEvidenceTest(_world.ReviewEvidenceWorld, unittest.TestCase):
    """The reviewer is handed the evidence current for its subject, and nothing else."""

    def test_current_evidence_may_be_reused(self) -> None:
        current = _settled.settles_current_evidence(self)

        ran = self.dispatched(self.reviewer(_world.declared_reuse(current.content_revision)))

        handed = _read.prompt(ran)
        self.assertIn(f"VERIFICATION: REUSED sha256:{current.content_revision}", handed)
        self.assertIn(f"> `{_world.SUITE}` -- exit 0", handed)
        self.assertIn("Reviewer-reported evidence.", handed)
        # Reused rather than run again: nothing new is published, and the
        # approval the evidence vouches for goes on.
        self.assertEqual(
            (
                len(_read.artifacts(self)),
                _read.current_evidence(self),
                self.github.label_history[-1],
            ),
            (1, current, DOCUMENTING),
        )

    def test_another_report_is_handed_none(self) -> None:
        # A later report on the same head is a new subject, and evidence about
        # the earlier one answers for a review nobody is asking for: it is not
        # handed over, and a reuse naming it is no approval.
        stale = _settled.settles_current_evidence(self)
        _published_reports.republishes_the_report(self.github, self.issue, LATER_REPORT)

        ran = self.dispatched(self.reviewer(_world.declared_reuse(stale.content_revision)))

        handed = _read.prompt(ran)
        self.assertIn(f"> {LATER_REPORT}", handed)
        self.assertIn("No current workflow verification evidence covers this subject", handed)
        self.assertNotIn("VERIFICATION: REUSED sha256:", handed)
        self.assertEqual(
            (self.pinned()[_world.PARK_REASON], DOCUMENTING in self.github.label_history),
            (_world.REASON_UNVERIFIED, False),
        )

    def test_an_edited_artifact_voids_the_reuse(self) -> None:
        # The evidence was current as it was handed, and its artifact was
        # edited while the reviewer ran: the reuse is proved again before the
        # approval relies on it, and a reuse of words the pull request no
        # longer shows is no approval.
        current = _settled.settles_current_evidence(self)

        self.dispatched(run_agent=_EditsTheArtifactFirst(self, current))

        refused = _read.issue_notices(self, REUSE_MOVED)
        self.assertEqual(
            (
                self.pinned()[_world.PARK_REASON],
                self.pinned().get(_world.APPROVED_SUBJECT),
                refused,
            ),
            (_world.REASON_UNVERIFIED, None, 1),
        )


if __name__ == "__main__":
    unittest.main()
