# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer report a reviewer's prompt hands it, beside the issue.

The reviewer is handed the report rather than left to fetch one: quoted whole
between the issue and the commands that inspect the branch, named by its
revision and location, and said to be the complete, current report. Where the
thread the reviewer reads has moved on since the report was written, the prompt
says so; where no report is recorded, it says that instead. None of it teaches
the reviewer a report outcome of the developer's own.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import review_prompts, review_subjects
from orchestrator.workflow.engine.report_outcome_models import (
    _REPORT_READY_MARKER,
    _REPORT_VERIFIED_MARKER,
)
from tests.support.fakes import make_issue
from tests.workflow.fixtures import _TEST_SPEC

_ISSUE_NUMBER = 67_400

_PR_NUMBER = 1_697

_COMMENT_ID = 5_579_567_555

_REVISION = 3

_REPORT_HEAD = "0b54a1c9e4f1d2a3b4c5d6e7f8091a2b3c4d5e6f"


_REQUIREMENTS = "requirements-at-the-report"

_EDITED_REQUIREMENTS = "requirements-after-an-edit"

_DIGEST = "f0e1d2c3b4a5968778695a4b3c2d1e0ff0e1d2c3b4a5968778695a4b3c2d1e0f"

# A report of the shape developers write: a heading, a list, and a fence --
# every line of which has to reach the reviewer.
_REPORT_LINES = (
    "### What changed",
    "- the foo flag is parsed",
    "```sh",
    "uv run pytest tests",
    "```",
    "Every check passed.",
)

_REPORT = "\n".join(_REPORT_LINES)

_ISSUE_BODY = "users want a foo flag"

_INSPECTION = "Inspect the change with:"

_COMPLETE_AND_CURRENT = "It is the complete, current report"


_EDITED_NOTE = "The issue has changed since this report was written"

_NO_REPORT = "No developer report is recorded for this pull request"


def _subject(
    *,
    commit: str = _REPORT_HEAD,
    requirements: str = _REQUIREMENTS,
    comment_id: int | None = _COMMENT_ID,
) -> review_subjects.ReviewSubject:
    return review_subjects.ReviewSubject(
        pr_number=_PR_NUMBER,
        commit=commit,
        requirements_revision=requirements,
        report=review_subjects.ReviewReport(
            text=_REPORT,
            report_revision=_REVISION,
            content_revision=_DIGEST,
            source_sha=_REPORT_HEAD,
            requirements_revision=_REQUIREMENTS,
            location=ReportLocation(pr_number=_PR_NUMBER, comment_id=comment_id),
        ),
    )


def _prompt(subject: review_subjects.ReviewSubject | None) -> str:
    return review_prompts._build_review_prompt(
        _TEST_SPEC,
        make_issue(_ISSUE_NUMBER, title="add a foo flag", body=_ISSUE_BODY),
        "",
        [_TEST_SPEC],
        review_prompts.ReviewHandover(subject=subject),
    )


def _ordered(prompt: str, *fragments: str) -> bool:
    """Whether every fragment is in the prompt, each after the one before it."""
    at = [prompt.find(fragment) for fragment in fragments]
    return -1 not in at and at == sorted(at)


class ReviewPromptReportTest(unittest.TestCase):
    """What the reviewer's prompt says about the report it is handed."""

    def test_the_report_is_quoted_whole(self) -> None:
        # The heading names what the report is and where it was read, and
        # every line follows it as one quoted block, in order -- between the
        # issue and the inspection commands. With nothing moved since it was
        # written there is no note saying otherwise, and no outcome marker of
        # the developer's.
        prompt = _prompt(_subject())
        quoted = "\n".join(f"> {line}" for line in _REPORT_LINES)

        self.assertIn(f"\n{quoted}\n", prompt)
        self.assertTrue(_ordered(
            prompt, _ISSUE_BODY, _COMPLETE_AND_CURRENT, quoted, _INSPECTION,
        ))
        for fragment in (
            f"revision {_REVISION}",
            f"PR #{_PR_NUMBER}, comment {_COMMENT_ID}",
            f"commit `{_REPORT_HEAD}`",
            f"requirements revision `{_REQUIREMENTS}`",
            "rather than fetching the pull request for another",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, prompt)
        for absent in (
            _EDITED_NOTE, _REPORT_READY_MARKER, _REPORT_VERIFIED_MARKER,
        ):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, prompt)

    def test_it_says_what_moved_since_the_report(self) -> None:
        # A thread that moved on since the report -- the reply that bought
        # this round -- is named, and a report verified on the description
        # says it was read there.
        prompt = _prompt(_subject(
            requirements=_EDITED_REQUIREMENTS,
            comment_id=None,
        ))

        self.assertIn(_EDITED_NOTE, prompt)
        self.assertIn(f"PR #{_PR_NUMBER}, its description", prompt)

    def test_no_report_is_said_to_be_none(self) -> None:
        no_report = review_subjects.ReviewSubject(
            pr_number=_PR_NUMBER,
            commit=_REPORT_HEAD,
            requirements_revision=_REQUIREMENTS,
        )
        for name, subject in (("no subject", None), ("no report", no_report)):
            with self.subTest(name):
                prompt = _prompt(subject)
                self.assertTrue(_ordered(prompt, _NO_REPORT, _INSPECTION))
                self.assertNotIn(_COMPLETE_AND_CURRENT, prompt)


if __name__ == "__main__":
    unittest.main()
