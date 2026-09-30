# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a generation's first late reading may take as its baseline.

The issue-wide `user_content_hash` records what the developer last worked
against, and the first late baseline is taken over the part of the thread that
hash covers and no further. A comment written after it was read by nobody, so
it is handed to the developer whole rather than folded in; an edit made after
it is the requirements moving under the candidate, so it parks, and taking
that edit back clears the park without a reply.
"""
from __future__ import annotations

from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.stages.decomposition import late_content_support as _support
from tests.workflow.stages.decomposition.late_content_replies import human_comment, reply
from tests.workflow.stages.decomposition.late_requirements_support import (
    KEY_USER_CONTENT_HASH,
    recorded_baselines,
    requirements,
)
from tests.workflow.stages.decomposition.late_revision_support import DEV_PIN, DEV_SESSION, RevisionCase
from tests.workflow.stages.decomposition.late_test_support import KEYS

INSTRUCTION = "and the importer must log every skipped row"

# Background past what a prompt's thread excerpt holds, so the next agent to
# read the comment through an excerpt of the thread's tail would lose its head.
BACKGROUND_WORDS = 700

BACKGROUND = "background " * BACKGROUND_WORDS

UNREAD = f"{INSTRUCTION}\n\n{BACKGROUND}"

# A comment the thread carried before the candidate was frozen.
OLDER_ID = 9

SETTLED_SCOPE = "the importer reads CSV only"

RUN_GRANT = "/orchestrator add-agent-runs 3"

# The spawn keyword that names the session a run resumes.
RESUMED = "resume_session_id"


class IssueBaselineCase(RevisionCase):
    """A late issue frozen on a settled issue-wide requirements baseline."""

    def _frozen_on_the_issue_baseline(self, comments: tuple = ()) -> str:
        """A generation with no late baseline, frozen on a settled issue-wide one.

        `comments` are what the thread carried when that baseline was settled,
        so the recorded hash covers them.
        """
        self._seed(baseline=False, comments=comments, **DEV_PIN)
        settled = requirements(self.issue)
        self.github.seed_state(self.issue.number, **{
            **self._pinned(), KEY_USER_CONTENT_HASH: settled,
        })
        return settled

    def _assert_read_as_it_stands(self) -> None:
        """The issue-wide baseline is recorded over the thread as it now reads."""
        self.assertEqual(self._pinned()[KEY_USER_CONTENT_HASH], requirements(self.issue))


class FirstBaselineTest(IssueBaselineCase):
    """The first late reading stops where the issue-wide baseline does."""

    def test_a_covered_reading_is_the_baseline(self) -> None:
        self._frozen_on_the_issue_baseline()

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        spawn.assert_called_once()
        self.assertTrue(self._pinned()[_support.KEY_TITLE_BODY_HASH])
        self._assert_read_as_it_stands()

    def test_an_unread_comment_goes_to_the_developer(self) -> None:
        # Written after the issue-wide baseline -- while the developer's last
        # run was out, say -- so no agent has read it. The developer is resumed
        # with it quoted whole instead of an adjudicator reading its tail.
        self._frozen_on_the_issue_baseline()
        reply(self.issue, UNREAD)

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        self.assertEqual(spawn.call_args.kwargs[RESUMED], DEV_SESSION)
        self.assertIn(UNREAD, spawn.call_args.args[1])
        self._assert_read_as_it_stands()

    def test_with_nothing_recorded_nothing_is_counted(self) -> None:
        # An issue with no recorded requirements baseline has recorded nothing
        # as read, so a comment already on the thread is not taken as the
        # baseline either: the developer is handed it whole.
        self._seed(baseline=False, comments=(human_comment(OLDER_ID, UNREAD),), **DEV_PIN)

        _outcome, spawn = self._revise()

        self.assertEqual(spawn.call_args.kwargs[RESUMED], DEV_SESSION)
        self.assertIn(UNREAD, spawn.call_args.args[1])

    def test_a_run_grant_is_no_guidance(self) -> None:
        # With nothing recorded, the command on the thread is uncounted. It
        # widens what the issue may spend and is no requirement, whether the
        # hold that reads it answered it -- leaving the shared mark past it --
        # or not: the adjudication carries on rather than resuming the
        # developer over a number. Carrying on consumes nothing, so the
        # reading is recorded as observed and no baseline is recorded.
        for place, marks in (
            ("answered", {_support.KEY_LAST_ACTION_COMMENT_ID: OLDER_ID}),
            ("unanswered", {}),
        ):
            with self.subTest(command=place):
                self._seed(
                    baseline=False, comments=(human_comment(OLDER_ID, RUN_GRANT),), **DEV_PIN, **marks,
                )

                outcome, spawn = self._run()

                self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
                spawn.assert_called_once()
                observed = requirements(self.issue)
                self.assertEqual(recorded_baselines(self._pinned()), (None, observed))

    def test_an_edit_since_the_issue_baseline_parks(self) -> None:
        # No part of the thread reproduces the issue-wide baseline beside the
        # body as it now reads, so the body moved after the developer last
        # worked against it: that is drift, and nothing is adjudicated over it.
        picked_up = self._frozen_on_the_issue_baseline()
        self.issue.body = _support.EDITED_BODY

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()
        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.park_reason], _support.PARK_CONTENT_DRIFT)
        self.assertEqual(pinned[KEY_USER_CONTENT_HASH], picked_up)

    def test_a_comment_beside_an_edit_is_delivered(self) -> None:
        # The edit leaves no prefix to baseline on, so which comments were
        # read cannot be told: none is counted. The comment then sits under
        # the drift park's notice as withheld guidance, and the certificate
        # that ends the park hands it to the developer whole instead of
        # folding it into a baseline an adjudicator reads only the end of.
        self._frozen_on_the_issue_baseline()
        self.issue.body = _support.EDITED_BODY
        reply(self.issue, UNREAD)
        self._run()
        reply(self.issue, _support.BARE_CONTINUE)

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        self.assertEqual(spawn.call_args.kwargs[RESUMED], DEV_SESSION)
        self.assertIn(UNREAD, spawn.call_args.args[1])
        self._assert_read_as_it_stands()


class RevertedEditTest(IssueBaselineCase):
    """An edit taken back under a first reading's drift park reconciles it.

    The issue-wide baseline covers a comment the thread already carried, so
    the park's baseline holds the title and body to a hash no text alone
    reproduces, and only the covered prefix found again can show the revert.
    """

    def test_the_park_clears_without_a_reply(self) -> None:
        # The covered comment is counted rather than handed on, and the
        # candidate is adjudicated rather than a developer resumed.
        settled = self._parked_then_reverted()

        outcome, spawn = self._run()

        self.assertEqual(outcome.disposition, _LateDisposition.DECIDED)
        spawn.assert_called_once()
        self.assertNotEqual(spawn.call_args.kwargs.get(RESUMED), DEV_SESSION)
        pinned = self._pinned()
        self.assertFalse(pinned[KEYS.awaiting])
        self.assertIsNone(pinned[KEYS.park_reason])
        self.assertEqual(pinned[_support.KEY_COMMENT_WATERMARK], OLDER_ID)
        self.assertEqual(pinned[KEY_USER_CONTENT_HASH], settled)

    def test_an_unread_comment_is_handed_on(self) -> None:
        # The revert reconciles the reading on the prefix the issue-wide
        # baseline covers, and no further: a comment written after it was
        # read by nobody, so the developer is resumed with it quoted whole.
        self._parked_then_reverted(unread=UNREAD)

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        self.assertEqual(spawn.call_args.kwargs[RESUMED], DEV_SESSION)
        self.assertIn(UNREAD, spawn.call_args.args[1])
        self._assert_read_as_it_stands()

    def _parked_then_reverted(self, unread: str | None = None) -> str:
        """Park a first reading on a body edit, then take the edit back.

        `unread` is a comment written past the issue-wide baseline beside the
        edit. Returns the recorded issue-wide hash.
        """
        settled = self._frozen_on_the_issue_baseline(
            comments=(human_comment(OLDER_ID, SETTLED_SCOPE),),
        )
        written = self.issue.body
        self.issue.body = _support.EDITED_BODY
        if unread is not None:
            reply(self.issue, unread)
        parked, _spawn = self._run()
        self.assertEqual(parked.disposition, _LateDisposition.PARKED)
        self.issue.body = written
        return settled


class LegacyBaselineTest(IssueBaselineCase):
    """A baseline taken over the whole thread before baselines were bounded.

    It counts a comment no stage consumed, and the body has moved since, so
    what the recorded hash covered can no longer be told. The drift park it
    takes counts no comment, and the continue that answers it resumes the
    developer with the comment quoted whole rather than certifying over it --
    whether an older hash is recorded or none at all.
    """

    def test_the_continue_hands_the_comment_on(self) -> None:
        for recorded in ("an older baseline", "no baseline"):
            with self.subTest(recorded=recorded):
                self._counted_over(older=recorded == "an older baseline")
                self.issue.body = _support.EDITED_BODY
                parked, _spawn = self._run()
                self.assertEqual(self._pinned()[KEYS.park_reason], _support.PARK_CONTENT_DRIFT)
                reply(self.issue, _support.BARE_CONTINUE)

                revised, resumed = self._revise()

                self.assertEqual(parked.disposition, _LateDisposition.PARKED)
                self.assertEqual(revised.disposition, _LateDisposition.REVISED)
                self.assertIn(UNREAD, resumed.call_args.args[1])
                self._assert_read_as_it_stands()

    def _counted_over(self, *, older: bool) -> None:
        """Seed a whole-thread baseline counting one comment the issue-wide one leaves out.

        The older baseline is the one recorded before the comment was written.
        """
        self._seed(bounded=False, comments=(human_comment(OLDER_ID, UNREAD),), **DEV_PIN)
        if older:
            counted = self.issue.comments.pop()
            self.github.seed_state(self.issue.number, **{
                **self._pinned(), KEY_USER_CONTENT_HASH: requirements(self.issue),
            })
            self.issue.comments.append(counted)
