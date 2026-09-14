# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One docs pass driven onto a pull request the remote already carries.

The final documentation pass is the last push before a human is asked to
merge, so its commit is measured like every other candidate for an open pull
request: what that pull request COMES TO with the commit in it, against the
configured ceiling. The three roads a docs commit reaches that push by are
seeded here -- a fresh pass that committed, a commit an earlier tick stranded,
and a `DOCS: NO_CHANGE` reply that still has one waiting.

The values sit beside them because the gate's contract is one contract read
from several roads: the ceiling a case seeds, the commits it names, and the
pinned fields a hold and a landed push write are the same wherever the tick
entered from.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator import config
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow import fixtures
from tests.workflow.stages.documenting import (
    documenting_test_support as documenting,
)

MEASURED_BASE_SHA = fixtures.MEASURED_BASE_SHA
MEASURED_CANDIDATE_SHA = fixtures.MEASURED_CANDIDATE_SHA
LABEL_DOCUMENTING = fixtures.LABEL_DOCUMENTING

# The head the pull request stands on when a docs pass opens, which is the one
# the pass hands the gate as the head its push replaces.
ENTERED_HEAD = documenting.SHA_BEFORE

# The ahead/behind reading a branch level with its remote answers.
IN_SYNC = (0, 0)

# What one docs commit waiting on top of the remote tip answers.
ONE_RECOVERED = (1, 0)

CEILING = 5
AT_THE_CEILING = 5
PAST_THE_CEILING = 6
UNDER_THE_CEILING = 4
MAX_ADDED_LINES = "MAX_ADDED_LINES"

# The stamp a finished pass carries, which is what tells the handoff's own
# durable write from every write a tick takes before it.
VERDICT_KEY = documenting.DOCS_VERDICT

# The receipt a hold leaves the handoff, and the frozen record beside it.
KEY_SETTLED_DOCS_SHA = "docs_settled_sha"
KEY_ADDITIONS = "late_additions"
KEY_BASE_SHA = "late_base_sha"
KEY_CANDIDATE_SHA = "late_candidate_sha"
KEY_SOURCE_STAGE = "late_source_stage"
KEY_PUBLISHED_PR = "late_published_pr_number"
KEY_PUBLISHED_SHA = "late_published_sha"

# The two halves of the debt a push that has not landed yet still owes.
KEY_APPROVED_SHA = "late_approved_sha"
KEY_APPROVED_LEASE = "late_approved_lease"

# Where a comment this orchestrator posted is recorded, so the watermark walk
# seeds past it and the in_review feedback scan drops it rather than resuming a
# dev over an informational post of ours.
ORCHESTRATOR_COMMENT_IDS = "orchestrator_comment_ids"
PR_LAST_COMMENT_ID = "pr_last_comment_id"

# The receipt a landed gated push leaves. It is the implementing seam's own
# field wherever the push was made from: it names what this branch put on the
# remote rather than the stage that put it there.
KEY_RECEIPT_SHA = "implementing_published_sha"

# The seam the count is taken through, and the two keywords a gated push names
# its commit and pins its ref by.
COUNT_ADDED_LINES = "_count_added_lines"
REVISION = "revision"
LEASE = "force_with_lease"

PARK_MEASUREMENT_FAILED = "late_measurement_failed"
PARK_CANDIDATE_MOVED = "late_candidate_moved"

# A pull request somebody else pushed to while the docs agent was out.
MOVED_PR_HEAD = "cafef00d" * 5

# A commit the checkout went to while the push was out, for the race the
# publication boundary refuses on the far side of its own effect.
MOVED_AFTER_PUSH = "de" * (fixtures.SHA_LENGTH // 2)

DOCS_REPLY = "docs: README tweak"

# What the pull request is told a docs commit that landed carries, and what a
# tick that only finished the handoff an earlier one left owed says instead.
PUSHED_NOTICE = ":books: documenting pass: pushed docs commit."
HANDOFF_NOTICE = "finished the handoff it was still owed"
NO_CHANGE_REPLY = "Nothing left to write.\nDOCS: NO_CHANGE"

# The human reply that wakes a parked docs pass, past the watermark the park
# left behind.
RESUME_WATERMARK = 7000
RESUME_COMMENT_ID = 7100
RESUME_REPLY = "try again"

WRITE_PINNED_STATE = "write_pinned_state"
WRITE_REJECTED = "pinned write rejected"
SET_WORKFLOW_LABEL = "set_workflow_label"
RELABEL_REJECTED = "label write rejected"


class _CrashesOnTheWrite:
    """A pinned write that dies on the first one `carrying` recognizes.

    Armed off what a write CARRIES rather than off how many came before it: a
    tick freezes, retires, approves, and settles a receipt before it reaches
    the tail, so counting writes would fail one of those instead and never
    reach the windows these are about.
    """

    def __init__(self, wrapped, carrying) -> None:
        self._wrapped = wrapped
        self._carrying = carrying

    def __call__(self, issue, state, **options):
        if self._carrying(state):
            raise RuntimeError(WRITE_REJECTED)
        return self._wrapped(issue, state, **options)


def _a_finished_pass(state) -> bool:
    """The handoff's own write: the first one carrying a stamped verdict.

    Every road that finishes a pass stamps the verdict and announces it before
    this write, so it is the one immediately behind the notice -- the crash
    the receipt the gate put down has to survive.
    """
    return state.get(VERDICT_KEY) is not None


# Where in the tail a tick is killed, as the seam it dies on and what the
# write it refuses carries. `None` refuses the seam outright, which is what a
# relabel that never lands looks like -- the one effect behind the write that
# records the pass.
DIES_ON_THE_WRITE = (WRITE_PINNED_STATE, _a_finished_pass)
DIES_ON_THE_RELABEL = (SET_WORKFLOW_LABEL, None)


class _DocsGateAssertionsMixin:
    """What a docs tick that reached the gate looks like afterwards."""

    def _pinned(self, github) -> dict:
        """What the pinned comment says once this tick has finished."""
        return github.pinned_data(self.issue_number)

    def _assert_unstamped(self, github) -> None:
        """No docs verdict, and the issue not handed on to be merged.

        Both together because either alone would pass for the wrong reason: a
        `docs_verdict` over a commit nothing published tells the next tick the
        docs are in the diff, and an `in_review` handoff puts a pull request
        the docs never joined in front of the person who merges it.
        """
        self.assertIsNone(self._pinned(github).get(documenting.DOCS_VERDICT))
        self.assertNotIn(
            (self.issue_number, documenting.IN_REVIEW), github.label_history,
        )

    def _assert_held(self, github, mocks) -> None:
        """Nothing reached the remote, and nothing was stamped over it."""
        mocks[documenting.PUSH_BRANCH].assert_not_called()
        self._assert_unstamped(github)

    def _assert_handed_off_once(
        self, github, notice=PUSHED_NOTICE, notices=1,
    ) -> None:
        """The stamp, the released receipt, one handoff, and what it said.

        The relabel is counted rather than merely present: the pass ends in
        one place and every road that reaches it has already published, so a
        second one would say a docs pass ran twice over one commit. `notices`
        is asked of each case because the one window the tail cannot close --
        a notice that went out and a write that did not -- re-announces on the
        tick that finishes the handoff.
        """
        pinned = self._pinned(github)
        self.assertEqual(
            pinned[documenting.DOCS_VERDICT], documenting.VERDICT_UPDATED,
        )
        self.assertEqual(
            pinned[documenting.DOCS_CHECKED_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertIsNone(pinned.get(KEY_SETTLED_DOCS_SHA))
        self.assertEqual(len(github.posted_pr_comments), notices)
        self.assertIn(notice, github.posted_pr_comments[-1][1])
        self.assertEqual(
            github.label_history.count(
                (self.issue_number, documenting.IN_REVIEW),
            ),
            1,
        )


class _DocsGateRunMixin:
    """How one documenting tick is driven, whole and interrupted."""

    def _docs_tick(self, github, issue, **run_options):
        """One whole documenting tick, under the ceiling these cases seed."""
        run_options.setdefault("push_branch", True)
        run_options.setdefault("branch_ahead_behind", IN_SYNC)
        with patch.object(config, MAX_ADDED_LINES, CEILING):
            return self._run_documenting(github, issue, **run_options)

    def _crashed(
        self, github, issue, tick, dies=DIES_ON_THE_WRITE, **run_options,
    ):
        """Run one tick with the effect `dies` names refused.

        What is left behind is that tick's effects up to that one and nothing
        past it, which is the state a process killed there leaves.
        """
        seam, carrying = dies
        refusing = MagicMock(side_effect=RuntimeError(RELABEL_REJECTED))
        if carrying is not None:
            refusing = _CrashesOnTheWrite(
                github.write_pinned_state, carrying,
            )
        with patch.object(github, seam, refusing):
            self.assertRaises(RuntimeError, tick, github, issue, **run_options)

    def _crashed_pass(self, dies=DIES_ON_THE_WRITE, **run_options):
        """A fresh docs pass killed where `dies` names, and what it left."""
        github, issue = self._seeded()
        self._crashed(
            github, issue, self._fresh_tick, dies=dies, **run_options,
        )
        return github, issue


class _DocsGateFixtureMixin(
    documenting._FreshDocumentingFixture,
    _DocsGateRunMixin,
    _DocsGateAssertionsMixin,
):
    """The roads a docs commit reaches the gated push by."""

    def _fresh_tick(self, github, issue, **run_options):
        """A docs agent that ran on a branch in sync and committed."""
        run_options.setdefault("run_agent", fixtures._agent(
            session_id=documenting.DEV_SESSION, last_message=DOCS_REPLY,
        ))
        run_options.setdefault(
            "head_shas", [ENTERED_HEAD, MEASURED_CANDIDATE_SHA],
        )
        return self._docs_tick(github, issue, **run_options)

    def _fresh_pass(self, **run_options):
        """A fresh docs pass over a checkout nothing else touched."""
        github, issue = self._seeded()
        return github, self._fresh_tick(github, issue, **run_options)

    def _recovered_pass(self, **run_options):
        """A docs commit an earlier tick committed and never pushed.

        No agent runs on this road: the ahead count is the whole of what says
        there is something to publish, so the seeded run is a spawn the test
        can prove did not happen rather than one it means to drive.
        """
        github, issue = self._seeded()
        return github, self._docs_tick(
            github, issue,
            run_agent=MagicMock(),
            head_shas=[MEASURED_CANDIDATE_SHA],
            branch_ahead_behind=ONE_RECOVERED,
            **run_options,
        )

    def _seeded_resume(self, **state):
        """A parked docs pass with the human reply that wakes it."""
        github, issue = self._seeded(
            awaiting_human=True,
            last_action_comment_id=RESUME_WATERMARK,
            park_reason=documenting.PARK_PUSH_FAILED,
            **state,
        )
        issue.comments.append(FakeComment(
            id=RESUME_COMMENT_ID,
            body=RESUME_REPLY,
            user=FakeUser(documenting.TRUSTED_AUTHOR),
        ))
        return github, issue

    def _no_change_tick(self, github, issue, **run_options):
        """A resumed dev that added nothing over a commit still waiting.

        The one road a `DOCS: NO_CHANGE` verdict still has something to
        publish on: the dev was resumed on a human's reply, committed nothing,
        and the commit an earlier tick left is ahead of the remote.
        """
        run_options.setdefault("run_agent", fixtures._agent(
            session_id=documenting.DEV_SESSION, last_message=NO_CHANGE_REPLY,
        ))
        return self._docs_tick(
            github, issue,
            head_shas=[MEASURED_CANDIDATE_SHA, MEASURED_CANDIDATE_SHA],
            branch_ahead_behind=ONE_RECOVERED,
            **run_options,
        )

    def _no_change_pass(self, seeded=None, **run_options):
        """A no-change verdict over a commit the remote has not got."""
        github, issue = self._seeded_resume(**(seeded or {}))
        return github, issue, self._no_change_tick(
            github, issue, **run_options,
        )

    def _settled_tick(self, github, issue, **run_options):
        """A tick whose only work is the handoff a receipt is still owed.

        Nothing is spawned and nothing is pushed on this road -- the commit is
        already on the pull request -- so the seeded run is a spawn the test
        can prove did not happen.
        """
        run_options.setdefault("run_agent", MagicMock())
        return self._docs_tick(
            github, issue, head_shas=[MEASURED_CANDIDATE_SHA], **run_options,
        )
