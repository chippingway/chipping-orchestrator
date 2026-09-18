# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reused pull request's description keeps, and when it holds the work.

The description is judged as it stands NOW, read afresh by number. One that
closes this issue and names the session stands; any other gets those two lines
above it with every word kept -- unless a developer report of this issue's may
live there, in which case nothing is edited at all. The body those lines come
from leaves the closing agent message to the managed report wherever one exists.
"""

from __future__ import annotations

import copy
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github import developer_reports as _reports
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.implementing import (
    dev_pr as _dev_pr,
    pr_description as _pr_description,
    state as _state,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_IMPLEMENTING,
    SHA_LENGTH,
    _agent,
    _open_pr_for,
)
from tests.workflow.stages.implementing import pr_test_support as support

ISSUE = support.BODY_SHORT_ISSUE

REUSED_PR = 71

LAST_MESSAGE = "The run's closing message."

LAST_MESSAGE_HEADING = "_Last agent message:_"

# What a human wrote over the body: no closing reference, no attribution, and
# a legacy tail an earlier build of this stage left, which is history now.
HUMAN_DESCRIPTION = (
    "### Notes\n\nRewritten by hand, and meant to stay.\n\n---\n"
    f"{LAST_MESSAGE_HEADING}\n\nAn excerpt from a run long finished."
)

# What the lookup fetched before that edit landed.
LOOKED_UP_DESCRIPTION = "### Plan\n\nThe description the lookup fetched."

PARK_REASON = "park_reason"

AWAITING_HUMAN = "awaiting_human"

# A record whose location still names the reused pull request's description
# while the rest of it will not read.
DAMAGED_RECORD = MappingProxyType({
    "location_pr": REUSED_PR, "location_comment": None,
})

# The line this stage closes the issue with, and the same reference qualified
# with this repository the way GitHub compares one: without case.
RESOLVES = f"Resolves #{ISSUE}"

SLUG = _TEST_SPEC.slug.upper()

QUALIFIED = f"fixes {SLUG}#{ISSUE}"

# References GitHub does not act on here: shown as code, or another repository's.
CLOSING_NOTHING = (
    f"```\n{RESOLVES}\n```",
    f"Write `{RESOLVES}` to close it.",
    f"Resolves someone/else#{ISSUE}",
)

EARLIER_SHA = "e" * SHA_LENGTH

REQUIREMENTS = _reports.content_digest("the requirements the run was handed")

UNREAD = "GitHub did not answer the pull-request read"

GET_PR = "get_pr"

TOO_LONG_NOTICE = "too long to have this issue's closing reference"

# A description a few characters under GitHub's ceiling, which the two lines
# this implementation needs above it would take past that ceiling.
NEAR_THE_CEILING = "x" * (MAX_PINNED_BODY - 10)

# What each notice of these says and the pinned comment beside them does not.
HELD = "held rather than handed to review"



def _pinned(**carried) -> PinnedState:
    """The pinned comment of an issue one developer session is implementing."""
    return PinnedState(state_data={
        "dev_agent": "claude", "dev_session_id": support.DEV_SESSION, **carried,
    })


def _own_description(reference: str = RESOLVES) -> str:
    """What this stage writes on a pull request it opened, however it closes."""
    return f"{reference}\n\n{_dev_pr._dev_pr_attribution(_pinned())}"


def _settled_on_the_description() -> dict:
    """The settled pair a report verified on the reused description left."""
    settled = PinnedState()
    _settlement.record_current_report(settled, _records.CurrentReport(
        subject=_records.ReportSubject(
            repo_slug=_TEST_SPEC.slug,
            pr_number=REUSED_PR,
            branch="orchestrator/issue",
            source_sha=EARLIER_SHA,
            requirements_revision=REQUIREMENTS,
        ),
        report_revision=1,
        content_revision=_reports.content_digest(HUMAN_DESCRIPTION),
        location=ReportLocation(pr_number=REUSED_PR),
    ))
    _settlement.record_handoff(settled, _records.ReportHandoff(
        receipt=f"issue-{ISSUE}-report-1",
        pr_number=REUSED_PR,
        report_revision=1,
        source_sha=EARLIER_SHA,
    ))
    return dict(settled.data)


SETTLED = MappingProxyType(_settled_on_the_description())

# Every record that may name the reused description, beside whether the report
# it is about has settled already -- which is what no retry frees.
CLAIMS = (
    ({_records.DELIVERED_REPORT: dict(DAMAGED_RECORD)}, False),
    ({_records.PENDING_REPORT: dict(DAMAGED_RECORD)}, False),
    ({**SETTLED, _records.CURRENT_REPORT: dict(DAMAGED_RECORD)}, True),
    ({**SETTLED, _records.CURRENT_REPORT: None}, True),
    (dict(SETTLED), True),
)

# What each pinned comment does to the closing message a body would carry.
EXCERPTED = (
    ({}, True),
    *((carried, False) for carried, _settled in CLAIMS),
    ({_report_delivery.OWED_REPORT: True}, False),
    ({PARK_REASON: _report_delivery.UNDELIVERABLE_REPORT}, False),
)


class _ReusedPullRequest:
    """A pull request already open on the branch this issue pushes."""

    def reused(self, description: str = HUMAN_DESCRIPTION, **carried) -> None:
        """Seed the client, the issue, the pinned comment and the pull request."""
        self.github = support.FakeGitHubClient()
        self.issue = support.make_issue(ISSUE, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self.state = _pinned(**carried)
        self.live = _open_pr_for(
            self.github, issue_number=ISSUE, pr_number=REUSED_PR,
        )
        self.live.body = description

    def names(self, looked_up=None):
        """Ask the verdict of the pull request object a lookup handed over."""
        return _pr_description._names_the_implementation(
            self.github, self.issue, self.state,
            _agent(last_message=LAST_MESSAGE), looked_up or self.live,
        )

    def kept_beneath(self) -> tuple:
        """Whether the body now opens on this stage's lines, and what it kept."""
        named, kept = self.live.body.split(_state._PR_BODY_EARLIER_HEADING)
        return named.startswith(_own_description()), kept.strip()

    def notices(self) -> list:
        """The notices a human was sent, apart from the pinned comment."""
        return [
            posted.body for posted in self.issue.comments if HELD in posted.body
        ]


class PullRequestBodyTest(unittest.TestCase):
    def test_a_managed_report_owns_the_message(self) -> None:
        # The closing reference and the attribution are always there. The
        # agent's closing message is written only while no report of this
        # issue's is owed or settled; a description kept beneath keeps its own
        # legacy tail, which is the only place the heading then appears.
        issue = support.make_issue(ISSUE, label=LABEL_IMPLEMENTING)
        for carried, excerpted in EXCERPTED:
            with self.subTest(carried=sorted(carried)):
                named, kept = _dev_pr._build_pr_body(
                    _pinned(**carried), issue,
                    _agent(last_message=LAST_MESSAGE), HUMAN_DESCRIPTION,
                ).split(_state._PR_BODY_EARLIER_HEADING)

                self.assertEqual(
                    (
                        named.startswith(_own_description()),
                        LAST_MESSAGE_HEADING in named,
                        LAST_MESSAGE in named,
                        kept.strip(),
                    ),
                    (True, excerpted, excerpted, HUMAN_DESCRIPTION),
                )


class DescriptionVerdictTest(unittest.TestCase, _ReusedPullRequest):
    def test_a_description_naming_the_work_stands(self) -> None:
        # However GitHub would honour the reference -- this stage's own line,
        # or one qualified with this repository -- with whatever else a human
        # added underneath.
        for reference in (RESOLVES, QUALIFIED):
            with self.subTest(reference=reference):
                described = f"{_own_description(reference)}\n\nA human's note."
                self.reused(described)

                self.assertIs(self.names(), True)

                self.assertEqual(
                    (self.github.edited_pr_bodies, self.live.body),
                    ([], described),
                )

    def test_an_edit_after_the_lookup_is_kept(self) -> None:
        # A human replaced the body after the lookup fetched it -- a plan's, or
        # this stage's own complete one. Judged afresh, what they wrote stays
        # beneath this implementation's lines, legacy tail and all.
        for fetched in (LOOKED_UP_DESCRIPTION, _own_description()):
            with self.subTest(fetched=fetched):
                self.reused()
                looked_up = copy.copy(self.live)
                looked_up.body = fetched

                self.assertIs(self.names(looked_up), True)

                self.assertEqual(self.kept_beneath(), (True, HUMAN_DESCRIPTION))

    def test_a_reference_closing_nothing_is_added_to(self) -> None:
        # A closing reference shown as code, or naming another repository, is
        # one GitHub does not act on here, so the body still earns the real one
        # above it -- with the run's closing message, no report managing it.
        for reference in CLOSING_NOTHING:
            with self.subTest(reference=reference):
                quoted = _own_description(reference)
                self.reused(quoted)

                self.assertIs(self.names(), True)

                self.assertEqual(self.kept_beneath(), (True, quoted))
                self.assertIn(LAST_MESSAGE, self.live.body)

    def test_a_claimed_description_is_never_edited(self) -> None:
        # Delivered, pending, settled, or too damaged to say otherwise: even an
        # edit keeping every word would move a verified description off its
        # digest. While a report is still owed the next settlement may free
        # it, so nothing parks; a report already settled there is freed by no
        # retry, so the work parks -- once -- for a report written elsewhere.
        for carried, settled in CLAIMS:
            with self.subTest(carried=sorted(carried), settled=settled):
                self.reused(**carried)

                self.assertEqual((self.names(), self.names()), (False, False))

                self.assertEqual(
                    (
                        self.github.edited_pr_bodies,
                        self.live.body,
                        {key: self.state.get(key) for key in carried},
                        self.state.get(AWAITING_HUMAN),
                        len(self.notices()),
                    ),
                    ([], HUMAN_DESCRIPTION, carried, settled or None, int(settled)),
                )

    def test_an_unreadable_description_holds(self) -> None:
        # Nothing is written over a description nobody could read, and nobody
        # is asked anything: the next tick reads it again.
        self.reused()

        with patch.object(self.github, GET_PR, side_effect=RuntimeError(UNREAD)):
            verdict = self.names()

        self.assertEqual(
            (verdict, self.github.edited_pr_bodies, self.live.body, self.notices()),
            (None, [], HUMAN_DESCRIPTION, []),
        )

    def test_a_description_too_long_to_name_is_held(self) -> None:
        # The two lines would take the description past GitHub's ceiling, and
        # cutting what somebody wrote is not this stage's to do.
        self.reused(NEAR_THE_CEILING)

        self.assertIsNone(self.names())

        self.assertEqual(
            (
                self.github.edited_pr_bodies,
                self.live.body,
                self.state.get(PARK_REASON),
            ),
            ([], NEAR_THE_CEILING, _report_delivery.UNDELIVERABLE_REPORT),
        )
        self.assertIn(TOO_LONG_NOTICE, self.notices()[0])


if __name__ == "__main__":
    unittest.main()
