# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pull request this orchestrator rebased, and the validating ticks that refresh its report.

The reviewed-report world moved on by one rebase: the settled report is about
the head the pull request stood on before it, the code-publication receipt
names the head the rebase published and the one it replaced, the pull request
and the checkout stand on the published head, and the pinned comment claims the
debt the rebase left. What a case varies is what the developer asked for that
head's report answers, what moves while it is out, and where the publication
behind it is interrupted.

The squashed world is the same rebase one step further from the report: the
settled report is about the commit a reviewer approved, this orchestrator's
approval squash published `SQUASHED_HEAD` on the same tree in its place and
carried the approved run onto it, and the rebase replaced the squash. So the
debt and the receipt name the squash as the head the rebase replaced, and the
carry is kept in the evidence history, invalidated once the head moved past it,
which is where a later validating tick finds it.
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from orchestrator import config
from orchestrator.github.developer_reports import developer_report_from_comment
from orchestrator.workflow.engine import (
    report_rewrite_debt as _rewrite_debt,
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
    verification_record_state as _evidence_record_state,
    verification_records as _evidence_records,
    verification_settlement_state as _evidence_settlement,
)
from tests.support.fakes import FakeUser
from tests.workflow import (
    drift_reports as _drift_world,
    fix_reports as _fix_world,
    published_reports as _published_reports,
    reviewed_reports as _reviewed,
)
from tests.workflow.engine import verification_record_test_support as _evidence_support
from tests.workflow.fixtures import LABEL_VALIDATING, _agent, _issue_branch
from tests.workflow.repo_values import _FAKE_TREE_SHA

ISSUE = 2_006

PR = 20_060

RUN_AGENT = "run_agent"

DEBT = _rewrite_debt.REWRITE_DEBT

# The head the rebase published over the one the settled report is about, one
# somebody else pushed over it, and the head a second rebase moves it to. None
# is the commit a run that commits leaves, which is `FIXED_HEAD`.
REWRITTEN_HEAD = "b" * len(_drift_world.FIXED_HEAD)

FOREIGN_HEAD = "d" * len(_drift_world.FIXED_HEAD)

SECOND_HEAD = "f" * len(_drift_world.FIXED_HEAD)

# What the developer writes about the head the rebase published.
FRESH_REPORT = "Rebased onto the updated base; the change reads as before and the suite passes."

REWRITE = _rewrite_debt.RewriteDebt(
    pr_number=PR,
    branch=_issue_branch(ISSUE),
    previous_head=_drift_world.PUBLISHED_HEAD,
    rewritten_head=REWRITTEN_HEAD,
)

# The commit an approval's squash published in place of the approved head the
# settled report is about. The rebase of that squash is `REWRITTEN_HEAD`.
SQUASHED_HEAD = "5c3a91b7" * 5

SQUASHED_REWRITE = replace(REWRITE, previous_head=SQUASHED_HEAD)

# What `unrecorded` reads where a refresh left no trace.
NOTHING = (None, None, [], False)

# What settling a report writes, and what a settlement replayed would write
# again: the report the pull request now carries, the handoff saying this
# transaction finished, and the round the road behind it spent.
SETTLED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_round")

# What an issue that predates the record carries in its place: nothing at all.
LEGACY = object()

# What a case that names no other claim is seeded with: the rebase's own debt.
_OWN = object()


def fresh(text: str = FRESH_REPORT) -> str:
    """A finished run's message, ending on a fresh report ready for publication."""
    return _drift_world.reported(text)


def published_texts(case, text: str) -> list:
    """The report each comment on the pull request carrying `text` reads back as.

    Read back the way the reviewer road reads it, so a comment that carries
    `text` and is not exactly the report it claims to be reads as None.
    """
    return [
        getattr(developer_report_from_comment(posted, bot_login=case.github._bot_login), "text", None)
        for posted in case.fresh_reports(text)
    ]


class PushedOver:
    """A run during which somebody pushes over the rebased head, then the reply."""

    def __init__(self, case, reply: str) -> None:
        self._case = case
        self._reply = reply

    def __call__(self, *_args, **_kwargs):
        self._case.pull_request.head.sha = FOREIGN_HEAD
        return _agent(session_id=_drift_world.DEV_SESSION, last_message=self._reply)


class _RefreshedReports(_reviewed._ReviewedReports):
    """Validating ticks over a pull request this orchestrator rebased."""

    def rebased(self, claim=_OWN, head: str = REWRITTEN_HEAD) -> None:
        """A validating issue a rebase published onto `REWRITTEN_HEAD`, owing it a report.

        The pull request stands on `head`: the rebase's own, or one somebody
        pushed over it, which leaves the receipt naming the rebase. `claim` is
        what the pinned comment carries where the debt is recorded -- the
        rebase's own debt unless a case names another, and no key at all for
        `LEGACY`.
        """
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        # The code-publication receipt the rebase's gated push leaves.
        rewrite = {
            "implementing_published_sha": REWRITTEN_HEAD,
            "implementing_published_lease": _drift_world.PUBLISHED_HEAD,
        }
        if claim is not LEGACY:
            rewrite[DEBT] = REWRITE.recorded() if claim is _OWN else claim
        _reviewed.restate(self, **rewrite)
        self.pull_request.head.sha = head

    def refreshed(self, *runs, **run_options):
        """One validating tick whose agent runs answer with `runs`, in order.

        The checkout stays where the pull request stands unless a case says
        otherwise, since a report asked for alone moves nothing.
        """
        return self._ticked(
            self._run_validating,
            MagicMock(side_effect=_fix_world._Runs(*runs)),
            committed=False,
            **run_options,
        )

    def fresh_reports(self, text: str = FRESH_REPORT) -> list:
        """Every comment on the pull request carrying the fresh report."""
        return self.published_reports(text)

    def unrecorded(self) -> tuple:
        """What the pinned comment and the pull request hold of a fresh report, and whether a park stands.

        `NOTHING` where no refresh left a trace: no delivery, no transaction,
        no comment, and no park.
        """
        records = self.records()
        return (
            records["delivered"],
            records["pending"],
            self.fresh_reports(),
            bool(self.pinned().get("awaiting_human")),
        )

    def claim(self):
        """What the pinned comment records for the debt, `LEGACY` where nothing."""
        return self.pinned().get(DEBT, LEGACY)

    def assert_reviewed_fresh(self, mocks, text: str = FRESH_REPORT) -> None:
        """The tick spawned the reviewer alone, handed `text`, and the debt is paid."""
        runs = mocks[RUN_AGENT].call_args_list
        self.assertEqual(
            ([run.args[0] for run in runs], self.claim()),
            ([config.REVIEW_AGENT], None),
        )
        self.assertIn(f"> {text}", _reviewed.prompt(mocks))

    def rebased_again(self, second: _rewrite_debt.RewriteDebt) -> None:
        """Record the debt a second rebase leaves, and move the receipt and the pull request onto its head."""
        state = self.github.read_pinned_state(self.issue)
        self.assertTrue(_rewrite_debt.records_rewrite(state, second))
        state.set("implementing_published_sha", second.rewritten_head)
        state.set("implementing_published_lease", second.previous_head)
        self.github.write_pinned_state(self.issue, state)
        self.pull_request.head.sha = second.rewritten_head


def settled_records(case) -> dict:
    """What the case's pinned comment holds of every record a settlement writes."""
    return {key: case.pinned().get(key) for key in SETTLED_RECORDS}


def squash_carry(state) -> _evidence_records.EvidenceBinding:
    """The approval squash's carry of the run on the settled report's commit onto `SQUASHED_HEAD`.

    The approved subject is the settled report exactly -- its commit, pull
    request, revision, digest, and requirements -- and the carry answers for
    the squash on the same repository, pull request, and branch, over the tree
    a tick reads every commit as unless a case seeds another.
    """
    settled = _report_settlement.read_current_report(state)
    reported = settled.subject
    approved = _review_subjects.ReviewSubject(
        pr_number=reported.pr_number,
        commit=reported.source_sha,
        requirements_revision=reported.requirements_revision,
        report=_review_subjects.ReviewReport(
            text=_published_reports.DELIVERED_REPORT,
            report_revision=settled.report_revision,
            content_revision=settled.content_revision,
            source_sha=reported.source_sha,
            requirements_revision=reported.requirements_revision,
            location=settled.location,
        ),
    )
    return _evidence_support.binding(
        target=_evidence_records.EvidenceTarget(
            publication=replace(reported, source_sha=SQUASHED_HEAD), subject=approved.recorded(),
        ),
        tested_sha=reported.source_sha,
        tested_tree=_FAKE_TREE_SHA,
    )


class _SquashedReports(_RefreshedReports):
    """Validating ticks over a pull request this orchestrator squashed on approval and then rebased."""

    def squashed_then_rebased(self, carry=squash_carry, claim=None) -> None:
        """A validating issue whose approved report's squash a rebase replaced, owing `REWRITTEN_HEAD` a report.

        `carry` builds the binding the squash's carry is recorded under from
        the pinned state, and None records no carry at all; `claim` is the
        debt the pinned comment carries, the rebase's of the squash unless a
        case names another.
        """
        self.rebased(SQUASHED_REWRITE.recorded() if claim is None else claim)
        state = self.github.read_pinned_state(self.issue)
        state.set("implementing_published_lease", SQUASHED_HEAD)
        if carry is not None:
            pending = _evidence_record_state.mint_pending_evidence(
                state, ISSUE, carry(state), (_evidence_support.ran(),),
            )
            self.assertTrue(_evidence_record_state.record_pending_evidence(state, pending))
            _evidence_support.settles(state, pending)
            self.assertTrue(_evidence_settlement.retire_current_evidence(state))
        self.github.write_pinned_state(self.issue, state)

    def approved_comment(self):
        """The comment the approved report landed as, which the settled record names."""
        return next(
            posted for posted in self.pull_request.issue_comments
            if posted.id == self.opening_report.location.comment_id
        )

    def acknowledges_an_edit(self) -> None:
        """Edit the issue and move the baseline onto it, as an `ACK:` to that edit leaves it.

        The settled report and the squash's carry stay written against the
        requirements before the edit.
        """
        _drift_world.edits(self, _drift_world.LATER_BODY)
        _reviewed.restate(self, user_content_hash=_drift_world.handed_revision(self.issue))

    def rewrites_the_approved_report(self, text: str = "", login: str = "") -> None:
        """Rewrite the approved report's comment in place: its words to `text`, its author to `login`, where given."""
        landed = self.approved_comment()
        if text:
            landed.body = landed.body.replace(_published_reports.DELIVERED_REPORT, text)
        if login:
            landed.user = FakeUser(login)
