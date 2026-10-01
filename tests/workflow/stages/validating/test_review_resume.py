# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A verdict an earlier tick left waiting is finished by the stage's own tick, spending nothing twice.

Through `review_resume`, as the handlers ask it: on `workflow:validating` ahead
of the round cap and the reviewer spawn, and on `workflow:fixing` ahead of the
feedback scan and its bounce. A held approval is proved and approved, and a
change request posted, relabelled, and handed to its one developer, with no
second reviewer, no usage folded again, and no round spent by the recovery; a
reservation its handoff took is honored rather than charged again, and a lost
feedback anchor is written back from the record -- where a verdict another
road put in its place meanwhile ends the tick, handing nothing over. A run of
the launch's very identity charged behind the handoff's checks launches
nobody. A subject that moved drops the verdict -- only while the comment still
carries it, so a verdict another road put in its place stands -- for a fresh
reviewer on the next tick, and a subject, issue, or thread nobody could read
holds it, a handed one whose developer may have run included. A reply that
bought a fresh round where a verdict waits, or the report hold stops that
round, settles the tick in one write over the comment read afresh -- keeping
the cleared park and what another road wrote meanwhile, a park of its own
included, and dropping the verdict only where the comment still carries it --
for the round to run next tick. A launch that may already have started is
`test_review_resume_launches`'s.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.validating import report_hold as _report_hold, review_verdicts as _verdicts
from tests.workflow.fixtures import (
    BACKEND_CLAUDE,
    LABEL_DOCUMENTING,
    LABEL_FIXING,
    LABEL_VALIDATING,
    STAGE_VALIDATING,
    _agent,
)
from tests.workflow.published_reports import DELIVERED_REPORT
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    resumed_verdict_test_support as _resumed,
    review_handoff_test_support as _handoff,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

TOKENS = "issue_total_tokens"

EXECUTION_FAILED = "agent_execution_failed"

RUN_LIMIT = "agent_run_limit"

ALLOWANCE = "agent_run_allowance"

# The run circuit's park over a spent allowance, as `parked` reads it: the
# request it refused still waiting.
_RUN_LIMIT_PARK = ((RUN_LIMIT, True), "changes_requested", [RUN_LIMIT])

CONTINUE = _resumed.CONTINUE

# A grant of one more review round, as a human replies it to the review cap.
_GRANT = "/orchestrator add-review-rounds 1"

FIXING = (_world.ISSUE, LABEL_FIXING)

VALIDATING = (_world.ISSUE, LABEL_VALIDATING)

_CHANGES_REQUESTED = "Needs another pass.\n\nVERDICT: CHANGES_REQUESTED"

_APPROVED = "approved"

_REPORT_REREAD = "reread_report_location"

# The event a relabel emits, and the stage it names.
_STAGE_ENTER = "stage_enter"

_STAGE = "stage"

# How a handed request's launch is left ahead of a tick the issue will not
# read again in: owed, its pinned anchor cleared, or started.
_LEFT_FOR_AN_UNREAD_ISSUE = (
    ("owed, its anchor cleared", _resumed.clears_the_anchor),
    ("started", partial(_resumed.starts, how=_resumed.STARTED)),
)

# The readings of a waiting verdict's subject that stop answering as a tick
# resolves it: the thread its report is re-read from, and the issue fetched
# afresh.
_UNREAD_SUBJECTS = (
    ("its report's thread", lambda case: patch.object(case.github.report_failures, "unreadable", {_world.PR})),
    ("the issue", lambda case: patch.object(case.github, "get_issue", side_effect=RuntimeError("issue unanswered"))),
)

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

# The park another road records over a report it cannot deliver.
_UNDELIVERABLE = "report_undeliverable"

# The reviewer-side park a reply answers with a fresh round.
_UNRECORDED = "reviewer_unrecorded"

# The park a grant of rounds answers.
_REVIEW_CAP = "review_cap"

# What another road posts while a reply's round is held that parks nothing.
_STATUS_LINE = "a status line"

# The park a reply clears into a fresh round, what another road does while
# that round is held -- nothing, a status line of its own, or a park behind a
# notice of its own -- and the park the tick settling the round leaves, as
# `parked` reads it: the reply's clear kept, or that road's park kept as it
# wrote it -- over a report it cannot deliver, or again for the very reason
# the reply answered, which only its notice shows, so the tick writes nothing
# over it. A status line naming nobody is no park, beside a grant of rounds as
# much as beside a `/orchestrator continue`.
_SETTLED_OVER = (
    (_UNRECORDED, None, (None, False)),
    (_UNRECORDED, _STATUS_LINE, (None, False)),
    (_UNRECORDED, _UNDELIVERABLE, (_UNDELIVERABLE, True)),
    (_UNRECORDED, _UNRECORDED, (_UNRECORDED, True)),
    (_REVIEW_CAP, _STATUS_LINE, (None, False)),
)

# The round a verdict another road records in place of the waiting one is of.
_REPLACEMENT_ROUND = 1

# The run count another road charges up to, and the allowance it grants.
_CHARGED = 9

_GRANTED = 100

# A fresh reviewer that returns no verdict, so its round parks and nothing else runs.
_UNDECIDED_REVIEWER = _agent(session_id="fresh-reviewer", last_message="Looked it over.")

# What a resume onto a session whose transcript its backend lost returns.
_LOST_SESSION = _agent(
    session_id="", last_message="", stderr=f"Error: No conversation found with session ID: {_world.DEV_SESSION}\n",
)

# The verdict a handed request left waiting, as `waiting` reads it.
_HANDED_REQUEST = "changes_requested"




def _fresh_round() -> dict:
    """How a tick runs whose fresh reviewer requests changes, answered by a developer who pushes."""
    reviewer = _agent(session_id="fresh-reviewer", last_message=_CHANGES_REQUESTED)
    return {**_disposed.fixing(), _world.RUN_AGENT: [reviewer, _handoff.developer()]}


def _settles_behind_a_held_approval(case) -> None:
    """A later report another road settles behind an approval left waiting on its evidence."""
    case.holds_an_approval()
    _read.settles_a_later_report(case)


def _relabelled_back_after_a_start(case) -> None:
    """A handed request whose developer was started, the issue relabelled to `workflow:validating` from outside."""
    case.hands_over_unstarted()
    _resumed.starts(case, _resumed.STARTED)
    case.github.set_workflow_label(case.issue, LABEL_VALIDATING)


def _allows(case, *, granted: bool) -> None:
    """Hold `case`'s issue to the runs it has spent, or -- `granted` -- lift that and its park, as a grant does."""
    state = case.github.read_pinned_state(case.issue)
    state.set(ALLOWANCE, 0 if granted else state.get(_world.AGENT_RUNS_USED))
    if granted:
        state.set(_AWAITING_HUMAN, False)
        state.set(_PARK_REASON, None)
    case.github.write_pinned_state(case.issue, state)


class ValidatingResumeTest(_resumed.ResumedVerdictWorld, unittest.TestCase):
    """A waiting verdict is finished ahead of the round cap and the spawn, or dropped for a fresh reviewer."""

    def test_a_held_approval_needs_no_reviewer(self) -> None:
        # The approval waits on its evidence's lost response; the next tick's
        # reconciliation finds the artifact, and the handler finishes the
        # approval even with every round spent, running nobody and spending
        # nothing.
        self.holds_an_approval()
        spent = _read.spent(self)

        with patch.object(config, "MAX_REVIEW_ROUNDS", 0):
            ran = self.validates(**_disposed.ON_THE_HEAD)

        self.assertEqual(
            (
                ran.call_count,
                _read.spent(self),
                self.github.label_history,
                self.waiting(),
            ),
            (0, spent, [(_world.ISSUE, LABEL_DOCUMENTING)], None),
        )

    def test_a_waiting_request_reaches_one_developer(self) -> None:
        # Its feedback post refused, or its relabel after the handed write:
        # the handler posts the feedback only where none was anchored, and
        # launches and charges the one developer -- never a reviewer -- with
        # the reviewer's usage still folded once.
        for name, stops, relabels in (
            ("its feedback post refused", _resumed.refuses_the_post, [FIXING, VALIDATING]),
            ("its relabel refused", _resumed.refuses_the_relabel, [FIXING, VALIDATING]),
        ):
            with self.subTest(name):
                self.setUp()
                stops(self)
                charged = self.pinned()[_world.AGENT_RUNS_USED]

                ran = self.validates(**_disposed.fixing())

                self.assertEqual(
                    (
                        ran.call_count,
                        ran.call_args.kwargs.get("resume_session_id"),
                        self.pinned()[_world.AGENT_RUNS_USED] - charged,
                        self.pinned()[TOKENS],
                        len(self.feedback_posts()),
                        self.github.label_history,
                        self.waiting(),
                    ),
                    (1, _world.DEV_SESSION, 1, _world.REVIEWER_TOKENS, 1, relabels, None),
                )

    def test_a_stale_verdict_goes_to_a_fresh_reviewer(self) -> None:
        # A later report settled behind the waiting approval, or a request
        # whose developer was started and whose issue was relabelled back:
        # the verdict is dropped for good, running nobody, and the next tick
        # hands a fresh reviewer the report the pull request carries. The drop
        # reads GitHub alone, so a checkout that will not restore holds
        # nothing up.
        for name, leaves, report in (
            ("a later report", _settles_behind_a_held_approval, _read.LATER_REPORT),
            ("a started developer relabelled back", _relabelled_back_after_a_start, DELIVERED_REPORT),
        ):
            with self.subTest(name):
                self.setUp()
                leaves(self)
                dropped = (
                    self.validates(**_disposed.fixing(), **_resumed.REFUSED_CHECKOUT).call_count,
                    self.waiting(),
                )

                ran = self.validates(**_fresh_round())

                self.assertEqual(
                    (dropped, report in ran.call_args_list[0].args[1], self.waiting()),
                    ((0, None), True, None),
                )

    def test_an_unread_subject_holds_the_verdict(self) -> None:
        # An approval held on its evidence, or a request whose developer was
        # started and whose issue was relabelled back, over a report thread
        # or an issue nobody could read: whether the verdict would be finished
        # or dropped, it waits with nothing run, relabelled, posted, or
        # written, for a later tick to read its subject.
        for (name, leaves), reading in product(
            (
                ("a held approval", _resumed.ResumedVerdictWorld.holds_an_approval),
                ("a started developer relabelled back", _relabelled_back_after_a_start),
            ),
            dict(_UNREAD_SUBJECTS),
        ):
            with self.subTest(name, unread=reading):
                self.setUp()
                leaves(self)
                before = (self.pinned(), tuple(self.github.label_history))

                with dict(_UNREAD_SUBJECTS)[reading](self):
                    ran = self.validates(**_disposed.ON_THE_HEAD)

                self.assertEqual(
                    (ran.call_count, (self.pinned(), tuple(self.github.label_history))),
                    (0, before),
                )

    def test_an_unread_subject_writes_no_anchor(self) -> None:
        # A handed request whose relabel never landed, its pinned anchor
        # cleared since, over a report nobody could read: the anchor is written
        # back only once the subject is established, so nothing is relabelled,
        # launched, or written.
        _resumed.refuses_the_relabel(self)
        _resumed.clears_the_anchor(self)
        _world.stops_answering(self)
        before = self.pinned()

        ran = self.validates(**_disposed.fixing())

        self.assertEqual(
            (ran.call_count, self.pinned(), self.github.label_history),
            (0, before, []),
        )

    def test_an_unread_thread_holds_the_verdict(self) -> None:
        # The issue thread the requirements are read off will not read: the
        # tick holds the waiting approval rather than failing, running nobody
        # and finishing nothing, for a later tick to resolve again.
        self.holds_an_approval()

        with patch.object(self.github, "comments_after", side_effect=RuntimeError("thread unanswered")):
            ran = self.validates(**_disposed.ON_THE_HEAD)

        self.assertEqual(
            (ran.call_count, self.waiting(), self.github.label_history),
            (0, _APPROVED, []),
        )

    def test_a_bought_round_outlives_the_report_hold(self) -> None:
        # A reply to a reviewer-side park buys a fresh round, and the report
        # hold stops that round for a tick: the write keeping the cleared park
        # drops the verdict the park outlived too, so the next tick runs the
        # reviewer the reply bought rather than finishing the old approval.
        self.holds_an_approval()
        parks = self.github.read_pinned_state(self.issue)
        parks.set(_AWAITING_HUMAN, True)
        parks.set(_PARK_REASON, _UNRECORDED)
        self.github.write_pinned_state(self.issue, parks)
        self.asks_to_continue()
        with patch.object(_report_hold, "_report_holds_the_review", return_value=True):
            held = (self.validates(**_disposed.ON_THE_HEAD).call_count, self.parked())

        reviewed = self.validates(**{**_disposed.ON_THE_HEAD, _world.RUN_AGENT: [_UNDECIDED_REVIEWER]})

        self.assertEqual(
            (held, reviewed.call_count, self.github.label_history),
            ((0, ((None, False), None, [])), 1, []),
        )


class FixingResumeTest(_resumed.ResumedVerdictWorld, unittest.TestCase):
    """A handed request's owed developer is launched ahead of the scan, once, and only while nothing shows a start."""

    def test_an_owed_launch_reaches_one_developer(self) -> None:
        # The relabel landed and the developer's start did not: the charge
        # it reserved is honored, not taken again, and where the pinned
        # anchor was cleared meanwhile it is written back from the record
        # ahead of the launch rather than holding the request for good. The
        # issue is on `workflow:fixing` already, so no label is written ahead
        # of the launch: the one label written, and the one stage entered, is
        # the hand-back to review.
        for name, meanwhile in (("its charge reserved", None), ("its anchor cleared", _resumed.clears_the_anchor)):
            with self.subTest(name):
                self.setUp()
                self.hands_over_unstarted()
                if meanwhile is not None:
                    meanwhile(self)
                before = (
                    self.pinned()[_world.RETURNED_VERDICT][_disposed.HANDED],
                    len(self.github.label_history),
                    len(self.github.recorded_events),
                )

                ran = self.fixes(**_disposed.fixing())

                self.assertEqual(
                    (
                        ran.call_count,
                        self.pinned()[_world.AGENT_RUNS_USED] - before[0],
                        len(self.feedback_posts()),
                        self.github.label_history[before[1]:],
                        [
                            event[_STAGE]
                            for event in self.github.recorded_events[before[2]:]
                            if event["event"] == _STAGE_ENTER
                        ],
                        self.waiting(),
                    ),
                    (1, 1, 1, [VALIDATING], [STAGE_VALIDATING], None),
                )

    def test_a_refused_launch_waits_out_its_park(self) -> None:
        # The relabel never landed and the run allowance is spent: the launch
        # the recovery makes is refused, and parked by the run circuit with the
        # request kept. While that park stands a fixing tick leaves it to the
        # park's own dispatch; once runs are granted, the one developer the
        # request owes is launched and charged once.
        _resumed.refuses_the_relabel(self)
        _allows(self, granted=False)
        handed = self.pinned()[_world.RETURNED_VERDICT][_disposed.HANDED]
        refused = self.validates(**_disposed.fixing()).call_count
        parked = (
            self.fixes(**_disposed.fixing()).call_count,
            self.parked(),
            tuple(self.github.label_history),
        )
        _allows(self, granted=True)

        ran = self.fixes(**_disposed.fixing())

        self.assertEqual(
            (
                refused,
                parked,
                ran.call_count,
                self.pinned()[_world.AGENT_RUNS_USED] - handed,
                self.waiting(),
            ),
            (0, (0, _RUN_LIMIT_PARK, (FIXING,)), 1, 1, None),
        )

    def test_a_lost_session_retries_the_owed_launch(self) -> None:
        # The owed developer is pinned to a Claude session whose transcript
        # its backend lost, so its launch retries once as a fresh spawn: that
        # continuation is the launch's own -- its start is already in hand --
        # and is charged and made, not refused as a second developer.
        state = self.github.read_pinned_state(self.issue)
        state.set("dev_agent", BACKEND_CLAUDE)
        state.set("dev_session_id", _world.DEV_SESSION)
        self.github.write_pinned_state(self.issue, state)
        self.hands_over_unstarted()
        handed = self.pinned()[_world.RETURNED_VERDICT][_disposed.HANDED]
        retried = {**_disposed.fixing(), _world.RUN_AGENT: [_LOST_SESSION, _handoff.developer()]}

        ran = self.fixes(**retried)

        self.assertEqual(
            (
                ran.call_count,
                ran.call_args.kwargs.get("resume_session_id"),
                self.pinned()[_world.AGENT_RUNS_USED] - handed,
                self.waiting(),
            ),
            (2, None, 2, None),
        )

    def test_an_unread_issue_holds_the_request(self) -> None:
        # The issue will not read again as the subject is resolved: an owed
        # launch whose anchor was cleared writes no anchor back, and a launch
        # that may have run posts no park notice -- nothing is launched,
        # posted, or written, and a later tick asks again.
        for name, leaves in _LEFT_FOR_AN_UNREAD_ISSUE:
            with self.subTest(name):
                self.setUp()
                self.hands_over_unstarted()
                leaves(self)
                before = (self.pinned(), len(self.github.posted_comments))

                with patch.object(self.github, "get_issue", side_effect=RuntimeError("issue unanswered")):
                    ran = self.fixes(**_disposed.fixing())

                self.assertEqual(
                    (ran.call_count, (self.pinned(), len(self.github.posted_comments))),
                    (0, before),
                )

    def test_a_start_behind_its_checks_holds_it(self) -> None:
        # Another road charges and starts a run of the owed launch's very
        # identity, recording no owed count, right before the relabel -- which
        # only a `workflow:validating` tick makes, its relabel never having
        # landed -- or right before the run circuit reads the ledger it
        # charges from: nobody is launched, only that road's run is counted,
        # and the request waits.
        for request, leaves, tick in (
            ("set_workflow_label", _resumed.refuses_the_relabel, "validates"),
            ("_durable_state", _resumed.ResumedVerdictWorld.hands_over_unstarted, "fixes"),
        ):
            with self.subTest(request):
                self.setUp()
                leaves(self)
                charged = self.pinned()[_world.AGENT_RUNS_USED]

                with self.charged_behind(request):
                    ran = getattr(self, tick)(**_disposed.fixing())

                self.assertEqual(
                    (ran.call_count, self.pinned()[_world.AGENT_RUNS_USED] - charged, self.waiting()),
                    (0, 1, _HANDED_REQUEST),
                )

    def test_a_stale_request_needs_no_checkout(self) -> None:
        # A handed request whose developer is still owed -- its relabel
        # refused, or its start -- and whose pull request was pushed to since,
        # over a checkout gone from this host that will not restore: the
        # request and its anchor are dropped over GitHub's readings alone,
        # nobody launched or relabelled, and nothing raised.
        for leaves, tick in (
            (_resumed.refuses_the_relabel, "validates"),
            (_resumed.ResumedVerdictWorld.hands_over_unstarted, "fixes"),
        ):
            with self.subTest(tick):
                self.setUp()
                leaves(self)
                _world.pushes(self)
                labelled = len(self.github.label_history)

                ran = getattr(self, tick)(**_disposed.fixing(), **_resumed.REFUSED_CHECKOUT)

                self.assertEqual(
                    (
                        ran.call_count,
                        self.waiting(),
                        self.pinned().get(_handoff.ANCHOR),
                        self.github.label_history[labelled:],
                    ),
                    (0, None, None, []),
                )

    def test_a_refused_restore_keeps_the_launch_owed(self) -> None:
        # The relabel never landed, and the checkout the developer resumes in
        # is gone and will not restore: the recovery relabels, then stops on
        # the restore with nothing charged, folded, or spent and the request
        # still waiting, and the next fixing tick launches and charges the one
        # developer it owes, its feedback never posted again.
        _resumed.refuses_the_relabel(self)
        spent = _read.spent(self)
        with self.assertRaises(RuntimeError):
            self.validates(**_disposed.fixing(), **_resumed.REFUSED_CHECKOUT)
        stopped = (_read.spent(self) == spent, self.waiting())
        relabelled = list(self.github.label_history)

        ran = self.fixes(**_disposed.fixing())

        self.assertEqual(
            (
                stopped,
                relabelled,
                ran.call_count,
                _read.spent(self)[0] - spent[0],
                len(self.feedback_posts()),
                self.waiting(),
            ),
            ((True, _HANDED_REQUEST), [FIXING], 1, 1, 1, None),
        )



class ReplacedVerdictTest(_resumed.ResumedVerdictWorld, unittest.TestCase):
    """A verdict recovery drops is dropped only while the comment still carries it, never over one put in its place."""

    def test_a_replacement_survives_the_drop(self) -> None:
        # The waiting approval's subject moved -- a later report settled --
        # and another road records a newer verdict while the tick re-reads
        # the report: recovery drops only the verdict it held, which the
        # comment no longer carries, so the newer one stands and nothing runs
        # over it this tick.
        _read.seeds_a_verdict(self, None)
        _read.settles_a_later_report(self)
        road = _world.AnotherRoadBehind(self, _REPORT_REREAD, bool, self._replaces_the_verdict)

        with patch.object(self.github, _REPORT_REREAD, road):
            ran = self.validates(**_fresh_round())

        self.assertEqual(
            (ran.call_count, self.pinned()[_world.RETURNED_VERDICT]["round"]),
            (0, _REPLACEMENT_ROUND),
        )

    def test_a_held_round_keeps_what_moved(self) -> None:
        # A reply to a reviewer-side park, or a grant of rounds on the review
        # cap, buys a fresh round, the report hold stops that round for a
        # tick, and another road records a newer verdict, charges a run, and
        # grants an allowance during the hold: the one write settling the tick
        # keeps the cleared park and carries all three, dropping the verdict
        # the park outlived only where the comment still carries it. Where
        # that road parks the issue anew as well, behind a notice of its own
        # -- over a report it cannot deliver, or again for the reason the reply
        # answered -- its park stands as it wrote it, not cleared by the reply
        # to the park before it; a status line it posts is no park, and leaves
        # the reply's clear to land rather than the old park to wait forever.
        for answered, meanwhile, park in _SETTLED_OVER:
            with self.subTest(answered=answered, meanwhile=meanwhile):
                self.setUp()
                self._parks_beside_a_verdict(answered)

                with patch.object(
                    _report_hold,
                    "_report_holds_the_review",
                    side_effect=partial(self._holds_behind_what_moves, meanwhile),
                ):
                    ran = self.validates(**_disposed.ON_THE_HEAD)

                pinned = self.pinned()
                self.assertEqual(
                    (
                        ran.call_count,
                        self.parked()[0],
                        pinned[_world.RETURNED_VERDICT]["round"],
                        pinned[_world.AGENT_RUNS_USED],
                        pinned[ALLOWANCE],
                    ),
                    (0, park, _REPLACEMENT_ROUND, _CHARGED, _GRANTED),
                )

    def test_a_replacement_after_the_drop_is_kept(self) -> None:
        # The reply's round is not run in the tick that drops the verdict the
        # park outlived: another road recording a newer verdict right behind
        # that drop is read by the next tick, which finishes it -- parking the
        # approval, which relies on no evidence -- with no second reviewer.
        self._parks_beside_a_verdict()
        dropped = _world.AnotherRoadBehind(
            self,
            "write_pinned_state",
            lambda written: written.get(_world.RETURNED_VERDICT) is None,
            self._replaces_the_verdict,
        )
        with patch.object(self.github, "write_pinned_state", dropped):
            settled = self.validates(**_disposed.ON_THE_HEAD).call_count

        ran = self.validates(**{**_disposed.ON_THE_HEAD, _world.RUN_AGENT: [_UNDECIDED_REVIEWER]})

        self.assertEqual(
            (settled, ran.call_count, self.parked()[0]),
            (0, 0, ("reviewer_unverified", True)),
        )

    def test_a_replacement_behind_an_anchor_is_left(self) -> None:
        # A handed request whose pinned anchor was cleared -- its relabel
        # never landed, on `workflow:validating`, or its launch still owed, on
        # `workflow:fixing` -- and another road records a request never handed
        # in its place while the tick re-reads the report: the comment read
        # ahead of the anchor's write-back shows the verdict moved, so the tick
        # ends there with nothing posted, relabelled, launched, or written,
        # and the replacement waits for a later tick.
        for tick, hands_over in (
            ("validates", _resumed.refuses_the_relabel),
            ("fixes", _resumed.ResumedVerdictWorld.hands_over_unstarted),
        ):
            with self.subTest(tick):
                self.setUp()
                hands_over(self)
                _resumed.clears_the_anchor(self)
                posted = (len(self.feedback_posts()), tuple(self.github.label_history))
                road = _world.AnotherRoadBehind(self, _REPORT_REREAD, bool, self._replaces_the_verdict)

                with patch.object(self.github, _REPORT_REREAD, road):
                    ran = getattr(self, tick)(**_disposed.fixing())

                self.assertEqual(
                    (
                        ran.call_count,
                        (len(self.feedback_posts()), tuple(self.github.label_history)),
                        self.pinned(),
                    ),
                    (0, posted, self.replaced),
                )

    def _parks_beside_a_verdict(self, reason: str = _UNRECORDED) -> None:
        """An approval relying on no evidence left waiting beside a park for `reason` a reply answers.

        `/orchestrator continue` answers a `reviewer_unrecorded` park, and a
        grant of one round the review cap, reached.
        """
        _read.seeds_a_verdict(self, None)
        self.waited = _verdicts.read_returned_verdict(self.github.read_pinned_state(self.issue))
        parks = self.github.read_pinned_state(self.issue)
        parks.set(_AWAITING_HUMAN, True)
        parks.set(_PARK_REASON, reason)
        if reason == _REVIEW_CAP:
            parks.set("review_round", config.MAX_REVIEW_ROUNDS)
        self.github.write_pinned_state(self.issue, parks)
        self.asks_to_continue(_GRANT if reason == _REVIEW_CAP else CONTINUE)

    def _holds_behind_what_moves(self, meanwhile: str | None, *_asked) -> bool:
        """The report hold stopping the round, behind which another road records a verdict, a run, and a grant.

        And, where `meanwhile` says so, posts a status line of its own, or
        parks for the reason it names behind a notice naming the human a park
        waits on, as every park's notice does.
        """
        self._replaces_the_verdict(self)
        state = self.github.read_pinned_state(self.issue)
        state.set(_world.AGENT_RUNS_USED, _CHARGED)
        state.set(ALLOWANCE, _GRANTED)
        if meanwhile == _STATUS_LINE:
            _comments._post_issue_comment(self.github, self.issue, state, ":information_source: still here.")
        elif meanwhile is not None:
            _comments._post_issue_comment(
                self.github, self.issue, state, f"{config.HITL_MENTIONS} parked again: {meanwhile}.",
            )
            state.set(_AWAITING_HUMAN, True)
            state.set(_PARK_REASON, meanwhile)
        self.github.write_pinned_state(self.issue, state)
        return True

    def _replaces_the_verdict(self, case) -> None:
        """Another road's newer verdict, of a later round and never handed, in place of the one `case` had waiting."""
        state = case.github.read_pinned_state(case.issue)
        waited = getattr(case, "waited", None) or _verdicts.read_returned_verdict(state)
        replacement = replace(waited, round_n=_REPLACEMENT_ROUND, handed=None, anchor=None)
        state.set(_world.RETURNED_VERDICT, replacement.recorded())
        case.github.write_pinned_state(case.issue, state)
        # The comment as that write left it, for a case to see nothing was written over it.
        case.replaced = case.pinned()

if __name__ == "__main__":
    unittest.main()
