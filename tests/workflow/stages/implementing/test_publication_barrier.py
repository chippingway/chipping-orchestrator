# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The last thing between an initial publication and work that has ended.

The stage terminal answers a pull request that was already over when the tick
opened. What it cannot answer is one that ends WHILE the tick runs: between
that reading and the push lie a developer run, a disposition, a size gate and
two checkout probes, and every one of them is time a poll on another worker
can find the world changing in.

Nothing downstream catches it either. The reuse behind this push is a lookup
by BRANCH, so a pull request that ended in the window answers nothing to it: a
second one is opened over the work and `pr_number` is overwritten with it,
which is how the pointer to what a human just decided is lost.

One ending is deliberately not one here. A `discussion` plan the humans have
settled is an agreement rather than a delivery, and what it licenses is an
implementation with a pull request of its own -- so it is never something this
push joins and never something it may be held back by.
"""

from __future__ import annotations

import unittest
from functools import partial
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.stages.implementing import (
    checkout_guards as _checkout,
    models as _models,
    push_barrier as _barrier,
)
from tests.support.fakes import FakeGitHubClient, FakePR, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_IMPLEMENTING,
    LABEL_VALIDATING,
    MEASURED_BASE_SHA,
    _agent,
    _issue_branch,
    _open_pr_for,
    _PatchedWorkflowMixin,
)
from tests.workflow.interleaving import _RacesPastTheStep, _RacesTheStep
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.patch_models import _reported

_REPO_SLUG = _TEST_SPEC.slug

_ISSUE = 830
_PR_NUMBER = 8300
_PROVED_PR_NUMBER = 8301
_BRANCH = _issue_branch(_ISSUE)

_OPEN = "open"
_CLOSED = "closed"
_DEV_SESSION = "sess-barrier"
_IMPLEMENTED = _reported()

# The transport this barrier must never let be reached, and the spawn a poll
# behind a refusal may not need.
_PUSH_BRANCH = "_push_branch"
_RUN_AGENT = "run_agent"

# Where the stage's own terminal puts an issue whose pull request is over.
_REJECTED = "rejected"

# The step the initial publication takes last before its barrier, so an
# ending hung on it lands in exactly the window the barrier exists for.
_DIRTIED_BEFORE_THE_PUSH = "_dirtied_before_the_push"

# The barrier's own pull-request reading, which is a request and so a window
# of its own: a close landing while it is in flight is one only the latch read
# AFTER it can still answer.
_PUBLICATION_IS_OVER = "_publication_is_over"

# The commit a plan publication put on the plan pull request, and the branch
# it published to.
_PLAN_SHA = MEASURED_BASE_SHA
_PLAN_BRANCH = "orchestrator/plan"

# The two records that tell a recorded number which is the `discussion`
# stage's design from one that is a delivery of this stage's.
_KEY_PLAN_PATH = "discussion_plan_path"
_KEY_PLAN_SHA = "discussion_plan_sha"
_PLAN_PATH = "plans/what-to-build.md"

# A checkout this barrier never reaches for: everything it decides on is the
# record, the latch and the remote.
_ABSENT_WORKTREE = "/nonexistent"

# The pinned key the barrier reads a publication by, and every shape a comment
# can CARRY there that this build cannot read back as one. The payload is
# JSON, so a hand edit or an older write can leave any of them -- and each
# reads absent through the fail-closed reader every identity here goes
# through, which is exactly what a barrier may not mistake for an issue that
# never published.
_KEY_PR_NUMBER = "pr_number"
_DAMAGED_IDENTITIES = (0, -1, True, 2.5, [])


def _ends(github, *, merged: bool = False, unreadable: bool = False) -> None:
    """End the pull request this push would join, leaving the ISSUE open.

    Three shapes with two flags between them. A merge and a plain close are
    different endings to a reader, and one this host cannot read at all is the
    third state a push may not land on -- the one that says which way the
    reading behind the barrier fails.
    """
    github.existing_open_pr.pop(_BRANCH, None)
    if unreadable:
        github.pulls.pop(_PR_NUMBER, None)
        return
    pull_request = github.get_pr(_PR_NUMBER)
    pull_request.merged = merged
    pull_request.state = _CLOSED


_ENDINGS = MappingProxyType({
    "merged": partial(_ends, merged=True),
    "closed": _ends,
    "unreadable": partial(_ends, unreadable=True),
})


def _approved_work(**fields) -> _models._ApprovedWork:
    """The candidate a publication is about, as its caller hands it over.

    The run behind it is a finished one carrying nothing this barrier reads:
    what it decides on is the record, the latch and the remote.
    """
    return _models._ApprovedWork(
        agent_result=_agent(
            session_id=_DEV_SESSION, last_message=_IMPLEMENTED,
        ),
        worktree=Path(_ABSENT_WORKTREE),
        **fields,
    )


class _BarrierCase(ObservedCloseCase, _PatchedWorkflowMixin):
    """One implementing issue whose record names an open pull request.

    The shape a round that crashed before its relabel leaves: the branch is on
    the remote, a pull request is open on it, and the stage label still says
    the work never finished. That is the only shape this barrier has anything
    to say about -- the first publication of all records no pull request, and
    so has none to have ended.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self._seed()

    def _seed(self, **recorded) -> None:
        """Re-seed this case's issue, its record, and the pull request it names."""
        self.github = FakeGitHubClient()
        self.issue = make_issue(_ISSUE, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self._restored()
        self.github.seed_state(_ISSUE, **{
            "branch": _BRANCH, _KEY_PR_NUMBER: _PR_NUMBER, **recorded,
        })

    def _publishes(self):
        """One implementing tick that commits and publishes what it wrote."""
        return self._run_implementing(
            self.github,
            self.issue,
            run_agent=_agent(
                session_id=_DEV_SESSION, last_message=_IMPLEMENTED,
            ),
            has_new_commits=[False, True],
            dirty_files=(),
            push_branch=True,
        )

    def _published_while(self, arrives):
        """Publish with the world ending the instant the last probe returns.

        Hung there because it is the step immediately before the barrier: the
        tick has read the pull request by then and the push has not run, which
        is exactly the window a poll on another worker can end it in.
        """
        with patch.object(
            _checkout,
            _DIRTIED_BEFORE_THE_PUSH,
            _RacesPastTheStep(
                _checkout._dirtied_before_the_push,
                lambda: arrives(self.github),
            ),
        ):
            return self._publishes()

    def _assert_refused(self, mocks) -> None:
        """Nothing pushed, no pull request opened, and no handoff behind it."""
        mocks[_PUSH_BRANCH].assert_not_called()
        self.assertEqual(self.github.opened_prs, [])
        self.assertNotIn(
            (_ISSUE, LABEL_VALIDATING), self.github.label_history,
        )

    def _restored(self) -> None:
        """Put the recorded pull request on the client, open and on the branch.

        Seeding and RE-seeding are one call, because the second is what says
        the barrier refuses an ending rather than refusing a remote: what a
        refusal costs has to be the poll that asks again, so the poll after
        the remote answers has to find exactly the publication the first one
        could not read and publish onto it.
        """
        pull_request = _open_pr_for(
            self.github, issue_number=_ISSUE, pr_number=_PR_NUMBER,
        )
        self.github.existing_open_pr[_BRANCH] = pull_request

    def _asked(self, **approved) -> bool:
        """The barrier itself, asked the way the publication owner asks it."""
        return _barrier._ended_before_the_push(
            self.github, _TEST_SPEC, self.issue,
            self.github.read_pinned_state(self.issue),
            _approved_work(**approved),
        )


class InitialPublicationBarrierTest(_BarrierCase, unittest.TestCase):
    """Nothing is published onto work that ended while the tick was working."""

    def test_an_ending_pull_request_refuses_the_push(self) -> None:
        # Every state a push may not land on, raced into the window -- the
        # unreadable one included, since this reading fails CLOSED: what
        # refusing costs is the poll that asks again, and what falling through
        # costs is a second pull request over work a human just decided about.
        for ending, over in _ENDINGS.items():
            with self.subTest(pull_request=ending):
                self.setUp()

                self._assert_refused(self._published_while(over))

    def test_a_latched_close_refuses_it(self) -> None:
        # The issue object this tick holds still reads open, so the latch is
        # the only reading that can answer for the window at all.
        self._assert_refused(self._published_while(
            lambda _github: self._latch_close(_REPO_SLUG, _ISSUE),
        ))

    def test_nothing_ending_publishes_as_ever(self) -> None:
        # The other side, so the barrier is about the ending rather than about
        # this seam having stopped publishing: the push lands, the pull
        # request the record names is reused, and the issue is handed on.
        mocks = self._publishes()

        mocks[_PUSH_BRANCH].assert_called_once()
        self.assertIn((_ISSUE, LABEL_VALIDATING), self.github.label_history)

    def test_a_damaged_record_refuses_the_push(self) -> None:
        # A `pr_number` the comment CARRIES and this build cannot read back is
        # not an issue that never published. Read as one, the barrier skips
        # its reading altogether and the push goes out onto a branch whose
        # pull request a human may have just closed -- opening a SECOND one
        # over the work and overwriting the pointer to what they decided,
        # which is the whole of what this barrier exists to withhold.
        for damaged in _DAMAGED_IDENTITIES:
            with self.subTest(pr_number=damaged):
                self._seed(**{_KEY_PR_NUMBER: damaged})
                _ends(self.github)

                self._assert_refused(self._publishes())

    def test_an_absent_record_publishes_as_ever(self) -> None:
        # The other side, and the reason the two are told apart rather than
        # typed together: an issue that records no pull request has published
        # nothing, and this seam's own push is what OPENS one. Refused here,
        # no issue would ever reach a first publication at all.
        self._seed(**{_KEY_PR_NUMBER: None})
        self.github.existing_open_pr.pop(_BRANCH, None)
        self.github.pulls.pop(_PR_NUMBER, None)

        mocks = self._publishes()

        mocks[_PUSH_BRANCH].assert_called_once()
        self.assertEqual(len(self.github.opened_prs), 1)


class RepeatedPollTest(_BarrierCase, unittest.TestCase):
    """What the polls behind a refusal find, and what they may do with it.

    Refusing writes nothing, so the commit stays in the worktree and every
    poll re-enters the publication over the same durable state. What must
    never come of that is a second pull request, a second announcement, or a
    handoff over work nobody can merge. What must eventually come of it is one
    of two things: the terminal that drains an ending, or the push that lands
    once the remote answers again.
    """

    def test_an_ended_one_drains_next_poll(self) -> None:
        # Poll one refuses at the barrier, because the ending landed inside
        # the window only the barrier covers. Poll two never reaches it: the
        # pull request is over by the time the tick opens, so the stage's own
        # terminal is what answers -- rejected, with no developer rerun and
        # nothing pushed onto work a human turned down.
        self._published_while(_ENDINGS["closed"])

        mocks = self._publishes()

        mocks[_PUSH_BRANCH].assert_not_called()
        mocks[_RUN_AGENT].assert_not_called()
        self.assertIn((_ISSUE, _REJECTED), self.github.label_history)

    def test_it_refuses_until_the_remote_answers(self) -> None:
        # The fail-CLOSED half over three polls, which is the one that says
        # the reading costs a poll rather than the work. Two refuse while the
        # remote will not answer, and neither opens a pull request nor hands
        # the issue on, so nothing is duplicated for the third to trip over.
        # The third publishes onto the very pull request the record names.
        self._published_while(_ENDINGS["unreadable"])

        self._assert_refused(self._publishes())

        self._restored()
        mocks = self._publishes()

        mocks[_PUSH_BRANCH].assert_called_once()
        self.assertEqual(self.github.opened_prs, [])
        self.assertIn((_ISSUE, LABEL_VALIDATING), self.github.label_history)


class BarrierOrderTest(_BarrierCase, unittest.TestCase):
    """Which of the barrier's two readings gets the final word, and why.

    Asked of the barrier itself rather than through a tick, because what it
    pins is an ORDER: both readings answer the same question on a whole run,
    so a case that only watched the push could not say which of them did.
    """

    def test_a_close_landing_in_the_read_is_answered(self) -> None:
        # The pull-request reading is a REQUEST, so it is a window of its own:
        # a poll finding the issue closed while it is in flight is one a latch
        # read BEFORE it has already answered "no" to. The reading that costs
        # nothing is the one that gets the last word for exactly that reason.
        with patch.object(
            _barrier,
            _PUBLICATION_IS_OVER,
            _RacesTheStep(
                _barrier._publication_is_over,
                lambda: self._latch_close(_REPO_SLUG, _ISSUE),
            ),
        ):
            self.assertTrue(self._asked())

    def test_a_live_publication_is_not(self) -> None:
        # The other side of the same call, so the order above is about the
        # window rather than about the barrier refusing everything it is asked.
        self.assertFalse(self._asked())


class SettledPlanCarveOutTest(_BarrierCase, unittest.TestCase):
    """What the one ending that is not an ending here needs, and who gets it.

    A `discussion` plan the humans have SETTLED is an agreement rather than a
    delivery, so it is never a publication this push is held back for. Two
    things bound that: it has to be SETTLED, which only a reading establishes,
    and it has to be a number the RECORD named -- a caller that proved one
    proved the branch is standing on the candidate, which no plan publication
    produces.
    """

    def test_a_settled_plan_is_not_an_ending(self) -> None:
        # A merged plan is an agreement, and the stage ahead of here lets such
        # a tick carry on for exactly that reason. Held back for it, the
        # developer's work would never reach a reviewer at all. Past the
        # handoff that retires `discussion_plan_path`, the commit the plan
        # publication left on that pull request is the whole of what says so.
        self._recording_a_plan(_KEY_PLAN_SHA, _PLAN_SHA)

        mocks = self._publishes()

        mocks[_PUSH_BRANCH].assert_called_once()
        self.assertIn((_ISSUE, LABEL_VALIDATING), self.github.label_history)

    def test_an_unreadable_plan_is_refused(self) -> None:
        # And what the carve-out needs before it may fire: a READING. The
        # record says which pull request is the design and never what anybody
        # did with it, so a live `discussion_plan_path` over a request that
        # failed is not a settled plan -- it is a plan this host cannot see.
        # Carved out on the record alone, the push goes out onto whatever
        # that failed request was hiding, a replacement pull request is opened
        # over it, and the issue is handed to review behind both.
        self._recording_a_plan(_KEY_PLAN_PATH, _PLAN_PATH, unreadable=True)

        self._assert_refused(self._publishes())

    def test_the_proved_number_is_the_one_read(self) -> None:
        # Both directions off one fixture, so the case says the proved number
        # is READ rather than merely that some number was: the recorded pull
        # request has ended in each, and only the proved one moves the answer.
        for described, proved_state, ended in (
            ("the proved one has ended", _CLOSED, True),
            ("the proved one is open", _OPEN, False),
        ):
            with self.subTest(reading=described):
                self._seed()
                self._proving(proved_state)

                self.assertEqual(
                    self._asked(delivered_pr=_PROVED_PR_NUMBER), ended,
                )

    def test_a_proved_number_earns_no_plan_carve_out(self) -> None:
        # The plan records are on the comment and the proved pull request has
        # ended, and it is still refused: what those records tell apart is a
        # number the RECORD named, and this one came from a proof.
        self._seed(**{_KEY_PLAN_PATH: _PLAN_PATH})
        self._proving(_CLOSED)

        self.assertTrue(self._asked(delivered_pr=_PROVED_PR_NUMBER))

    def _proving(self, state: str) -> None:
        """Add a proved pull request beside a recorded one that has ended."""
        self.github.get_pr(_PR_NUMBER).state = _CLOSED
        self.github.add_pr(FakePR(
            number=_PROVED_PR_NUMBER, head_branch=_BRANCH, state=state,
        ))

    def _recording_a_plan(
        self, record: str, recorded: str, *, unreadable: bool = False,
    ) -> None:
        """Re-seed with the recorded pull request the `discussion` plan.

        Settled by default, which is the state the carve-out is about;
        `unreadable` takes it off the client instead, which is the state no
        record can tell from a settled one.
        """
        self._seed(**{record: recorded})
        self.github.existing_open_pr.pop(_BRANCH, None)
        self.github.pulls.pop(_PR_NUMBER, None)
        if unreadable:
            return
        plan = FakePR(
            number=_PR_NUMBER,
            head_branch=_PLAN_BRANCH,
            merged=True,
            state=_CLOSED,
        )
        plan.head.sha = _PLAN_SHA
        self.github.add_pr(plan)


if __name__ == "__main__":
    unittest.main()
