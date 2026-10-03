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
"""
from __future__ import annotations

from unittest.mock import MagicMock

from orchestrator import config
from orchestrator.github.developer_reports import developer_report_from_comment
from orchestrator.workflow.engine import report_rewrite_debt as _rewrite_debt
from tests.workflow import (
    drift_reports as _drift_world,
    fix_reports as _fix_world,
    reviewed_reports as _reviewed,
)
from tests.workflow.fixtures import LABEL_VALIDATING, _agent, _issue_branch

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

# What `unrecorded` reads where a refresh left no trace.
NOTHING = (None, None, [], False)

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
