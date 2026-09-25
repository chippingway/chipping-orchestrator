# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer report every reviewer is handed, and what its approval covers.

Each reviewer is handed the report the pull request carries when it spawns --
re-read from the location it settled at and quoted whole -- and the subject it
reviewed is recorded: pull request, head, requirements, and report revision. A
report the thread has moved out of reach is refused rather than reviewed, and a
reading nobody could take holds. An approval of words the pull request no
longer carries is not acted on, and a settled squash handoff moves the label
only while the report its approval covered is still the current one -- so a
report changed on an unchanged commit always reaches a fresh reviewer.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import MagicMock, patch

from orchestrator.git.verification.models import VerifyResult
from orchestrator.github.developer_reports import content_digest
from orchestrator.workflow.engine import prompt_context as _prompt_context, report_records as _records
from orchestrator.workflow.late_split import collapses as _collapses, handoffs as _late_handoffs
from orchestrator.workflow.stages.validating import (
    review_coverage as _review_coverage,
    review_report as _review_report,
)
from tests.workflow import (
    drift_reports as _drift_world,
    fix_reports as _fix_world,
    reviewed_reports as world,
)
from tests.workflow.fixtures import (
    LABEL_DOCUMENTING,
    LABEL_VALIDATING,
    REVIEW_APPROVED_MESSAGE,
    REVIEW_CHANGES_REQUESTED_MESSAGE,
    _agent,
    _open_pr_for,
)

ISSUE = 1_797

PR = 17_970

OTHER_PR = 17_971

RUN_AGENT = world.RUN_AGENT

HANDOFF_SHA = _late_handoffs.LATE_COLLAPSE_HANDOFF

NO_REPORT = "No developer report is recorded for this pull request"

# A report a maintainer published on the pull request, which a round verifies.
HUMAN_REPORT = "### Report\n\nRan the suite by hand; every check is green."

HUMAN = "alice"

LATE_REVIEWER = "late-reviewer"

# Where a human pushes the branch while a reviewer is out.
MOVED_HEAD = "b0a7" * 10

# The base a squash an earlier tick began was collapsing onto.
COLLAPSE_BASE = "ba5e" * 10

# An acceptance criterion a human adds after the drift check has measured the
# thread, and before the reviewer's own read of it.
LATE_CRITERION = "Also cover the empty-input case, please."

# What a reviewer that ran while something changed comes back with.
LATE_APPROVAL = _agent(session_id=LATE_REVIEWER, last_message=REVIEW_APPROVED_MESSAGE)

LATE_CHANGE_REQUEST = _agent(
    session_id=LATE_REVIEWER,
    last_message=f"1. Tighten the guard.\n\n{REVIEW_CHANGES_REQUESTED_MESSAGE}",
)

# What a developer resumed on an edit answers when it says the work, and the
# report, already cover it.
ACK_REPLY = "ACK: the report already covers the edited criteria."


class _DamagedReports(world._ReviewedReports):
    """What can happen to a settled report before the next reviewer spawns."""

    def pushes(self) -> None:
        self.pull_request.head.sha = MOVED_HEAD

    def acknowledges(self) -> None:
        _drift_world.edits(self, _drift_world.LATER_BODY)
        self._ticked(
            self._run_validating,
            MagicMock(side_effect=_fix_world._Runs(ACK_REPLY)),
            committed=False,
        )

    def truncates(self) -> None:
        landed = self.report_comment()
        landed.body = landed.body[: len(landed.body) // 2]

    def moves(self) -> None:
        _open_pr_for(self.github, issue_number=ISSUE, pr_number=OTHER_PR)
        world.restate(self, pr_number=OTHER_PR)

    def unhands(self) -> None:
        handoff = dict(self.pinned()[_records.REPORT_HANDOFF])
        world.restate(self, **{_records.REPORT_HANDOFF: {**handoff, "revision": 2}})

    def damages(self) -> None:
        world.restate(self, **{_records.CURRENT_REPORT: {"revision": "one"}})


# Every settled report no reviewer may be handed: what happened to it, and what
# the park says of it. The last two read intact and are stale against the
# subject: a push onto the branch, and an edit the developer only acknowledged.
REFUSED_REPORTS = (
    ("missing", world.deletes_report, _review_report._MISSING),
    ("edited", world.edits_report, _review_report._EDITED),
    ("truncated", _DamagedReports.truncates, _review_report._EDITED),
    ("moved", _DamagedReports.moves, _review_report._MOVED.format(settled=PR)),
    ("stale", _DamagedReports.unhands, _review_report._STALE),
    ("unreadable", _DamagedReports.damages, _review_report._UNREADABLE),
    ("pushed past", _DamagedReports.pushes, _review_report._MOVED_COMMIT.format(
        reported=_fix_world.PUBLISHED_HEAD, head=MOVED_HEAD,
    )),
    ("acknowledged", _DamagedReports.acknowledges, _review_report._MOVED_REQUIREMENTS),
)


class _ChangedMidway:
    """A step -- a reviewer's run, a verification, a read -- during which something changes.

    `answer` is what the step comes back with once `change` has happened: the
    result itself, or the real step to call through to.
    """

    def __init__(self, change, answer) -> None:
        self._change = change
        self._answer = answer

    def __call__(self, *called, **options):
        self._change()
        if callable(self._answer):
            return self._answer(*called, **options)
        return self._answer


class HandedReportTest(unittest.TestCase, world._ReviewedReports):
    """What each reviewer is handed, under whatever allowlist is configured."""

    def test_each_reviewer_reads_the_current_report(self) -> None:
        # Two report-only rounds on one commit: the first reviewer has no
        # report, the second reads the first report, and the third reads the
        # second and never the first -- whatever the pull request still holds
        # as history. The approval records the subject it was given.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        first = self.reported_round(world.FIRST_REPORT)
        second = self.reported_round(world.SECOND_REPORT)
        approved = self.reviewed(REVIEW_APPROVED_MESSAGE)

        self.assertIn(NO_REPORT, world.prompt(first))
        self.assertIn(f"> {world.FIRST_REPORT}", world.prompt(second))
        self.assertIn(f"> {world.SECOND_REPORT}", world.prompt(approved))
        self.assertNotIn(world.FIRST_REPORT, world.prompt(approved))
        pinned = self.pinned()
        subject = {
            "pr": PR,
            "sha": _fix_world.PUBLISHED_HEAD,
            "requirements": pinned["user_content_hash"],
            "report_revision": 2,
            "report_content": content_digest(world.SECOND_REPORT),
        }
        self.assertEqual(
            (pinned[world.REVIEWED], pinned[world.APPROVED]), (subject, subject),
        )
        self.assertEqual(self.github.label_history[-1], (ISSUE, LABEL_DOCUMENTING))

    def test_a_granted_round_reads_the_report(self) -> None:
        # The grant is the reply that bought the round, and the reviewer's to
        # read: the report written before it is handed over, and approved.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.replies_to_a_park()

        approved = self.reviewed(REVIEW_APPROVED_MESSAGE)

        self.assertEqual(
            (
                f"> {world.FIRST_REPORT}" in world.prompt(approved),
                world.GRANT_COMMAND in world.prompt(approved),
                self.github.label_history[-1],
            ),
            (True, True, (ISSUE, LABEL_DOCUMENTING)),
        )

    def test_our_report_passes_a_human_allowlist(self) -> None:
        # The allowlist names the humans; the report this orchestrator
        # published is read as ours by login, not by that list.
        self.allowed = (HUMAN,)
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)

        self.assertIn(f"> {world.FIRST_REPORT}", world.prompt(self.reviewed()))

    def test_a_verified_report_needs_trust(self) -> None:
        # A report a human published and a round verified is handed whole
        # while its author is trusted, and refused once the deployment no
        # longer trusts them.
        for allowed, handed in (((HUMAN,), True), (("bob",), False)):
            with self.subTest(allowed=allowed):
                self.allowed = (HUMAN,)
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                published = _fix_world.published_report(self, HUMAN_REPORT)
                self.requested_fix(
                    _fix_world.verified(PR, published.id, HUMAN_REPORT),
                    committed=False,
                )
                self.allowed = allowed

                reviewed = self.reviewed()

                if handed:
                    self.assertIn("> Ran the suite by hand", world.prompt(reviewed))
                else:
                    self.assert_refused(reviewed, _review_report._EDITED)


class RefusedReportTest(unittest.TestCase, _DamagedReports):
    """A settled report the thread has moved out of reach is never reviewed."""

    def test_a_report_nobody_may_be_handed_parks(self) -> None:
        for name, damage, detail in REFUSED_REPORTS:
            with self.subTest(name):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.reported_round(world.FIRST_REPORT)
                damage(self)

                self.assert_refused(self.reviewed(REVIEW_APPROVED_MESSAGE), detail)

    def test_an_unread_report_holds_silently(self) -> None:
        # A location nobody could read this tick is no refusal: nothing is
        # parked or posted, and the reviewer runs once it reads again.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        notices = len(self.github.posted_comments)
        self.github.report_failures.unreadable.add(PR)

        self.reviewed()[RUN_AGENT].assert_not_called()

        self.assertEqual(
            (self.pinned().get(world.AWAITING_HUMAN), len(self.github.posted_comments)),
            (False, notices),
        )
        self.github.report_failures.unreadable.clear()
        self.assertIn(f"> {world.FIRST_REPORT}", world.prompt(self.reviewed()))

    def test_an_unread_report_answers_a_grant_once(self) -> None:
        # A granted round whose report will not read holds, and writes the
        # grant it was bought with: the next tick neither announces the grant
        # again nor finds the cap spent, and the round runs once it reads.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.replies_to_a_park()
        self.github.report_failures.unreadable.add(PR)

        self.reviewed()
        self.reviewed()
        posted = [body for _, body in self.github.posted_comments]
        held = (
            sum(world.GRANT_NOTICE in body for body in posted),
            self.pinned().get("review_round"),
        )
        self.github.report_failures.unreadable.clear()

        self.assertIn(f"> {world.FIRST_REPORT}", world.prompt(self.reviewed()))
        self.assertEqual(held, (1, _fix_world._REVIEW_ROUNDS - 1))

    def test_a_reply_brings_a_fresh_report(self) -> None:
        # The reply to the park resumes the developer, whose report is
        # published with no commit and handed to the next reviewer.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        world.edits_report(self)
        self.reviewed()
        _fix_world.replied(self, "please publish the report again")

        self._ticked(
            self._run_validating,
            MagicMock(side_effect=_fix_world._Runs(
                _fix_world.reported(world.SECOND_REPORT),
            )),
            committed=False,
        )

        self.assertIn(f"> {world.SECOND_REPORT}", world.prompt(self.reviewed()))


class ApprovalCoverageTest(unittest.TestCase, world._ReviewedReports):
    """An approval is acted on only for the report the reviewer was handed."""

    def test_an_edit_during_review_voids_the_verdict(self) -> None:
        # A human edits the report while the reviewer runs. Whatever comes
        # back is about words the pull request no longer carries: an approval
        # is not announced, recorded, or relabelled, a change request pays no
        # developer and moves no label, the run itself is recorded, and the
        # next tick refuses the edited report.
        for name, verdict in (
            ("approved", LATE_APPROVAL), ("changes requested", LATE_CHANGE_REQUEST),
        ):
            with self.subTest(name):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.reported_round(world.FIRST_REPORT)
                announced = len(self.github.posted_pr_comments)

                ran = self._ticked(
                    self._run_validating,
                    MagicMock(side_effect=_ChangedMidway(
                        partial(world.edits_report, self), verdict,
                    )),
                    committed=False,
                )

                self.assertEqual(
                    (
                        ran[RUN_AGENT].call_count,
                        self.pinned().get("last_review_session_id"),
                        world.APPROVED in self.pinned(),
                        self.github.label_history[-1],
                        len(self.github.posted_pr_comments),
                    ),
                    (1, LATE_REVIEWER, False, (ISSUE, LABEL_VALIDATING), announced),
                )
                self.assert_refused(self.reviewed(), _review_report._EDITED)

    def test_an_edit_during_verify_voids_approval(self) -> None:
        # The report is edited while the local verification runs, after the
        # subject was checked on the reviewer's return: the approval is not
        # recorded, announced, or squashed under.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)

        mocks = self._ticked(
            self._run_validating,
            [LATE_APPROVAL],
            committed=False,
            verify_result=_ChangedMidway(
                partial(world.edits_report, self), VerifyResult(status="not_run"),
            ),
        )

        mocks["_squash_and_force_push"].assert_not_called()
        self.assertEqual(
            (world.APPROVED in self.pinned(), self.pinned().get("last_review_session_id")),
            (False, LATE_REVIEWER),
        )
        self.assertFalse(any(
            "review approved" in body for _, body in self.github.posted_pr_comments
        ))
        self.assert_refused(self.reviewed(), _review_report._EDITED)


class SquashHandoffTest(unittest.TestCase, world._ReviewedReports):
    """The label a finished squash owes moves only under an approval that stands."""

    def test_an_unrecorded_approval_voids_handoff(self) -> None:
        # An approval recorded before approvals named a subject, over a pull
        # request that carries a report: nothing says that report was the one
        # approved, so the handoff goes and a reviewer is handed it.
        self._approved_and_relabelled()
        world.restate(self, **{HANDOFF_SHA: self.pull_request.head.sha})
        world.forgets_approval(self)

        reviewed = self.reviewed()

        self.assertIn(f"> {world.FIRST_REPORT}", world.prompt(reviewed))
        self.assertEqual(
            self.github.label_history.count((ISSUE, LABEL_DOCUMENTING)), 1,
        )

    def test_a_covered_squash_handoff_relabels(self) -> None:
        # A finished squash whose relabel did not land leaves the head the
        # move is owed over. While the report its approval covered is current,
        # the next tick moves the label without a reviewer.
        self._approved_and_relabelled()
        world.restate(self, **{HANDOFF_SHA: self.pull_request.head.sha})

        self.reviewed()[RUN_AGENT].assert_not_called()

        self.assertEqual(
            self.github.label_history.count((ISSUE, LABEL_DOCUMENTING)), 2,
        )

    def test_an_edited_report_voids_squash_handoff(self) -> None:
        # The approved report is still the current record, but a human has
        # edited its comment since: the handoff is not moved past the
        # reviewer, and the reviewer round refuses the edited report.
        self._approved_and_relabelled()
        world.restate(self, **{HANDOFF_SHA: self.pull_request.head.sha})
        world.edits_report(self)

        self.assert_refused(self.reviewed(), _review_report._EDITED)

        self.assertEqual(
            (
                self.pinned().get(HANDOFF_SHA),
                self.github.label_history.count((ISSUE, LABEL_DOCUMENTING)),
            ),
            (None, 1),
        )

    def test_a_later_report_voids_squash_handoff(self) -> None:
        # The same handoff, over an approval of the FIRST report, once the
        # second has settled on that very head: the record is dropped and a
        # fresh reviewer is handed the second report.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.reported_round(world.SECOND_REPORT)
        world.restate(self, **{
            world.APPROVED: self.pinned()[world.REVIEWED],
            HANDOFF_SHA: self.pull_request.head.sha,
        })

        reviewed = self.reviewed()

        self.assertIn(f"> {world.SECOND_REPORT}", world.prompt(reviewed))
        self.assertEqual(
            (self.pinned().get(HANDOFF_SHA), self.github.label_history[-1]),
            (None, (ISSUE, LABEL_VALIDATING)),
        )

    def test_an_edited_report_holds_squash_recovery(self) -> None:
        # A squash the approval began and did not finish is finished -- no
        # branch may be left standing mid-rewrite -- but the report its
        # approval covered has been edited since, so the label is not moved
        # past a reviewer: the next tick drops the handoff that squash left,
        # and its reviewer round refuses the edited report.
        self._approved_and_relabelled()
        self._owes_a_collapse()
        world.edits_report(self)

        recovered = self._ticked(
            self._run_validating, [LATE_APPROVAL], committed=False,
            squash_result=(True, self.pull_request.head.sha, 1, None),
        )

        recovered["_squash_and_force_push"].assert_called_once()
        recovered[RUN_AGENT].assert_not_called()
        self.assertEqual(
            self.github.label_history.count((ISSUE, LABEL_DOCUMENTING)), 1,
        )
        self.assert_refused(self.reviewed(), _review_report._EDITED)

    def _approved_and_relabelled(self) -> None:
        """Approve the first report, and put the issue back on `validating`."""
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.reviewed(REVIEW_APPROVED_MESSAGE)
        self.github.apply_foreign_label(self.issue, LABEL_VALIDATING)

    def _owes_a_collapse(self) -> None:
        """Leave the terms of a squash an earlier tick began and did not finish."""
        state = self.github.read_pinned_state(self.issue)
        _collapses.record_pending_collapse(
            state, head=_fix_world.PUBLISHED_HEAD, base_sha=COLLAPSE_BASE, count=2,
        )
        self.github.write_pinned_state(self.issue, state)


class SubjectCoverageTest(unittest.TestCase, world._ReviewedReports):
    """An approval covers the whole subject it was handed, report or none."""

    def test_a_pushed_head_voids_approval(self) -> None:
        # The reviewer was handed no report at all, and still approved one
        # head: a push landing while it ran is work it never read.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        self._approves_while(partial(setattr, self.pull_request.head, "sha", MOVED_HEAD))

        self._assert_not_acted_on()

    def test_an_issue_edit_voids_approval(self) -> None:
        self.seeded(ISSUE, PR, LABEL_VALIDATING)

        self._approves_while(partial(_drift_world.edits, self, _drift_world.LATER_BODY))

        self._assert_not_acted_on()

    def test_another_revision_voids_approval(self) -> None:
        # Words are not the subject: a revision the reviewer was not handed is
        # another report however it reads, and so is the report's absence.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        state = self.github.read_pinned_state(self.issue)
        with self._author_policy():
            handed = _review_report._resolves_the_subject(
                self.github, self.issue, state, PR,
                _prompt_context._delivered_thread(self.github, self.issue, state),
            )
            covers = [
                _review_coverage._subject_still_stands(
                    self.github, self.issue, state, subject,
                )
                for subject in (
                    handed,
                    replace(handed, report=replace(handed.report, report_revision=2)),
                    replace(handed, report=None),
                )
            ]

        self.assertEqual(covers, [True, False, False])

    def test_a_late_criterion_holds_the_round(self) -> None:
        # A criterion the report never saw reaches the reviewer's read: landing
        # after the drift check on an ordinary round, landing after the
        # operator's grant that bought the round -- the grant is the reviewer's
        # to read, the criterion is not -- or written as the very reply that
        # retried a reviewer park, which retries itself unasked and so is
        # answered in words only where somebody has something to say. Handed
        # over, it would sit beside a report that never saw it: the round is
        # held with nothing parked or approved and the owed round stood down,
        # and the next tick's drift check resumes the developer on it, whose
        # report is the one a reviewer is then handed beside it.
        for name, reply, reason, lands_late in (
            ("after the drift check", "", "", True),
            ("after a grant", world.GRANT_COMMAND, world.CAP_PARK, True),
            ("as the retry reply", LATE_CRITERION, "reviewer_failed", False),
        ):
            with self.subTest(name):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.reported_round(world.FIRST_REPORT)
                if reply:
                    self.replies_to_a_park(reply, reason)
                read = _prompt_context._delivered_thread
                if lands_late:
                    read = _ChangedMidway(
                        partial(_drift_world.human_reply, self, LATE_CRITERION), read,
                    )

                with patch.object(_prompt_context, "_delivered_thread", read):
                    self.reviewed(REVIEW_APPROVED_MESSAGE)[RUN_AGENT].assert_not_called()

                self.assertEqual(
                    (self.pinned().get(world.AWAITING_HUMAN), world.APPROVED in self.pinned()),
                    (False, False),
                )
                self._answers_the_criterion()

    def _answers_the_criterion(self) -> None:
        """The developer's report reaches the next reviewer beside the criterion."""
        self._ticked(
            self._run_validating,
            MagicMock(side_effect=_fix_world._Runs(
                _fix_world.reported(world.SECOND_REPORT),
            )),
            committed=False,
        )
        handed = world.prompt(self.reviewed())
        self.assertEqual(
            (f"> {world.SECOND_REPORT}" in handed, LATE_CRITERION in handed),
            (True, True),
        )

    def _approves_while(self, change) -> None:
        self._ticked(
            self._run_validating,
            MagicMock(side_effect=_ChangedMidway(change, LATE_APPROVAL)),
            committed=False,
        )

    def _assert_not_acted_on(self) -> None:
        """The run is recorded, and nothing an approval does has happened."""
        pinned = self.pinned()
        self.assertEqual(
            (pinned.get("last_review_session_id"), world.APPROVED in pinned),
            (LATE_REVIEWER, False),
        )
        self.assertNotIn((ISSUE, LABEL_DOCUMENTING), self.github.label_history)


if __name__ == "__main__":
    unittest.main()
