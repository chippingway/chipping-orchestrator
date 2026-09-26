# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reviewer-requested fix round, and the report it hands its pull request.

One fix loop, entered two ways. The DIRECT round is the tick whose own reviewer
votes CHANGES_REQUESTED and resumes the developer behind the label flip; the
PARKED resume is the `fixing` tick that answers a human reply to whatever park
that round ended on. Both publish through the same disposition, so the world is
one: an open pull request on the issue's branch whose last publication the
code-publication receipt names, a checkout standing on its head, a push that
moves the pull request to the commit it sends, and a requirements baseline
already agreeing with the issue -- so nothing here reads as a body edit and the
round is the reviewer's.

The pull-request world, the report messages, and the readings a settlement takes
are the requirements-drift world's, which is the same open pull request seen
from the other road; only the ticks and the park these cases drive are this
module's.
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github import developer_reports as _developer_reports
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow import drift_reports as _drift_world, published_reports as _published_reports
from tests.workflow.fixtures import (
    LABEL_FIXING,
    REVIEW_CHANGES_REQUESTED_MESSAGE,
    TEST_REPO_SLUG,
    _agent,
)

DEV_SESSION = _drift_world.DEV_SESSION

# The head the pull request stands on when the round opens, and the commit a
# round that answers in code leaves on the branch.
PUBLISHED_HEAD = _drift_world.PUBLISHED_HEAD

FIXED_HEAD = _drift_world.FIXED_HEAD

REPORT_TEXT = _drift_world.REPORT_TEXT

# A finished round's message, ending on a report ready for publication. The
# same sentence either road's run writes, since what a round reports is not
# what earned it.
reported = _drift_world.reported

# The reviewer's own session, which is not the developer's: a fix round spawns
# a fresh reviewer and resumes the locked dev, and the park events are keyed by
# which of the two produced the result.
REVIEWER_SESSION = "rev-sess"

# What a reviewer asks for that only the report can answer, and the reply a
# developer that answered it in words comes back with.
REPORT_ONLY_FEEDBACK = "the report never says how the suite was run"

# What a human writes to the park a round ended on, which is what the parked
# resume reads its work off.
PARKED_REPLY = "please write the report for the work that is already there"

# The park a round that asked rather than answered leaves, which is the one the
# parked resume clears.
QUESTION_REPLY = "Should the helper move, or only its caller?"


def verified(pr_number: int, comment_id: int, body: str) -> str:
    """A finished round's message, asserting the report is already published.

    The exact comment and the digest read there, which is the whole of what a
    verification asserts -- and the whole of what the transaction re-reads
    before it settles anything.
    """
    return (
        "done\n\nREPORT: VERIFIED "
        f"https://github.com/{TEST_REPO_SLUG}/pull/{pr_number}"
        f"#issuecomment-{comment_id} "
        f"sha256:{_developer_reports.content_digest(body)}"
    )


class _FixReportMixin(_drift_world._DriftReportMixin):
    """Fix-loop ticks over an open pull request the reviewer has read.

    `seeded` builds the world the drift cases build and then agrees the pinned
    baseline with the issue, because the two roads differ in exactly that: a
    drift resume is earned by a baseline the issue has moved off, and a
    reviewer round must not be read as one.
    """

    def seeded(self, issue_number: int, pr_number: int, label: str, **extra) -> None:
        super().seeded(issue_number, pr_number, label, **extra)
        # The baseline the tick's own drift check leaves for the round behind
        # it. Left stale, every case here would resume the developer over an
        # edit instead of over the reviewer's feedback.
        state = self.github.read_pinned_state(self.issue)
        state.set("user_content_hash", _drift_world.handed_revision(self.issue))
        self.github.write_pinned_state(self.issue, state)
        # And the report the pull request was opened with, which is what the
        # first reviewer of the loop is handed.
        _published_reports.publishes_the_report(self.github, self.issue)
        self.opening_report = None
        self.opening_report = self.records()["current"]

    def requested_fix(self, reply, **run_options):
        """One validating tick: the reviewer asks for changes, the dev answers.

        The reviewer is a fresh spawn and the developer is the locked session
        resumed behind the label flip, which is the order the stage runs them
        in -- so the two results are handed to the runner in that order.
        """
        return self._ticked(self._run_validating, MagicMock(side_effect=_Runs(
            _agent(
                session_id=REVIEWER_SESSION,
                last_message=(
                    f"{REPORT_ONLY_FEEDBACK}\n\n"
                    f"{REVIEW_CHANGES_REQUESTED_MESSAGE}"
                ),
            ),
            reply,
        )), **run_options)

    def parked_resume(self, reply, **run_options):
        """One fixing tick: the developer resumed over a human's fresh reply."""
        return self._ticked(
            self._run_fixing, MagicMock(side_effect=_Runs(reply)), **run_options,
        )

    def reconcile(self):
        """The dispatch reconciliation ahead of the next handler, on this host.

        Under the same author policy the ticks run under, because the reading
        it takes over the issue's requirements walks the thread and counts the
        replies it trusts: decided under a different policy, a report recorded
        by one of these ticks would read as answering requirements the issue
        has moved off.
        """
        with self._author_policy():
            return super().reconcile()

    def reviewed(self, last_message: str = "read it"):
        """One later `validating` tick, which spawns a reviewer or does not.

        The road a report left owed is finished on: the review hold binds the
        delivery and settles it there, and refuses the spawn for as long as it
        cannot.
        """
        return self._ticked(
            self._run_validating,
            [_agent(session_id=REVIEWER_SESSION, last_message=last_message)],
            committed=False,
        )

    def _author_policy(self):
        """The author policy every reading in these cases is taken under."""
        return author_policy()

    def _ticked(self, stage, run_agent, **run_options):
        """Run one tick of the fix loop over a checkout on this host.

        A round that `committed` leaves the checkout on `FIXED_HEAD`; one that
        did not leaves it where the pull request stands. The push moves the
        pull request onto the commit it sends and the fetched tip agrees with
        it, as GitHub would answer both once a push has landed.
        """
        standing = self.pull_request.head.sha
        after = FIXED_HEAD if run_options.pop("committed", True) else standing
        options = {
            "has_new_commits": True,
            "dirty_files": (),
            "push_branch": _drift_world._LandingPush(self.pull_request),
            _drift_world.HEAD_SHAS: (standing, after),
            _drift_world.FETCHED_TIP: after,
            **run_options,
        }
        with patch.object(
            _worktree_paths,
            "_worktree_path",
            return_value=_drift_world._EXISTING_WORKTREE,
        ), patch.object(
            config, "MAX_REVIEW_ROUNDS", _REVIEW_ROUNDS,
        ), self._author_policy():
            return stage(self.github, self.issue, run_agent=run_agent, **options)


# Wide enough that no case here is ended by the review cap, which is a bound of
# its own with its own park and its own operator command.
_REVIEW_ROUNDS = 10

# The two run options every case names by their own spelling, and the fetch a
# case seeds to refuse one.
HEAD_SHAS = _drift_world.HEAD_SHAS

AHEAD_BEHIND = _drift_world.AHEAD_BEHIND

REFUSED_FETCH = MagicMock(returncode=1, stderr="no such remote ref")

# What an allowlist that trusts every author is spelled as: empty.
_EVERY_AUTHOR: tuple = ()


@contextlib.contextmanager
def author_policy():
    """The author policy every reading in these cases is taken under.

    Named rather than inherited: an empty allowlist trusts everyone, which is
    the deployment default, and a process whose environment carries one would
    otherwise decide for itself whether a human's reply is feedback, whether it
    counts towards the issue's requirements, and whether the report they
    published is one a verification may settle on.
    """
    with patch.object(config, "ALLOWED_ISSUE_AUTHORS", _EVERY_AUTHOR):
        yield


def parked(case, reason: str | None = None, **extra) -> None:
    """Leave the issue where a round that ended in a park left it.

    The label the fix loop parks under, the flags its notice set, and whatever
    the route recorded beside them -- the shape the direct round leaves behind
    for the resume on the other side of the park.
    """
    case.github.apply_foreign_label(case.issue, LABEL_FIXING)
    state = case.github.read_pinned_state(case.issue)
    state.set("awaiting_human", True)
    state.set("park_reason", reason)
    for key, staged in extra.items():
        state.set(key, staged)
    case.github.write_pinned_state(case.issue, state)


def replied(case, body: str = PARKED_REPLY) -> None:
    """One trusted human reply, above everything the thread already holds."""
    _drift_world.human_reply(case, body)


def published_report(case, body: str) -> FakeComment:
    """One trusted human's report, already on the pull request."""
    comment = FakeComment(
        id=_drift_world.LATER_COMMENT_ID, body=body, user=FakeUser("alice"),
    )
    case.pull_request.issue_comments.append(comment)
    return comment


# Every reading that leaves the head a report alone would go onto unproved, and
# the one world each is seeded in. Four are readings that did not HAPPEN -- a
# tree, a fetch, a divergence count, a local head -- and the last is one that
# happened and disagrees: a remote that has moved on.
#
# A branch git proves is AHEAD is not here, because that reading proves
# something: the commit is stranded, and it goes to the pull request through the
# ordinary gate under the report that describes it.
UNPROVED_HEADS = (
    ("the tree could not be read", {"tree_readable": False}),
    ("the fetch failed", {"authed_fetch_result": REFUSED_FETCH}),
    ("the divergence was unreadable", {"branch_divergence_readable": False}),
    ("the local head would not read", {HEAD_SHAS: ("",)}),
    ("the remote has moved on", {AHEAD_BEHIND: (0, 1)}),
)


class _Runs:
    """The agent runs one tick makes, in order, each resolved as it is reached.

    A member a case BUILT -- a run during which a human edits the issue before
    the agent replies -- is CALLED where the tick reaches it, which is what a
    bare side-effect list cannot do: the runner hands such a member back as the
    object it is, so the change it stages never happens and the result never
    arrives. A reply spelled as text is the developer's own session answering.
    """

    def __init__(self, *staged) -> None:
        self._staged = list(staged)

    def __call__(self, *called, **options):
        staged = self._staged.pop(0)
        if isinstance(staged, str):
            return _agent(session_id=DEV_SESSION, last_message=staged)
        return staged(*called, **options) if callable(staged) else staged
