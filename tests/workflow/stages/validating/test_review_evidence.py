# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification evidence a reviewer is handed beside its subject.

Only evidence settled for exactly the subject the reviewer is handed -- the
pull request, head, requirements, and the complete report by revision and
digest -- is handed, and only once it proves current again and its artifact,
re-read for the prompt, is still exactly the one that settled. Evidence about
another subject, a record that is absent or will not read, evidence the world
has moved under, and an artifact edited, deleted, or unreadable between the
proof and the prompt's read each hand nothing, and each is logged with its own
reason: a reading nobody could take is never reported as evidence that moved.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from orchestrator.github import developer_reports as _reports, verification_artifacts as _artifacts
from orchestrator.github.verification_evidence import VerifiedCommand
from orchestrator.workflow.engine import (
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import review_evidence
from tests.workflow.engine import (
    verification_evidence_test_support as support,
    verification_report_fixture as _report,
)
from tests.workflow.fixtures import _TEST_SPEC

# Words a report or an artifact did not carry when the evidence settled.
EDITED = "13 passed"

# Why the prompt's own read of the artifact hands nothing.
PROMPT_READ_MOVED = "re-read for the prompt is gone or no longer the one that settled"

PROMPT_READ_UNREAD = "could not be re-read for the prompt"

ANOTHER_SUBJECT = "answers for another subject than the one handed"

# A requirements revision the issue never had.
OTHER_REQUIREMENTS = _reports.content_digest("an edit nobody reviewed")


def _other_words(case):
    """`case`'s subject over a report of the same revision whose complete text is other words."""
    report = replace(
        case.subject.report, text=EDITED, content_revision=_reports.content_digest(EDITED),
    )
    return replace(case.subject, report=report)


# Every subject the settled evidence is not about, as a reviewer would be handed it.
_OTHER_SUBJECTS = (
    (
        "a later report on the same head",
        lambda case: _report.settles_report(case, 2, _report.LATER_REPORT_TEXT, reviewed=False),
    ),
    ("other words under the same revision", _other_words),
    ("other requirements", lambda case: replace(case.subject, requirements_revision=OTHER_REQUIREMENTS)),
    ("another head", lambda case: replace(case.subject, commit=support.REBASED_SHA)),
)

# Every move after settlement that hands nothing though the subject is the
# bound one, and the reason it is logged under.
_MOVES = (
    (
        "nothing is current",
        lambda case: case.state.set(_records.CURRENT_EVIDENCE, None),
        "records no current verification evidence",
    ),
    (
        "the current record will not read",
        lambda case: case.state.set(_records.CURRENT_EVIDENCE, {"receipt": "damaged"}),
        "recorded on the pinned comment will not read",
    ),
    (
        "the thread would not read for the proof",
        lambda case: case.gh.report_failures.unreadable.add(support.PR_NUMBER),
        "the current evidence's artifact could not be re-read",
    ),
    (
        "the artifact was edited",
        lambda case: setattr(support.artifact_comment(case), "body", "Tests passed, trust me."),
        "artifact is gone or no longer the one that settled",
    ),
    (
        "the head moved",
        lambda case: case.moves_the_head(support.REBASED_SHA),
        "moved off the recorded commit",
    ),
)


def _rewrites(case) -> None:
    """Rewrite the settled artifact into another valid one: same identity, other output."""
    posted = support.artifact_comment(case)
    posted.body = _artifacts.render_verification_artifact(replace(
        case.artifacts()[-1], commands=(VerifiedCommand(support.SUITE, 0, EDITED),),
    ))


# What lands between the proof's read of the artifact and the prompt's, and
# the reason the prompt's read hands nothing for.
_BETWEEN_THE_READS = (
    ("the artifact was rewritten into another valid one", _rewrites, PROMPT_READ_MOVED),
    (
        "the artifact was deleted",
        lambda case: case.pull_request.issue_comments.remove(support.artifact_comment(case)),
        PROMPT_READ_MOVED,
    ),
    (
        "the thread would not read",
        lambda case: case.gh.report_failures.unreadable.add(support.PR_NUMBER),
        PROMPT_READ_UNREAD,
    ),
)


class _OnTheSecondRead:
    """Artifact rereads, before the second of which `happens` lands.

    The first is the proof that the evidence is current; the second is the
    reading the prompt quotes. A rewrite into another valid artifact only a
    comparison with the settled record can tell.
    """

    def __init__(self, case, happens) -> None:
        self._case = case
        self._happens = happens
        self._reread = case.gh.reread_verification_artifact
        self._reads = 0

    def __call__(self, pull_request, comment_id):
        self._reads += 1
        if self._reads == 2:
            self._happens(self._case)
        return self._reread(pull_request, comment_id)


class HandedEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """Evidence current for exactly the handed subject, and nothing else."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.record()
        self.reconcile()

    def handed(self, subject=None):
        """What a reviewer of `subject` -- the settled report's by default -- is handed now."""
        with self.seams():
            return review_evidence.handed_evidence(
                self.gh, _TEST_SPEC, self.issue, self.state, subject or self.subject,
            )

    def test_current_evidence_is_handed_as_reread(self) -> None:
        handed = self.handed()

        current = _settlement.read_current_evidence(self.state)
        self.assertEqual(
            (handed.current, handed.artifact, handed.revision),
            (current, self.artifacts()[-1], current.content_revision),
        )

    def test_another_subject_is_handed_none(self) -> None:
        # Evidence of an earlier report on the same head, or of other
        # requirements or another head, answers for a review nobody is asking
        # for now, however current it is.
        for name, other in _OTHER_SUBJECTS:
            with self.subTest(name):
                self.setUp()

                subject = other(self)

                with self.assertLogs(support.WORKFLOW_LOG, "INFO") as logged:
                    self.assertIsNone(self.handed(subject))
                    self.assertIn(ANOTHER_SUBJECT, support.logged_refusal(logged))

    def test_moved_evidence_is_handed_none(self) -> None:
        for name, moves, refusal in _MOVES:
            with self.subTest(name):
                self.setUp()
                moves(self)

                with self.assertLogs(support.WORKFLOW_LOG, "INFO") as logged:
                    self.assertIsNone(self.handed())
                    self.assertIn(refusal, support.logged_refusal(logged))

    def test_a_move_between_the_reads_hands_none(self) -> None:
        # What the prompt would quote is not what the revision names, or
        # nobody could read it to say.
        for name, happens, refusal in _BETWEEN_THE_READS:
            with self.subTest(name):
                self.setUp()
                rereads = _OnTheSecondRead(self, happens)

                with (
                    patch.object(self.gh, "reread_verification_artifact", rereads),
                    self.assertLogs(support.WORKFLOW_LOG, "INFO") as logged,
                ):
                    self.assertIsNone(self.handed())
                    self.assertIn(refusal, support.logged_refusal(logged))


if __name__ == "__main__":
    unittest.main()
