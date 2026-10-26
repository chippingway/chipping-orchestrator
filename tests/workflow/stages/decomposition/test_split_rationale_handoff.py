# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a split parent's developer is handed of the rationale its split recorded.

A parent that is no umbrella goes back to its own work once every child is
done, and the decomposer's rationale is where the split named the residual
scope that work owes. Its developer prompts quote it in an attributed section
of their own, read off the parent's record rather than out of the bounded
thread excerpt, so it reaches the first spawn and any session that replaces
it however far back the split summary sits. A record holding nothing usable,
an umbrella's, and one whatever superseded the split cleared hand nothing.
"""
from __future__ import annotations

import json
import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.decomposition import blocked as _blocked
from orchestrator.workflow.stages.implementing import (
    handler as _implementing,
    resume as _resume,
    resume_request as _resume_request,
)
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    LABEL_DONE,
    LABEL_IMPLEMENTING,
    LABEL_READY,
    _agent,
    _manifest,
)
from tests.workflow.stages.decomposition import late_restart_support as _restart
from tests.workflow.stages.decomposition.decomposing_test_support import _DecomposingWorkflowMixin

KEY_SPLIT_RATIONALE = "split_rationale"
KEY_SPLIT_ATTEMPT = "split_attempt"
KEY_UMBRELLA = "umbrella"
KEY_SILENT_PARK_COUNT = "silent_park_count"
PARENT_NUMBER = 94
DECOMPOSER_SESSION = "dec-sess"
DEV_SESSION = "dev-sess"
REPLACEMENT_SESSION = "dev-sess-fresh"
FOLLOWUP = "address the review feedback"

# The silent-park streak that retires a developer session.
SILENT_STREAK = 2

# The account the split keeps for the parent's own pass, built to escape a
# careless quote: a fence line, an HTML comment opener, an orchestrator
# marker, and lines ended by a bare carriage return and by CRLF.
RATIONALE = (
    "Split the API from its docs.\n"
    "The parent keeps the release notes and the settings change for its own pass.\r"
    "```\n"
    "<!-- not a comment here\r\n"
    "<!--orchestrator-comment-->\n"
    "The last line."
)

_SLICES = (
    {"title": "API", "body": "the api", "depends_on": []},
    {"title": "Docs", "body": "the docs", "depends_on": [0]},
)

# What the section a developer prompt quotes the rationale in opens with.
_SECTION = "Decomposer split rationale ("

# What every split summary opens with, which none of these prompts may carry:
# the excerpt is bounded, and the summary is long past by the time the parent
# implements.
_SUMMARY = ":bookmark_tabs: decomposer split this into"

# The orchestrator notices that land on the parent after its summary: enough
# of them, each long enough, to carry the summary out of a 4000-character
# excerpt.
_NOTICES = 5
_NOTICE_REPEATS = 20
_NOTICE = "held: a child of this parent is still in flight. " * _NOTICE_REPEATS

_SINGLE = _manifest('{"decision": "single", "rationale": "it fits one pass after all"}')

# What a parent whose children all finished still records of its split
# beside the rationale.
_HANDED_BACK = MappingProxyType({"children": [941, 942], KEY_UMBRELLA: False})

# Records whose rationale no developer is handed: nothing a reader can use as
# text, or an umbrella's, which keeps no work of its own.
_WITHHELD = MappingProxyType({
    "missing": {},
    "null": {KEY_SPLIT_RATIONALE: None},
    "blank": {KEY_SPLIT_RATIONALE: " \n\t "},
    "number": {KEY_SPLIT_RATIONALE: 42},
    "list": {KEY_SPLIT_RATIONALE: [RATIONALE]},
    "object": {KEY_SPLIT_RATIONALE: {"why": RATIONALE}},
    "umbrella": {KEY_SPLIT_RATIONALE: RATIONALE, KEY_UMBRELLA: True},
})

# A baseline the edited body no longer hashes to.
STALE_HASH = "stale-hash"


def _quoted(rationale: str) -> str:
    """The rationale as the section quotes it: every line, whatever ends it, prefixed `> `."""
    return "".join(f"> {line}" for line in rationale.splitlines(keepends=True))


def _spawned_prompt(run_agent: MagicMock) -> str:
    """The prompt the one developer run was spawned with."""
    run_agent.assert_called_once()
    return run_agent.call_args.args[1]


class _HandoffCase(unittest.TestCase, _DecomposingWorkflowMixin):
    """A parent the developer is about to be spawned on, and what it is handed."""

    def _assert_handed(self, prompt: str) -> None:
        """The prompt quotes `RATIONALE` whole, in the attributed section between the issue body and the thread."""
        before, section, after = prompt.partition(_SECTION)
        self.assertTrue(section, "the rationale is quoted under its own heading")
        self.assertTrue(before.endswith("\n\n"), "the section stands apart from the issue body")
        self.assertIn("Issue body:\n", before)
        self.assertIn(f"{_quoted(RATIONALE)}\n\nConversation so far:\n", after, "quoted whole, ahead of the thread")
        self.assertEqual(prompt.count(_SECTION), 1)
        self.assertNotIn(_SUMMARY, prompt, "the summary is outside the excerpt, so the section is all that carries it")

    def _assert_withheld(self, prompt: str) -> None:
        """The prompt carries no rationale section and none of the recorded words."""
        self.assertNotIn(_SECTION, prompt)
        self.assertNotIn("release notes", prompt)

    def _implemented(self, gh: FakeGitHubClient, issue: FakeIssue) -> str:
        """Hand a `ready` issue to implementation, and answer the prompt its developer was spawned with."""
        run_agent = MagicMock(return_value=_agent(session_id=DEV_SESSION))
        self._run(lambda: _blocked._handle_ready(gh, _TEST_SPEC, issue), run_agent=run_agent)
        return _spawned_prompt(run_agent)


class HandedBackParentTest(_HandoffCase):
    """A parent whose children all finished is handed the scope its split kept, off its own record."""

    def test_its_implementer_is_handed_the_scope(self) -> None:
        gh, parent = self._handed_back()

        prompt = self._implemented(gh, parent)

        self._assert_handed(prompt)
        self.assertIsNone(gh.pinned_data(PARENT_NUMBER).get(KEY_SPLIT_ATTEMPT), "the hand-back retired the attempt")
        for child in gh.created_child_issues:
            with self.subTest(child=child.number):
                self.assertNotIn(KEY_SPLIT_RATIONALE, gh.pinned_data(child.number), "read off the parent, not copied")

    def test_a_replacement_session_is_handed_it_again(self) -> None:
        # The silent-park streak retires the first session, so the next
        # resume is a fresh conversation re-grounded from the record, not
        # from the transcript that held the first spawn's section.
        gh, parent = self._handed_back()
        self._implemented(gh, parent)
        state = gh.read_pinned_state(parent)
        state.set(KEY_SILENT_PARK_COUNT, SILENT_STREAK)
        run_agent = MagicMock(return_value=_agent(session_id=REPLACEMENT_SESSION))

        self._run(
            lambda: _resume._resume_dev_with_text(
                _resume_request._DevResumeRequest(gh, _TEST_SPEC, parent, state, FOLLOWUP),
            ),
            run_agent=run_agent,
        )

        prompt = _spawned_prompt(run_agent)
        self.assertIsNone(run_agent.call_args.kwargs["options"].resume_session_id, "a fresh conversation, not a resume")
        self.assertIn("You are resuming work on GitHub issue", prompt)
        self._assert_handed(prompt)
        self.assertTrue(prompt.endswith(FOLLOWUP), "the stage's own instruction follows the re-grounding")

    def _handed_back(self) -> tuple[FakeGitHubClient, FakeIssue]:
        """A parent split with `RATIONALE`, every child done, handed back to `ready` with its summary long past."""
        gh = FakeGitHubClient()
        parent = make_issue(PARENT_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(parent)
        payload = {"decision": "split", KEY_UMBRELLA: False, "rationale": RATIONALE, "children": list(_SLICES)}
        decomposer = _agent(session_id=DECOMPOSER_SESSION, last_message=_manifest(json.dumps(payload)))
        self._run_decomposing(gh, parent, run_agent=decomposer)
        self.assertEqual(gh.workflow_label(parent), LABEL_BLOCKED)
        self._post_notices(gh, parent)
        for child in gh.created_child_issues:
            gh.apply_foreign_label(child, LABEL_DONE)

        self._run(lambda: _blocked._handle_blocked(gh, _TEST_SPEC, parent), run_agent=_agent())

        self.assertEqual(gh.workflow_label(parent), LABEL_READY)
        return gh, parent

    def _post_notices(self, gh: FakeGitHubClient, parent: FakeIssue) -> None:
        """Orchestrator notices posted after the summary, which count as no requirements edit."""
        state = gh.read_pinned_state(parent)
        for _ in range(_NOTICES):
            _comments._post_issue_comment(gh, parent, state, _NOTICE)
        gh.write_pinned_state(parent, state)


class WithheldRationaleTest(_HandoffCase):
    """A parent whose developer is handed nothing of a split: no usable text, an umbrella's, or a superseded one."""

    def test_an_unusable_record_hands_nothing(self) -> None:
        for case, recorded in _WITHHELD.items():
            with self.subTest(record=case):
                gh = FakeGitHubClient()
                parent = make_issue(PARENT_NUMBER, label=LABEL_READY)
                gh.add_issue(parent)
                gh.seed_state(parent, **{**_HANDED_BACK, **recorded})

                self._assert_withheld(self._implemented(gh, parent))

    def test_a_superseding_edit_withholds_it(self) -> None:
        # The edit reroutes the handed-back parent to decomposition, which
        # clears the account, and the decomposer then keeps the issue whole.
        gh = FakeGitHubClient()
        parent = make_issue(PARENT_NUMBER, label=LABEL_READY, body="the requirements as edited")
        gh.add_issue(parent)
        gh.seed_state(parent, **_HANDED_BACK, split_rationale=RATIONALE, user_content_hash=STALE_HASH)
        self._run(lambda: _blocked._handle_ready(gh, _TEST_SPEC, parent), run_agent=_agent())
        self.assertEqual(gh.workflow_label(parent), LABEL_DECOMPOSING)
        self._run_decomposing(gh, parent, run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=_SINGLE))
        self.assertEqual(gh.workflow_label(parent), LABEL_READY)

        self._assert_withheld(self._implemented(gh, parent))


class RestartedIssueTest(_restart.RestartCase, _HandoffCase):
    """A restart straight into implementation hands its first developer no earlier split's account."""

    def test_the_fresh_cycle_is_handed_none(self) -> None:
        self._seed(**_restart.CARRIED_OVER, split_rationale=RATIONALE)
        with patch("orchestrator.config.DECOMPOSE", False):
            self._reported_route()
        self.assertEqual(self._labels(), ((self.issue.number, LABEL_IMPLEMENTING),))
        run_agent = MagicMock(return_value=_agent(session_id=DEV_SESSION))

        self._run(
            lambda: _implementing._handle_implementing(self.github, _TEST_SPEC, self.issue),
            run_agent=run_agent,
        )

        self._assert_withheld(_spawned_prompt(run_agent))


if __name__ == "__main__":
    unittest.main()
