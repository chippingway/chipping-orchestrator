# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Base-ref catalog collection, its record shape, and the tick that drives it."""
from __future__ import annotations

import tempfile
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.skills import catalog
from orchestrator.workflow.engine import issue_processing as _issue_processing, tick as _engine_tick
from tests.skills.skills_test_support import (
    _capture_analytics_records,
    _catalog_identity,
    _completed,
    _spec,
)

_TEST_REPO_SLUG = "chippingway/orchestrator"
_REFRESH_BASE = "_refresh_base_and_worktrees"
_TEST_BASE_BRANCH = "main"
_TEST_REMOTE_NAME = "origin"
_DEVELOP_SKILL = "develop"
_REVIEW_SKILL = "review"
_AGENT_SKILLS_ROOT = ".agents/skills"
_AGENT_DEVELOP_SKILL_PATH = ".agents/skills/develop/SKILL.md"
_AGENT_REVIEW_SKILL_PATH = ".agents/skills/review/SKILL.md"
_CLAUDE_REVIEW_SKILL_PATH = ".claude/skills/review/SKILL.md"
_PROJECT_LEVEL = "project"
_SKILLS_AVAILABLE_FIELD = "skills_available"
_LIST_SKILL_TREE_METHOD = "_list_skill_tree"
_RECORD_CATALOG_METHOD = "record_repo_skill_catalog"
_BAD_REF_EXIT_CODE = 128


class ExtractSkillCatalogTest(unittest.TestCase):
    """`_extract_skill_catalog` keeps only direct `<root>/<name>/SKILL.md`
    definitions, dedupes by name across roots, and preserves source paths.
    """

    def test_agents_extraction(self) -> None:
        # `.agents/skills/<name>/SKILL.md` definitions are extracted; the
        # name is the single segment between the root and the SKILL.md file.
        paths = [
            _AGENT_DEVELOP_SKILL_PATH,
            _AGENT_REVIEW_SKILL_PATH,
        ]
        skills, skill_paths = catalog._extract_skill_catalog(paths)
        self.assertEqual(skills, [_DEVELOP_SKILL, _REVIEW_SKILL])
        self.assertEqual(
            skill_paths,
            {
                _DEVELOP_SKILL: [_AGENT_DEVELOP_SKILL_PATH],
                _REVIEW_SKILL: [_AGENT_REVIEW_SKILL_PATH],
            },
        )

    def test_claude_extraction(self) -> None:
        # `.claude/skills/<name>/SKILL.md` definitions are extracted the
        # same way as the `.agents` root.
        paths = [
            ".claude/skills/verify/SKILL.md",
            ".claude/skills/run/SKILL.md",
        ]
        skills, skill_paths = catalog._extract_skill_catalog(paths)
        self.assertEqual(skills, ["run", "verify"])
        self.assertEqual(
            skill_paths,
            {
                "run": [".claude/skills/run/SKILL.md"],
                "verify": [".claude/skills/verify/SKILL.md"],
            },
        )

    def test_cross_root_dedupe(self) -> None:
        # A skill defined under both roots appears once in the names list,
        # but every source path that produced it is preserved (sorted).
        paths = [
            _CLAUDE_REVIEW_SKILL_PATH,
            _AGENT_REVIEW_SKILL_PATH,
            _AGENT_DEVELOP_SKILL_PATH,
        ]
        skills, skill_paths = catalog._extract_skill_catalog(paths)
        self.assertEqual(skills, [_DEVELOP_SKILL, _REVIEW_SKILL])
        self.assertEqual(
            skill_paths[_REVIEW_SKILL],
            [
                _AGENT_REVIEW_SKILL_PATH,
                _CLAUDE_REVIEW_SKILL_PATH,
            ],
        )
        self.assertEqual(
            skill_paths[_DEVELOP_SKILL], [_AGENT_DEVELOP_SKILL_PATH],
        )

    def test_nested_and_unrelated_paths_ignored(self) -> None:
        # Only a direct `<root>/<name>/SKILL.md` counts: a built-in nested
        # under `.system`, a non-SKILL file, a SKILL.md directly under the
        # root with no name segment, and a path outside the known roots are
        # all rejected. Blank lines are skipped.
        paths = [
            ".claude/skills/.system/imagegen/SKILL.md",
            _AGENT_REVIEW_SKILL_PATH,
            ".agents/skills/review/README.md",
            ".agents/skills/SKILL.md",
            ".agents/skills/nested/sub/SKILL.md",
            "docs/skills/leaked/SKILL.md",
            "",
        ]
        skills, skill_paths = catalog._extract_skill_catalog(paths)
        self.assertEqual(skills, [_REVIEW_SKILL])
        self.assertEqual(
            skill_paths, {_REVIEW_SKILL: [_AGENT_REVIEW_SKILL_PATH]},
        )

    def test_empty_input_yields_empty_catalog(self) -> None:
        skills, skill_paths = catalog._extract_skill_catalog([])
        self.assertEqual(skills, [])
        self.assertEqual(skill_paths, {})


class RecordRepoSkillCatalogShapeTest(unittest.TestCase):
    """`recording.record_repo_skill_catalog` builds a repo-level
    `repo_skill_catalog` record carrying the catalog in extras.
    """

    def test_keyword_contract_is_enforced(self) -> None:
        # The recorder binds through a declared signature rather than a
        # parameter list, so a producer's spelling stays the contract: a
        # required keyword left out and a keyword the record has no field
        # for both still fail at the call.
        catalog_call = {
            "repo": _TEST_REPO_SLUG,
            "base_branch": _TEST_BASE_BRANCH,
            "remote_name": _TEST_REMOTE_NAME,
            _SKILLS_AVAILABLE_FIELD: [],
        }
        for dropped, extra in (("remote_name", None), (None, "skill_level")):
            with self.subTest(dropped=dropped, extra=extra):
                call_kwargs = dict(catalog_call)
                call_kwargs.pop(dropped, None)
                if extra is not None:
                    call_kwargs[extra] = {}
                with self.assertRaises(TypeError):
                    _recording_events.record_repo_skill_catalog(**call_kwargs)

    def test_record_shape(self) -> None:
        captured = _capture_analytics_records(self)
        _recording_events.record_repo_skill_catalog(
            repo=_TEST_REPO_SLUG,
            base_branch=_TEST_BASE_BRANCH,
            remote_name=_TEST_REMOTE_NAME,
            skills_available=[_DEVELOP_SKILL, _REVIEW_SKILL],
            skill_paths={
                _DEVELOP_SKILL: [_AGENT_DEVELOP_SKILL_PATH],
                _REVIEW_SKILL: [
                    _AGENT_REVIEW_SKILL_PATH,
                    _CLAUDE_REVIEW_SKILL_PATH,
                ],
            },
            skill_levels={
                _DEVELOP_SKILL: _PROJECT_LEVEL,
                _REVIEW_SKILL: _PROJECT_LEVEL,
            },
        )
        self.assertEqual(len(captured), 1)
        record = captured[0]
        self.assertEqual(
            _catalog_identity(record),
            (
                "repo_skill_catalog",
                0,
                _TEST_REPO_SLUG,
                _TEST_BASE_BRANCH,
                _TEST_REMOTE_NAME,
            ),
        )
        self.assertEqual(
            record[_SKILLS_AVAILABLE_FIELD],
            [_DEVELOP_SKILL, _REVIEW_SKILL],
        )
        self.assertEqual(
            record["skill_paths"][_REVIEW_SKILL],
            [
                _AGENT_REVIEW_SKILL_PATH,
                _CLAUDE_REVIEW_SKILL_PATH,
            ],
        )
        self.assertEqual(
            record["skill_levels"],
            {
                _DEVELOP_SKILL: _PROJECT_LEVEL,
                _REVIEW_SKILL: _PROJECT_LEVEL,
            },
        )
        self.assertIsInstance(record["ts"], str)
        self.assertNotIn("stage", record)

    def test_empty_catalog_keeps_skills_drops_maps(
        self,
    ) -> None:
        # An empty catalog still records `skills_available: []` (the
        # "scanned, found none" signal); both per-name maps are dropped
        # when None.
        captured = _capture_analytics_records(self)
        _recording_events.record_repo_skill_catalog(
            repo=_TEST_REPO_SLUG,
            base_branch=_TEST_BASE_BRANCH,
            remote_name=_TEST_REMOTE_NAME,
            skills_available=[],
            skill_paths=None,
            skill_levels=None,
        )
        record = captured[0]
        self.assertEqual(record[_SKILLS_AVAILABLE_FIELD], [])
        self.assertNotIn("skill_paths", record)
        self.assertNotIn("skill_levels", record)


class ListSkillTreeTest(unittest.TestCase):
    """`_list_skill_tree` invokes git against the spec's base ref and is
    fail-open on a missing clone or a git error.
    """

    def test_missing_target_root_returns_none(self) -> None:
        spec = _spec(target_root="/tmp/does-not-exist-skill-catalog-xyz")
        git_mock = MagicMock()
        with patch.object(catalog, "_git", git_mock):
            self.assertIsNone(catalog._list_skill_tree(spec))
        git_mock.assert_not_called()

    def test_ls_tree_command_and_parse(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            spec = _spec(
                target_root=td, remote_name="upstream", base_branch="release",
            )
            git_mock = MagicMock(return_value=_completed(
                ".agents/skills/develop/SKILL.md\n"
                ".claude/skills/review/SKILL.md\n"
                "\n",
            ))
            with patch.object(catalog, "_git", git_mock):
                lines = catalog._list_skill_tree(spec)
        self.assertEqual(
            lines,
            [
                _AGENT_DEVELOP_SKILL_PATH,
                _CLAUDE_REVIEW_SKILL_PATH,
            ],
        )
        git_call = git_mock.call_args
        self.assertEqual(
            git_call.args,
            (
                "ls-tree", "-r", "--name-only", "upstream/release",
                _AGENT_SKILLS_ROOT, ".claude/skills",
            ),
        )
        self.assertEqual(git_call.kwargs["cwd"], spec.target_root)

    def test_git_failure_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            spec = _spec(target_root=td)
            with patch.object(
                catalog, "_git",
                return_value=_completed(
                    returncode=_BAD_REF_EXIT_CODE,
                    stderr="bad ref",
                ),
            ):
                self.assertIsNone(catalog._list_skill_tree(spec))


class EmitRepoSkillCatalogTest(unittest.TestCase):
    """`_emit_repo_skill_catalog` wires spec fields into the analytics
    record, classifies every name it enumerated as a `project` definition,
    and never raises out of the producer.
    """

    def test_wires_spec_fields_into_record(self) -> None:
        spec = _spec(
            slug="acme/widgets", remote_name="upstream", base_branch="trunk",
        )
        paths = [
            _CLAUDE_REVIEW_SKILL_PATH,
            _AGENT_REVIEW_SKILL_PATH,
            _AGENT_DEVELOP_SKILL_PATH,
        ]
        record_mock = MagicMock()
        with patch.object(
            catalog, _LIST_SKILL_TREE_METHOD, return_value=paths,
        ), patch.object(
            _recording_events, _RECORD_CATALOG_METHOD, record_mock,
        ):
            catalog._emit_repo_skill_catalog(spec)
        record_mock.assert_called_once_with(
            repo="acme/widgets",
            base_branch="trunk",
            remote_name="upstream",
            skills_available=[_DEVELOP_SKILL, _REVIEW_SKILL],
            skill_paths={
                _DEVELOP_SKILL: [_AGENT_DEVELOP_SKILL_PATH],
                _REVIEW_SKILL: [
                    _AGENT_REVIEW_SKILL_PATH,
                    _CLAUDE_REVIEW_SKILL_PATH,
                ],
            },
            skill_levels={
                _DEVELOP_SKILL: _PROJECT_LEVEL,
                _REVIEW_SKILL: _PROJECT_LEVEL,
            },
        )

    def test_empty_catalog_passes_none_per_name_maps(self) -> None:
        spec = _spec()
        record_mock = MagicMock()
        with patch.object(
            catalog, _LIST_SKILL_TREE_METHOD, return_value=[],
        ), patch.object(
            _recording_events, _RECORD_CATALOG_METHOD, record_mock,
        ):
            catalog._emit_repo_skill_catalog(spec)
        _, kwargs = record_mock.call_args
        self.assertEqual(kwargs[_SKILLS_AVAILABLE_FIELD], [])
        self.assertIsNone(kwargs["skill_paths"])
        self.assertIsNone(kwargs["skill_levels"])

    def test_unavailable_tree_records_nothing(self) -> None:
        spec = _spec()
        record_mock = MagicMock()
        with patch.object(
            catalog, _LIST_SKILL_TREE_METHOD, return_value=None,
        ), patch.object(
            _recording_events, _RECORD_CATALOG_METHOD, record_mock,
        ):
            catalog._emit_repo_skill_catalog(spec)
        record_mock.assert_not_called()

    def test_failure_is_swallowed(self) -> None:
        spec = _spec()
        record_mock = MagicMock()
        with patch.object(
            catalog, _LIST_SKILL_TREE_METHOD,
            side_effect=RuntimeError("boom"),
        ), patch.object(
            _recording_events, _RECORD_CATALOG_METHOD, record_mock,
        ):
            # Must not raise -- catalog collection is fail-open.
            catalog._emit_repo_skill_catalog(spec)
        record_mock.assert_not_called()


class TickEmitsRepoSkillCatalogTest(unittest.TestCase):
    """`workflow.engine.tick.tick` drives `_emit_repo_skill_catalog` once per tick."""

    def test_tick_calls_emit_once(self) -> None:
        # The tick names this owner, so patching it here is what intercepts
        # the pass -- and what proves the spec it is handed is the one being
        # polled, which is all the catalog needs to read the right base ref.
        from tests.support.fakes import FakeGitHubClient, make_issue
        from tests.workflow.fixtures import _TEST_SPEC
        from tests.workflow.git_owners import seam_patch

        gh = FakeGitHubClient()
        gh.add_issue(make_issue(1, label="workflow:implementing"))
        emit = MagicMock()
        with seam_patch(_REFRESH_BASE), \
                patch.object(_issue_processing, "_process_issue"), \
                patch.object(catalog, "_emit_repo_skill_catalog", emit):
            _engine_tick.tick(gh, _TEST_SPEC)
        emit.assert_called_once_with(_TEST_SPEC)


if __name__ == "__main__":
    unittest.main()
