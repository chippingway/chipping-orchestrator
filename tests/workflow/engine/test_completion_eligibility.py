# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which developer returns earn a captured completion, on which roads, and what the capture holds.

Eligibility is read through the outcome owner's completed-run reader and the
backend's incomplete-execution diagnostics, and a road's own contract: an exit
code, a role, or a report-like message alone qualifies nothing. A READY report
is captured with its complete text and a VERIFIED one as the reference it is.
"""
from __future__ import annotations

import dataclasses
import hashlib
import unittest

from orchestrator.agents.models import TerminalFailure
from orchestrator.observability.usage.agy_events import ToolLifecycle
from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_records as _records,
    completion_routes as _routes,
    report_outcome_models as _outcome_models,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import completion_test_support as support

_ROUTE = _routes.CompletionRoute
_INELIGIBLE = _routes.Ineligible
_REFUSAL = _outcome_models._ReportRefusal
_FROZEN = (("review_returned_verdict", hashlib.sha256(b"the handed request").hexdigest()),)

# Runs that did not complete on their own terms, each refused before its
# message is read -- a READY block in it included -- and the reason it earns.
_SHORTFALLS = (
    ({"invoked": False}, _REFUSAL.NOT_INVOKED),
    ({"interrupted": True}, _REFUSAL.INTERRUPTED),
    ({"timed_out": True}, _REFUSAL.TIMED_OUT),
    ({"exit_code": 1}, _REFUSAL.NONZERO_EXIT),
)

# Completed runs whose message earns no report: a clean exit alone is nothing.
_NO_REPORT = (
    ({"last_message": "Done; everything passed."}, _REFUSAL.NO_MARKER),
    ({"last_message": "REPORT: READY\nNo end marker."}, _REFUSAL.MALFORMED),
    ({"last_message": f"{support.READY}\n\nACK: nothing else"}, _REFUSAL.MALFORMED),
)

# Completed runs whose backend recorded them unfinished, whatever their message.
_INCOMPLETE = (
    {"unfinished_steps": (ToolLifecycle(step_index=3, tool_name="run_command", state="RUNNING"),)},
    {"terminal_failure": TerminalFailure(process_exit_code=0, status="SUCCESS")},
)


def _road(route: _routes.CompletionRoute, origin: WorkflowLabel, **overrides) -> _records.CompletionHandoff:
    """A road's handoff, its requirements the ones the world's run was handed."""
    return dataclasses.replace(support.IMPLEMENTATION, route=route, origin=origin, **overrides)


class CompletionEligibilityTest(unittest.TestCase):
    """What one returned run earns, read through the outcome owner and the backend's diagnostics."""

    def setUp(self) -> None:
        self.world = support.seeded()

    def earns(self, message: str = support.READY, handoff=support.IMPLEMENTATION, **overrides):
        """What one run returned under charge 1 earns on `handoff`'s road."""
        returned = support.returned(self.world.invocation(), message, **overrides)
        return _checkpoint.captured(returned, handoff, support.RUN)

    def test_a_completed_report_is_captured_whole(self) -> None:
        """A READY report is captured with its complete text, the session, what ran, and the settled accounting."""
        captured = self.earns()
        self.assertEqual(
            (
                captured.outcome,
                captured.invocation,
                captured.handoff,
                captured.run,
                captured.session_id,
                captured.accounting,
                captured.stage,
            ),
            (
                _outcome_models._ReadyReport(support.REPORT),
                self.world.invocation(),
                support.IMPLEMENTATION,
                support.RUN,
                support.SESSION,
                _records.CaptureAccounting.SETTLED,
                support.STAGE.PENDING,
            ),
        )

    def test_a_verified_report_stays_a_reference(self) -> None:
        """A VERIFIED outcome is captured as the location and revision read, with no text made up for it."""
        self.assertEqual(
            self.earns(support.VERIFIED).outcome,
            _outcome_models._VerifiedReport(
                _outcome_models._ReportLocation(support.REPO, support.VERIFIED_PR, support.VERIFIED_COMMENT),
                support.VERIFIED_REVISION,
            ),
        )

    def test_a_run_that_fell_short_earns_nothing(self) -> None:
        """A run that did not complete, or completed on no report, earns the outcome owner's own refusal."""
        for overrides, refusal in (*_SHORTFALLS, *_NO_REPORT):
            with self.subTest(overrides=overrides):
                self.assertIs(self.earns(**overrides), refusal)

    def test_an_unfinished_run_earns_nothing(self) -> None:
        """Unfinished tool steps or a terminal failure record make a clean READY return incomplete."""
        for overrides in _INCOMPLETE:
            with self.subTest(overrides=overrides):
                self.assertIs(self.earns(**overrides), _INELIGIBLE.INCOMPLETE)



class CompletionIdentityTest(unittest.TestCase):
    """What a capture says of the process it came from: its identity, its session, and its accounting."""

    def earns(self, **overrides):
        """What one completed READY run under charge 1 earns on the implementation's road."""
        world = support.seeded()
        returned = support.returned(world.invocation(), **overrides)
        return _checkpoint.captured(returned, support.IMPLEMENTATION, support.RUN)

    def test_an_unidentified_return_earns_nothing(self) -> None:
        """A result carrying no invocation identity has nothing its capture could be bound to."""
        self.assertIs(self.earns(invocation=None), _INELIGIBLE.UNIDENTIFIED)

    def test_the_accounting_is_the_spawns(self) -> None:
        """An unresolved checkpoint and an unparsed usage are captured as such; a missing session stays missing."""
        unresolved = self.earns(unaccounted=True)
        unpriced = self.earns(usage=None, session_id=None)
        self.assertEqual(
            (unresolved.accounting, unpriced.accounting, unpriced.session_id),
            (_records.CaptureAccounting.UNRESOLVED, _records.CaptureAccounting.NOTHING_OWED, None),
        )


class RouteContractTest(unittest.TestCase):
    """Which labels each road records under, which outcomes pay it, and which owe a frozen handoff."""

    def setUp(self) -> None:
        self.world = support.seeded()

    def earns(self, handoff: _records.CompletionHandoff, message: str = support.READY):
        """What one completed run under charge 1 earns on `handoff`'s road."""
        returned = support.returned(self.world.invocation(), message)
        return _checkpoint.captured(returned, handoff, support.RUN)

    def test_every_road_has_a_contract(self) -> None:
        """Each road the capture names is one the contract table answers for."""
        self.assertEqual(set(_routes.CONTRACTS), set(_ROUTE))

    def test_a_report_off_its_road_earns_nothing(self) -> None:
        """A label the road does not record its report under is refused, and each one it does is taken."""
        drift = _routes.CONTRACTS[_ROUTE.REQUIREMENTS_DRIFT].labels
        for origin in drift:
            with self.subTest(origin=origin):
                captured = self.earns(_road(_ROUTE.REQUIREMENTS_DRIFT, origin))
                self.assertEqual(captured.handoff.origin, origin)
        off_road = _road(_ROUTE.IMPLEMENTATION, WorkflowLabel.FIXING)
        self.assertIs(self.earns(off_road), _INELIGIBLE.OFF_ROUTE)

    def test_a_handed_road_owes_its_frozen_handoff(self) -> None:
        """A reviewer's change request and a feedback round are captured only beside the handoff they answer."""
        for route in (_ROUTE.REQUESTED_CHANGES, _ROUTE.PR_FEEDBACK):
            with self.subTest(route=route):
                self.assertIs(self.earns(_road(route, WorkflowLabel.FIXING)), _INELIGIBLE.UNHANDED)
                handed = self.earns(_road(route, WorkflowLabel.FIXING, frozen=_FROZEN))
                self.assertEqual(handed.handoff.frozen, _FROZEN)

    def test_a_refresh_is_paid_only_by_a_fresh_report(self) -> None:
        """A rewritten-head refresh refuses a verification, which every other road takes."""
        refresh = _road(_ROUTE.REPORT_REFRESH, WorkflowLabel.VALIDATING)
        self.assertIs(self.earns(refresh, support.VERIFIED), _INELIGIBLE.STALE_VERIFICATION)
        self.assertIsInstance(self.earns(refresh), _records.CompletionCapture)
        self.assertIsInstance(self.earns(support.IMPLEMENTATION, support.VERIFIED), _records.CompletionCapture)


if __name__ == "__main__":
    unittest.main()
