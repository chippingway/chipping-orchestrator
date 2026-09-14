# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared builders and projections for the skill-enumeration owners' tests."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.config import models as _config_models
from orchestrator.observability.analytics.recording import events as recording_events

_TEST_REPO_SLUG = "chippingway/orchestrator"
_TEST_BASE_BRANCH = "main"
_TEST_REMOTE_NAME = "origin"


def _spec(
    *,
    slug: str = _TEST_REPO_SLUG,
    target_root: str = "/tmp/orchestrator-skill-catalog-target",
    base_branch: str = _TEST_BASE_BRANCH,
    remote_name: str = _TEST_REMOTE_NAME,
) -> _config_models.RepoSpec:
    return _config_models.RepoSpec(
        slug=slug,
        target_root=Path(target_root),
        base_branch=base_branch,
        remote_name=remote_name,
    )


def _completed(
    stdout: str = "",
    returncode: int = 0,
    stderr: str = "",
):
    return subprocess.CompletedProcess(
        args=["git", "ls-tree"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _capture_analytics_records(
    case: unittest.TestCase,
) -> list[dict]:
    captured: list[dict] = []
    patcher = patch.object(recording_events, "append_record", captured.append)
    patcher.start()
    case.addCleanup(patcher.stop)
    return captured


def _catalog_identity(record: dict) -> tuple:
    return (
        record["event"],
        record["issue"],
        record["repo"],
        record["base_branch"],
        record["remote_name"],
    )


def _make_skill(root: Path, name: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "# skill\n",
        encoding="utf-8",
    )
