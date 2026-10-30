# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured completion's wire shape: what each stage is spelled as, and what reads back as no capture.

Every stage round-trips exactly through the pinned comment's JSON, and the
spelling is pinned, since live issues will carry it. A field the issue never
wrote is the supported absence; anything else a reader cannot take whole --
`null`, a key too many or too few, a member out of its bound, a report the
report records refuse, a road its contract refuses -- is a damaged claim,
never an absence. A frozen handoff tells a record another road moved from one
it left alone, `null` from missing included.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import unittest
from types import MappingProxyType

from orchestrator.github.comments import RECEIPT_MARKER_PREFIX
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    completion_records as _records,
    completion_routes as _routes,
    completion_spelling as _spelling,
    completion_state as _state,
    completion_values as _bounds,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import completion_test_support as support

_DIGEST = hashlib.sha256(b"a frozen record").hexdigest()
_ROUTE = "route"
_ORIGIN = "origin"
_FROZEN = "frozen"
_DELIVERED = "delivered"
_RESUMED = "resumed"
_PINNED = "pinned"
_SUPERSEDES = "supersedes"
_STAGE = "stage"
_REPORT = "report"
_PR = "pr_number"
_FIX = "pending_fix_at"
_VERDICT = "review_returned_verdict"
_RECEIPT = "issue-2426-report-3"
_REVISION = 3
_OVERSIZED = "x" * (_bounds.MAX_COMMAND + 1)
_LONG_SESSION = "s" * (_bounds.MAX_SESSION + 1)

# The keys a PENDING READY capture is spelled with, beside the invocation's.
_INVOCATION_KEYS = frozenset(("repo", "issue", "comment", "cycle", "ordinal", "nonce"))
_PENDING_KEYS = frozenset((
    _STAGE, _ROUTE, _ORIGIN, "requirements", "watermarks", "spends", _FROZEN, _DELIVERED,
    "command", "prompt", "worktree", "branch", "before", "source", _RESUMED, _PINNED, "session",
    "outcome", _REPORT, "accounting", _SUPERSEDES,
))

# One member of an otherwise sound PENDING READY spelling, replaced; each
# reads back as no capture at all. None for a value removes the key.
_DAMAGED = MappingProxyType({
    "a key too many": ("retired", "yes"),
    "no report": (_REPORT, None),
    "an unknown stage": (_STAGE, "parked"),
    "an unknown road": (_ROUTE, "documentation"),
    "an unknown outcome": ("outcome", "acknowledged"),
    "a label off its road": (_ORIGIN, str(WorkflowLabel.FIXING)),
    "a nonce of another shape": ("nonce", "XYZ"),
    "a comment no record has": ("comment", 0),
    "a negative cycle": ("cycle", -1),
    "a flag for a cycle": ("cycle", True),
    "a command on two lines": ("command", "claude\n--resume"),
    "a command past its bound": ("command", _OVERSIZED),
    "a session past its bound": ("session", _LONG_SESSION),
    "an empty checkout": ("worktree", ""),
    "a branch with a space": ("branch", "issue 2426"),
    "an abbreviated commit": ("before", "abc1234"),
    "a report quoting a receipt marker": (_REPORT, f"Quoted {RECEIPT_MARKER_PREFIX}state here."),
    "a blank report": (_REPORT, "  "),
    "an unknown watermark": ("watermarks", [["somebody_elses_field", 1]]),
    "no spend group": ("spends", None),
    "a frozen record of no pinned name": (_FROZEN, [["Not A Key", _DIGEST]]),
    "a frozen record twice": (_FROZEN, [[_PR, _DIGEST], [_PR, _DIGEST]]),
    "frozen records out of order": (_FROZEN, [[_PR, _DIGEST], ["branch", _DIGEST]]),
    "a frozen record of no digest": (_FROZEN, [[_PR, "1"]]),
    "an unknown accounting": ("accounting", "refunded"),
    "an upper-case prompt digest": ("prompt", support.RUN.prompt_revision.upper()),
    "a stretch of one end": (_DELIVERED, [0]),
    "a stretch upside down": (_DELIVERED, [9, 3]),
    "a stretch below zero": (_DELIVERED, [-1, 3]),
    "a stretch of flags": (_DELIVERED, [False, True]),
    "no stretch at all": (_DELIVERED, None),
    "a resumed conversation past its bound": (_RESUMED, _LONG_SESSION),
    "a pinned conversation past its bound": (_PINNED, _LONG_SESSION),
    "no superseded handoff spelled": (_SUPERSEDES, None),
    "a superseded handoff of another shape": (_SUPERSEDES, "issue-2426-report-3"),
})

# What a resolved capture's own members may not be.
_DAMAGED_RESOLVED = MappingProxyType({
    "a handoff naming no receipt": (_records.CaptureStage.HANDED_OFF, "receipt", None),
    "a handoff of no revision": (_records.CaptureStage.HANDED_OFF, "revision", 0),
    "a retirement for no reason": (_records.CaptureStage.RETIRED, "reason", "forgotten"),
    "a retirement keeping a receipt": (_records.CaptureStage.RETIRED, "receipt", _RECEIPT),
    "a retirement spelling no carried handoff": (_records.CaptureStage.RETIRED, _SUPERSEDES, None),
    "a retirement carrying no handoff": (_records.CaptureStage.RETIRED, _SUPERSEDES, {_STAGE: "retired"}),
    "a handoff spelling a carried one": (_records.CaptureStage.HANDED_OFF, _SUPERSEDES, {_STAGE: "handed_off"}),
})


def _resolved(stage: _records.CaptureStage, invocation) -> _records.ResolvedCapture:
    """A resolved capture of `invocation` at `stage`, as its writer leaves it."""
    if stage is _records.CaptureStage.RETIRED:
        return _records.ResolvedCapture(invocation, stage, reason=_records.RetirementReason.INVALIDATED)
    return _records.ResolvedCapture(
        invocation, stage, receipt=_RECEIPT, report_revision=_REVISION, branch=support.BRANCH,
        source_sha=support.SOURCE,
    )


def _replaced(spelling: dict, key: str, member) -> dict:
    """`spelling` with `key` set to `member`, or removed where `member` is None."""
    changed = {**spelling, key: member}
    if member is None:
        changed.pop(key)
    return changed


class CompletionSpellingTest(unittest.TestCase):
    """Each stage round-trips exactly, under the keys live issues will carry."""

    def setUp(self) -> None:
        self.world = support.seeded()

    def assert_round_trips(self, record) -> None:
        """`record` reads back as itself from what its JSON spelling parses into."""
        spelled = _spelling.spelled(record)
        self.assertEqual(json.loads(json.dumps(spelled)), spelled)
        self.assertEqual(_spelling.read_record(spelled), record)

    def test_every_stage_round_trips(self) -> None:
        """READY and VERIFIED captures, a description verification, a stretch, both resolved stages, and a carrier."""
        verified = self.world.completion(message=support.VERIFIED, session_id=None)
        description = dataclasses.replace(verified, outcome=dataclasses.replace(
            verified.outcome, location=dataclasses.replace(verified.outcome.location, comment_id=None),
        ))
        stretched = dataclasses.replace(
            self.world.completion(2),
            handoff=dataclasses.replace(support.IMPLEMENTATION, delivered=(0, 41)),
            run=dataclasses.replace(support.RUN, resumed=support.SESSION, pinned=support.SESSION),
            supersedes=_resolved(_records.CaptureStage.HANDED_OFF, self.world.invocation()),
        )
        resolved = (
            _resolved(support.STAGE.HANDED_OFF, self.world.invocation()),
            _resolved(support.STAGE.RETIRED, self.world.invocation()),
            dataclasses.replace(
                _resolved(support.STAGE.RETIRED, self.world.invocation(2)), supersedes=stretched.supersedes,
            ),
        )
        for record in (self.world.completion(), verified, description, stretched, *resolved):
            with self.subTest(stage=record.stage):
                self.assert_round_trips(record)

    def test_the_pending_spelling_is_pinned(self) -> None:
        """A pending READY capture is one flat object: the invocation's keys and the stage's, and no others."""
        spelled = _spelling.spelled(self.world.completion())
        self.assertEqual(set(spelled), {*_INVOCATION_KEYS, *_PENDING_KEYS})
        pinned = (_STAGE, _ROUTE, _ORIGIN, "outcome", _REPORT, _DELIVERED, _RESUMED, _PINNED, _SUPERSEDES)
        self.assertEqual(
            tuple(spelled[key] for key in pinned),
            ("pending", "implementation", "workflow:implementing", "ready", support.REPORT, [], None, None, None),
        )


class CompletionReadingTest(unittest.TestCase):
    """What reads back as no capture, and how a state tells that damage from an absence."""

    def setUp(self) -> None:
        self.world = support.seeded()
        self.spelled = _spelling.spelled(self.world.completion())

    def test_a_damaged_member_reads_as_no_capture(self) -> None:
        """Each member out of its bound, or a key too many or too few, refuses the whole capture."""
        for case, (key, member) in _DAMAGED.items():
            with self.subTest(case=case):
                self.assertIsNone(_spelling.read_record(_replaced(self.spelled, key, member)))

    def test_a_damaged_resolved_member_reads_as_none(self) -> None:
        """A resolved stage's own members are held to their bounds and to that stage's keys."""
        for case, (stage, key, member) in _DAMAGED_RESOLVED.items():
            spelled = _spelling.spelled(_resolved(stage, self.world.invocation()))
            with self.subTest(case=case):
                self.assertIsNone(_spelling.read_record(_replaced(spelled, key, member)))

    def test_a_road_its_contract_refuses_is_none(self) -> None:
        """A refresh verified, and a handed road with no frozen handoff, are no capture this build writes."""
        verified = _spelling.spelled(self.world.completion(message=support.VERIFIED))
        refreshed = {**verified, _ROUTE: str(_routes.CompletionRoute.REPORT_REFRESH)}
        refreshed[_ORIGIN] = str(WorkflowLabel.VALIDATING)
        unhanded = {**self.spelled, _ROUTE: str(_routes.CompletionRoute.REQUESTED_CHANGES)}
        unhanded[_ORIGIN] = str(WorkflowLabel.FIXING)
        read_back = (_spelling.read_record(refreshed), _spelling.read_record(unhanded))
        self.assertEqual(read_back, (None, None))

    def test_damage_is_a_claim_and_absence_is_none(self) -> None:
        """A missing field carries nothing; `null`, a list, and a damaged object are each a claim nothing reads."""
        absent = PinnedState()
        read_back = (_state.carries(absent), _state.read(absent))
        self.assertEqual(read_back, (False, None))
        for claimed in (None, [self.spelled], {**self.spelled, "nonce": 1}):
            state = PinnedState(state_data={support.FIELD: claimed})
            with self.subTest(claimed=type(claimed).__name__):
                read_back = (_state.carries(state), _state.read(state))
                self.assertEqual(read_back, (True, None))


class FrozenHandoffTest(unittest.TestCase):
    """A handoff frozen over a reading, asked of a later one."""

    def test_a_moved_record_is_named(self) -> None:
        """Only the records spelled otherwise since are named, `null` where one was missing included."""
        launched = PinnedState(state_data={_PR: support.VERIFIED_PR, _VERDICT: None})
        frozen = _frozen.frozen_over(launched, (_VERDICT, _PR, _FIX))
        moved = PinnedState(state_data={**launched.state_data, _FIX: None})
        moved.set(_PR, support.VERIFIED_PR + 1)
        self.assertEqual(
            (
                [field for field, _digest in frozen],
                _frozen.moved_since(launched, frozen),
                _frozen.moved_since(moved, frozen),
            ),
            ([_FIX, _PR, _VERDICT], (), (_FIX, _PR)),
        )
        self.assertEqual(_bounds.frozen([list(pair) for pair in frozen]), frozen)


if __name__ == "__main__":
    unittest.main()
