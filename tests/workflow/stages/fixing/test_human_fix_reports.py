# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a fix round answering a human's PR comment hands back, and what it costs.

The human-feedback route is the one that reaches `fixing` from an APPROVED pull
request: a human comments, `in_review` bookmarks the batch and flips the label,
and the round behind it answers. What that round hands back is the same set of
handovers the reviewer's route makes -- a commit under the report of it, a
report alone on the head the pull request already carries, and a report a human
published that the round only verifies -- and every one of them goes back to
`workflow:validating` for a fresh read, because a report is a handover the next
reviewer has to see.

The round it closes on is this route's own. The approval the issue was carrying
was earned against the prior head, so the counter RESETS rather than advancing.
That value is frozen onto the report's record before anything is published, so a
settlement landing ticks later applies the reset rather than re-deriving one from
a comment whose route anchor it has itself already cleared.

What keeps its own road is here too: the ordinary non-actionable `ACK:` still
returns the pull request to `in_review`, a question still parks with the batch
preserved, a requirements edit nobody answered publishes nothing, and a
verification whose location no longer says what the developer read there
publishes nothing either.
"""

from __future__ import annotations

import unittest

from orchestrator.workflow.engine import report_delivery as _report_delivery
from tests.workflow import (
    drift_reports as _drift_world,
    fix_report_crashes as crashes,
    fix_reports as world,
    human_fix_reports as human,
)
from tests.workflow.fixtures import (
    LABEL_FIXING,
    LABEL_IN_REVIEW,
    LABEL_VALIDATING,
)

ISSUE = 1_795

PR = 17_950

RUN_AGENT = "run_agent"

PUSH_BRANCH = "_push_branch"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

REVIEW_ROUND = "review_round"

PENDING_FIX_AT = "pending_fix_at"

PENDING_FIX_IDS = "pending_fix_issue_ids"

PR_LAST_COMMENT_ID = "pr_last_comment_id"

USER_CONTENT_HASH = "user_content_hash"

AGENT_RUNS_USED = "agent_runs_used"

CURRENT = "current"

# The round the issue arrives carrying. The reviewer approved it -- which is
# what put the issue on `in_review` at all -- so the count behind that approval
# is what this route's handover drops rather than advances.
SPENT_ROUNDS = 2

# Where a round this route hands back leaves the issue, and what the pull
# request carries afterwards: `validating` for a fresh read, the approval's
# count reset, nobody waited for, and the round's one report.
HANDED_BACK = ((ISSUE, LABEL_VALIDATING), 0, False, 1)

# The report a human published on the pull request themselves, which a round
# can verify instead of writing one of its own.
HUMAN_REPORT = "### Report\n\nRan the suite by hand; every check is green."

# What the whole route costs: the fixing tick's own developer, and nothing for
# the `in_review` tick ahead of it or any replay behind it.
_THE_ONE_DEVELOPER = 1

# The comment that names no actionable change, and the reply it earns: the one
# road out of this stage that goes back to `in_review` rather than to review.
VAGUE_FEEDBACK = "ping -- anything else needed here?"

ACK_REPLY = "ACK: the comments name no actionable change."

# The two handovers a round writes its own report for: what the human asked
# for, whether the branch moves, and the commit the report ends up bound to.
_HANDOVERS = (
    ("a commit", human.HUMAN_CODE_FEEDBACK, True, world.FIXED_HEAD),
    ("a report alone", human.HUMAN_REPORT_FEEDBACK, False, world.PUBLISHED_HEAD),
)

# What a human can do to the report they published between the developer
# reading it and the transaction re-reading it. Both are definite answers about
# content this workflow does not own, and neither may be settled on.
_LOST_VERIFICATIONS = (
    ("edited since", lambda case, posted: posted.edit("rewritten by hand")),
    (
        "gone since",
        lambda case, posted: case.pull_request.issue_comments.remove(posted),
    ),
)


def _handed(case, report: str = world.REPORT_TEXT) -> tuple:
    """What a road left behind.

    Where the issue landed, the round it is carrying now, whether it is waiting
    on a human, and how many comments on the pull request carry `report`.
    """
    return (
        case.github.label_history[-1],
        case.pinned()[REVIEW_ROUND],
        case.pinned()[AWAITING_HUMAN],
        len(case.published_reports(report)),
    )


class HumanFeedbackHandoverTest(unittest.TestCase, human._HumanFixReportMixin):
    """The handovers a comment on an approved pull request earns."""

    def test_every_handover_earns_a_fresh_review(self) -> None:
        # Code or words, the round hands the pull request back for a fresh read
        # with its report on it: the bookmarks the route wrote are gone, the
        # approval's round is reset rather than advanced, nobody is waited for,
        # and the pull request carries the report exactly once.
        for described, asked, commits, head in _HANDOVERS:
            with self.subTest(handover=described):
                self.seeded(
                    ISSUE, PR, LABEL_IN_REVIEW, review_round=SPENT_ROUNDS,
                )

                mocks = self.human_fix(
                    world.reported(), feedback=asked, committed=commits,
                )

                self.assertEqual(
                    mocks[PUSH_BRANCH].call_count, int(commits),
                    "the branch moves exactly when the round committed",
                )
                self.assertEqual(
                    (
                        self.records()[CURRENT].subject.source_sha,
                        self.pull_request.head.sha,
                    ),
                    (head, head),
                    "the report is bound to the head the reviewer will read",
                )
                self.assertEqual(
                    (
                        *_handed(self),
                        self.pinned()[PENDING_FIX_AT],
                        self.pinned()[PENDING_FIX_IDS],
                    ),
                    (*HANDED_BACK, None, None),
                    "the route's own bookkeeping is closed by the handover",
                )

    def test_a_human_published_report_is_verified(self) -> None:
        # The human wrote the report onto the pull request themselves and the
        # round says so rather than writing another. The transaction re-reads
        # that exact comment and holds its text to the digest the round named,
        # so the pull request keeps the one report it had -- and the route
        # hands the issue on for the same fresh review a written one earns.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, review_round=SPENT_ROUNDS)
        published = world.published_report(self, HUMAN_REPORT)

        self.human_fix(
            world.verified(PR, published.id, HUMAN_REPORT),
            feedback=human.HUMAN_REPORT_FEEDBACK,
            committed=False,
        )

        self.assertEqual(
            self.records()[CURRENT].location.comment_id, published.id,
            "the record names the comment the round verified",
        )
        self.assertEqual(
            _handed(self, HUMAN_REPORT), HANDED_BACK,
            "a verified report is never reposted beside itself",
        )

    def test_a_human_sharing_the_account_is_read(self) -> None:
        # One personal access token between a person and the orchestrator is
        # the ordinary single-operator deployment, and it is the shape a filter
        # answering on the AUTHOR would silence: this comment wears the login
        # the orchestrator posts under and carries none of its markers. Read as
        # the feedback it is, it opens the round any other comment opens.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, review_round=SPENT_ROUNDS)
        human.shared_account_reply(self, human.HUMAN_REPORT_FEEDBACK)

        self.rescanned()
        self.resumed(world.reported(), committed=False)

        self.assertEqual(_handed(self), HANDED_BACK)

    def test_a_later_comment_outlives_the_round(self) -> None:
        # A human adds to the pull request while the developer is out. This
        # round's prompt never carried it, so every reader stops below it and
        # the next `in_review` tick routes it to a fix of its own -- rather
        # than recording it as answered by a report that says nothing about it.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, review_round=SPENT_ROUNDS)
        landing = human.comments_mid_run(self, world.reported())

        self.human_fix(
            landing, feedback=human.HUMAN_REPORT_FEEDBACK, committed=False,
        )

        self.assertEqual(_handed(self), HANDED_BACK)
        self.assertLess(
            self.pinned()[PR_LAST_COMMENT_ID], landing.comment.id,
            "the reader stops below the comment no prompt carried",
        )
        self.github.apply_foreign_label(self.issue, LABEL_IN_REVIEW)

        self.rescanned()

        self.assertEqual(
            (self.github.label_history[-1], self.pinned()[PENDING_FIX_IDS]),
            ((ISSUE, LABEL_FIXING), [landing.comment.id]),
            "the comment nobody answered opens a round of its own",
        )


class HumanFeedbackRefusalTest(unittest.TestCase, human._HumanFixReportMixin):
    """The replies this route publishes nothing for, and where each goes."""

    def test_the_replies_that_keep_their_own_road(self) -> None:
        # Neither of these is a handover, so neither costs the approval's round
        # or puts anything on the pull request. The acknowledgement says the
        # comment asked for nothing and re-arms the ready ping from
        # `in_review`; the question says the developer could not answer and
        # parks, with the bookmarks kept so a human's reply replays the batch
        # instead of losing it.
        roads = (
            (VAGUE_FEEDBACK, ACK_REPLY, LABEL_IN_REVIEW, False),
            (
                human.HUMAN_CODE_FEEDBACK, world.QUESTION_REPLY,
                LABEL_FIXING, True,
            ),
        )
        for asked, reply, landed, parked in roads:
            with self.subTest(road=landed):
                self.seeded(
                    ISSUE, PR, LABEL_IN_REVIEW, review_round=SPENT_ROUNDS,
                )

                self.human_fix(reply, feedback=asked, committed=False)

                self.assertEqual(
                    _handed(self),
                    ((ISSUE, landed), SPENT_ROUNDS, parked, 0),
                )
                self.assertEqual(
                    self.pinned()[PENDING_FIX_AT] is None, not parked,
                    "only the road that ends the round drops the bookmarks",
                )

    def test_an_edit_mid_run_is_not_answered(self) -> None:
        # A human rewrites the requirements while the developer is out. The
        # report the round wrote answers the criteria as they were, so nothing
        # of it goes out and nothing of the round is charged -- and the
        # baseline is left where the developer's own read put it, below the
        # edit, so the content nobody has answered still reads as unanswered.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, review_round=SPENT_ROUNDS)

        self.human_fix(
            self.mid_run("edit", world.reported()),
            feedback=human.HUMAN_REPORT_FEEDBACK,
            committed=False,
        )

        self.assertEqual(
            _handed(self), ((ISSUE, LABEL_FIXING), SPENT_ROUNDS, False, 0),
        )
        self.assertNotEqual(
            self.pinned()[USER_CONTENT_HASH],
            _drift_world.handed_revision(self.issue),
            "the edit nobody answered is still ahead of the baseline",
        )

    def test_a_verification_its_location_lost(self) -> None:
        # The developer read a report a human published and verified it, and
        # the human moved it out from under them. Nothing about that is the
        # round's to fix and nothing about it may be settled on: the pull
        # request gets no report, the approval's round is not spent, the issue
        # stays on `workflow:fixing`, and the poll behind it resumes NOBODY --
        # it announces the wait only a human can end.
        for described, breaks in _LOST_VERIFICATIONS:
            with self.subTest(verification=described):
                self.seeded(
                    ISSUE, PR, LABEL_IN_REVIEW, review_round=SPENT_ROUNDS,
                )
                published = world.published_report(self, HUMAN_REPORT)
                reply = world.verified(PR, published.id, HUMAN_REPORT)
                breaks(self, published)

                self.human_fix(
                    reply,
                    feedback=human.HUMAN_REPORT_FEEDBACK,
                    committed=False,
                )
                held = self.polled()

                held[RUN_AGENT].assert_not_called()
                self.assertEqual(
                    (
                        *_handed(self, HUMAN_REPORT),
                        self.pinned()[PARK_REASON],
                    ),
                    (
                        (ISSUE, LABEL_FIXING),
                        SPENT_ROUNDS,
                        True,
                        0,
                        _report_delivery.UNDELIVERABLE_REPORT,
                    ),
                )


class HumanFeedbackRoundTest(unittest.TestCase, human._HumanFixReportMixin):
    """What the reset costs, and how many times a replay may charge it."""

    def test_the_reset_survives_a_lost_relabel(self) -> None:
        # The settlement applied what the record froze -- the reset, the
        # bookmarks, the readers -- and the process ended before the label
        # moved. The tick behind it finishes that round on the mark the
        # settlement raised: no second developer, no second report, and the
        # round still this route's own 0 rather than a count re-derived from a
        # comment whose `pending_fix_at` that settlement has already cleared.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, review_round=SPENT_ROUNDS)
        self.routed(human.HUMAN_REPORT_FEEDBACK)

        with crashes.dying_before_the_relabel(self):
            self.resumed(world.reported(), committed=False)
        self.assertEqual(self.github.label_history[-1], (ISSUE, LABEL_FIXING))

        handed = self.polled()

        handed[RUN_AGENT].assert_not_called()
        self.assertEqual(_handed(self), HANDED_BACK)

    def test_a_settled_replay_charges_nothing(self) -> None:
        # The reconciliation ahead of every later handler reads the same
        # comment. Replayed over a round that already settled, twice, it posts
        # no second report, charges no second run, and counts no second round:
        # what a settlement applies is the pair the transaction froze, and
        # re-derived here -- with the route anchor gone -- this route's reset
        # would read as the reviewer's bump.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW, review_round=SPENT_ROUNDS)
        self.human_fix(
            world.reported(),
            feedback=human.HUMAN_REPORT_FEEDBACK,
            committed=False,
        )

        self.reconcile()
        self.reconcile()

        self.assertEqual(
            (*_handed(self), self.pinned()[AGENT_RUNS_USED]),
            (*HANDED_BACK, _THE_ONE_DEVELOPER),
        )


if __name__ == "__main__":
    unittest.main()
