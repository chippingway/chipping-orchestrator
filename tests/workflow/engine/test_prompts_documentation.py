# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Prompt builder for the documentation stage: the contract it teaches the
agent is the one `_parse_documentation_verdict` then enforces, so the prompt
has to name the machine-readable marker and say outright that the prose
alternative will be parked."""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import prompts
from tests.support.fakes import make_issue
from tests.workflow.fixtures import _TEST_SPEC

_DOCUMENTATION_ISSUE_NUMBER = 67100


def _documentation_prompt() -> str:
    return prompts._build_documentation_prompt(
        _TEST_SPEC,
        make_issue(
            _DOCUMENTATION_ISSUE_NUMBER,
            title="add foo flag",
            body="users want a foo flag",
        ),
        comments_text="",
        specs=[_TEST_SPEC],
    )


class BuildDocumentationPromptTest(unittest.TestCase):
    """The documentation prompt is what teaches the agent the contract
    the parser relies on. Verify the contract is actually communicated:
    diff vs stable docs (README and `docs/` only -- the `plans/` tree
    and roadmap entries are working notes owned by humans and the
    prompt must steer the agent away from them), a repo-local (NOT
    forced `docs:`) commit subject for the update branch, explicit
    `DOCS: NO_CHANGE` marker for the no-update branch, and a refusal to
    accept ambiguous phrasing.
    """

    def test_one_prompt_carries_the_whole_contract(self) -> None:
        prompt = _documentation_prompt()

        self.assertIn(f"#{_DOCUMENTATION_ISSUE_NUMBER}", prompt)
        self.assertIn("add foo flag", prompt)
        self.assertIn("DOCS: NO_CHANGE", prompt)
        self._assert_it_diffs_against_readme_and_docs(prompt)
        self._assert_it_steers_away_from_plans(prompt)
        self._assert_it_leaves_the_subject_repo_local(prompt)
        self._assert_it_warns_against_ambiguous_prose(prompt)

    def _assert_it_diffs_against_readme_and_docs(self, prompt: str) -> None:
        base_ref = f"{_TEST_SPEC.remote_name}/{_TEST_SPEC.base_branch}"

        self.assertIn("README.md", prompt)
        self.assertIn("docs/", prompt)
        self.assertIn(f"git diff {base_ref}...HEAD", prompt)

    def _assert_it_steers_away_from_plans(self, prompt: str) -> None:
        # `plans/` and roadmap entries are working notes owned by
        # humans -- the final-docs pass must not target them. The prompt
        # has to call that out explicitly so the agent does not infer
        # `plans/` from convention.
        self.assertIn("plans/", prompt)
        self.assertIn("roadmap", prompt)
        self.assertIn("out of scope", prompt)

    def _assert_it_leaves_the_subject_repo_local(self, prompt: str) -> None:
        # The docs pass must not force the `docs:` Conventional-Commit type:
        # the agent mirrors the repo's own recent commit style (pinned in
        # `test_prompts.py`), so a project-specific prefix (`event:`,
        # `career:`, ...) is allowed for a documentation update just as for
        # any other commit.
        self.assertNotIn("docs:", prompt)
        self.assertNotIn('git commit -m "docs: <subject>"', prompt)

    def _assert_it_warns_against_ambiguous_prose(self, prompt: str) -> None:
        # The prompt itself must tell the agent that prose like
        # 'no changes needed' will be parked, mirroring the parser's
        # refusal to accept it.
        self.assertIn("'no changes needed'", prompt)
