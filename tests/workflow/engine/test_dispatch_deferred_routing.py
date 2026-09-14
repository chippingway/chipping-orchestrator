# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a held close observation outranks when the next tick sorts its issues.

An observation is not a reading the current tick took. It came from a poll
that found the issue closed and could hand that to nobody, so everything this
tick can see about the issue has been overtaken: a human may have reopened it,
parked it with `backlog` / `paused`, or moved its label off the two the closed
sweep queries. Each of those would otherwise take the reading away for good --
the park drops the issue before the partition even sees it, and the relabel
means the enumeration never yields it at all.

So the observation decides the route by NUMBER, ahead of every filter above
the builder. What the sweep does with the issue it reaches is the same either
way: mark the cancellation an observed close already earned, and defer every
external step to a pass that can trust its own reading.
"""
from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from orchestrator.agents import runner as _agent_runner
from orchestrator.github.labels import BACKLOG_LABEL, PAUSED_LABEL
from orchestrator.workflow.engine import dispatch
from tests.support.fakes import FakeGitHubClient, FakeLabel, make_issue
from tests.workflow.fixtures import (
    LABEL_BLOCKED,
    LABEL_IMPLEMENTING,
    LABEL_UMBRELLA,
)
from tests.workflow.observation_support import ObservedCloseCase

_SPEC = SimpleNamespace(slug="acme/widget")

_RUN_AGENT = "run_agent"

_OWNER_NUMBER = 41


class HeldObservationOutranksTheFiltersTest(ObservedCloseCase, unittest.TestCase):
    """A held observation is not a reading this tick took, and outranks both.

    It came from a poll that found the issue closed and could hand that to
    nobody, so everything the CURRENT tick can see about the issue has been
    overtaken: a human may have reopened it, parked it, or moved its label off
    the two the closed sweep queries. Each of those would otherwise take the
    reading away -- the park drops the issue before the partition, and the
    relabel means the enumeration never yields it at all.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.github = FakeGitHubClient()
        self.owed = frozenset((_OWNER_NUMBER,))

    def test_a_parked_owner_is_still_swept(self) -> None:
        # `paused` defers every external step the ending owes, which is what
        # the sweep does with a parked issue anyway -- and never the mark.
        for parked in (BACKLOG_LABEL, PAUSED_LABEL):
            with self.subTest(parked=parked):
                self.setUp()
                issue = make_issue(_OWNER_NUMBER, label=LABEL_UMBRELLA)
                issue.labels.append(FakeLabel(parked))
                self.github.add_issue(issue)

                partition = self._partitioned()

                self.assertIn(_OWNER_NUMBER, partition.cleanup_numbers)
                self.assertIn(_OWNER_NUMBER, partition.fanout_numbers)
                self.assertNotIn(_OWNER_NUMBER, partition.family_numbers)

    def test_an_owner_the_poll_never_yields_is_added(self) -> None:
        # Closed on a label the sweep does not query, so the enumeration
        # skips it entirely. The observation is older than the relabel and is
        # not lost with it.
        self.github.add_issue(make_issue(
            _OWNER_NUMBER, label=LABEL_BLOCKED, closed=True,
        ))

        partition = self._partitioned()

        self.assertIn(_OWNER_NUMBER, partition.cleanup_numbers)
        self.assertIn(_OWNER_NUMBER, partition.fanout_closed)

    def test_an_owner_gone_from_the_repo_is_added(self) -> None:
        # Nothing yields it and nothing reads it: the number alone is what a
        # worker needs, and its own refetch is what decides the rest.
        partition = self._partitioned()

        self.assertEqual(partition.cleanup_numbers, {_OWNER_NUMBER})

    def test_nothing_owed_leaves_the_partition_alone(self) -> None:
        # The baseline: a parked issue nobody observed closed is dropped
        # exactly where it always was.
        issue = make_issue(_OWNER_NUMBER, label=LABEL_UMBRELLA)
        issue.labels.append(FakeLabel(PAUSED_LABEL))
        self.github.add_issue(issue)

        partition = dispatch._partition_pollable_issues(self.github, _SPEC)

        self.assertEqual(partition.cleanup_numbers, set())
        self.assertEqual(partition.fanout_numbers, [])
        self.assertEqual(partition.family_numbers, [])

    def _partitioned(self) -> dispatch._PollablePartition:
        """Partition this repo with the one held observation in hand."""
        return dispatch._partition_pollable_issues(
            self.github, _SPEC, self.owed,
        )


class ParkedClosedOwnerTest(ObservedCloseCase, unittest.TestCase):
    """A close survives the filter that parks an issue, with nothing held.

    `backlog` and `paused` run ahead of the partition, and dropping a CLOSED
    issue there loses the close itself: an observed close ends a late cycle
    irreversibly, and the pass being dropped is the only one that would ever
    record it. So the reading survives on its own, and what the control label
    defers is everything past the mark.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.github = FakeGitHubClient()

    def test_a_parked_closed_owner_is_kept(self) -> None:
        # Nothing observed this one yet, and the park would drop it before
        # the builder ever saw it -- taking with it the close that is the
        # only thing anything will ever record. So a CLOSED issue survives
        # the filter on its own reading, and what the label defers is
        # everything past the mark.
        issue = make_issue(
            _OWNER_NUMBER, label=LABEL_IMPLEMENTING, closed=True,
        )
        issue.labels.append(FakeLabel(PAUSED_LABEL))
        self.github.add_issue(issue)

        partition = self._partitioned()

        self.assertIn(_OWNER_NUMBER, partition.fanout_numbers)
        self.assertIn(_OWNER_NUMBER, partition.fanout_closed)

    def test_a_parked_open_issue_is_still_dropped(self) -> None:
        # The exception is exactly one reading wide.
        issue = make_issue(_OWNER_NUMBER, label=LABEL_IMPLEMENTING)
        issue.labels.append(FakeLabel(PAUSED_LABEL))
        self.github.add_issue(issue)

        partition = self._partitioned()

        self.assertEqual(partition.fanout_numbers, [])
        self.assertEqual(partition.family_numbers, [])

    def _partitioned(self) -> dispatch._PollablePartition:
        """Partition this repo with no held observation at all."""
        return dispatch._partition_pollable_issues(self.github, _SPEC)


class ParkedWithNoCycleTest(ObservedCloseCase, unittest.TestCase):
    """What the waived park buys is the MARK, and a record can owe none.

    The closed reading is let past `backlog` / `paused` so an observed close
    is recorded before the pass that would record it is dropped. An issue
    whose record carries no late cycle records nothing, so everything past
    that point is the reaction an operator applied the label to prevent --
    the stage handler included.
    """

    def setUp(self) -> None:
        self._fresh_process()
        self.github = FakeGitHubClient()

    def test_no_handler_runs_under_either_label(self) -> None:
        for control in (PAUSED_LABEL, BACKLOG_LABEL):
            with self.subTest(control=control):
                dispatched = self._dispatched(control)

                dispatched.assert_not_called()

    def test_no_agent_is_spawned_under_either_label(self) -> None:
        # The handler is what would spawn one, so this is the same claim
        # taken at the seam an operator's park is actually about.
        for control in (PAUSED_LABEL, BACKLOG_LABEL):
            with self.subTest(control=control):
                with patch.object(_agent_runner, _RUN_AGENT) as spawned:
                    self._dispatched(control)
                    spawns = spawned.call_count

                self.assertEqual(spawns, 0)

    def test_a_reopen_before_the_worker_still_parks(self) -> None:
        # The window the reading exists for, on a record that owes nothing:
        # the worker refetches and finds the issue open again, and the park
        # is exactly as good a reason to stop as it was when it was closed.
        dispatched = self._dispatched(PAUSED_LABEL, reopened=True)

        dispatched.assert_not_called()

    def _dispatched(self, control: str, *, reopened: bool = False):
        """Route a parked issue carrying a closed reading and no cycle."""
        github = FakeGitHubClient()
        issue = make_issue(
            _OWNER_NUMBER, label=LABEL_IMPLEMENTING, closed=not reopened,
        )
        issue.labels.append(FakeLabel(control))
        github.add_issue(issue)
        github.seed_state(_OWNER_NUMBER, pr_number=7)
        module_name, handler_name = dispatch._STAGE_HANDLER_TARGETS[
            LABEL_IMPLEMENTING
        ]
        dispatched = Mock()
        with patch.object(
            importlib.import_module(module_name), handler_name, dispatched,
        ):
            dispatch._process_issue(
                github, _SPEC, issue,
                reading=dispatch._PollReading(closed=True),
            )
        return dispatched


if __name__ == "__main__":
    unittest.main()
