# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Nothing is published or declared current until the whole world is proved.

Each case moves exactly one thing the evidence is bound to and asserts the same
outcomes: no artifact reached the pull request, the transaction is still owed,
the refusal logged is the one that move earns, and the tick is held only where
a reading could not be taken. A move that a route behind the guard answers -- a
push, a drift resume, a fresh reviewer, fresher evidence -- stands down
instead, so the stage behind it still runs.

The review subject is held to the records a reviewer actually wrote, and the
report it names is re-read where its settlement put it, exactly as a reviewer
is handed it: a subject nobody recorded, one a later review replaced, a report
settled after the review, and a report deleted, edited, out of step with its
handoff, or unreadable are each refused.

The settlement proves the pull request and the requirements once more after the
post, since a push can land while the artifact is being written: evidence is
then left owed rather than declared current over a head nobody verified.
"""
from __future__ import annotations

import functools
import unittest
from dataclasses import replace
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    report_delivery as _report_delivery,
    report_records as _report_records,
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import state as _validating_state
from tests.support.github.models import FakeComment, FakeLabel, FakeUser
from tests.workflow.engine import (
    verification_evidence_test_support as support,
    verification_report_fixture as _report,
    verification_world_fixture as _world,
)
from tests.workflow.fixtures import LABEL_DONE

_LEVEL = "INFO"

# A reply on the issue thread, past every comment the case seeds.
_REPLY_ID = 9_999_999

# Why an issue is parked, which names an undeliverable report as a debt.
_PARK_REASON = "park_reason"

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
        lambda case: setattr(case.world, "path", case.world.path / "absent"),
        False, "not on this host",
    ),
    (
        "the tested commit carries another tree",
        lambda case: case.world.trees.update({support.TESTED_SHA: support.REBASED_TREE}),
        False, "does not carry the tested tree",
    ),
    (
        "the tested id names an annotated tag of the tested tree",
        lambda case: case.world.retags(support.TESTED_SHA),
        False, "tested commit cannot be read",
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
        "a report is owed as undeliverable",
        lambda case: case.persists(_PARK_REASON, _report_delivery.UNDELIVERABLE_REPORT),
        False, "would describe is still owed",
    ),
    (
        "the round was bought through a later thread",
        lambda case: case.buys_a_round("a later thread"),
        False, "not the revision its reviewer was due",
    ),
    (
        "no review subject is recorded",
        lambda case: case.persists(_review_subjects.REVIEW_SUBJECT, None),
        False, "no readable review_subject is recorded",
    ),
    (
        "a later review was handed another report",
        lambda case: case.settles(_report.settles_report(case, 2, _report.LATER_REPORT_TEXT)),
        False, "another subject than the recorded review_subject",
    ),
    (
        "a report settled after the review",
        lambda case: case.settles(_report.settles_report(
            case, 2, _report.LATER_REPORT_TEXT, reviewed=False,
        )),
        False, "not about the report the pull request carries",
    ),
    (
        "the report comment was deleted",
        lambda case: case.pull_request.issue_comments.remove(case.report_comment()),
        False, "no longer at the location it was recorded at",
    ),
    (
        "the report comment was edited",
        lambda case: setattr(case.report_comment(), "body", "Rewritten by hand."),
        False, "was edited, cut short, or rewritten",
    ),
    (
        "the report handoff is gone",
        lambda case: case.persists(_report_records.REPORT_HANDOFF, None),
        False, "disagrees with the handoff that settled it",
    ),
    (
        "the report would not re-read",
        lambda case: case.gh.report_failures.unreadable.add(support.PR_NUMBER),
        True, "the settled developer report could not be re-read",
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
        "the issue records another pull request",
        lambda case: case.persists("pr_number", support.PR_NUMBER + 1),
        False, "another pull request than the one this issue records",
    ),
    (
        "the drift baseline moved past the report",
        lambda case: case.buys_a_round(
            case.subject.requirements_revision, baseline="a later baseline",
        ),
        False, "written against requirements the issue has since moved past",
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

    def buys_a_round(self, through: str, baseline: str | None = None) -> None:
        """Record a reviewer round a reply bought through `through`, and any later baseline.

        The subject's requirements are then due only where they are `through`.
        """
        self.state.set(_validating_state._REVIEWER_OWES_A_ROUND, _validating_state._ROUND_BOUGHT_BY_A_REPLY)
        self.state.set(_validating_state._ROUND_BOUGHT_THROUGH, through)
        if baseline is not None:
            self.state.set(_report.BASELINE, baseline)
        self.gh.write_pinned_state(self.issue, self.state)

    def settles(self, _subject) -> None:
        """Persist what a later settlement staged on the comment."""
        self.gh.write_pinned_state(self.issue, self.state)

    def report_comment(self):
        """The comment the settled report was published as."""
        location = self.subject.report.location
        return next(
            posted for posted in self.pull_request.issue_comments
            if posted.id == location.comment_id
        )

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

    def test_a_subject_about_another_head(self) -> None:
        # Even a subject a reviewer really was handed never makes evidence
        # current where it is not about the head the evidence answers for: a
        # head carrying another tree is a review of different content, and a
        # head carrying the same tree is still not the head the validating
        # reader would build a subject from.
        for head in (support.REBASED_SHA, support.SQUASHED_SHA):
            with self.subTest(head=head):
                self.setUp()
                subject = dict(self.subject.recorded(), sha=head)
                self.state.set(_review_subjects.REVIEW_SUBJECT, subject)
                pending = self.record(self.binding(
                    target=_records.EvidenceTarget(self.binding().target.publication, subject),
                ))

                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertFalse(self.reconcile())
                    self.assertIn(
                        "not about the head the evidence answers for",
                        support.logged_refusal(logged),
                    )

                self.assertEqual(self.artifacts(), [])
                self.assertEqual(_record_state.read_pending_evidence(self.state), pending)


class ReviewerReportedEvidenceTest(unittest.TestCase, support.VerificationEvidenceCase):
    """A reviewer's account answers for the subject the reviewer that RETURNED read."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.pending = self.record(
            self.binding(source=EvidenceSource.REVIEWER_REPORTED),
        )

    def test_it_settles_over_the_returned_subject(self) -> None:
        self.assertFalse(self.reconcile())

        self.assertEqual(
            [found.source for found in self.artifacts()],
            [EvidenceSource.REVIEWER_REPORTED],
        )

    def test_no_returned_subject_answers_for_it(self) -> None:
        # A launch whose reviewer never returned leaves `review_subject`
        # naming the report and nothing saying a reviewer read it.
        self.state.set(_review_subjects.RETURNED_SUBJECT, None)
        self.gh.write_pinned_state(self.issue, self.state)

        with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
            self.assertFalse(self.reconcile())
            self.assertIn(
                "no readable review_returned_subject", support.logged_refusal(logged),
            )

        self.assertEqual(self.artifacts(), [])


class SettledReplyRoundTest(unittest.TestCase, support.VerificationEvidenceCase):
    """Evidence of a round a reply bought answers for the requirements that round read."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)

    def test_its_own_settlement_is_no_staleness(self) -> None:
        # The reply is settled as the round returns, moving the drift
        # baseline onto the requirements its reviewer read -- past the report,
        # which the reader handed over as written against the baseline before.
        # That is the round's own settlement, not an edit anybody owes, so the
        # reviewer's evidence of that subject settles.
        self.issue.comments.append(FakeComment(
            id=_REPLY_ID, body="Please also check the empty case.", user=FakeUser(self.issue.user.login),
        ))
        requirements = _content_hash._compute_user_content_hash(self.issue, set())
        subject = replace(self.subject, requirements_revision=requirements)
        self.state.set(_review_subjects.RETURNED_SUBJECT, subject.recorded())
        self.state.set(_report.BASELINE, requirements)
        publication = replace(
            self.binding().target.publication, requirements_revision=requirements,
        )
        pending = self.record(self.binding(
            source=EvidenceSource.REVIEWER_REPORTED,
            target=_records.EvidenceTarget(publication, subject.recorded()),
        ))

        self.assertFalse(self.reconcile())

        self.assertEqual(
            (
                _settlement.read_current_evidence(self.state).receipt,
                subject.report.requirements_revision == requirements,
            ),
            (pending.receipt, False),
        )


class MovedDuringPublicationTest(unittest.TestCase, support.VerificationEvidenceCase):
    """Whatever moves while the artifact is written leaves the evidence owed."""

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.pending = self.record()
        self.posts = self.gh._post_verification_artifact
        self.meanwhile = None

    def posts_then_moves(self, pull_request, body: str):
        """Land the artifact, then let `meanwhile` move the world before the settlement."""
        landed = self.posts(pull_request, body)
        if self.meanwhile is not None:
            self.meanwhile()
        return landed

    def test_a_push_during_the_post(self) -> None:
        self.meanwhile = functools.partial(self.moves_the_head, support.REBASED_SHA)
        with patch.object(
            self.gh, "_post_verification_artifact", self.posts_then_moves,
        ), self.assertLogs(support.WORKFLOW_LOG, _LEVEL):
            self.assertFalse(self.reconcile())

        persisted = self.gh.read_pinned_state(self.issue)
        self.assertEqual(
            [found.target_head for found in self.artifacts()], [support.TESTED_SHA],
        )
        self.assertIsNone(_settlement.read_current_evidence(persisted))
        self.assertEqual(_record_state.read_pending_evidence(persisted), self.pending)
        # The artifact is ours on the ledger even though it never settled.
        self.assertIn(
            self.pull_request.issue_comments[-1].id, persisted.get(support.LEDGER),
        )

    def test_a_report_settling_during_the_post(self) -> None:
        # A later report revision, and the review of it, land while the
        # artifact is posted -- written to the pinned comment, or still only
        # in the state the tick holds. Either way the evidence for the earlier
        # subject is not declared current, and the refusal writes nothing back
        # over what the comment carries.
        for persisted_first in (True, False):
            with self.subTest(persisted_first=persisted_first):
                self.setUp()
                self.meanwhile = functools.partial(self.settles_later, persisted=persisted_first)
                with patch.object(
                    self.gh, "_post_verification_artifact", self.posts_then_moves,
                ), self.assertLogs(support.WORKFLOW_LOG, _LEVEL):
                    self.assertFalse(self.reconcile())

                persisted = self.gh.read_pinned_state(self.issue)
                self.assertIsNone(_settlement.read_current_evidence(persisted))
                self.assertEqual(
                    _record_state.read_pending_evidence(persisted), self.pending,
                )
                self.assertEqual(
                    _report_settlement.read_current_report(persisted).report_revision,
                    2 if persisted_first else 1,
                )

    def test_the_issue_ending_during_the_post(self) -> None:
        # Closed, paused, or relabelled `done` while the artifact was posted:
        # nothing is declared current, and nothing at all is written onto an
        # issue somebody has just stopped.
        for ends in ("closed", "paused", "done"):
            with self.subTest(ends=ends):
                self.setUp()
                self.meanwhile = functools.partial(self.ends_the_issue, ends)
                writes = self.gh.write_state_calls
                with patch.object(
                    self.gh, "_post_verification_artifact", self.posts_then_moves,
                ), self.assertLogs(support.WORKFLOW_LOG, _LEVEL):
                    self.assertFalse(self.reconcile())

                persisted = self.gh.read_pinned_state(self.issue)
                self.assertEqual(len(self.artifacts()), 1)
                self.assertEqual(self.gh.write_state_calls, writes)
                self.assertIsNone(_settlement.read_current_evidence(persisted))
                self.assertEqual(
                    _record_state.read_pending_evidence(persisted), self.pending,
                )

    def settles_later(self, *, persisted: bool) -> None:
        """Settle and review report revision 2, and write it where `persisted` says."""
        _report.settles_report(self, 2, _report.LATER_REPORT_TEXT)
        if persisted:
            self.gh.write_pinned_state(self.issue, self.state)

    def ends_the_issue(self, ends: str) -> None:
        """Close the issue, pause it, or relabel it `done`, as a human would.

        Only on GitHub: the issue the tick holds is left live, and the next
        read of the issue returns a distinct object carrying the change, so
        what stands the settlement down is the issue it read afresh.
        """
        fresh = replace(self.issue, labels=list(self.issue.labels))
        self.enterContext(patch.object(self.gh, "get_issue", return_value=fresh))
        if ends == "closed":
            fresh.closed = True
        elif ends == "paused":
            fresh.labels.append(FakeLabel("paused"))
        else:
            fresh.labels = [FakeLabel(LABEL_DONE)]


if __name__ == "__main__":
    unittest.main()
