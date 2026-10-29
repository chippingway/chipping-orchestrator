# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite whose finish captured its head's evidence and stopped short of its route.

The finish case (`rewrite_finish_evidence_test_support`): the tested commit
rebased onto the rebased head and landed, a report about that head settled and
handed a reviewer, and the attempt pinned with the base tip its replay was made
onto. The publication's finish runs the configured suite on that head and
records the run as a pending transaction, and the answer to that write is
lost, so nothing routes: the run is captured for the head beside the standing
attempt, which is what the recovery helpers are asked about
(`CapturedEvidenceCase`).

A case asks one helper directly (`asks`) over the finish a later tick's
recovery would hold (`landed`), under the world's git readings, with the
verify runner and the agent runner recorded so it can read back that the
helper ran no command, launched no developer, and relabelled nothing, beside
the evidence records and the anchor it left (`assert_dormant`).
"""
from __future__ import annotations

from copy import copy
from dataclasses import replace
from unittest.mock import Mock, patch

from orchestrator.agents import runner as _agent_runner
from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding, _PushOutcome
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from tests.support.checkout_identity import stated_identity
from tests.workflow.engine import (
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    verification_evidence_test_support as support,
)
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.git_owners import seam_patch

REBASED = support.REBASED_SHA


class _LandedEvidenceCase(finish_support.RewriteFinishCase):
    """Issue #7's `head` landed, and the finish a later tick's recovery holds for it."""

    head = REBASED

    def setUp(self) -> None:
        finish_support.RewriteFinishCase.setUp(self)
        self.verify = Mock()
        self.developer = Mock()

    def landed(self) -> LandedFinish:
        """The finish a later tick's recovery of the landing holds, over the issue and comment as they read now."""
        return LandedFinish(
            gh=self.gh,
            spec=_TEST_SPEC,
            issue=copy(self.issue),
            state=self.gh.read_pinned_state(self.issue),
            landed=replace(self._landing(self.head), outcome=_PushOutcome.OBSERVED),
            label=self.gh.workflow_label(self.issue),
            road=finish_support.FOUND,
        )

    def asks(self, helper, *args, **kwargs):
        """What `helper` answers under the world's readings, with nothing run or launched beside it.

        The base is read against the tip the helper hands in, and a blank one
        proves nothing, as the git owner answers it.
        """
        with (
            self.seams(),
            seam_patch("_standing_on_the_remote_base", self._stands),
            seam_patch("_run_verify_commands", self.verify),
            patch.object(_agent_runner, "run_agent", self.developer),
        ):
            return helper(*args, **kwargs)

    def calls_to(self, step: str, helper, *args) -> int:
        """How many times `helper`, asked as `asks` asks it, calls the client's `step`."""
        counted = Mock(wraps=getattr(self.gh, step))
        with patch.object(self.gh, step, counted):
            self.asks(helper, *args)
        return counted.call_count

    def records(self) -> tuple:
        """The evidence records the pinned comment carries now (`rewrite_finish_readings.records`)."""
        return readings.pinned_records(self)

    def assert_dormant(self, records: tuple | None = None, anchor: str | None = support.TESTED_SHA) -> None:
        """Nothing ran, launched, or relabelled; the comment carries `records` and the anchor `anchor`.

        `records` are the evidence records (`records`), those the case keeps
        (`kept`) where none are named; `anchor` is the attempt's anchor,
        standing unless a case's reset released the attempt.
        """
        self.assertEqual(
            (
                self.verify.call_count,
                self.developer.call_count,
                readings.relabels(self),
                self.records(),
                readings.pinned(self)[readings.KEY_PENDING_PUSH],
            ),
            (0, 0, (), self.kept() if records is None else records, anchor),
        )

    def _stands(self, *args) -> _BaseStanding:
        return self.world.base if args[-1] else _BaseStanding.UNPROVEN


class CapturedEvidenceCase(_LandedEvidenceCase):
    """Issue #7's rebased head landed, its run captured by a finish that never routed it."""

    def setUp(self) -> None:
        _LandedEvidenceCase.setUp(self)
        # A road off the landing that resets proves the checkout the issue's
        # own first, and the checkout here is no real worktree at a layout path.
        stated_identity(self)
        self.attempts(REBASED)
        self.rewrites(REBASED)
        self.during = moves.loses_answers
        self.assertEqual(self.finishes(REBASED), FinishOutcome.UNCONFIRMED)
        self.gh.pinned_failures.lost.clear()
        self.during = moves.unmoved
        self.captured = readings.pinned_records(self)[0]
        self.assertIsNotNone(self.captured)

    def abandoned(self) -> tuple:
        """The evidence records once the captured run was abandoned: nothing pending, nothing current."""
        abandoned = (self.captured.receipt, readings.ABANDONED)
        return None, None, (*self.invalidated(), abandoned)

    def kept(self) -> tuple:
        """The evidence records while the captured run still stands."""
        return self.captured, None, self.invalidated()


def dropped(case: CapturedEvidenceCase) -> tuple:
    """The evidence records once `case`'s captured run was dropped for want of room: no history entry for it."""
    return None, None, case.invalidated()


class FailsOnce:
    """A client read failing the first time it is asked, and answering as the client does after."""

    def __init__(self, read) -> None:
        self._read = read
        self._failed = False

    def __call__(self, *args):
        """Raise the first time; read as the client reads every time after."""
        if not self._failed:
            self._failed = True
            raise RuntimeError("GitHub did not answer")
        return self._read(*args)
