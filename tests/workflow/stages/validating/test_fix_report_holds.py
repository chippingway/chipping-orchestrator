# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What review-fix work a park held for its report may go out under, and where that hold ends.

A round a human's answer resumes over held work may hand over a `REPORT:
VERIFIED` -- an assertion that a report somebody else wrote is already on
GitHub. Its worth is somewhere else: in a place the binding may refuse and a
human may edit, read again only when the report settles, after the push. So
before the push the verification is asked what the binding would ask of it --
a report on this issue's own pull request, and not on the description that pull
request needs for its closing reference and attribution -- and whether it still
reads back. A push that failed and is retried asks again, since the comment can
move between the two attempts. A refusal keeps the commit in the worktree and
parks for a human.

The hold has an edge it must not cross: an Antigravity round the timeout killed
over work nothing held leaves the feedback it consumed for the next poll to
replay, as it always has.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.agents.models import ToolLifecycle
from orchestrator.github.developer_reports import content_digest
from orchestrator.workflow.engine import report_delivery as _report_delivery
from orchestrator.workflow.stages.implementing import dev_pr as _dev_pr
from tests.support.fakes import FakeComment, FakePR, FakeUser
from tests.workflow import drift_reports as _drift_world, fix_reports as world
from tests.workflow.fixtures import LABEL_VALIDATING, TEST_REPO_SLUG, _agent

ISSUE = 1_812

PR = 18_120

PUSH_BRANCH = "_push_branch"

RUN_AGENT = "run_agent"

PARK_REASON = "park_reason"

# The round that holds the work: one fix committed, and the question about the
# other with no report -- and the human's answer, which resumes it.
ASKED = (
    "Committed the first fix. Who lands the second one?\n\n"
    "1. I open a separate pull request.\n"
    "2. You land it."
)

DECIDED = "Open a separate pull request."

# The report a human wrote, as the developer verifies it.
HELD_REPORT = "Report for the held fix."

# A report on another pull request of the same repository, and where it is.
ELSEWHERE_ID = 98_123

ELSEWHERE = FakeComment(id=ELSEWHERE_ID, body="Report for another change.", user=FakeUser("alice"))

OTHER_PR = PR + 1

# What the notice names of each refusal.
ON_ANOTHER_PR = f"names a report on PR #{OTHER_PR}"

ON_THE_DESCRIPTION = "this pull request's own description"

NOT_READ_BACK = "the report it names is gone, was edited since"

# The park a held push leaves, and what a push that went out leaves instead.
HELD = (0, world.PUBLISHED_HEAD, _report_delivery.UNDELIVERABLE_REPORT, True)

PUSHED = (1, world.FIXED_HEAD, None, None)

# The edit a human makes to the verified comment between a push that failed
# and its retry, or none.
RETRIES = (
    ("an edited report", "Edited report.", HELD),
    ("the report as verified", HELD_REPORT, PUSHED),
)

# An Antigravity command the timeout killed the round with, still running.
RUNNING_STEP = ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE")


def _on_another_pull_request(case) -> str:
    """A verification of a report on another pull request of this repository."""
    case.github.add_pr(FakePR(number=OTHER_PR, head_branch="other", issue_comments=[ELSEWHERE]))
    return world.verified(OTHER_PR, ELSEWHERE.id, ELSEWHERE.body)


def _on_the_bare_description(case) -> str:
    """A verification of this pull request's description, which closes nothing and names no session."""
    case.pull_request.body = HELD_REPORT
    return _on_the_description(case.pull_request.body)


def _on_a_named_description(case) -> str:
    """A verification of this pull request's description, which closes the issue and names the session."""
    attribution = _dev_pr._dev_pr_attribution(case.github.read_pinned_state(case.issue))
    case.pull_request.body = f"{HELD_REPORT}\n\nResolves #{ISSUE}\n\n{attribution}"
    return _on_the_description(case.pull_request.body)


def _on_the_description(body: str) -> str:
    """A finished round's message verifying the report this pull request's description holds."""
    return f"done\n\nREPORT: VERIFIED https://github.com/{TEST_REPO_SLUG}/pull/{PR} sha256:{content_digest(body)}"


# What each verification the binding is asked about leaves, and the words
# the notice over a held one carries.
VERIFICATIONS = (
    ("a report on another pull request", _on_another_pull_request, HELD, ON_ANOTHER_PR),
    ("a description that closes nothing", _on_the_bare_description, HELD, ON_THE_DESCRIPTION),
    ("a description naming the issue and session", _on_a_named_description, PUSHED, None),
)


class VerifiedHoldTest(unittest.TestCase, world._FixReportMixin):
    """A verified report over held work, asked before the push it would let out."""

    def test_the_binding_is_asked_before_the_push(self) -> None:
        # A verification the binding refuses -- on another pull request, or on
        # the description this one needs to close the issue -- is refused with
        # nothing pushed, since the commits a report lets out are not taken
        # back by its refusal. A description that closes the issue and names
        # the session is one the binding takes, and the work goes out under it.
        for described, arranged, left, notice in VERIFICATIONS:
            with self.subTest(report=described):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.requested_fix(ASKED)
                world.replied(self, DECIDED)

                mocks = self.parked_resume(arranged(self), **_drift_world.STRANDED)

                self.assertEqual(_left(self, mocks), left)
                if notice:
                    self.assertIn(notice, self.github.posted_comments[-1][1])

    def test_a_retried_push_reads_the_report_again(self) -> None:
        # The report read back when it was recorded, and the push then failed.
        # A human editing it before the retry moves it off the revision the
        # developer verified, so the retry keeps the commit in the worktree
        # and parks; left as verified, the retry publishes the work under it.
        for described, body, left in RETRIES:
            with self.subTest(report=described):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.requested_fix(ASKED)
                verified = world.published_report(self, HELD_REPORT)
                world.replied(self, DECIDED)
                self.parked_resume(
                    world.verified(PR, verified.id, verified.body), push_branch=False, **_drift_world.STRANDED,
                )
                verified.body = body

                mocks = self._ticked(self._run_fixing, MagicMock(), **_drift_world.STRANDED)

                mocks[RUN_AGENT].assert_not_called()
                self.assertEqual(_left(self, mocks), left)
                if left == HELD:
                    self.assertIn(NOT_READ_BACK, self.github.posted_comments[-1][1])


class UnheldTimeoutTest(unittest.TestCase, world._FixReportMixin):
    """An Antigravity timeout over work nothing held."""

    def test_its_feedback_is_replayed(self) -> None:
        # The round a human's answer resumed committed and was killed by the
        # timeout with a command still running, over work no park held. The
        # feedback it consumed stays unread, so the next poll resumes the
        # developer on it again rather than pushing what the killed run left.
        self.seeded(ISSUE, PR, LABEL_VALIDATING, dev_agent="agy")
        self.requested_fix(ASKED, committed=False)
        world.replied(self, DECIDED)
        self.parked_resume(_agent(session_id=world.DEV_SESSION, timed_out=True, unfinished_steps=(RUNNING_STEP,)))

        mocks = self._ticked(
            self._run_fixing, MagicMock(return_value=_agent(invoked=False)), **_drift_world.STRANDED,
        )

        mocks[RUN_AGENT].assert_called_once()
        self.assertEqual(
            (
                DECIDED in mocks[RUN_AGENT].call_args.args[1],
                mocks[PUSH_BRANCH].call_count,
                self.pull_request.head.sha,
            ),
            (True, 0, world.PUBLISHED_HEAD),
        )


def _left(case, mocks) -> tuple:
    """What the tick left: its pushes, the pull request's head, the park, and the undescribed-work flag."""
    pinned = case.pinned()
    return (
        mocks[PUSH_BRANCH].call_count,
        case.pull_request.head.sha,
        pinned.get(PARK_REASON),
        pinned.get(_report_delivery.UNREPORTED_WORK),
    )


if __name__ == "__main__":
    unittest.main()
