# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The `decompose` skill is one definition both roots load, its trigger
anchor names what both decomposition prompts actually ask for, and its sizing
policy is the one the initial prompt hands the agent.

A harness pulls a skill on its `description` frontmatter, not its body. The
initial decomposer and the late adjudicator both size a change, decide single
versus split, and plan child issues, so the anchor is pinned to those shared
actions and to neither stage's manifest fence: the two fences are different
contracts, and an anchor naming one would point the other stage at the wrong
block. Neither run may commit, push, or open a pull request, so an anchor
advertising any of those names an action the agent never takes.

The active prompt wins over the skill, so a sizing rule changed in one and not
the other leaves the agent reading two policies and following the prompt's.
Both are held to the same scope-and-effort wording here, neither may let a
file or commit count decide a split, and the skill keeps the safeguards and
the late addition budget that wording must not loosen. These checks read the
instructions an agent is given; they do not judge any decision it makes.
"""
from __future__ import annotations

import re
import unittest
from itertools import product
from pathlib import Path

from orchestrator.skills import discovery
from orchestrator.workflow.engine import decomposition_prompts as _decomposition_prompts
from orchestrator.workflow.stages.decomposition import late_prompt as _late_prompt
from tests.repository.skill_metadata_test_support import REPO_ROOT, frontmatter_field, skill_paths
from tests.support.fakes import make_issue
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.decomposition.late_test_support import late_generation

_SKILL_NAME = "decompose"
_ENCODING = "utf-8"
_PROJECT_LEVEL = "project"
_ISSUE_NUMBER = 1

# Lowercase stems naming the actions both prompts ask for, which the
# description has to name too.
_ACTION_ANCHORS = ("decompose", "single", "split", "child issues")

# Each stage's own fence. The description names neither, because the manifest
# a run emits is whichever one its active prompt requires.
_STAGE_FENCES = ("orchestrator-manifest", "orchestrator-late-manifest")

# Actions a decomposition run is forbidden to take.
_FORBIDDEN_ACTIONS = ("commit", "push", "open a pr", "opening a pr", "pull request")

# The read-only instruction both prompts carry, which the forbidden list mirrors.
_READ_ONLY_RULE = "MUST NOT commit, push"

# A file or commit count standing in as a split trigger, however it is spelled.
_COUNT_CUTOFF = re.compile(
    r"(?:more than|over|exceeds?|approximately|~)[\s~-]*"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)[\s-]+"
    r"(?:logical\s+)?(?:files?|commits?)\b"
    r"|\b(?:\d+|five)-file\b",
    re.IGNORECASE,
)

# Spellings the cutoff pattern has to catch, so a guard that matches nothing
# cannot pass vacuously.
_COUNT_CUTOFF_SPELLINGS = (
    "if the change touches more than ~5 files",
    "needs more than one logical commit",
    "under the prompt's approximately-five-file heuristic",
    "The five-file heuristic does not apply",
)

# Lowercase sizing wording the skill and the initial prompt both carry: the
# complete deliverable judged by behaviors, coupling, and verification effort,
# counts that never decide alone, meaningful boundaries, coarser groupings, the
# child limit as a ceiling, residual parent work in one context, and the final
# check that valid JSON does not make a valid manifest.
_SHARED_SIZING = (
    "complete deliverable",
    "distinct behaviors",
    "coupled",
    "effort needed to verify",
    "neither decides single versus split on its own",
    "meaningful deliverable boundaries",
    "coarser groupings",
    "a different file, owner, layer, or display",
    "a ceiling, not a target",
    "fit one context",
    "valid json",
    "explicit `depends_on` array",
)

# Skill wording for the safeguards scope-based sizing must not loosen: the
# completion closure, the transitive residual test, sibling ownership, parent
# coverage, and the late stage's addition budget and explained `single`.
_SKILL_SAFEGUARDS = (
    "checks-only",
    "mechanical documentation cleanup",
    "direct and transitive",
    "unique acceptance criterion",
    "predicted non-empty diff",
    "duplicate semantic ownership",
    "exactly once",
    '"umbrella": true',
    "`estimated_added_lines`",
    "strictly below the ceiling",
    "headroom for review fixes",
    "never replaces or loosens this budget",
    "dependency-ordered slices",
    "`split_blocker`",
)


def _description(path: Path) -> str:
    return frontmatter_field(path.read_text(encoding=_ENCODING), "description").lower()


def _skill_text() -> str:
    """The canonical definition both roots resolve to."""
    return skill_paths(_SKILL_NAME)[0].read_text(encoding=_ENCODING)


def _stage_prompts() -> dict[str, str]:
    """Both decomposition prompts, built for one local issue."""
    issue = make_issue(_ISSUE_NUMBER)
    return {
        "initial": _decomposition_prompts._build_decompose_prompt(
            _TEST_SPEC, issue, "", [_TEST_SPEC],
        ),
        "late": _late_prompt._build_late_decompose_prompt(
            _TEST_SPEC, issue, "", late_generation(), [_TEST_SPEC],
        ),
    }


class DecomposeSkillDefinitionTest(unittest.TestCase):
    """Both roots carry one canonical definition that discovery reports once."""

    def test_claude_entry_links_to_the_agents_file(self) -> None:
        # A file symlink rather than a copy or a linked directory, so either
        # root reads one text and the two cannot drift apart; relative, so it
        # resolves in every checkout and worktree.
        agents_path, claude_path = skill_paths(_SKILL_NAME)
        self.assertFalse(agents_path.is_symlink())
        self.assertFalse(claude_path.parent.is_symlink())
        self.assertTrue(claude_path.is_symlink())
        self.assertFalse(claude_path.readlink().is_absolute())
        self.assertEqual(
            claude_path.resolve(strict=True), agents_path.resolve(strict=True),
        )

    def test_both_roots_carry_the_same_definition(self) -> None:
        agents_path, claude_path = skill_paths(_SKILL_NAME)
        agents_text = agents_path.read_text(encoding=_ENCODING)
        self.assertEqual(claude_path.read_text(encoding=_ENCODING), agents_text)
        for path in (agents_path, claude_path):
            with self.subTest(path=str(path)):
                self.assertEqual(
                    frontmatter_field(path.read_text(encoding=_ENCODING), "name"),
                    _SKILL_NAME,
                )

    def test_local_discovery_reports_it_once(self) -> None:
        # Each root lists the skill on its own; the scan across both reports
        # the name once, as the repository's own definition. A project
        # definition shadows any same-named global one, so an operator's
        # installed skills cannot change this answer.
        for root in discovery._SKILL_ROOTS:
            with self.subTest(root=root):
                self.assertIn(
                    _SKILL_NAME, discovery._direct_skill_names(REPO_ROOT / root),
                )
        sources = discovery.discover_local_skill_sources(REPO_ROOT)
        self.assertEqual(
            [source for source in sources if source.name == _SKILL_NAME],
            [discovery.SkillSource(_SKILL_NAME, _PROJECT_LEVEL)],
        )


class DecomposeSkillTriggerAnchorTest(unittest.TestCase):
    """The description names the actions both prompts ask for and none they forbid."""

    def test_prompts_ask_for_the_anchored_actions(self) -> None:
        for (stage, prompt), anchor in product(_stage_prompts().items(), _ACTION_ANCHORS):
            with self.subTest(stage=stage, anchor=anchor):
                self.assertIn(anchor, prompt.lower())

    def test_anchor_names_the_shared_actions(self) -> None:
        for path, anchor in product(skill_paths(_SKILL_NAME), _ACTION_ANCHORS):
            with self.subTest(path=str(path), anchor=anchor):
                self.assertIn(anchor, _description(path))

    def test_anchor_defers_to_the_active_manifest(self) -> None:
        for path, fence in product(skill_paths(_SKILL_NAME), _STAGE_FENCES):
            with self.subTest(path=str(path), fence=fence):
                self.assertIn("manifest", _description(path))
                self.assertNotIn(fence, _description(path))

    def test_anchor_advertises_no_forbidden_action(self) -> None:
        for path, action in product(skill_paths(_SKILL_NAME), _FORBIDDEN_ACTIONS):
            with self.subTest(path=str(path), action=action):
                self.assertNotIn(action, _description(path))
        for stage, prompt in _stage_prompts().items():
            with self.subTest(stage=stage):
                self.assertIn(_READ_ONLY_RULE, prompt)


class DecomposeSizingPolicyTest(unittest.TestCase):
    """The skill and the initial prompt size by scope and effort, never by a count."""

    def test_no_count_decides_a_split(self) -> None:
        for spelling in _COUNT_CUTOFF_SPELLINGS:
            with self.subTest(spelling=spelling):
                self.assertRegex(spelling, _COUNT_CUTOFF)
        for source, text in (("skill", _skill_text()), *_stage_prompts().items()):
            with self.subTest(source=source):
                self.assertIsNone(_COUNT_CUTOFF.search(text))

    def test_skill_and_prompt_share_sizing_policy(self) -> None:
        prompt = _stage_prompts()["initial"].lower()
        sources = (("skill", _skill_text().lower()), ("initial", prompt))
        for (source, text), wording in product(sources, _SHARED_SIZING):
            with self.subTest(source=source, wording=wording):
                self.assertIn(wording, text)

    def test_skill_keeps_safeguards_and_late_budget(self) -> None:
        skill_text = _skill_text()
        for safeguard in _SKILL_SAFEGUARDS:
            with self.subTest(safeguard=safeguard):
                self.assertIn(safeguard, skill_text)


if __name__ == "__main__":
    unittest.main()
