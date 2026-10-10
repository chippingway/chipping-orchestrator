# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a head this orchestrator rewrote is owed, obtained with no human.

A validating tick over a pull request a rebase moved asks the developer for a
fresh report of the head the rebase published before any reviewer runs, and
publishes and settles it through the same records every developer report
passes through. The next tick finds the debt paid by that report and hands it
to the reviewer. A later rebase is refreshed at its own head.

A run that brings no fresh report -- a question, a silent exit, a timeout, a
verification of the report the rebase left behind, a commit, loose work, a
report quoting a receipt -- parks once and asks again of nobody until a reply
comes, and the report that reply brings is published once, pays the debt, and
is reviewed, with nothing a later tick repeats. A receipt nobody can read, or
loose work in the checkout as it stands, parks before any run. A world that
moves while the agent is out records nothing: a head somebody pushed is left to
the reviewer road's refusal, and an edit to the drift resume that answers it --
as is an edit the drift check stood down for, which nothing pays or asks for
until it is answered. An interrupted publication finishes on a later tick with
no second run and no second comment.

A claim nobody can read, or one saying nothing about the head standing, earns
no refresh: the reviewer road parks for the stale report as it always did, and
the report the reply brings pays the debt all the same.

A settled report of the approved commit an approval squash collapsed, which the
rebase of that squash left behind, is refreshed the same way once the squash's
carry proves the lineage and the report re-reads intact -- and is left as it
was written. A report moved out of reach, requirements past it, a repointed
pull request or branch, a debt on another branch, a carry onto another head or
none at all, and a head somebody pushed are refused exactly as before, with
nobody run, recorded, or charged, and a tree or location nobody could read
holds with nobody run. Walked whole -- the approval, its squash, the docs pass,
`in_review`, and a later automatic base rebase -- the rebased head is reported
once before any reviewer sees it, through a push whose answer was lost, an
interrupted publication, and a second base advance alike; one that comes while
a report is still in flight waits for that report to settle about the head it
was written for.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from types import MappingProxyType

from orchestrator import config
from orchestrator.agents.models import ToolLifecycle
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.engine import report_delivery as _report_delivery
from orchestrator.workflow.stages.validating import review_report as _review_report
from tests.workflow import (
    drift_reports as _drift_world,
    fix_reports as _fix_world,
    published_reports as _published_reports,
    report_guidance as _report_guidance,
    report_refusals as _refusals,
    reviewed_reports as _reviewed,
)
from tests.workflow.fixtures import _agent, _open_pr_for
from tests.workflow.stages.validating import (
    report_refresh_crashes as _crashes,
    report_refresh_test_support as _support,
    review_verdict_readings as _read,
    squash_rebase_journey_support as _journey,
)

RUN_AGENT = _support.RUN_AGENT

REWRITE = _support.REWRITE

REWRITTEN_HEAD = _support.REWRITTEN_HEAD

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

UNDELIVERABLE = _report_delivery.UNDELIVERABLE_REPORT

OWES_A_ROUND = "validating_reviewer_owes_a_round"

PUSH = "_push_branch"

# The records `records()` reads a report's progress off.
DELIVERED = "delivered"

PENDING = "pending"

# The notices a refresh that brought no fresh report parks with.
TIMED_OUT = "timed out before it wrote one"

VERIFIED_INSTEAD = "verified a report already on the pull request instead"

LEFT_THE_HEAD = "did not leave the checkout as it found it"

# Every run that brings no fresh report and the park it earns, beside the
# words its notice carries: the agent failures park as an agent failure always
# parks, and a timeout under the report it did not write.
FAILED_RUNS = (
    ("a question", "Should the rebase be undone first?", None, "Should the rebase be undone first?"),
    ("a silent exit", "", "agent_silent", "agent produced no output"),
    (
        "a timeout",
        _agent(session_id=_drift_world.DEV_SESSION, timed_out=True),
        UNDELIVERABLE,
        TIMED_OUT,
    ),
    # A report block from a run that ended with a command still running is no
    # report: nothing it claims was verified.
    (
        "an unfinished command",
        _agent(
            session_id=_drift_world.DEV_SESSION,
            last_message=_support.fresh(),
            unfinished_steps=(ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE"),),
        ),
        "agent_execution_failed",
        "agent command execution failed",
    ),
)

_CLEAN = _WorktreeStatus(readable=True, paths=())

# A run that leaves the checkout off the rebased head, beside what it leaves
# recorded as work nothing describes.
LEFT_CHECKOUTS = (
    ("a commit", {_drift_world.HEAD_SHAS: (REWRITTEN_HEAD, _drift_world.FIXED_HEAD)}, True),
    ("loose work", {"tree_states": (_CLEAN, _WorktreeStatus(readable=True, paths=("notes.txt",)))}, None),
)

# Every world a refresh refuses before any agent runs -- what the pinned comment
# carries, what the checkout reads as, and what the notice names: a receipt
# group this build cannot read, and loose work in the existing checkout of a
# branch with nothing past the base, which a recreation would have reclaimed
# files and all. The receipt is repaired and the tree cleaned before the reply.
UNFROZEN = (
    ("a damaged receipt", {"implementing_published_lease": "not-a-commit"}, {}, "`implementing_published_lease`"),
    (
        "loose work in the checkout",
        {},
        {"has_new_commits": False, "tree_states": (_WorktreeStatus(readable=True, paths=("notes.txt",)),)},
        "uncommitted work",
    ),
)

REPAIRED = MappingProxyType({"implementing_published_lease": _drift_world.PUBLISHED_HEAD})

# The two ways the drift resume can answer an edit that landed behind a settled
# refresh, as the runs that follow it: a report of the edited requirements, or
# an `ACK:` after which the next refresh asks for that report.
ANSWERED_EDITS = (
    ("a report", (_support.fresh(_drift_world.LATER_REPORT_TEXT),)),
    (
        "an acknowledgement",
        ("ACK: the rebased branch already covers it", _support.fresh(_drift_world.LATER_REPORT_TEXT)),
    ),
)

# Every window the publication behind a refresh can be interrupted in.
INTERRUPTIONS = (
    ("a refused post", _crashes.refusing_the_post),
    ("a lost response", _crashes.losing_the_response),
    ("a crash before the binding", _crashes.dying_before_the_binding),
    ("a crash on the settlement", _crashes.dying_on_the_settlement),
)

UNREADABLE = MappingProxyType({"pr": _support.PR})

# Every debt that does not explain the head the pull request stands on, beside
# that head: none recorded, one paid, one nobody can read, and one about
# another head, pull request, branch, or report than the ones standing.
UNEXPLAINED = (
    ("legacy", _support.LEGACY, REWRITTEN_HEAD),
    ("paid", None, REWRITTEN_HEAD),
    ("unreadable", dict(UNREADABLE), REWRITTEN_HEAD),
    ("not an object", [], REWRITTEN_HEAD),
    ("one head", replace(REWRITE, rewritten_head=_drift_world.PUBLISHED_HEAD).recorded(), REWRITTEN_HEAD),
    ("foreign head", REWRITE.recorded(), _support.FOREIGN_HEAD),
    ("another pull request", replace(REWRITE, pr_number=_support.PR + 1).recorded(), REWRITTEN_HEAD),
    ("another branch", replace(REWRITE, branch="elsewhere").recorded(), REWRITTEN_HEAD),
    ("another report", replace(REWRITE, previous_head=_drift_world.STRANDED_HEAD).recorded(), REWRITTEN_HEAD),
)


# The refusal the reviewer road parks a report of the head before a rebase
# with, beside the head somebody pushed over the rebase.
_MOVED_COMMIT = _review_report._MOVED_COMMIT.format(
    reported=_drift_world.PUBLISHED_HEAD, head=REWRITTEN_HEAD,
)

# A hand edit pinning another branch of this orchestrator's than the one the
# rebase rewrote, which the resume would check out and bind a report to.
REPOINTED_BRANCH = MappingProxyType({"branch": "orchestrator/elsewhere"})

# What `unrecorded` reads where the reviewer road parked and no refresh ran:
# no delivery, no transaction, and no comment, beside the park.
PARKED_UNRECORDED = (*_support.NOTHING[:-1], True)

# Every way the settled report of the approved commit an approval squash
# collapsed falls outside what the squash's proof may refresh -- what the
# squashed world is seeded with, what then moves in it, and what the reviewer
# road parks for, exactly as it would with no squash behind the report: the
# report removed, edited, rewritten under another author, or out of step with
# its handoff; requirements moved past it; a repointed pull request or branch;
# a debt on another branch; no carry, or one onto another head; and a head
# somebody pushed over the rebase.
SQUASH_REFUSALS = (
    (
        "the report removed", {},
        lambda case: case.pull_request.issue_comments.remove(case.approved_comment()),
        _review_report._MISSING,
    ),
    (
        "the report edited", {},
        lambda case: case.rewrites_the_approved_report(text=_reviewed.EDITED_REPORT),
        _review_report._EDITED,
    ),
    (
        "the report untrusted", {},
        lambda case: case.rewrites_the_approved_report(login="mallory"),
        _review_report._EDITED,
    ),
    (
        "the report out of step with its handoff", {},
        lambda case: _reviewed.restate(case, developer_report_handoff={
            **case.pinned()["developer_report_handoff"], "revision": 2,
        }),
        _review_report._STALE,
    ),
    ("requirements moved past the report", {}, _support._SquashedReports.acknowledges_an_edit, _MOVED_COMMIT),
    (
        "a repointed pull request", {},
        lambda case: _reviewed.restate(case, pr_number=_open_pr_for(
            case.github, issue_number=_support.ISSUE, pr_number=_support.PR + 1,
        ).number),
        _review_report._MOVED.format(settled=_support.PR),
    ),
    ("a repointed branch", {}, lambda case: _reviewed.restate(case, **REPOINTED_BRANCH), _MOVED_COMMIT),
    (
        "a debt on another branch",
        {"claim": replace(_support.SQUASHED_REWRITE, branch="elsewhere").recorded()},
        None,
        _MOVED_COMMIT,
    ),
    ("no carry", {"carry": None}, None, _MOVED_COMMIT),
    (
        "a carry onto another head",
        {"carry": lambda state: _support.squash_carry(state).retargeted(_support.FOREIGN_HEAD)},
        None,
        _MOVED_COMMIT,
    ),
    (
        "a head pushed over the rebase", {},
        lambda case: setattr(case.pull_request.head, "sha", _support.FOREIGN_HEAD),
        _review_report._MOVED_COMMIT.format(
            reported=_drift_world.PUBLISHED_HEAD, head=_support.FOREIGN_HEAD,
        ),
    ),
)

# Every reading the squash's road cannot take, as the tick's options and what
# moves before it: the trees the proof reads, and the approved report's
# location, which is re-read before anything is asked.
SQUASH_UNREAD = (
    ("the squash's trees", {"checkout_tree": ""}, _journey.uninterrupted),
    ("the approved report", {}, lambda case: case.github.report_failures.unreadable.add(_support.PR)),
)

# What the dispatched ticks spawn from a rebase of the squash on, once each:
# the report refresh, the reviewer handed its report, and the docs pass behind
# that approval.
REFRESHED_AND_REVIEWED = (_journey.REFRESHER, _journey.REVIEWER, _journey.DOCUMENTER)

# Every place the journey can be cut short once the rebase has published: the
# push's own answer lost, which the next base refresh's recovery finishes, and
# every window the refresh's publication opens, which the next dispatch's
# reconciliation finishes.
JOURNEY_INTERRUPTIONS = (
    ("the rebase push's answer lost", _journey.LandsThenDies, _journey.uninterrupted),
    *((name, None, interrupted) for name, interrupted in INTERRUPTIONS),
)

# The record of the report the pull request carries, and the member naming the
# commit it is about, as the pinned comment spells them.
CURRENT_REPORT = "developer_report_current"

REPORTED_COMMIT = "sha"

# How a refresh of the second advance names the report standing, where that
# is a report of the first rebased head.
_REBASED_REPLACED = f"describes `{_journey.REBASED}`, the head"

# Every way the base can move again before the first rebased head's debt is
# paid, as what is done with that head before the second advance, the runs the
# journey spawns from the first rebase on, and how the last refresh names the
# report standing. Before any report of the first head, the debt carried onto
# the second still rests on the squash; once a report of the first head
# settled, that report paid it; and while that report is still in flight, the
# advance waits until it settles and its reviewer is handed it on its own head.
SECOND_ADVANCES = (
    (
        "before any report of the first head",
        lambda case: None,
        REFRESHED_AND_REVIEWED,
        f"describes `{_journey.HEAD}`, the approved commit",
    ),
    (
        "after a report of the first head",
        lambda case: case.dispatched(_journey.refresh()),
        (_journey.REFRESHER, *REFRESHED_AND_REVIEWED),
        _REBASED_REPLACED,
    ),
    (
        "a report of the first head in flight behind a refused post",
        lambda case: case.settles_over_an_advance(_crashes.refusing_the_post),
        REFRESHED_AND_REVIEWED * 2,
        _REBASED_REPLACED,
    ),
    (
        "a report of the first head in flight behind a lost response",
        lambda case: case.settles_over_an_advance(_crashes.losing_the_response),
        REFRESHED_AND_REVIEWED * 2,
        _REBASED_REPLACED,
    ),
    (
        "a report of the first head in flight behind a crash before the binding",
        lambda case: case.settles_over_an_advance(_crashes.dying_before_the_binding),
        REFRESHED_AND_REVIEWED * 2,
        _REBASED_REPLACED,
    ),
    (
        "a report of the first head in flight behind a crash on the settlement",
        lambda case: case.settles_over_an_advance(_crashes.dying_on_the_settlement),
        REFRESHED_AND_REVIEWED * 2,
        _REBASED_REPLACED,
    ),
)


class ReportRefreshTest(unittest.TestCase, _support._RefreshedReports):
    """A claim owed a fresh report asks the developer for it, and that report pays the claim."""

    def test_a_rebased_head_is_reported_then_reviewed(self) -> None:
        # One developer run is asked for a report of the head the rebase
        # published, and nothing else. Its report is published once and
        # settled about that head under the baseline, with nothing parked.
        # The next tick finds the debt paid and hands the reviewer that
        # report, with no second developer run.
        self.rebased()

        refreshed = self.refreshed(_support.fresh())

        runs = refreshed[RUN_AGENT].call_args_list
        self.assertNotEqual(runs[0].args[0], config.REVIEW_AGENT)
        self.assertEqual(len(runs), 1)
        self.assertIn(f"stands on commit `{REWRITTEN_HEAD}`", _reviewed.prompt(refreshed))
        _report_guidance.assert_teaches_report_scope(self, _reviewed.prompt(refreshed))
        _report_guidance.assert_teaches_receipt_restriction(self, _reviewed.prompt(refreshed))
        settled = self.records()["current"]
        self.assertEqual(
            (
                settled.subject.source_sha,
                settled.subject.requirements_revision,
                len(self.fresh_reports()),
                bool(self.pinned().get(AWAITING_HUMAN)),
                self.claim(),
            ),
            (REWRITTEN_HEAD, self.pinned()["user_content_hash"], 1, False, REWRITE.recorded()),
        )

        self.assert_reviewed_fresh(self.reviewed())
        self.assertEqual(len(self.fresh_reports()), 1)

    def test_a_later_rebase_is_refreshed_at_its_head(self) -> None:
        # A report of the first rebased head settles, and a second rebase
        # lands before any tick drops the debt that report paid. The second
        # rebase's own debt takes its place, and the head it published is the
        # one the developer is asked about and the reviewer is handed.
        self.rebased()
        self.refreshed(_support.fresh())
        second = replace(REWRITE, previous_head=REWRITTEN_HEAD, rewritten_head=_support.SECOND_HEAD)
        self.rebased_again(second)

        refreshed = self.refreshed(_support.fresh(_drift_world.LATER_REPORT_TEXT))

        self.assertIn(f"stands on commit `{_support.SECOND_HEAD}`", _reviewed.prompt(refreshed))
        self.assertEqual(self.claim(), second.recorded())
        self.assert_reviewed_fresh(self.reviewed(), _drift_world.LATER_REPORT_TEXT)

    def test_only_an_intact_report_pays(self) -> None:
        # The report the refresh settled is edited on the thread before the
        # tick that would drop the debt. It pays nothing: the debt stands, and
        # the reviewer road parks for the report as it would with no debt.
        self.rebased()
        self.refreshed(_support.fresh())
        self.report_comment().body = self.report_comment().body.replace(
            _support.FRESH_REPORT, _reviewed.EDITED_REPORT,
        )

        self.assert_refused(self.reviewed(), _review_report._EDITED)
        self.assertEqual(self.claim(), REWRITE.recorded())


class RefreshFailureTest(unittest.TestCase, _support._RefreshedReports):
    """A refresh that brings no fresh report parks once, and a reply's report pays the debt."""

    def test_a_reportless_run_parks_until_a_reply(self) -> None:
        # Nothing is recorded and the debt stands. Ticks with no reply run
        # nobody and say nothing more; the reply resumes the developer, whose
        # report settles and is the one the reviewer is handed.
        for name, reply, reason, notice in FAILED_RUNS:
            with self.subTest(name):
                self.rebased()
                self.refreshed(reply)
                self.assert_parked(reason, notice)

                self.assert_recovered_by_a_reply()

    def test_a_verified_carry_forward_is_refused(self) -> None:
        # The developer points at the report the rebase left behind rather
        # than writing one: that report is about the head before the rebase,
        # so nothing is settled on it and the issue parks for a human.
        self.rebased()
        verified = _fix_world.verified(
            _support.PR, self.opening_report.location.comment_id,
            _published_reports.DELIVERED_REPORT,
        )

        self.refreshed(verified)

        self.assert_parked(UNDELIVERABLE, VERIFIED_INSTEAD)
        self.assertIsNone(self.records()["current"])
        self.assert_recovered_by_a_reply()

    def test_a_quoted_receipt_parks_until_prose(self) -> None:
        # A delimited report well inside the writing budget that quotes a split
        # child's receipt in inline code is refused for that receipt, in the
        # notice and the log alike and with nothing said about size: nothing
        # is recorded, pushed, or posted on the pull request, and the settled
        # report stands. The reply's resume commits nothing and says the same
        # in prose, which is the report published, paid, and reviewed.
        self.rebased()
        standing = (len(self.pull_request.issue_comments), _support.settled_records(self))
        self.assertLess(len(_refusals.QUOTING_REPORT), _refusals.WRITING_BUDGET)

        with self.assertLogs("orchestrator.workflow", "ERROR") as captured:
            self.refreshed(_support.fresh(_refusals.QUOTING_REPORT))[PUSH].assert_not_called()
            logged = "\n".join(captured.output)

        self.assertEqual(
            (len(self.pull_request.issue_comments), _support.settled_records(self)), standing,
        )
        self.assert_parked(UNDELIVERABLE, _refusals.RECEIPT_REFUSAL.notice[0])
        notice = next(
            body for _, body in reversed(self.github.posted_comments)
            if _refusals.RECEIPT_REFUSAL.notice[0] in body
        )
        _refusals.RECEIPT_REFUSAL.assert_said(self, notice, logged)
        self.assert_recovered_by_a_reply(_refusals.PROSE_REPORT)

    def test_a_run_that_moves_the_checkout_parks(self) -> None:
        # A run asked for a report alone that committed or left loose work
        # handed back a report of something the pull request does not carry.
        # A commit is recorded as work no report describes.
        for name, options, unreported in LEFT_CHECKOUTS:
            with self.subTest(name):
                self.rebased()

                self.refreshed(_support.fresh(), **options)

                self.assert_parked(UNDELIVERABLE, LEFT_THE_HEAD)
                self.assertEqual(
                    (self.pinned().get(_report_delivery.UNREPORTED_WORK), self.fresh_reports()),
                    (unreported, []),
                )

    def test_an_unfrozen_world_parks_before_any_run(self) -> None:
        # No developer is asked for a report nothing could settle, and the
        # checkout is read where it stands rather than put back first. The
        # park names what to repair, and a reply after the repair pays.
        for name, pinned, options, notice in UNFROZEN:
            with self.subTest(name):
                self.rebased()
                _reviewed.restate(self, **pinned)

                refused = self.refreshed(**options)

                self.assertEqual(
                    (refused[RUN_AGENT].call_count, refused["_ensure_worktree"].call_count),
                    (0, 0),
                )
                self.assert_parked(UNDELIVERABLE, notice)
                _reviewed.restate(self, **REPAIRED)
                self.assert_recovered_by_a_reply()

    def assert_parked(self, reason, notice: str) -> None:
        """Parked with the report owed and nothing recorded or published; a tick with no reply runs nobody."""
        pinned = self.pinned()
        self.assertEqual(
            (
                pinned.get(AWAITING_HUMAN),
                pinned.get(PARK_REASON),
                pinned.get(_report_delivery.OWED_REPORT),
                self.records()[DELIVERED],
                self.records()[PENDING],
                self.fresh_reports(),
                self.claim(),
            ),
            (True, reason, True, None, None, [], REWRITE.recorded()),
        )
        posted = [body for _, body in self.github.posted_comments]
        self.assertTrue(any(notice in body for body in posted), notice)
        notices = len(posted)
        self.refreshed()[RUN_AGENT].assert_not_called()
        self.assertEqual(len(self.github.posted_comments), notices)

    def assert_recovered_by_a_reply(self, text: str = _support.FRESH_REPORT) -> None:
        """A reply's resume commits nothing and reports `text`, which is published once and reviewed.

        The report reaches the pull request exactly as the developer wrote
        it, with no code pushed, the report debt the park recorded paid, and
        the reviewer handed it. The reconciliation and the ticks behind it
        publish no second report and settle nothing again.
        """
        _fix_world.replied(self, "please write the report of the rebased head")
        self.refreshed(_support.fresh(text))[PUSH].assert_not_called()

        settled = _support.settled_records(self)
        self.assertEqual(
            (
                _support.published_texts(self, text),
                self.pull_request.head.sha,
                _report_delivery.owes_a_report(self.github.read_pinned_state(self.issue)),
                self.pinned().get(_report_delivery.UNREPORTED_WORK),
            ),
            ([text], REWRITTEN_HEAD, False, None),
        )
        self.assert_reviewed_fresh(self.reviewed(), text)
        self.reconcile()
        self.refreshed()[RUN_AGENT].assert_not_called()
        self.assertEqual(
            (_support.published_texts(self, text), _support.settled_records(self)),
            ([text], settled),
        )


class RefreshWorldMovedTest(unittest.TestCase, _support._RefreshedReports):
    """A world that moves while the refresh is out records nothing, and its own road answers it."""

    def test_a_head_pushed_over_the_run_is_refused(self) -> None:
        # Nothing is recorded, published, or parked by the refresh; the next
        # tick finds a head the debt does not explain and the reviewer road
        # parks for the stale report, with no second developer run.
        self.rebased()

        self.refreshed(_support.PushedOver(self, _support.fresh()))

        self.assertEqual(self.unrecorded(), _support.NOTHING)
        refusal = _review_report._MOVED_COMMIT.format(
            reported=_drift_world.PUBLISHED_HEAD, head=_support.FOREIGN_HEAD,
        )
        self.assert_refused(self.reviewed(), refusal)

    def test_an_edit_under_the_run_goes_to_drift(self) -> None:
        # The issue is edited while the agent is out: the report is recorded
        # nowhere. The next tick's drift check resumes the developer on the
        # edit, and the report it writes of the rebased head pays the debt.
        self.rebased()

        self.refreshed(self.mid_run("edit", _support.fresh()))

        self.assertEqual(self.unrecorded(), _support.NOTHING)
        resumed = self.refreshed(_support.fresh(_drift_world.LATER_REPORT_TEXT))
        self.assertIn("edited the issue", _reviewed.prompt(resumed))
        self.assert_reviewed_fresh(self.reviewed(), _drift_world.LATER_REPORT_TEXT)

    def test_a_deferred_edit_holds_the_refresh(self) -> None:
        # The drift check stands down for a reviewer round a reply bought,
        # and the refresh runs over no requirements a report has not seen: it
        # drops that note instead, and the next tick's drift resume answers
        # the edit with a report that pays the debt.
        self.rebased()
        _reviewed.restate(self, **{OWES_A_ROUND: True})
        _drift_world.edits(self, _drift_world.LATER_BODY)

        self.refreshed()[RUN_AGENT].assert_not_called()

        self.assertIsNone(self.pinned().get(OWES_A_ROUND))
        resumed = self.refreshed(_support.fresh())
        self.assertIn(_drift_world.LATER_BODY, _reviewed.prompt(resumed))
        self.assert_reviewed_fresh(self.reviewed())


    def test_an_edit_after_settlement_pays_nothing(self) -> None:
        # The refresh's report settles, then the issue is edited behind a
        # reviewer round the drift check stands down for. That report answers
        # requirements the issue no longer has, so it pays nothing: the claim
        # stands, no reviewer runs, and the note is dropped. The drift resume
        # answers the edit, and only a report of the edited requirements pays
        # -- the one it writes, or, after an `ACK:`, the next refresh's.
        for name, answers in ANSWERED_EDITS:
            with self.subTest(name):
                self.rebased()
                self.refreshed(_support.fresh())
                _reviewed.restate(self, **{OWES_A_ROUND: True})
                _drift_world.edits(self, _drift_world.LATER_BODY)

                self.reviewed()[RUN_AGENT].assert_not_called()

                standing = (self.claim(), self.pinned().get(OWES_A_ROUND))
                self.assertEqual(standing, (REWRITE.recorded(), None))
                for answer in answers:
                    self.refreshed(answer)
                self.assert_reviewed_fresh(self.reviewed(), _drift_world.LATER_REPORT_TEXT)


class RefreshInterruptionTest(unittest.TestCase, _support._RefreshedReports):
    """Every window the refresh's publication opens finishes with one run and one comment."""

    def test_an_interrupted_publication_finishes(self) -> None:
        # The report is recorded before anything is posted, so the dispatch
        # reconciliation or the next tick's hold finishes whatever the
        # interrupted tick left -- finding a comment that landed by its
        # receipt rather than posting again -- and the reviewer is handed it.
        for name, interrupted in INTERRUPTIONS:
            with self.subTest(name):
                self.rebased()
                with interrupted(self):
                    self.refreshed(_support.fresh())
                owed = self.records()
                self.assertIsNone(owed["current"])
                self.assertIsNotNone(owed[PENDING] or owed[DELIVERED])

                self.reconcile()

                self.assert_reviewed_fresh(self.reviewed())
                self.assertEqual(len(self.fresh_reports()), 1)


class RewriteDebtHoldTest(unittest.TestCase, _support._RefreshedReports):
    """A claim that explains nothing about the head standing earns no refresh."""

    def test_a_head_the_debt_does_not_explain_parks(self) -> None:
        # The reviewer road refuses the stale report exactly as it would with
        # no debt at all, and the claim -- readable or not -- is left as it
        # stood.
        for name, claim, head in UNEXPLAINED:
            with self.subTest(name):
                self.rebased(claim, head)
                refusal = _review_report._MOVED_COMMIT.format(
                    reported=_drift_world.PUBLISHED_HEAD, head=head,
                )

                self.assert_refused(self.reviewed(), refusal)
                self.assertEqual(self.claim(), claim)

    def test_a_repointed_branch_earns_no_refresh(self) -> None:
        # The issue pins another branch than the one the rebase rewrote. No
        # developer is resumed in that branch's checkout, so nothing is
        # recorded or charged, and the reviewer road parks for the stale
        # report as it would with no claim, the claim left as it stood.
        self.rebased()
        _reviewed.restate(self, **REPOINTED_BRANCH)
        spent = _read.spent(self)

        self.assert_refused(self.reviewed(), _MOVED_COMMIT)
        self.assertEqual(
            (self.claim(), _read.spent(self), self.unrecorded()),
            (REWRITE.recorded(), spent, PARKED_UNRECORDED),
        )

    def test_a_reply_pays_a_debt_it_did_not_explain(self) -> None:
        # The park's reply resumes the developer, whose report of the head the
        # pull request stands on pays the debt whatever the claim named -- or
        # whether it could be read -- and that report is what is reviewed.
        for name, claim in (
            ("unreadable", dict(UNREADABLE)),
            ("another report", replace(REWRITE, previous_head=_drift_world.STRANDED_HEAD).recorded()),
        ):
            with self.subTest(name):
                self.rebased(claim)
                self.reviewed()
                _fix_world.replied(self, "please report the head the pull request stands on")
                self.refreshed(_support.fresh())

                self.assert_reviewed_fresh(self.reviewed())


class SquashedRefreshHoldTest(unittest.TestCase, _support._SquashedReports):
    """A squashed report the proof does not reach is refused as before, and one nobody could read runs nobody."""

    def test_an_unproved_squash_is_refused(self) -> None:
        # No developer is asked for a report, so nothing is recorded or
        # charged: the reviewer road parks for the stale report as it would
        # with no squash behind it, and the claim is left as it stood.
        for name, seeds, moves, refusal in SQUASH_REFUSALS:
            with self.subTest(name):
                self.squashed_then_rebased(**seeds)
                if moves is not None:
                    moves(self)
                standing = (self.claim(), _read.spent(self))

                self.assert_refused(self.reviewed(), refusal)
                self.assertEqual(
                    (self.claim(), _read.spent(self), self.unrecorded()),
                    (*standing, PARKED_UNRECORDED),
                )

    def test_an_unreadable_prerequisite_runs_nobody(self) -> None:
        # The tick holds with nothing run, parked, or posted, and the claim
        # standing. Once the reading can be taken the developer is asked for
        # the report, and the next tick hands the reviewer that report.
        for name, options, moves in SQUASH_UNREAD:
            with self.subTest(name):
                self.squashed_then_rebased()
                moves(self)
                posted = len(self.github.posted_comments)

                self.refreshed(**options)[RUN_AGENT].assert_not_called()

                held = (
                    len(self.github.posted_comments),
                    bool(self.pinned().get(AWAITING_HUMAN)),
                    self.claim(),
                )
                self.assertEqual(held, (posted, False, _support.SQUASHED_REWRITE.recorded()))
                self.github.report_failures.unreadable.clear()
                self.refreshed(_support.fresh())
                self.assert_reviewed_fresh(self.reviewed())


class SquashedRebaseJourneyTest(_journey._SquashRebaseJourney, unittest.TestCase):
    """An approved report squashed and put in review is reported afresh, once, for each head a base rebase leaves."""

    def test_a_rebased_squash_is_refreshed_once(self) -> None:
        # The rebase's debt names the squash as the head it replaced while the
        # settled report is of the approved commit, and the squash's carry
        # proves the two one tree. So the next validating tick asks the
        # developer for a report of the rebased head -- told the report
        # standing there describes the approved commit -- and publishes and
        # settles it once, leaving that report as it was written. The tick
        # after pays the debt and hands the reviewer the fresh report, whose
        # approval goes on through the docs pass to `in_review`, nothing
        # undeliverable parked or asked of a human on the way. Later ticks
        # spawn, charge, post, and review nothing more.
        self.walks_into_review()
        approved = self.pull_request.issue_comments[0].body
        self.base_refresh(_journey.REBASED)

        self.dispatched(_journey.refresh())

        self._assert_refreshed_over(approved)
        self.approved_into_review(_journey.REBASED)
        standing = self._standing()
        for _ in range(3):
            self.dispatched()
        self.assertEqual((self.roles(), self._standing()), (REFRESHED_AND_REVIEWED, standing))
        self._assert_one_report_each(_journey.REBASED_REPORT)

    def test_an_interruption_ends_in_one_report(self) -> None:
        # A push whose answer was lost is finished by the next base refresh,
        # which records the debt and hands the issue back; a publication cut
        # short is finished by the next dispatch, found by its receipt. Either
        # way the developer is asked once, the report lands once, and the
        # reviewer is handed it with nothing parked.
        for name, push, interrupted in JOURNEY_INTERRUPTIONS:
            with self.subTest(name):
                self.setUp()
                self.walks_into_review()
                self.base_refresh(_journey.REBASED, push=push and push(self.pull_request))
                if push is not None:
                    self.dispatched()
                    self.base_refresh()
                with interrupted(self):
                    self.dispatched(_journey.refresh())

                self.approved_into_review(_journey.REBASED)

                self.assertEqual(self.roles(), REFRESHED_AND_REVIEWED)
                self._assert_one_report_each(_journey.REBASED_REPORT)

    def test_a_second_advance_is_reported_at_its_head(self) -> None:
        # The base moves again before the first debt is paid. Whatever stood
        # on the first rebased head, the head the second advance published is
        # reported once before its reviewer runs, that reviewer is handed only
        # the report of that head, and no report was ever bound to, or left
        # standing on, a head no developer read.
        for name, first, spawned, replaced in SECOND_ADVANCES:
            with self.subTest(name):
                self.setUp()
                self.walks_into_review()
                self.base_refresh(_journey.REBASED)
                first(self)
                self.base_refresh(_journey.ADVANCED)

                self.dispatched(_journey.refresh(_journey.ADVANCED_REPORT))
                self.approved_into_review(_journey.ADVANCED)

                told = self.spawned(_journey.REFRESHER)[-1]
                self.assertEqual((self.roles(), replaced in told), (spawned, True))
                self._assert_one_report_each(_journey.ADVANCED_REPORT)

    def settles_over_an_advance(self, interrupted) -> None:
        """Refresh the first rebased head under `interrupted`, move the base, then settle and review that report.

        The advance lands nothing while the report is recorded and unsettled:
        the pull request and the debt stay on the head it was written about,
        so the report that settles is that head's, and so is the reviewer it
        is handed to.
        """
        with interrupted(self):
            self.dispatched(_journey.refresh())
        debt = self.pinned()["developer_report_rewrite_debt"]
        self.base_refresh(_journey.ADVANCED)
        held = (self.pull_request.head.sha, self.pinned()["developer_report_rewrite_debt"])
        self.assertEqual(held, (_journey.REBASED, debt))
        self.approved_into_review(_journey.REBASED)
        self.assertIn(f"> {_journey.REBASED_REPORT}", self.spawned(_journey.REVIEWER)[0])
        self.assertEqual(self.pinned()[CURRENT_REPORT][REPORTED_COMMIT], _journey.REBASED)

    def _assert_refreshed_over(self, approved: str) -> None:
        """One report of the rebased head settled, the approved report left as written, and nothing parked.

        The developer was told which commits stand behind the head: the
        approved one the settled report describes, and the squash the rebase
        replaced.
        """
        settled = self.pinned()[CURRENT_REPORT]
        refreshed = (
            settled[REPORTED_COMMIT],
            settled["revision"],
            self.pull_request.issue_comments[0].body,
            self.pinned()["park_reason"],
        )
        self.assertEqual(refreshed, (_journey.REBASED, 2, approved, None))
        told = f"describes `{_journey.HEAD}`, the approved commit this orchestrator squashed into `{_journey.SQUASHED}`"
        self.assertIn(told, self.spawned(_journey.REFRESHER)[0])

    def _assert_one_report_each(self, latest: str) -> None:
        """Each head's report on the pull request once, `latest` settled and handed over, and nothing undeliverable.

        The debt is paid, the report the last reviewer was handed is `latest`,
        no notice anywhere says a report could not be delivered, and every run
        spawned since the walk into review was charged once.
        """
        bodies = [posted.body for posted in self.pull_request.issue_comments]
        said = bodies + [notice for _, notice in self.github.posted_comments]
        published = [
            sum(text in body for body in bodies)
            for text in (_journey.REBASED_REPORT, _journey.ADVANCED_REPORT)
        ]
        pinned = self.pinned()
        self.assertEqual(
            (
                max(published),
                pinned[CURRENT_REPORT][REPORTED_COMMIT],
                pinned["developer_report_rewrite_debt"],
                any(_journey.UNDELIVERABLE_NOTICE in body for body in said),
                self.spent_since(self.charged)[0],
            ),
            (1, self.pull_request.head.sha, None, False, len(self.spawns)),
        )
        self.assertIn(f"> {latest}", self.spawned(_journey.REVIEWER)[-1])

    def _standing(self) -> tuple:
        """Where the issue stands: its label, and how much its pull request and thread were told."""
        told = len(self.pull_request.issue_comments)
        return self.labels()[-1], told, len(self.github.posted_comments)
