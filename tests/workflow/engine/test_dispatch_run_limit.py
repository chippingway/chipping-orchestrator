# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one park the dispatcher answers instead of the stage its label names.

An issue that has spent every agent run it is allowed is stopped for good, and
`awaiting_human` means something different on every road below: a resume on
the next trusted reply, a hold waiting on guidance, a classifier that refuses
a command carrying none. Each of those is right about the park it was written
against and none of them buys back a run, so the park is held once, ahead of
the table.

The exemption is the other half of it. What work that has ENDED reaches below
is a terminal that ends the issue rather than a road that spends anything on
it, so the hold steps aside and lets the ending finish. Two facts say so and
the free one is asked first: the issue object, and the PULL REQUEST the record
names -- a merge leaves the issue open until a stage terminal reads it, and a
close nobody merged leaves it open for good, so a spent issue behind either
would sit on a park nothing can lift over work a human already decided. The
`discussion` stage's own plan is carved out of that, since merging a design is
an agreement to build it rather than a delivery.

The ending is asked AHEAD of the command below, and the order is what these
pin: reading that command mutates -- an allowance widened, a park cleared, a
batch consumed, a receipt posted, a phase recorded -- and none of that is
anything work a human has already merged or closed should earn.

The command that buys an issue out of the park is asked by the same hold, for
the same reason it is held there: the ledger is spent by every role at every
stage, so no one handler is where a human would say it.
"""
from __future__ import annotations

import importlib
import unittest
from types import MappingProxyType, SimpleNamespace
from unittest.mock import Mock, patch

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import (
    dispatch_guards as _dispatch_guards,
    issue_processing as _issue_processing,
    poll_models as _poll_models,
    stage_targets as _stage_targets,
)
from tests.support.fakes import (
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    make_issue,
)
from tests.workflow.engine import (
    run_grant_test_support as grant,
    run_limit_seeds as _limit_seeds,
    run_limit_test_support as support,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_DISCUSSION,
    LABEL_DOCUMENTING,
    LABEL_IMPLEMENTING,
    LABEL_VALIDATING,
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
)

_SPEC = SimpleNamespace(slug="acme/widget")

_ADD_RUNS = "/orchestrator add-agent-runs 2"

# A request the grammar turns away, which writes as surely as a granted one
# does: a marker-scoped receipt on the thread and a `refused` phase beside it.
_REFUSED_REQUEST = "/orchestrator add-agent-runs 0"

_PR_NUMBER = 15410

_CLOSED = "closed"

# The FakePR flag a merge sets, named because both tables below key a case on
# it and a repeated literal is one a rename would leave behind at some of them.
_MERGED = "merged"

# The three stages that carry no PR-state arc of their own, so the terminal
# that ends a merged or closed pull request runs at handler entry -- which is
# exactly what a spent issue never reaches.
_SWEPT_LABELS = (LABEL_IMPLEMENTING, LABEL_VALIDATING, LABEL_DOCUMENTING)

# The commit a `discussion` publication left on its plan pull request, and the
# record that says the recorded number is that plan rather than a delivery.
_PLAN_SHA = "the-commit-the-plan-pr-carried"
_KEY_PLAN_SHA = "discussion_plan_sha"

# Which stage a settled plan is not an ending ON. An issue relabelled out of
# `discussion` arrives here still recording the plan's number, and merging
# that plan is the agreement that licensed the build -- so `implementing`
# carries on rather than finalizing. `discussion` itself drains the same pull
# request through its own terminal, and behind a permanent park there is no
# later tick to do it instead.
_PLAN_CARVE_OUT_LABEL = LABEL_IMPLEMENTING

# Both ways the humans can settle a plan, which are one answer to every stage
# but the one the carve-out is for.
_SETTLED_PLANS = MappingProxyType({
    _MERGED: MappingProxyType({_MERGED: True}),
    "closed unmerged": MappingProxyType({}),
})


# Every way the work behind a spent issue can be over, paired with where the
# terminal behind the lifted hold puts it. A merge and a close are different
# endings to a reader and the same answer to this hold; an open pull request
# is what the park is for, and is not here.
_ENDED_PULL_REQUESTS = MappingProxyType({
    _MERGED: (MappingProxyType({_MERGED: True}), "done"),
    "closed without merging": (MappingProxyType({}), "rejected"),
})

# Every stage the hold has to step aside on, against every ending, as one
# table -- so a stage added to the sweep and not to it is a stage nothing here
# holds to the exemption.
_TERMINAL_WORK = MappingProxyType({
    f"{ending} on {label}": (label, ended, lands_on)
    for label in _SWEPT_LABELS
    for ending, (ended, lands_on) in _ENDED_PULL_REQUESTS.items()
})

# The seams a real handler reaches for behind the hold: a checkout this case
# never makes, and the spawn it must never take.
_WORKTREE_PATH = "_worktree_path"
_TEMP_ROOT = "/tmp/orchestrator-run-limit-ending"
_RUN_AGENT = "run_agent"


class _HoldCase:
    """One issue routed by label, with the stage handler it names patched."""

    def setUp(self) -> None:
        self.gh = FakeGitHubClient()
        self.reached = Mock()

    def _issue(self, *, closed: bool = False, label: str = LABEL_IMPLEMENTING):
        issue = make_issue(support.ISSUE_NUMBER, label=label, closed=closed)
        self.gh.add_issue(issue)
        return issue

    def _route(
        self,
        issue,
        *,
        reading=_poll_models._POLLED_OPEN,
        label: str = LABEL_IMPLEMENTING,
    ) -> None:
        module_name, handler_name = _stage_targets._STAGE_HANDLER_TARGETS[label]
        with patch.object(
            importlib.import_module(module_name), handler_name, self.reached,
        ):
            _issue_processing._route_issue_to_handler(
                self.gh, _SPEC, issue, label, reading=reading,
            )

    def _seed(self, state) -> None:
        self.gh.seed_state(support.ISSUE_NUMBER, **state.data)

    def _assert_dispatched(self, issue) -> None:
        """The hold stepped aside, and the stage its label names was reached."""
        self.reached.assert_called_once_with(self.gh, _SPEC, issue)

    def _spent_on(self, label: str, pull_request):
        """A parked issue on that stage, recording that pull request.

        `None` is the issue whose record names one nothing put on the client,
        which is what a lookup that fails reads as.
        """
        issue = self._issue(label=label)
        if pull_request is not None:
            self.gh.add_pr(pull_request)
        self._seed(_limit_seeds.parked_state(pr_number=_PR_NUMBER))
        return issue

    def _pull_request(self, **fields):
        """The pull request a record names, in the state a case wants it in."""
        return FakePR(**{
            "number": _PR_NUMBER,
            "head_branch": _issue_branch(support.ISSUE_NUMBER),
            "state": _CLOSED,
            **fields,
        })


class RunLimitHoldTest(_HoldCase, unittest.TestCase):
    """What a spent lifetime ledger stops, and what it lets through."""

    def test_a_parked_issue_reaches_no_handler(self) -> None:
        issue = self._issue()
        self._seed(_limit_seeds.parked_state())

        self._route(issue)

        self.reached.assert_not_called()
        # A park nobody can see going on refusing reads as a workflow that
        # stopped for no reason.
        self.assertEqual(support.phases(self.gh), [support.STANDING])

    def test_a_closed_issue_completes_its_ending(self) -> None:
        # The terminal below ends the issue rather than spending a run on it,
        # and a refusal here would leave it permanently mid-ending.
        issue = self._issue(closed=True)
        self._seed(_limit_seeds.parked_state())

        self._route(issue)

        self.reached.assert_called_once_with(self.gh, _SPEC, issue)
        self.assertEqual(support.phases(self.gh), [])

    def test_the_polls_own_closed_reading_counts(self) -> None:
        # The issue this tick was routed on was closed when it was
        # enumerated, whatever the object in hand now reads as.
        issue = self._issue()
        self._seed(_limit_seeds.parked_state())

        self._route(issue, reading=_poll_models._PollReading(closed=True))

        self._assert_dispatched(issue)

    def test_another_park_is_not_this_one(self) -> None:
        # `awaiting_human` alone is every stage's park, and each of those has
        # a road of its own below that answers it.
        issue = self._issue()
        self._seed(_limit_seeds.state_with(**{
            _limit_seeds.AWAITING_HUMAN: True, _limit_seeds.PARK_REASON: "retry_cap",
        }))

        self._route(issue)

        self.reached.assert_called_once_with(self.gh, _SPEC, issue)


class TerminalWorkTest(_HoldCase, _PatchedWorkflowMixin, unittest.TestCase):
    """A spent ledger may not outlast the work it was spent on.

    The park is permanent -- a lifetime total buys no clock and no road below
    returns one -- so an ending this hold refuses is an ending nothing else
    reaches. A closed ISSUE is the half the object in hand can show. The PULL
    REQUEST the record names is the other, and the stages that carry no
    PR-state arc of their own drain it at handler entry, which is behind here.

    Asked both ways round, because they say different things. With the handler
    mocked, what a case reads is whether the hold stepped aside. With the real
    one behind it, what it reads is whether the issue actually ENDS -- which
    is the whole of what stepping aside was for.
    """

    def test_terminal_work_reaches_the_handler(self) -> None:
        # Both endings on all three stages, because what the hold is deciding
        # is whether the work is over rather than which ending finished it or
        # which stage was holding it when it did.
        for described, (label, ended, _lands_on) in _TERMINAL_WORK.items():
            with self.subTest(work=described):
                self.setUp()
                issue = self._spent_on(label, self._pull_request(**ended))

                self._route(issue, label=label)

                self._assert_dispatched(issue)

    def test_a_live_pull_request_holds_it(self) -> None:
        # The other side, so the exemption is about the ending rather than
        # about the hold having stopped holding: an issue whose work can still
        # be joined is exactly the one a spent ledger is for.
        issue = self._spent_on(
            LABEL_IMPLEMENTING, self._pull_request(state="open"),
        )

        self._route(issue)

        self.reached.assert_not_called()

    def test_one_nothing_can_read_holds_it(self) -> None:
        # Read fail-OPEN: a request that did not come back says nothing about
        # whether the work is over, and lifting a permanent park on one is how
        # a blink would put a spent issue back in front of its stage.
        issue = self._spent_on(LABEL_IMPLEMENTING, None)

        self._route(issue)

        self.reached.assert_not_called()

    def test_the_stage_terminal_finalizes_it(self) -> None:
        for described, (label, ended, lands_on) in _TERMINAL_WORK.items():
            with self.subTest(work=described):
                self.setUp()
                self._spent_on(label, self._pull_request(**ended))

                mocks = self._polled()

                mocks[_RUN_AGENT].assert_not_called()
                self.assertIn(
                    (support.ISSUE_NUMBER, lands_on), self.gh.label_history,
                )

    def test_a_second_poll_finds_nothing_left(self) -> None:
        # The shape the park left behind: a poll that ends the issue is
        # followed by ones that find it ended, rather than by the same refusal
        # said again over work a human already decided.
        self._spent_on(LABEL_VALIDATING, self._pull_request())

        self._polled()
        posted = list(self.gh.posted_comments)
        self._polled()

        self.assertEqual(self.gh.posted_comments, posted)
        self.assertEqual(len(self.gh.label_history), 1)

    def _polled(self):
        """One poll of this issue with the real stage handler behind it."""
        issue = self.gh.get_issue(support.ISSUE_NUMBER)
        with patch.object(
            _worktree_paths, _WORKTREE_PATH, return_value=_TEMP_ROOT,
        ):
            return self._run(
                lambda: _issue_processing._route_issue_to_handler(
                    self.gh, _TEST_SPEC, issue,
                    self.gh.workflow_label(issue),
                ),
                run_agent=_agent(),
            )


class TerminalBeforeTheGrantTest(_HoldCase, unittest.TestCase):
    """What a command on a thread about finished work may not buy.

    Reading `/orchestrator add-agent-runs` is not a question: it widens the
    allowance, clears this park, consumes the batch it read, posts an
    acknowledgement and records a phase. An issue whose work a human has
    already merged or closed earns none of that -- the runs would never be
    spent, and the receipt would land on a thread about to be finalized -- so
    the ending is classified first and the command is left where it is.
    """

    def test_a_valid_grant_is_left_unconsumed(self) -> None:
        issue = self._asking(grant.VALID)

        self._route(issue)

        self._assert_dispatched(issue)
        self._assert_nothing_bought()

    def test_an_invalid_request_earns_no_receipt(self) -> None:
        # The refused road writes too -- one marker-scoped receipt and a
        # `refused` phase -- and a thread about to carry a terminal receipt is
        # not where that belongs either.
        issue = self._asking(_REFUSED_REQUEST)

        self._route(issue)

        self._assert_dispatched(issue)
        self._assert_nothing_bought()

    def test_a_settled_plan_holds_implementing(self) -> None:
        # The carve-out, made here rather than left to the stage behind: a
        # settled plan is an agreement to build, and `implementing` lets such
        # a tick carry on rather than finalizing. Answered as an ending, the
        # hold would step aside every poll for an issue no terminal below it
        # is going to finalize -- and say in the log that it had let one
        # through.
        for described, settled in _SETTLED_PLANS.items():
            with self.subTest(plan=described):
                self.setUp()
                issue = self._recording_a_plan(
                    _PLAN_CARVE_OUT_LABEL, **settled,
                )

                self._route(issue, label=_PLAN_CARVE_OUT_LABEL)

                self.reached.assert_not_called()

    def test_a_settled_plan_ends_discussion(self) -> None:
        # And the other side of the same record, which is the whole reason the
        # LABEL decides it. On `discussion` that pull request is not a licence
        # to build but the work itself, drained by that stage's own terminal
        # -- so a carve-out applied there stops the one stage the plan belongs
        # to from ever ending, and behind a permanent park nothing comes back
        # for it.
        for described, settled in _SETTLED_PLANS.items():
            with self.subTest(plan=described):
                self.setUp()
                issue = self._recording_a_plan(LABEL_DISCUSSION, **settled)

                self._route(issue, label=LABEL_DISCUSSION)

                self._assert_dispatched(issue)

    def _recording_a_plan(self, label: str, **settled):
        """A parked issue on that stage, recording a plan the humans settled."""
        issue = self._issue(label=label)
        self.gh.add_pr(self._pull_request(
            head=FakePRRef(sha=_PLAN_SHA), **settled,
        ))
        self._seed(_limit_seeds.parked_state(**{
            "pr_number": _PR_NUMBER, _KEY_PLAN_SHA: _PLAN_SHA,
        }))
        return issue

    def _asking(self, text: str):
        """A parked issue over ended work, with that request on its thread."""
        issue = self._issue()
        self.gh.add_pr(self._pull_request(merged=True))
        self._seed(grant.spent_state(pr_number=_PR_NUMBER))
        issue.comments.append(grant.command(text))
        return issue

    def _assert_nothing_bought(self) -> None:
        """No allowance widened, no park cleared, and nothing said about it."""
        recorded = self.gh.pinned_data(support.ISSUE_NUMBER)
        self.assertNotIn(support.ALLOWANCE_FIELD, recorded)
        self.assertEqual(recorded[support.USED_FIELD], _limit_seeds.ALLOWANCE)
        self.assertTrue(recorded[_limit_seeds.AWAITING_HUMAN])
        self.assertEqual(self.gh.posted_comments, [])
        self.assertEqual(support.phases(self.gh), [])


class RunLimitNoticeTest(_HoldCase, unittest.TestCase):
    """The sentence the hold says, and the ticks that say nothing more."""

    def test_an_owed_sentence_is_replayed(self) -> None:
        # Nothing below the hold runs, so a notice a refused post left owed
        # would be owed for as long as the issue is parked.
        issue = self._parked_issue()

        self._route(issue)

        self.reached.assert_not_called()
        posted = self.gh.posted_comments[-1][1]
        self.assertIn(support.notice_text(), posted)
        self.assertNotIn(
            support.NOTICE, self.gh.pinned_data(support.ISSUE_NUMBER),
        )
        self.assertEqual(
            support.phases(self.gh), [support.DELIVERED, support.STANDING],
        )

    def test_a_said_sentence_is_not_repeated(self) -> None:
        issue = self._parked_issue()
        polls = 3

        for _ in range(polls):
            self._route(issue)

        said = support.phases(self.gh)
        self.assertEqual(len(self.gh.posted_comments), 1)
        self.assertEqual(len(said), polls + 1)
        self.assertEqual(said[0], support.DELIVERED)
        self.assertEqual(set(said[1:]), {support.STANDING})

    def _parked_issue(self):
        issue = self._issue()
        self._seed(_limit_seeds.parked_state(owing=True))
        return issue


class BoughtRunTest(_HoldCase, unittest.TestCase):
    """The one command the hold answers, and where its answer lands.

    A trusted `/orchestrator add-agent-runs N` is the only reading of a thread
    that lifts this park, and lifting it is worth nothing a poll later: the
    run a human just paid for is the one the issue was stopped for, so the
    tick goes on to the stage its label names.
    """

    def test_a_bought_run_reaches_the_handler(self) -> None:
        issue = self._issue()
        self._seed(grant.spent_state())
        issue.comments.append(grant.command(_ADD_RUNS))

        self._route(issue)

        self.reached.assert_called_once_with(self.gh, _SPEC, issue)
        recorded = self.gh.pinned_data(support.ISSUE_NUMBER)
        self.assertEqual(
            recorded[support.ALLOWANCE_FIELD], _limit_seeds.ALLOWANCE + 2,
        )
        self.assertEqual(support.phases(self.gh), [support.GRANTED])

    def test_a_refused_request_still_holds_the_tick(self) -> None:
        issue = self._issue()
        self._seed(grant.spent_state())
        issue.comments.append(grant.command("/orchestrator add-agent-runs 0"))

        self._route(issue)

        self.reached.assert_not_called()
        self.assertNotIn(
            support.ALLOWANCE_FIELD, self.gh.pinned_data(support.ISSUE_NUMBER),
        )
        self.assertEqual(
            support.phases(self.gh), [support.REFUSED, support.STANDING],
        )

    def test_the_command_answers_no_other_park(self) -> None:
        # It is read only where the park it lifts stands: on any other one it
        # would be answering a question it was not asked.
        issue = self._issue()
        self._seed(_limit_seeds.state_with(**{
            _limit_seeds.AWAITING_HUMAN: True, _limit_seeds.PARK_REASON: "retry_cap",
        }))
        issue.comments.append(grant.command(_ADD_RUNS))

        self._route(issue)

        self.reached.assert_called_once_with(self.gh, _SPEC, issue)
        self.assertEqual(self.gh.posted_comments, [])
        self.assertNotIn(
            support.ALLOWANCE_FIELD, self.gh.pinned_data(support.ISSUE_NUMBER),
        )


class HoldPlacementTest(unittest.TestCase):
    """Where in the guard chain the hold sits, and what that costs.

    Behind the pair that RUN, because a cancelled cycle still holding a branch
    and a restart an operator authorized are endings rather than work: parked
    behind this hold they would be owed for as long as the issue is stopped,
    which on a lifetime total is for good.
    """

    def test_a_restart_outranks_the_hold(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(support.ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        gh.add_issue(issue)
        gh.seed_state(support.ISSUE_NUMBER, **_limit_seeds.parked_state().data)
        restart = Mock(return_value=True)

        with patch.object(
            importlib.import_module(_stage_targets._LATE_RESTART_OWNER),
            "_restarts", restart,
        ):
            held = _dispatch_guards._pinned_state_refuses(
                gh, _SPEC, issue, LABEL_IMPLEMENTING,
            )

        self.assertTrue(held)
        restart.assert_called_once()
        self.assertEqual(support.phases(gh), [])


if __name__ == "__main__":
    unittest.main()
