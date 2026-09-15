# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The `develop` skill's model-facing trigger anchor must name an action the
implementer prompt actually performs.

Claude decides whether to pull a skill from its `description` frontmatter, not
its body. The implementer prompt tells the agent to COMMIT and explicitly NOT
to push or open the PR (the orchestrator does that), so an anchor phrased around
"opening a PR" points at an action the developer never takes and the skill goes
unused -- the low `develop` trigger rate. These tests pin the anchor to
committing and pin the implementer prompt to the commit-not-push contract it
must stay aligned with, so the two cannot silently drift back apart.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import prompts
from tests.repository.skill_metadata_test_support import frontmatter_field, skill_paths
from tests.support.fakes import make_issue
from tests.workflow.fixtures import _TEST_SPEC

_DEVELOP_SKILLS = skill_paths("develop")


class DevelopSkillTriggerAnchorTest(unittest.TestCase):
    def test_anchor_names_commit_not_pr(self) -> None:
        for path in _DEVELOP_SKILLS:
            desc = frontmatter_field(
                path.read_text(encoding="utf-8"), "description",
            ).lower()
            with self.subTest(path=str(path)):
                # The action every developer run actually performs.
                self.assertIn("commit", desc)
                # Actions the implementer is forbidden to take must not be
                # advertised as the trigger, or the skill goes unused.
                self.assertNotIn("opening a pr", desc)
                self.assertNotIn("open a pr", desc)
                self.assertNotIn("push", desc)

    def test_implementer_prompt_matches_anchor(self) -> None:
        prompt = prompts._build_implement_prompt(
            _TEST_SPEC, make_issue(1), "", [_TEST_SPEC],
        )
        # The prompt drives the agent to commit -- the anchor's verb -- while
        # forbidding the push / open-PR action the anchor must never name.
        self.assertIn("COMMIT", prompt)
        self.assertIn("Do NOT push", prompt)
        self.assertIn("orchestrator pushes and opens the PR", prompt)


if __name__ == "__main__":
    unittest.main()
