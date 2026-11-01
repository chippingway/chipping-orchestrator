# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A rewritten head's report refresh whose developer reports while an operator holds the issue, dispatched whole.

The world is the rebased one (`report_refresh_test_support`): a pull request a
rebase published onto `REWRITTEN_HEAD`, the receipt naming that head, the
checkout clean on it at the issue's own path, and the debt the rebase left. The
developer an operator holds the issue under applies the control to the issue
itself as it runs (`HeldAs`, as `captured_fixes.HeldUnder` does), so the
live-pause guard behind it, and every poll after it, reads it. Every tick is a
whole dispatch (`issue_processing._process_issue`), since it is the dispatcher
that decides a captured completion ahead of the stage handler, and the report
hold behind it.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator.agents import models as _agent_models
from orchestrator.agents.backends import agy as _agy
from tests.support import agy_stream as _agy_stream
from tests.support.fakes import FakeLabel
from tests.workflow import captured_fixes as _fixes, drift_reports as _drift_world, fix_reports as _fix_world
from tests.workflow.fixtures import AGENT_RUN_WRITES, Launched, _agent
from tests.workflow.held_returns import accounted
from tests.workflow.stages.validating import report_refresh_test_support as _support

RUN_AGENT = _support.RUN_AGENT

# What a held return writes beside its charge and accounting: its capture.
HELD_WRITES = 1

HELD_FIELDS = (_fixes.CAPTURED,)

_ROUND = "review_round"

# What a refresh's report declares nothing about: an approval, verification
# evidence, a docs pass's completion, and readiness.
_UNDECLARED = (
    "review_approved_subject",
    "verification_evidence_pending",
    "verification_evidence_current",
    "docs_final_provenance",
    "ready_ping_sha",
    "ready_ping_pending",
)

_AWAITING = "awaiting_human"

# The developer command an Antigravity session is pinned under, and the
# conversation its stream names.
AGY = "agy"

AGY_SESSION = _agy_stream.SESSION_ID


def unfinished_agy_run() -> _agent_models.AgentResult:
    """An Antigravity exit that left a command running, normalized as a stage receives it: continued once."""
    return _agy.agy_result(_agent_models.AgentRunOptions(), _agent_models.SubprocessResult(
        _agy_stream.ToolStream.canceled_active_command(), "", 1, False, False,
    ))


def continued(text: str = _support.FRESH_REPORT) -> _agent_models.AgentResult:
    """That exit's continuation, finished on a fresh report of the rewritten head."""
    return _agent(session_id=AGY_SESSION, last_message=_support.fresh(text))


class HeldAs:
    """The developer's run, during which an operator applies `control` to the issue, coming back as `answer`.

    `answer` is a finished run's message, or the run's whole result.
    """

    def __init__(self, case, control: str, answer) -> None:
        self._case = case
        self._control = control
        self._answer = answer

    def __call__(self, *_spawn, **_options):
        """Apply the control as the run goes on, then answer as the run finished."""
        self._case.issue.labels.append(FakeLabel(self._control))
        if isinstance(self._answer, str):
            return _agent(session_id=_drift_world.DEV_SESSION, last_message=self._answer)
        return self._answer


class UnansweredAfter:
    """A run behind which GitHub leaves every read of the pull request unanswered, finished on a fresh report."""

    def __init__(self, case) -> None:
        self._unanswered = patch.object(case.github, "get_pr", side_effect=ConnectionError("GitHub did not answer"))

    def __call__(self, *_spawn, **_options):
        """Leave the pull request unanswered from here on, then answer as the run finished."""
        self._unanswered.start()
        return _agent(session_id=_drift_world.DEV_SESSION, last_message=_support.fresh())

    def answered(self) -> None:
        """Answer the pull request's reads again, as GitHub does once it is back."""
        self._unanswered.stop()


class _HeldLaunches(_support._RefreshedReports, _fixes.HeldFixTicks):
    """Whole dispatches over a rebased pull request, its report refresh's developer held as it returns."""

    def held_refresh(self, reply=None, control: str = _fixes.PAUSED, *, before: tuple = (), **run_options) -> dict:
        """A dispatch of the refresh, held under `control` as it returns `reply`, and captured; the record it left.

        `before` are the runs ahead of the held one in the same launch -- an
        Antigravity exit its continuation follows -- each accounted once.
        Nothing moves but each run's charge and accounting and the capture:
        no report, park, round, session, or debt.
        """
        launched = Launched.over(self.github, _support.ISSUE)
        answer = _support.fresh() if reply is None else reply
        self.launch_held(answer, control, before, **run_options)
        if before:
            left = self.pinned()
            self.assertEqual(self.exits_since(launched.record), len(before) + 1)
        else:
            writes = AGENT_RUN_WRITES + HELD_WRITES
            left = launched.held(self, self.github, _support.ISSUE, writes=writes, beside=HELD_FIELDS)
        self.assert_waiting(_fixes.PENDING)
        self.assertFalse(left.get(_AWAITING))
        self.assertEqual(left[_support.DEBT], launched.record[_support.DEBT])
        return left

    def held_unpaid(self, reply, control: str = _fixes.PAUSED, **run_options) -> dict:
        """A dispatch of the refresh, held under `control` as it returns `reply`, which earns no capture.

        The run's accounting is all it leaves: nothing is captured, recorded,
        parked, or published, and the debt stands. `run_options` are the
        dispatch's readings -- the checkout a run returns over among them.
        """
        launched = Launched.over(self.github, _support.ISSUE)
        self.launch_held(reply, control, **run_options)
        left = launched.held(self, self.github, _support.ISSUE)
        unpaid = (left.get(_fixes.CAPTURED), self.unrecorded(), self.claim())
        self.assertEqual(unpaid, (None, _support.NOTHING, _support.REWRITE.recorded()))
        return left

    def launch_held(self, reply, control: str, before: tuple = (), **run_options) -> None:
        """Dispatch the refresh once, its developer launched once and held under `control` as it returns `reply`."""
        self.control = control
        runs = _fix_world._Runs(*before, HeldAs(self, control, reply))
        ran = self.dispatched(MagicMock(side_effect=runs), **run_options)
        self.assertEqual(ran[RUN_AGENT].call_count, len(before) + 1)

    def dispatched(self, run_agent=None, **run_options):
        """One whole dispatch of the issue over its checkout, which a refresh leaves where it stands."""
        run_options.setdefault("committed", False)
        return super().dispatched(run_agent, **run_options)

    def captured_stage(self) -> str | None:
        """The stage of the capture the pinned comment carries, as its record spells it; None where it carries none."""
        return (self.pinned().get(_fixes.CAPTURED) or {}).get("stage")

    def assert_waiting(self, stage: str) -> None:
        """The capture at `stage`, and nothing on the pull request carrying the fresh report."""
        self.assertEqual(_fixes.stage_of(self.pinned()), stage)
        self.assertEqual(self.fresh_reports(), [])


class _Readings(_HeldLaunches):
    """What those dispatches leave the issue having spent, and the record as it stands."""

    def spent(self, record: dict | None = None) -> tuple:
        """What the issue has spent, now or in `record`: the run ledger, the exits accounted, and the round."""
        pinned = self.pinned() if record is None else record
        ledger = tuple(pinned.get(field) for field in _fixes.LEDGER)
        return (*ledger, accounted(pinned), pinned.get(_ROUND))

    def kept(self, record: dict | None = None) -> tuple:
        """What a recovery must not move, now or in `record`: what the issue has spent, the debt, and the undeclared.

        The undeclared are the records of an approval, verification
        evidence, a docs pass's completion, and readiness, none of which a
        refresh's report answers for.
        """
        pinned = self.pinned() if record is None else record
        undeclared = tuple(pinned.get(field) for field in _UNDECLARED)
        return (*self.spent(pinned), pinned.get(_support.DEBT), undeclared)

    def exits_since(self, record: dict) -> int:
        """How many exits the issue has accounted since `record`."""
        return accounted(self.pinned())[0] - accounted(record)[0]

    def standing(self) -> tuple:
        """The pinned record and the writes taken so far, for `HeldRefreshes.assert_held`."""
        return self.pinned(), self.github.write_state_calls

    def published(self, text: str = _support.FRESH_REPORT) -> list:
        """The report each comment on the pull request carrying `text` reads back as."""
        return _support.published_texts(self, text)


class HeldRefreshes(_Readings):
    """Those dispatches, with what a recovery must have left."""

    def assert_finished(self, kept: tuple, text: str = _support.FRESH_REPORT) -> None:
        """The capture handed off, `text` published once and settled about the rewritten head, nothing else moved.

        Settled under the requirements the run was handed, one revision past
        the report the rebase left behind, with nothing parked, no run
        charged or accounted, no round spent, and the debt still standing for
        the next tick to drop.
        """
        finished = self.pinned()
        settled = self.records()["current"].subject
        revision = self.records()["current"].report_revision
        self.assertEqual(
            (_fixes.stage_of(finished), self.published(text), revision - 1),
            (_fixes.HANDED_OFF, [text], self.opening_report.report_revision),
        )
        about = (settled.source_sha, settled.requirements_revision)
        self.assertEqual(about, (_support.REWRITTEN_HEAD, finished["user_content_hash"]))
        self.assertFalse(finished.get(_AWAITING))
        self.assertEqual(self.kept(), kept)

    def reviewed_next(self, text: str = _support.FRESH_REPORT) -> None:
        """The next dispatch pays the debt and runs the reviewer alone, handed `text`; never the developer again."""
        reviewer = _agent(session_id=_fix_world.REVIEWER_SESSION, last_message="read it")
        self.assert_reviewed_fresh(self.dispatched(MagicMock(side_effect=[reviewer])), text)

    def assert_retired(self, held: dict) -> None:
        """The capture retired with nothing recorded, published, or parked, and nothing spent since `held`."""
        self.assertEqual(_fixes.stage_of(self.pinned()), _fixes.RETIRED)
        self.assertEqual(self.unrecorded(), _support.NOTHING)
        self.assertEqual(self.spent(), self.spent(held))

    def assert_held(self, before: tuple) -> None:
        """Nothing written or published since `before`, the capture still pending."""
        self.assertEqual(self.standing(), before)
        self.assert_waiting(_fixes.PENDING)
