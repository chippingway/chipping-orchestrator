# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue of `disposed_verdict_test_support`, whose waiting verdict a stage's own tick finishes.

A case leaves a verdict waiting the way a tick the disposition service ran
leaves it -- its publication held, its feedback post refused, its relabel or
its developer's start refused -- and then runs a whole `workflow:validating`
tick (`validates`) or `workflow:fixing` tick (`fixes`), whose recovery
(`review_resume`) finishes it ahead of the round cap and the reviewer spawn,
or ahead of the feedback scan and its bounce. What the developer launch the
handoff left behind recorded is spelled here too (`starts`): its start, a
start under that very launch's identity recording no owed count -- its charge
reserved ahead of the handoff included, so counted in the count it was handed
at, and one whose fingerprint, phase, or count no reader takes -- a charge
never started under a fingerprint no reader takes, or an owed count no reader
takes, and the `/orchestrator continue` a park of that launch is
answered with (`asks_to_continue`). So is a checkout gone from this host whose
restore is refused (`REFUSED_CHECKOUT`), and another road charging and
starting a run under that launch's very identity right before one of the
handoff's requests (`ChargesFirst`, `charged_behind`).
"""
from __future__ import annotations

from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import (
    run_charge_state as _run_charge_state,
    run_ledger as _run_ledger,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.stages.implementing import execution as _execution
from orchestrator.workflow.stages.validating import handler as _validating
from orchestrator.workflow.state import stage_name
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.fixtures import LABEL_FIXING
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    review_handoff_test_support as _handoff,
    review_verdict_test_support as _world,
)

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# A reviewer asking for that change beside its declared run of the suite, which
# failed: a request whose claim is that run's published evidence.
DECLARED_REQUEST = _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED")

CONTINUE = "/orchestrator continue"

# How the developer launch a handed request owes was left: started, or read
# as it cannot be told from a start -- that launch's own identity started
# with no owed count, or an owed count spelled as none.
STARTED = "started"

SAME_IDENTITY = "started under its identity"

RESERVED_AHEAD = "started under its identity, reserved ahead of the handoff"

UNREADABLE = "an unreadable owed start"

NULL_START = "an owed start spelled null"

# A charge for that launch whose record the run circuit cannot read, so
# nothing tells it from that launch: started with its fingerprint gone,
# spelled as no fingerprint, its phase spelled as no phase, or its run count
# unread with the other meter behind the handed count -- or never started,
# under a fingerprint no reader takes, which the circuit cannot honor.
NO_FINGERPRINT = "started under no fingerprint"

UNREAD_FINGERPRINT = "started under a fingerprint no reader takes"

UNREAD_PHASE = "under its identity, in a phase no reader takes"

UNREAD_COUNT = "started under its identity, its run count unread and the other meter behind"

RESERVED_UNREAD = "reserved under a fingerprint no reader takes"

# What each of those writes over the charge, the fingerprint dropped first for
# a start under none.
_UNREAD_LEDGERS = MappingProxyType({
    UNREAD_FINGERPRINT: {_run_ledger_values.AGENT_RUN_FINGERPRINT: 7},
    UNREAD_PHASE: {_run_ledger_values.AGENT_RUN_RESERVATION: "running"},
    UNREAD_COUNT: {_run_ledger_values.AGENT_RUNS_USED: "two", _run_ledger_values._LEGACY_RUNS_USED: 0},
    RESERVED_UNREAD: {_run_ledger_values.AGENT_RUN_FINGERPRINT: 7},
})

# The issue's checkout gone from this host and its restore refused, as the run
# options a tick takes over it.
REFUSED_CHECKOUT = MappingProxyType({"worktree_restore_error": RuntimeError("git worktree add failed")})


def starts(case, how: str) -> None:
    """Leave the charge `case`'s handoff reserved for its developer as `how` says."""
    state = case.github.read_pinned_state(case.issue)
    verdict = state.get(_world.RETURNED_VERDICT)
    handed = verdict[_disposed.HANDED]
    if how in {UNREADABLE, NULL_START}:
        state.set(_run_ledger_values.AGENT_RUN_OWED_STARTED, str(handed) if how == UNREADABLE else None)
    elif how != RESERVED_UNREAD:
        _run_ledger._start_reserved_run(state, handed if how == STARTED else None)
    if how == RESERVED_AHEAD:
        # Handed at the count that charge was already in, so starting it moved nothing past that count.
        state.set(_world.RETURNED_VERDICT, {**verdict, _disposed.HANDED: _run_ledger_values._runs_used(state)})
    if how == NO_FINGERPRINT:
        state.data.pop(_run_ledger_values.AGENT_RUN_FINGERPRINT)
    state.data.update(_UNREAD_LEDGERS.get(how, {}))
    case.github.write_pinned_state(case.issue, state)


def refuses_the_post(case, message: str = UNDECLARED_REQUEST) -> None:
    """The tick whose reviewer requested changes as `message`, its feedback post refused, handing nothing over."""
    refuses = _handoff.RefusesOnce(case.github.pr_comment, _handoff.FEEDBACK_NOTICE, lands=False)
    with patch.object(case.github, "pr_comment", refuses):
        case.returns(message, **_disposed.fixing())


def refuses_the_relabel(case, message: str = UNDECLARED_REQUEST) -> None:
    """The tick handing the request `message` asks for over, dying on the relabel refused ahead of its developer."""
    refused = patch.object(case.github, "set_workflow_label", side_effect=RuntimeError("refused"))
    with refused, case.assertRaises(RuntimeError):
        case.returns(message, **_disposed.fixing())


def asks_for_a_continue(body: str) -> bool:
    """Whether a posted body is a park notice asking for `/orchestrator continue`."""
    return CONTINUE in body


def clears_the_anchor(case) -> None:
    """Another write clearing the pinned feedback anchor, as the fixing stage's bookmark clear does."""
    _handoff.moves_the_anchor(case, to="nowhere")


class ChargesFirst:
    """`request`, ahead of which, the first time, another road charges a run of the owed launch's identity.

    The run is charged and started under the very fingerprint the developer
    launch a handed request owes is charged under, and records no owed count,
    so nothing tells it from that launch.
    """

    def __init__(self, case, request) -> None:
        self._case = case
        self._request = request
        self._left = True

    def __call__(self, *asked, **named):
        if self._left:
            self._left = False
            self._charges()
        return self._request(*asked, **named)

    def _charges(self) -> None:
        github, issue = self._case.github, self._case.issue
        state = github.read_pinned_state(issue)
        _run_ledger._reserve_run(state, _execution._first_launch_fingerprint(state, stage_name(LABEL_FIXING)))
        _run_ledger._start_reserved_run(state)
        github.write_pinned_state(issue, state)


class ResumedVerdictWorld(_disposed.DisposedVerdictWorld):
    """The same issue, whose waiting verdict is finished by the stage's own handler."""

    def validates(self, **run_options):
        """One `workflow:validating` tick -- the evidence reconciliation, then the handler; the agent runs it made."""
        run_options.setdefault(_world.RUN_AGENT, [])
        return self._run(self._validating_tick, **run_options)[_world.RUN_AGENT]

    def fixes(self, **run_options):
        """One `workflow:fixing` tick over the pinned comment as it reads; the agent runs it made."""
        run_options.setdefault(_world.RUN_AGENT, [])
        return self._run_fixing(self.github, self.issue, **run_options)[_world.RUN_AGENT]

    def hands_over_unstarted(self, message: str = UNDECLARED_REQUEST) -> None:
        """The tick handing the change request `message` asks for over, relabelled to `fixing`, its start refused.

        The handed write and the relabel land, and the charge the launch took
        stands reserved, so nobody is launched.
        """
        refuses = _handoff.RefusesTheStart(self.github.write_pinned_state)
        with patch.object(self.github, "write_pinned_state", refuses):
            self.returns(message, **_disposed.fixing())
        self.assertEqual(self.github.workflow_label(self.issue), LABEL_FIXING)

    def holds_an_approval(self) -> None:
        """The tick whose approval's evidence post lands with its response lost, leaving the approval waiting."""
        self.github.report_failures.lost.add(_world.PR)
        self.returns(_world.declared_run(), **_disposed.ON_THE_HEAD)
        self.github.report_failures.lost.discard(_world.PR)

    def charged_behind(self, request: str):
        """`request` -- the client's relabel, or the run circuit's ledger read -- patched behind `ChargesFirst`."""
        owner = self.github if hasattr(self.github, request) else _run_charge_state
        return patch.object(owner, request, ChargesFirst(self, getattr(owner, request)))

    def asks_to_continue(self, words: str = CONTINUE) -> None:
        """A trusted `/orchestrator continue` on the issue thread, or the reply `words` says in its place."""
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(FakeComment(identified, words, user=FakeUser("alice")))

    def _validating_tick(self) -> None:
        """The validating handler, behind the reconciliation that runs ahead of every handler."""
        if not _world.reconciles(self):
            _validating._handle_validating(self.github, _TEST_SPEC, self.issue)
