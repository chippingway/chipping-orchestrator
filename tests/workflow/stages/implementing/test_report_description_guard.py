# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reused pull request's description has to say, and that it is never rewritten.

The description is judged as it stands NOW, read afresh by number. One that
closes this issue and names the session stands; any other holds the work for a
human, who is handed the two lines to put there. Nothing is written by the
verdict itself, since no write of a description can be kept from overwriting an
edit saved a moment earlier -- so human text, legacy tails and concurrent edits
all stand exactly as they were found. The body this stage opens its own pull
requests with leaves the closing agent message to the managed report wherever
one exists.
"""

from __future__ import annotations

import copy
import unittest
from types import MappingProxyType
from unittest.mock import PropertyMock, patch

from orchestrator.github import developer_reports as _reports
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.implementing import (
    dev_pr as _dev_pr,
    pr_description as _pr_description,
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
    f">     {RESOLVES}",
    f"> ~~~\n> {RESOLVES}\n> ~~~",
    f"<pre>{RESOLVES}</pre>",
    f"Escaped \\` then `{RESOLVES}`.",
    f"An unmatched ` here.\n\n`{RESOLVES}`",
    f"- > ~~~\n  > {RESOLVES}\n  > ~~~",
    f"- -     {RESOLVES}",
    f"`unmatched\n<pre>` {RESOLVES}</pre>",
    f"<code><code>example</code> {RESOLVES}</code>",
    f"Intro\r\r    {RESOLVES}",
    f'<pre data-example="> </pre>">{RESOLVES}</pre>',
    f"Example `<pre` then <code>{RESOLVES}</code>",
    f"```\n<pre\n```\n\n<code>{RESOLVES}</code>",
    f"| Field | Value |\n| --- | --- |\n| stray ` | `{RESOLVES}` |",
    f'see <a title="`">a link</a> `{RESOLVES}`',
    f"<http://example.com/`x> `{RESOLVES}`",
    f'[link](https://example.com "`") `{RESOLVES}`',
    f'![image](https://example.com/a.png "`") `{RESOLVES}`',
    f'<code><a title="</code>">{RESOLVES}</a></code>',
    f'<pre><a title="</pre>">{RESOLVES}</a></pre>',
    f"<pre>Literal </pre\N{NO-BREAK SPACE}> {RESOLVES}</pre>",
    f"`<x`<code>{RESOLVES}</code>",
    f"https://example.com/`x `{RESOLVES}`",
    f"www.example.com/`x `{RESOLVES}`",
    f"<!DOCTYPE html {RESOLVES}>",
    f"<?{RESOLVES}?>",
    f"<![CDATA[{RESOLVES}]]>",
    f"Resolves someone/else#{ISSUE}",
)

# HTML quoted as an example, in code that is code however the text is read:
# no tag of it opens anything, so the lines beneath it still name the work.
QUOTED_EXAMPLES = (
    "Wrap the output in `<pre>` so it keeps its columns.",
    "```html\n<pre>\n```",
)

EARLIER_SHA = "e" * SHA_LENGTH

REQUIREMENTS = _reports.content_digest("the requirements the run was handed")

UNREAD = "GitHub did not answer the pull-request read"

# What a human saves over the description after this stage has read it.
SAVED_MEANWHILE = "### Notes\n\nSaved after the orchestrator's last read."

GET_PR = "get_pr"

UNREAD_REPOSITORY = "GitHub did not answer the repository read"

REPO_SLUG = "repo_slug"

# The client's one request that rewrites a description, which nothing here may
# make: a case that reached it fails on the spot rather than on a later assert.
EDIT_PR_BODY = "edit_pr_body"

REWROTE = "the verdict rewrote a description"

# What each notice of these says and the pinned comment beside them does not,
# and what only the notice about a settled report says.
HELD = "held rather than handed to review"

SETTLED_THERE = "is where this issue's developer report settled"


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
        rewriting = patch.object(
            self.github, EDIT_PR_BODY, side_effect=AssertionError(REWROTE),
        )
        rewriting.start()
        self.addCleanup(rewriting.stop)

    def names(self, looked_up=None):
        """Ask the verdict of the pull request object a lookup handed over."""
        return _pr_description._names_the_implementation(
            self.github, self.issue, self.state, looked_up or self.live,
        )

    def read_then_edited(self, number: int):
        """Read the description as it stands, then have a human save over it.

        The reading handed back is the one taken BEFORE the save: the last the
        verdict takes, so everything it does next it does to a description that
        is no longer the one it read.
        """
        judged = copy.copy(self.reads(number))
        self.live.body = SAVED_MEANWHILE
        return judged

    def notices(self) -> list:
        """The notices a human was sent, apart from the pinned comment."""
        return [
            posted.body for posted in self.issue.comments if HELD in posted.body
        ]

    def assert_held_with_the_lines(self, stands: str) -> None:
        """Parked once, the two lines quoted, and the description as it stood."""
        notices = self.notices()
        notice = notices[0]
        self.assertEqual(
            (
                len(notices),
                self.live.body,
                RESOLVES in notice,
                _dev_pr._dev_pr_attribution(self.state) in notice,
                self.state.get(PARK_REASON),
                self.state.get(_report_delivery.OWED_REPORT),
            ),
            (1, stands, True, True, _report_delivery.UNDELIVERABLE_REPORT, True),
        )


class PullRequestBodyTest(unittest.TestCase):
    def test_a_managed_report_owns_the_message(self) -> None:
        # The closing reference and the attribution are always there. The
        # agent's closing message is written only while no report of this
        # issue's is owed or settled, since the report comment is the authority.
        issue = support.make_issue(ISSUE, label=LABEL_IMPLEMENTING)
        for carried, excerpted in EXCERPTED:
            with self.subTest(carried=sorted(carried)):
                body = _dev_pr._build_pr_body(
                    _pinned(**carried), issue, _agent(last_message=LAST_MESSAGE),
                )

                self.assertEqual(
                    (
                        body.startswith(_own_description()),
                        LAST_MESSAGE_HEADING in body,
                        LAST_MESSAGE in body,
                    ),
                    (True, excerpted, excerpted),
                )


class DescriptionVerdictTest(unittest.TestCase, _ReusedPullRequest):
    def test_a_description_naming_the_work_stands(self) -> None:
        # However GitHub would honour the reference -- this stage's own line,
        # or one qualified with this repository -- with whatever else a human
        # added underneath, or above: an HTML example quoted as code swallows
        # nothing beneath it.
        named = (
            *(_own_description(reference) for reference in (RESOLVES, QUALIFIED)),
            *(f"{example}\n\n{_own_description()}" for example in QUOTED_EXAMPLES),
        )
        for naming in named:
            with self.subTest(naming=naming):
                described = f"{naming}\n\nA human's note."
                self.reused(described)

                self.assertIs(self.names(), True)

                self.assertEqual(
                    (self.live.body, self.notices()), (described, []),
                )

    def test_an_unnamed_description_is_held(self) -> None:
        # Judged afresh rather than off the lookup's snapshot -- a plan's, or
        # this stage's own complete body, since replaced by hand. What stands
        # names nothing, so the work parks, once, with the two lines quoted;
        # every word there, the legacy tail included, stays as it was.
        for fetched in (LOOKED_UP_DESCRIPTION, _own_description()):
            with self.subTest(fetched=fetched):
                self.reused()
                looked_up = copy.copy(self.live)
                looked_up.body = fetched

                self.assertEqual(
                    (self.names(looked_up), self.names(looked_up)), (None, None),
                )

                self.assert_held_with_the_lines(HUMAN_DESCRIPTION)

    def test_an_edit_after_the_last_read_stands(self) -> None:
        # A human saved over the description after the verdict's last read of
        # it. No request follows that read that could write over the save, so
        # what they wrote is what stands, and the next tick is what judges it.
        self.reused()
        self.reads = self.github.get_pr

        with patch.object(self.github, GET_PR, self.read_then_edited):
            self.assertIsNone(self.names())

        self.assert_held_with_the_lines(SAVED_MEANWHILE)
        self.live.body = _own_description()
        self.assertIs(self.names(), True)

    def test_a_reference_closing_nothing_is_held(self) -> None:
        # A closing reference shown as code -- quoted, fenced, in HTML, or
        # behind an escaped backtick -- or naming another repository is one
        # GitHub does not act on here, so the description still has to be named.
        for reference in CLOSING_NOTHING:
            with self.subTest(reference=reference):
                quoted = _own_description(reference)
                self.reused(quoted)

                self.assertIsNone(self.names())

                self.assert_held_with_the_lines(quoted)

    def test_a_claimed_description_is_told_apart(self) -> None:
        # Delivered, pending, settled, or too damaged to say otherwise. While
        # the report is still owed the binding is what parks the collision, so
        # nothing parks here; one already settled there is freed by no retry,
        # so it parks -- once -- under the notice that says a report lives there.
        for carried, settled in CLAIMS:
            with self.subTest(carried=sorted(carried), settled=settled):
                self.reused(**carried)

                self.assertEqual((self.names(), self.names()), (False, False))

                self.assertEqual(
                    (
                        self.live.body,
                        {key: self.state.get(key) for key in carried},
                        [SETTLED_THERE in notice for notice in self.notices()],
                    ),
                    (HUMAN_DESCRIPTION, carried, [True] if settled else []),
                )

    def test_an_unreadable_description_holds(self) -> None:
        # Nobody is asked anything over a description nobody could read: the
        # next tick reads it again.
        self.reused()

        with patch.object(self.github, GET_PR, side_effect=RuntimeError(UNREAD)):
            verdict = self.names()

        self.assertEqual(
            (verdict, self.live.body, self.notices()),
            (None, HUMAN_DESCRIPTION, []),
        )

    def test_an_unreadable_repository_holds(self) -> None:
        # The description was read and the repository a qualified reference
        # in it has to name was not -- a fresh worker's client fetches it on
        # that read. Nothing is decided on half of what the verdict compares.
        self.reused(_own_description())
        unread = PropertyMock(side_effect=RuntimeError(UNREAD_REPOSITORY))

        with patch.object(type(self.github), REPO_SLUG, unread):
            verdict = self.names()

        self.assertEqual(
            (verdict, unread.call_count, self.live.body, self.notices()),
            (None, 1, _own_description(), []),
        )


if __name__ == "__main__":
    unittest.main()
