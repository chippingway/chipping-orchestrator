# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A close the POLL observed while a worker was publishing.

The latch is what the barriers standing immediately before a push read, and
what puts a reading in it is the enumeration: a poll that finds an issue closed
latches it, writes the durable half down, and drops it again where the record
says there is nothing to end. That last rule was written for the late-split
protocol, where "nothing to end" means no live cycle -- and it is exactly what
every publication a barrier guards looks like. A first push has no generation
yet; an approved or recovered one retires its own before pushing.

So the two threads meet: the poll drops the reading, the worker asks the latch
a moment later and is told nothing was seen, and the push it should have
refused goes out onto an issue a human closed. What holds them apart is the
window the dispatch advertises around itself -- inside it the drop is
postponed, and taken again on the way out.

Two production calls put a reading there and drop it again -- the enumeration
that first reads the issue closed, and the refused fan-out submit that holds
what the poll was carrying when the scheduler turned it away because a worker
already had the issue. Both are driven here rather than a latch planted, so
what these pin is the behaviour a poll actually has.

WHEN the hold starts is the other half, and the refused submit is what makes
it matter: that refusal happens because a worker has the issue, and the worker
has it from the moment the scheduler admits the submit -- not from whenever it
gets around to reading something. The queue, the refetch and the label checks
all sit in between, and a reading dropped in there is one no barrier ever sees.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    dispatch_closure as _dispatch_closure,
    issue_processing as _issue_processing,
    observations,
    poll_models as _poll_models,
    scheduled_dispatch as _scheduled_dispatch,
)
from orchestrator.workflow.stages.implementing import (
    checkout_guards as _checkout,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_IMPLEMENTING,
    LABEL_VALIDATING,
    _agent,
    _issue_branch,
    _open_pr_for,
    _PatchedWorkflowMixin,
)
from tests.workflow.interleaving import _RacesPastTheStep
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.report_values import _named_description, _reported

_ISSUE = 6310
_PR_NUMBER = 63100
_BRANCH = _issue_branch(_ISSUE)

_DEV_SESSION = "sess-polled-close"
_IMPLEMENTED = _reported()

_PUSH_BRANCH = "_push_branch"
_WORKTREE_PATH = "_worktree_path"
_TEMP_ROOT = "/tmp/orchestrator-polled-close"

# The step the publication takes last before its barrier, which is where a
# poll on another thread still has time to see the close.
_DIRTIED_BEFORE_THE_PUSH = "_dirtied_before_the_push"

# Both production calls that latch a reading and drop it again, named by the
# poll's own act. Resolved on the case, so each reads as the one line it is.
_DROPS = ("_polled_closed", "_refused_submit")


class _AdmitsTheSubmit:
    """A scheduler that admits one submit and hands the task back unrun.

    The gap this module is about is between the admission and the worker, so
    the task has to be held rather than run: a double that ran it inline would
    have no gap for a poll to arrive in.
    """

    def __init__(self) -> None:
        self.task = None

    def submit(self, _slug, _issue_number, callable_, **_options) -> bool:
        self.task = callable_
        return True


class _PublishingCase(ObservedCloseCase, _PatchedWorkflowMixin):
    """One implementing issue with committed work and no late generation.

    The ordinary shape, and the one the drop rule reads as "nothing to end":
    every publication these barriers guard carries the same.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.github = FakeGitHubClient()
        self.issue = make_issue(_ISSUE, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        pull_request = _open_pr_for(
            self.github, issue_number=_ISSUE, pr_number=_PR_NUMBER,
            body=_named_description(_ISSUE, _DEV_SESSION),
        )
        self.github.existing_open_pr[_BRANCH] = pull_request
        self.github.seed_state(_ISSUE, branch=_BRANCH, pr_number=_PR_NUMBER)

    def _polled_closed(self) -> None:
        """What the enumeration does with an issue it finds closed.

        The production call, not a planted latch: it observes, writes the
        durable half, and drops the reading again where the record says there
        is nothing to end -- which is what this issue's record says.
        """
        self.issue.closed = True
        _dispatch_closure._recorded_at_poll(self.github, _TEST_SPEC, self.issue)

    def _refused_submit(self) -> None:
        """What the poll does when the scheduler turns its submit away."""
        self.issue.closed = True
        _dispatch_closure._refused_submit(
            self.github, _TEST_SPEC, _ISSUE, cleanup_only=False, closed=True,
        )


class PolledCloseDuringPublicationTest(_PublishingCase, unittest.TestCase):
    """What a poll's own observation buys the worker it could not reach."""

    def test_a_polled_close_refuses_the_push(self) -> None:
        # Both drops, because each is a poll acting on the record and the
        # record says the same thing to both: there is nothing to end. Without
        # the hold either would drop the very reading the barrier is about to
        # ask for, and the branch would go out with a pull request opened over
        # it. The refused submit is the sharper of the two -- that path exists
        # precisely because a worker already holds the issue.
        for drop in _DROPS:
            with self.subTest(poll=drop):
                self.setUp()

                mocks = self._published_while(getattr(self, drop))

                mocks[_PUSH_BRANCH].assert_not_called()
                self.assertEqual(self.github.opened_prs, [])
                self.assertNotIn(
                    (_ISSUE, LABEL_VALIDATING), self.github.label_history,
                )

    def test_the_hold_leaves_no_latch_behind(self) -> None:
        # The drop is postponed rather than refused. Held for good, an issue
        # somebody reopens would inherit a latch no later poll clears and
        # every future push would be refused on a close nobody still means.
        self._published_while(self._polled_closed)

        self.assertFalse(observations.close_observed(_TEST_SPEC.slug, _ISSUE))

    def test_an_open_issue_publishes_as_ever(self) -> None:
        # The other side, so the hold is about the observation rather than
        # about the dispatch having stopped publishing: with no poll seeing
        # anything, the push lands and the issue is handed on.
        mocks = self._published_while(lambda: None)

        mocks[_PUSH_BRANCH].assert_called_once()
        self.assertIn((_ISSUE, LABEL_VALIDATING), self.github.label_history)

    def _published_while(self, polls):
        """Dispatch one tick, with that poll landing just before the push."""
        with patch.object(
            _checkout,
            _DIRTIED_BEFORE_THE_PUSH,
            _RacesPastTheStep(_checkout._dirtied_before_the_push, polls),
        ), patch.object(
            _worktree_paths, _WORKTREE_PATH, return_value=_TEMP_ROOT,
        ):
            return self._run(
                lambda: _issue_processing._process_issue(
                    self.github, _TEST_SPEC, self.issue,
                ),
                run_agent=_agent(
                    session_id=_DEV_SESSION, last_message=_IMPLEMENTED,
                ),
                has_new_commits=[False, True],
                dirty_files=(),
                push_branch=True,
            )


class ClaimedBeforeTheWorkerTest(_PublishingCase, unittest.TestCase):
    """The gap between the claim and anything the worker reads.

    The queue, the worker's own refetch and its label checks all sit between
    the scheduler admitting a submit and the handler taking the issue up, and
    a poll refused in there is refused because a worker has it.
    """

    def test_a_claim_holds_it_before_the_worker_reads(self) -> None:
        # The interleaving the hold is placed for, and the one a latch exists
        # for at all: the scheduler admits the submit, a later poll meets the
        # issue CLOSED and is refused because a worker has it, and a human
        # reopens it before that worker reads anything. From there the close
        # is a reading GitHub can no longer give back -- the refetch says open
        # -- so the latch is the only thing that remembers it. Held only from
        # the handler, the refusal drops it through the queue, the refetch and
        # the label checks, and the barrier is asked about a close nothing
        # kept.
        task = self._admitted()
        self._refused_submit()
        self.issue.closed = False

        mocks = self._runs(task)

        mocks[_PUSH_BRANCH].assert_not_called()
        self.assertEqual(self.github.opened_prs, [])
        self.assertNotIn((_ISSUE, LABEL_VALIDATING), self.github.label_history)

    def _admitted(self):
        """Submit this issue the way the poll does, and hold the task back."""
        scheduler = _AdmitsTheSubmit()
        _scheduled_dispatch._submit_scheduler_fanout_issues(
            self.github,
            _TEST_SPEC,
            scheduler,
            _poll_models._PollablePartition(
                family_numbers=[],
                family_labels=[],
                fanout_numbers=[_ISSUE],
                fanout_closed=set(),
            ),
            1,
        )
        return scheduler.task

    def _runs(self, task):
        """Let the worker take the issue up, once the poll has had its turn."""
        with patch.object(
            _worktree_paths, _WORKTREE_PATH, return_value=_TEMP_ROOT,
        ):
            return self._run(
                task,
                run_agent=_agent(
                    session_id=_DEV_SESSION, last_message=_IMPLEMENTED,
                ),
                has_new_commits=[False, True],
                dirty_files=(),
                push_branch=True,
            )


if __name__ == "__main__":
    unittest.main()
