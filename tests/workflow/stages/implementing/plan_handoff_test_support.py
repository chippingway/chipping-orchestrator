# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The plan PR an implementing tick can arrive carrying, in its two shapes.

An issue relabeled out of `discussion` reaches this stage with a pull request
that says what to BUILD rather than a build, and the two shapes it arrives in
are what every test here is seeded from: the relabel as the humans left it,
with the publication's park and records still standing, and the same issue once
this stage's own handoff has accepted it -- park gone, path record retired, and
the tip it certified sitting in `read_only_baseline_sha`.

The second is a durable state and not a momentary one. The handoff is written
before the developer runs and everything the tick stages after it is dropped by
an interruption on purpose, so an issue can sit there for polls at a time with
the design still on an open pull request the humans can move.

The tick that drives both is here too, since what differs between the cases is
never how it is run: the branch sits where publication left it and only the
head GitHub reports for that PR changes.
"""

from __future__ import annotations

from tests.support.fakes import FakePR, FakePRRef
from tests.workflow.fixtures import (
    LABEL_DONE,
    LABEL_VALIDATING,
    STATE_CLOSED,
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
    _reported,
)
from tests.workflow.stages.implementing import read_only_relabel_test_support as _support

# The issue whose number the seeded plan path names. Every seeded issue carries
# the same path record, since what the tests turn on is the record standing,
# never which file it points at.
PLAN_ISSUE_NUMBER = 1000
HANDOFF_PR_NUMBER = 5150

PLAN_PATH = f"plans/issue-{PLAN_ISSUE_NUMBER}.md"
PLAN_COMMIT = "the-commit-the-plan-pr-carried"
# What a human's own work on the plan PR leaves as its head: a correction
# pushed to the Markdown, or the base merged in to make the PR mergeable.
AMENDED_PLAN_COMMIT = "the-commit-a-human-edit-left-on-the-plan-pr"
IMPLEMENTED = _reported()
KEY_BRANCH = "branch"


def _add_plan_pr(gh, issue, *, head_sha: str, merged: bool) -> None:
    """Put the issue's recorded plan PR on the remote at `head_sha`."""
    gh.add_pr(
        FakePR(
            number=HANDOFF_PR_NUMBER,
            head_branch=_issue_branch(issue.number),
            head=FakePRRef(sha=head_sha),
            merged=merged,
            state=STATE_CLOSED if merged else "open",
        ),
    )


def _seed_published_plan(issue_number: int, *, head_sha: str, merged: bool = True):
    """An issue relabeled here while the plan's own record still stands.

    The shape the relabel arrives in: the publication's park and its records,
    including the anchor it moved onto the commit it put on the PR -- so the
    branch, the record, and that PR's head name one tip until a human moves it.
    `head_sha` is what they left on it, and no value of it is work of this
    stage's: the record clears before anything here can push.
    """
    seeded = _support._seed_relabeled_discussion(
        issue_number,
        _support.PARK_DISCUSSION_PLAN_PUBLISHED,
        **{
            _support.KEY_PLAN_PATH: PLAN_PATH,
            _support.KEY_PR_NUMBER: HANDOFF_PR_NUMBER,
            _support.KEY_PLAN_SHA: PLAN_COMMIT,
            _support.KEY_ROUND_SHA: PLAN_COMMIT,
            # Recorded beside `pr_number` by the publication that opened the
            # PR, and what keeps the branch resolution off the legacy name.
            KEY_BRANCH: _issue_branch(issue_number),
        },
    )
    _add_plan_pr(*seeded, head_sha=head_sha, merged=merged)
    return seeded


def _seed_accepted_handoff(
    issue_number: int, *, head_sha: str, merged: bool = True,
):
    """An issue whose relabel this stage has already accepted, durably.

    What the guard's own write leaves before the spawn: the park gone, the
    round anchor retired into `read_only_baseline_sha`, and the plan-path
    record spent -- so the commit this stage records is all that is left to
    tell a design from a build, and the only shape a push from here can
    have happened in.

    The baseline beside it is the other half of that reading: it says the
    handoff was accepted and nothing here has published since. That is a
    durable state and not a momentary one, since the write lands before the
    developer runs and an interruption drops everything staged after it.
    """
    seeded = _support._seed_relabeled_discussion(
        issue_number,
        None,
        **{
            _support.KEY_PR_NUMBER: HANDOFF_PR_NUMBER,
            _support.KEY_PLAN_SHA: PLAN_COMMIT,
            _support.KEY_ROUND_BRANCH: None,
            _support.KEY_ROUND_SHA: None,
            _support.KEY_READ_ONLY_BASELINE: PLAN_COMMIT,
        },
    )
    _add_plan_pr(*seeded, head_sha=head_sha, merged=merged)
    return seeded


class _HandoffTickMixin(_PatchedWorkflowMixin, _support._ReadOnlyRelabelMixin):
    """One implementing tick on a branch whose plan PR the humans hold.

    The branch sits where publication left it, which is the commit that PR was
    opened on -- so the guard's own reading of the tip is the certified one and
    what moves between cases is only the head GitHub reports.
    """

    def _run_handoff_tick(self, gh, issue, **overrides):
        """Drive the tick, optionally cut short after the handoff's own write.

        An interrupted run is how a test reads what the handoff recorded: that
        write is durable and everything the tick stages after it is dropped, so
        the pinned state left behind is the handoff's and nothing else's.
        """
        run_options = {
            "unpushed_branch": None,
            "run_agent": _agent(
                session_id=_support.DEV_SESSION, last_message=IMPLEMENTED,
            ),
            "has_new_commits": [False, True],
            "branch_tip_sha": PLAN_COMMIT,
            # The guard reads the checkout first, and a published plan's is on
            # the commit its PR carries; the dev run's own reads follow.
            "head_shas": (PLAN_COMMIT, _support.HEAD_BEFORE_ROUND, _support.HEAD_AFTER_COMMIT),
        }
        run_options.update(overrides)
        return self._run_implementing_on_worktree(gh, issue, **run_options)

    def _assert_nothing_ran(self, mocks) -> None:
        """A tick that ended before the run: nothing spawned, nothing pushed."""
        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.PUSH_BRANCH].assert_not_called()

    def _assert_dev_ran(self, mocks) -> None:
        """A tick whose handoff landed: the implementer spawned exactly once."""
        mocks[_support.RUN_AGENT].assert_called_once()

    def _assert_built_not_finalized(
        self, issue_number: int, head_sha: str,
    ) -> None:
        """The dev ran, the issue went forward, and the plan record is spent."""
        gh, _issue, mocks, pinned = self._run_published_handoff(
            issue_number, head_sha=head_sha,
        )

        self._assert_dev_ran(mocks)
        self.assertNotIn((issue_number, LABEL_DONE), gh.label_history)
        # And the work the developer wrote actually reaches a reviewer. The
        # plan PR the record arrived naming is a document the humans decided
        # on, never the pull request this push joins -- so the push goes out,
        # an implementation PR is opened for it, and the issue is handed on.
        mocks[_support.PUSH_BRANCH].assert_called_once()
        self.assertEqual(len(gh.opened_prs), 1)
        self.assertIn((issue_number, LABEL_VALIDATING), gh.label_history)
        # Its own PR is what the records name from here, so a merge of THAT one
        # finalizes normally.
        self.assertNotEqual(pinned.get(_support.KEY_PR_NUMBER), HANDOFF_PR_NUMBER)
        self.assertIsNone(pinned.get(_support.KEY_PLAN_PATH))

    def _run_published_handoff(
        self, issue_number: int, *, head_sha: str, merged: bool = True, **overrides,
    ):
        """Seed a plan PR on `head_sha`, hand its issue over, and read it back."""
        gh, issue = _seed_published_plan(
            issue_number, head_sha=head_sha, merged=merged,
        )
        mocks = self._run_handoff_tick(gh, issue, **overrides)
        return gh, issue, mocks, dict(gh.pinned_data(issue.number))
