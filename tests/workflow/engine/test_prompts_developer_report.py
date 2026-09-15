# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer report contract, as every developer prompt teaches it.

The developer writes the report and the orchestrator publishes it, routinely
and without asking anybody, and a report that needs no repository change needs
no commit. Every prompt a developer finishes work on carries that contract
whole -- resumes too, since a resumed transcript may predate it -- and the two
outcomes it spells are the ones `report_outcomes` accepts. A prompt that still
offers `ACK:` offers it only for a reply whose report needs no change either.
A fresh respawn's preamble defers the outcome to the task below it, and the
prompts that close on a marker of their own teach no report at all.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    conversation_prompts as _conversation_prompts,
    drift,
    prompt_notes as _prompt_notes,
    prompts,
    report_outcomes,
)
from orchestrator.workflow.engine.report_outcome_models import (
    _REPORT_END_MARKER,
    _REPORT_READY_MARKER,
    _REPORT_VERIFIED_MARKER,
    _ReadyReport,
    _ReportLocation,
    _VerifiedReport,
)
from orchestrator.workflow.stages.decomposition import late_revision as _late_revision
from tests.support.fakes import FakeComment, FakeUser, make_issue
from tests.workflow.fixtures import _TEST_SPEC

_ISSUE_NUMBER = 67300
_REPORT_PLACEHOLDER = "<complete report>"
_READY_TEMPLATE = (
    f"  {_REPORT_READY_MARKER}\n  {_REPORT_PLACEHOLDER}\n  {_REPORT_END_MARKER}"
)
_VERIFIED_TEMPLATE = f"  {_REPORT_VERIFIED_MARKER} <location> <revision>"
_REPORT = "Adds the foo flag; verified with the foo tests."
_SLUG = "chippingway/orchestrator"
_PULL_NUMBER = 1697
_COMMENT_ID = 5579567555
_COMMENT_URL = f"https://github.com/{_SLUG}/pull/{_PULL_NUMBER}#issuecomment-{_COMMENT_ID}"
_DIGEST = "0123456789abcdef" * 4
_BASE_REF = "origin/main"
_DRIFT_ACK = "  ACK: <one-line justification>\n"
_UNCHANGED_REPORT = "nothing your report says has to change"


def _issue():
    return make_issue(
        _ISSUE_NUMBER, title="add a foo flag", body="users want a foo flag",
    )


def _developer_prompts() -> dict[str, str]:
    """Every prompt a developer session may finish its work on."""
    comments = [
        FakeComment(
            id=1, body="please describe how this was tested", user=FakeUser("alice"),
        ),
    ]
    return {
        "initial": prompts._build_implement_prompt(
            _TEST_SPEC, _issue(), "", [_TEST_SPEC],
        ),
        "automated_fix": prompts._build_fix_prompt("1. The report omits testing."),
        "requirements_drift": drift._build_user_content_change_prompt(_issue(), ""),
        "late_revision": _late_revision._revision_prompt(_issue(), tuple(comments)),
        "pr_feedback": _conversation_prompts._build_pr_comment_followup(comments),
        "human_reply_resume": _conversation_prompts._build_human_reply_followup(
            comments,
        ),
        "continue_retry_resume": _prompt_notes._DEVELOPER_CONTINUE_RETRY_PROMPT,
    }


class DeveloperReportContractTest(unittest.TestCase):
    """What the contract says, where it is said, and that its outcomes parse."""

    def test_every_developer_prompt_carries_it(self) -> None:
        for name, prompt in _developer_prompts().items():
            with self.subTest(prompt=name):
                self.assertIn(_prompt_notes._DEVELOPER_REPORT_NOTE, prompt)

    def test_it_names_ownership_and_outcomes(self) -> None:
        for fragment in (
            "you write it, and the orchestrator publishes it",
            "routine orchestrator work that needs no permission",
            "do NOT ask a human whether or how to publish",
            "Never create an empty commit",
            "delivered with no commit at all",
            "each alone on its own line and outside any code fence",
            _READY_TEMPLATE,
            "End with this single line, outside any code fence",
            _VERIFIED_TEMPLATE,
            "https://github.com/<owner>/<repo>/pull/<number>",
            "#issuecomment-<id>",
            "`sha256:` followed by the 64 lowercase hex digits",
            "never shares a message with an `ACK:` line",
            "emit neither outcome and end with your question",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, _prompt_notes._DEVELOPER_REPORT_NOTE)

    def test_taught_outcomes_are_parser_outcomes(self) -> None:
        verified_line = _VERIFIED_TEMPLATE.replace("<location>", _COMMENT_URL)
        # The report replaces its placeholder line whole: the indent the prompt
        # sets it off with is the prompt's, and the report keeps its own.
        ready_block = _READY_TEMPLATE.replace(f"  {_REPORT_PLACEHOLDER}", _REPORT)
        taught = {
            ready_block: _ReadyReport(_REPORT),
            verified_line.replace("<revision>", f"sha256:{_DIGEST}"): _VerifiedReport(
                _ReportLocation(_SLUG, _PULL_NUMBER, _COMMENT_ID), _DIGEST,
            ),
        }
        for message, outcome in taught.items():
            with self.subTest(message=message):
                self.assertEqual(
                    report_outcomes._parse_report_outcome(message), outcome,
                )

    def test_ack_waits_for_an_unchanged_report(self) -> None:
        # The ACK outcome survives beside the report contract on the routes
        # that offer it, spelled as its reader expects, and only for a reply
        # after which the report needs no change either: a requirements change
        # can leave the code as it is and still change what the report says.
        developer_prompts = _developer_prompts()
        acknowledgements = {
            "requirements_drift": (_DRIFT_ACK, _UNCHANGED_REPORT),
            "late_revision": (
                _DRIFT_ACK,
                _UNCHANGED_REPORT,
                "never in the same message as a report outcome",
            ),
            "pr_feedback": (
                "`ACK: <brief reason>`",
                "neither the branch nor your report has to change",
            ),
        }
        for name, fragments in acknowledgements.items():
            for fragment in fragments:
                with self.subTest(prompt=name, fragment=fragment):
                    self.assertIn(fragment, developer_prompts[name])


class RespawnAndStagePromptTest(unittest.TestCase):
    """A fresh respawn restates ownership without claiming the task's ending,
    and a prompt that closes on its own marker teaches no report."""

    def test_respawn_preamble_defers_the_outcome(self) -> None:
        preamble = prompts._build_fresh_respawn_preamble(
            _TEST_SPEC, _issue(), "", [_TEST_SPEC],
        )
        self.assertIn(_prompt_notes._RESPAWN_REPORT_NOTE, preamble)
        self.assertNotIn(_prompt_notes._DEVELOPER_REPORT_NOTE, preamble)
        for fragment in (
            "Wherever the task below asks for your completion report",
            "the previous session's commits included",
            "the orchestrator publishes it as routine work",
            "no permission to ask for",
            "no empty commit",
            _REPORT_READY_MARKER,
            _REPORT_END_MARKER,
            _REPORT_VERIFIED_MARKER,
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, _prompt_notes._RESPAWN_REPORT_NOTE)

    def test_marker_closed_prompts_teach_no_report(self) -> None:
        closing_prompts = {
            "documentation": prompts._build_documentation_prompt(
                _TEST_SPEC, _issue(), "", [_TEST_SPEC],
            ),
            "review": prompts._build_review_prompt(
                _TEST_SPEC, _issue(), "", [_TEST_SPEC],
            ),
            "conflict": prompts._build_conflict_resolution_prompt(
                _BASE_REF, ["a.rs"],
            ),
        }
        for name, prompt in closing_prompts.items():
            with self.subTest(prompt=name):
                self.assertNotIn(_REPORT_READY_MARKER, prompt)
                self.assertNotIn(_REPORT_VERIFIED_MARKER, prompt)


if __name__ == "__main__":
    unittest.main()
