# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A reviewer's change request whose developer reports while an operator holds the issue, dispatched as a poll does.

The world is the fix loop's (`fix_reports`): an open pull request on the
issue's branch whose last publication the code-publication receipt names, a
checkout on its head at the issue's own path, and a push that moves the pull
request onto the commit it sends. The direct round is the validating tick whose
reviewer requests changes and whose developer the handoff launches; the
resumed round is the fixing tick a human's reply, or an operator's
`/orchestrator continue`, buys on the far side of a park that round took. The
developer an operator holds the issue under applies the control to the issue
itself as it runs, so the live-pause guard behind it, and every poll after
it, reads it. Every later tick is a whole dispatch
(`issue_processing._process_issue`), since it is the dispatcher that decides a
captured completion ahead of the stage handler.

What a lost process or a lost answer leaves is made at the one edit that hands
a capture off (`LostAtTheHandoff`), or at the one that takes it: the process
gone before it is sent, gone once it landed, or the edit landing with its
answer lost.
"""
from __future__ import annotations

import sys
from functools import partial
from types import MappingProxyType
from unittest.mock import MagicMock

from orchestrator.git.publication import probes as _publication_probes
from orchestrator.github.labels import BACKLOG_LABEL, PAUSED_LABEL
from orchestrator.github.pull_request_reports import ReportLookup, ReportPresence
from orchestrator.workflow.engine import (
    completion_records as _records,
    completion_spelling as _spelling,
    issue_processing as _issue_processing,
    report_records as _report_records,
    run_ledger_values as _run_ledger_values,
)
from tests.support.fakes import FakeLabel
from tests.workflow import drift_reports as _drift_world, fix_reports as world
from tests.workflow.fixtures import _TEST_SPEC, _agent

CAPTURED = _records.DEVELOPER_COMPLETION
CURRENT_REPORT = _report_records.CURRENT_REPORT
REPORT_HANDOFF = _report_records.REPORT_HANDOFF
STAGE = "stage"
VERDICT = "review_returned_verdict"
ANCHOR = "pending_fix_reviewer_comment_id"
ROUND = "review_round"
AWAITING = "awaiting_human"
RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"

# The run ledger a recovery charges nothing against: the runs counted, and the
# start of the developer launch a handed request owed.
LEDGER = (_run_ledger_values.AGENT_RUNS_USED, _run_ledger_values.AGENT_RUN_OWED_STARTED)

# The two controls an operator holds an issue with.
PAUSED = PAUSED_LABEL
BACKLOG = BACKLOG_LABEL

# A capture's stage, as its record spells it.
PENDING = "pending"
HANDED_OFF = "handed_off"
RETIRED = "retired"

# Where a lost process or a lost answer leaves the handoff of a capture:
# never sent, landed, or landed with its answer lost.
SENT = "sent"
LANDED = "landed"
ANSWER = "answer"

# The checkout every round runs in: the issue's own path, which every reading
# of its committed work -- the capture's admission among them -- is taken at.
CHECKOUT = _drift_world._EXISTING_WORKTREE

# What a recovery reads of the checkout: the commit the held run left, which
# the remote agrees with once the push lands; and the head the pull request
# already carries, where the run committed nothing.
COMMITTED = MappingProxyType({_drift_world.HEAD_SHAS: (world.FIXED_HEAD,), _drift_world.FETCHED_TIP: world.FIXED_HEAD})
UNMOVED = MappingProxyType({
    _drift_world.HEAD_SHAS: (world.PUBLISHED_HEAD,), _drift_world.FETCHED_TIP: world.PUBLISHED_HEAD,
})

# Which of those a recovery reads, by whether the run committed.
READING = MappingProxyType({True: COMMITTED, False: UNMOVED})

# What a tick reads of a checkout carrying a commit a handed-off report is
# about and no push has sent: one ahead of the pull request's head.
STRANDED = _drift_world.STRANDED

# The reviewer's words, which its feedback post on the pull request carries.
FEEDBACK = world.REPORT_ONLY_FEEDBACK

# What a hand edit spells a field as to take its key off the record altogether.
OMITTED = object()

# The settled report pair left disagreeing, each case the record moved and
# how: a revision past the other's, or taken off from beside it. One
# settlement writes the two together and nothing clears either, so each is
# damage, never a report settled since.
REVISION = "revision"
DISAGREEING = (
    (CURRENT_REPORT, REVISION), (CURRENT_REPORT, OMITTED), (REPORT_HANDOFF, REVISION), (REPORT_HANDOFF, OMITTED),
)

# A reviewer requesting changes over a passing check it declared on the head
# the pull request carries, whose request claims the evidence that publishes.
_VERIFIED_REVIEW = (
    f"Please clarify the report.\nVERIFICATION: RUN {world.PUBLISHED_HEAD}\n"
    "COMMAND: true\nEXIT: 0\nVERIFICATION: END\nVERDICT: CHANGES_REQUESTED"
)


def capture_of(record: dict):
    """The capture a pinned record carries, read as its own reader reads it."""
    return _spelling.read_record(record.get(CAPTURED))


def stage_of(record: dict) -> str:
    """The stage of the capture a pinned record carries, as its record spells it."""
    return record[CAPTURED][STAGE]


class HeldUnder:
    """The developer's run, during which an operator applies `control` to the issue, coming back as `reply`."""

    def __init__(self, case, control: str, reply: str) -> None:
        self._case = case
        self._control = control
        self._reply = reply

    def __call__(self, *_spawn, **_options):
        """Apply the control as the run goes on, then answer as the run finished."""
        self._case.issue.labels.append(FakeLabel(self._control))
        return _agent(session_id=world.DEV_SESSION, last_message=self._reply)


class LostAtTheHandoff:
    """The strict edit, at the one handing a capture off: the process lost before or after it, or its answer lost.

    `stage` names another edit to lose it at instead, by the stage it moves
    the capture to: `PENDING` is the one taking the capture.
    """

    def __init__(self, github, lost: str, stage: str = HANDED_OFF) -> None:
        self._github = github
        self._lost = lost
        self._stage = stage

    def __call__(self, issue, state, *, over: dict):
        """Send the edit, losing the process or the answer around the one that hands the capture off."""
        handing_off = self._hands_off(state) and not self._hands_off(over)
        if handing_off and self._lost == SENT:
            sys.exit("the process was lost as the handoff went out")
        if handing_off and self._lost == ANSWER:
            self._github.pinned_failures.lost.add(issue.number)
        sent = type(self._github).edit_pinned_state(self._github, issue, state, over=over)
        self._github.pinned_failures.lost.discard(issue.number)
        if handing_off and self._lost == LANDED:
            sys.exit("the process was lost once the handoff landed")
        return sent

    def _hands_off(self, state) -> bool:
        """Whether `state`, a pinned state or the record an edit is sent over, carries a capture at the edit's stage."""
        captured = state.get(CAPTURED) or {}
        return captured.get(STAGE) == self._stage


class ReadAt:
    """The report re-read, at one location left unanswered -- or answered, with the issue moved as it is read.

    With no move, the re-read at `location` is left unconfirmed. A `control`
    is applied to the case's issue as that re-read is answered, an `edit`
    rewrites its body as GitHub answers every later read with it
    (`drift_reports.edits`), a `push` moves the pull request onto
    `drift_reports.CONCURRENT_HEAD`, every later reading of the branch
    counting the checkout one commit ahead of it, and a `damage` rewrites the
    pinned fields it maps as a hand edit would (`CapturedFixTicks.hand_edit`)
    -- so every read behind that re-read finds the issue, its pull request,
    or its pinned comment moved.
    """

    def __init__(self, case, location, **moves) -> None:
        self._case = case
        self._reread = case.github.reread_report_location
        self._location = location
        self._moves = moves

    def __call__(self, where, *, content_sha256):
        """Re-read the report at `where`, as this case's re-read at the one location answers."""
        if where != self._location:
            return self._reread(where, content_sha256=content_sha256)
        if not any(self._moves.values()):
            return ReportLookup(ReportPresence.UNCONFIRMED)
        if self._moves.get("control"):
            self._case.issue.labels.append(FakeLabel(self._moves["control"]))
        if self._moves.get("edit"):
            _drift_world.edits(self._case, self._moves["edit"])
        if self._moves.get("push"):
            self._case.pull_request.head.sha = _drift_world.CONCURRENT_HEAD
            _publication_probes._branch_divergence.return_value = _publication_probes._BranchDivergence(
                tip=_drift_world.CONCURRENT_HEAD, ahead=1, behind=0, readable=True,
            )
        if self._moves.get("damage"):
            self._case.hand_edit(**self._moves["damage"])
        return self._reread(where, content_sha256=content_sha256)


class HeldFixTicks(world._FixReportMixin):
    """The fix loop's ticks over one issue, its developer held as it runs and the later ticks dispatched whole."""

    def held_fix(self, reply: str, control: str = PAUSED, **run_options):
        """The direct round, its developer held under `control` as it runs and finishing as `reply`."""
        self.control = control
        return self.requested_fix(HeldUnder(self, control, reply), issue_worktree=CHECKOUT, **run_options)

    def held_resume(self, reply: str, control: str = PAUSED, **run_options):
        """A dispatch of the parked round's resume, its developer held under `control` and finishing as `reply`."""
        self.control = control
        runs = world._Runs(HeldUnder(self, control, reply))
        return self.dispatched(MagicMock(side_effect=runs), **run_options)

    def dispatched(self, run_agent=None, **run_options):
        """One whole dispatch of the issue over the round's checkout; the seams it ran over."""
        agents = MagicMock() if run_agent is None else run_agent
        return self._ticked(self._dispatch, agents, issue_worktree=CHECKOUT, **run_options)

    def held_ticks(self) -> None:
        """Two dispatches while the issue stays held: neither runs anything nor writes anything."""
        for tick in ("first", "second"):
            with self.subTest(held_tick=tick):
                before = (self.pinned(), self.github.write_state_calls)
                held = self.dispatched()
                held[RUN_AGENT].assert_not_called()
                self.assertEqual((self.pinned(), self.github.write_state_calls), before)

    def lifts_the_control(self) -> None:
        """Take the control the issue is held under off it."""
        for label in tuple(self.issue.labels):
            if label.name == self.control:
                self.issue.labels.remove(label)

    def unheld(self, **run_options):
        """Take the control off and dispatch once; no agent may run."""
        self.lifts_the_control()
        recovered = self.dispatched(**run_options)
        recovered[RUN_AGENT].assert_not_called()
        return recovered

    def _dispatch(self, github, issue, *, run_agent, **run_options):
        """Dispatch `issue` once, as a poll does."""
        return self._run(
            partial(_issue_processing._process_issue, github, _TEST_SPEC, issue), run_agent=run_agent, **run_options,
        )


class CapturedFixTicks(HeldFixTicks):
    """Those ticks, with what a case edits between them and reads back after them."""

    def hand_edit(self, **fields) -> None:
        """Rewrite pinned fields as another road, or a human, would between two ticks; `OMITTED` drops a key."""
        state = self.github.read_pinned_state(self.issue)
        for key, spelled in fields.items():
            if spelled is OMITTED:
                state.state_data.pop(key)
            else:
                state.set(key, spelled)
        self.github.write_pinned_state(self.issue, state)

    def unsettles(self, field: str, moved) -> dict:
        """Leave the settled report pair disagreeing, `field` moved as a `DISAGREEING` case says; what it was."""
        settled = self.pinned()[field]
        revised = dict(settled)
        revised[REVISION] += 1
        self.hand_edit(**{field: OMITTED if moved is OMITTED else revised})
        return settled

    def reports(self) -> int:
        """How many posts of the round's report the pull request carries."""
        return len(self.published_reports())

    def feedback_posts(self) -> int:
        """How many posts of the reviewer's feedback the pull request carries."""
        return sum(FEEDBACK in (posted.body or "") for posted in self.pull_request.issue_comments)

    def ledger(self) -> tuple:
        """The run ledger's count and owed start, as the record carries them."""
        return tuple(self.pinned().get(field) for field in LEDGER)

    def held_verified_fix(self, control: str = PAUSED):
        """The direct round over a reviewer that declared a passing check, its developer held as it reports alone."""
        self.control = control
        return self.verified_round(HeldUnder(self, control, world.reported()))

    def verified_round(self, developer):
        """The direct round over a reviewer that declared a passing check, its developer answering as `developer`.

        The request the reviewer returns claims the verification evidence
        that declaration publishes. `developer` is a reply, or the run itself.
        """
        runs = world._Runs(_agent(session_id=world.REVIEWER_SESSION, last_message=_VERIFIED_REVIEW), developer)
        return self._ticked(self._run_validating, MagicMock(side_effect=runs), committed=False, issue_worktree=CHECKOUT)
