# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Poetry's committed lock, environment policy, and workflow installation contract."""
from __future__ import annotations

import re
import subprocess
import textwrap
import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

_ROOT = Path(__file__).resolve().parents[2]
_ENCODING = "utf-8"
_MANIFEST_NAME = "pyproject.toml"
_COOLDOWN_DAYS = 14
_AUDIT_WORKFLOW = "vulnerability-scan.yml"
_WORKFLOWS = ("ci.yml", "docs.yml", _AUDIT_WORKFLOW)
_POETRY_PIN = re.compile(r'pipx install "poetry==([^"]+)"')
_ENVIRONMENT_COMMAND = 'poetry env use "$(command -v python)"'
_LOCK_CHECK = "poetry check --lock"
_INSTALL_COMMANDS = (
    "poetry sync --no-interaction",
    "poetry sync --with docs --no-interaction",
    "poetry export --all-groups --without-hashes -f requirements.txt",
)


def _toml(name: str) -> dict:
    return tomllib.loads((_ROOT / name).read_text(encoding=_ENCODING))


def _poetry_table() -> dict:
    return _toml(_MANIFEST_NAME)["tool"]["poetry"]


def _poetry_requirement() -> SpecifierSet:
    return SpecifierSet(_poetry_table()["requires-poetry"])


def _workflow_version(workflow: str) -> Version:
    pins = _POETRY_PIN.findall(workflow)
    if len(pins) == 1:
        return Version(pins[0])
    raise ValueError("Each workflow must install exactly one pinned Poetry version")


class PoetryLockTest(unittest.TestCase):
    def test_lock_uses_implicit_pypi(self) -> None:
        packages = _toml("poetry.lock")["package"]
        names = [canonicalize_name(package["name"]) for package in packages]
        self.assertTrue(names)
        self.assertEqual(len(names), len(set(names)), "Locked package names must be unique")
        self.assertNotIn("chipping-orchestrator", names)
        self.assertEqual([package["name"] for package in packages if "source" in package], [])
        self.assertNotIn("source", _poetry_table())

    def test_runtime_ranges_cover_locked_versions(self) -> None:
        packages = _toml("poetry.lock")["package"]
        for declared in _toml(_MANIFEST_NAME)["project"]["dependencies"]:
            dependency = Requirement(declared)
            with self.subTest(dependency=dependency.name):
                locked = [
                    Version(package["version"]) for package in packages
                    if canonicalize_name(package["name"]) == canonicalize_name(dependency.name)
                ]
                self.assertTrue(locked)
                floors = [Version(bound.version) for bound in dependency.specifier if bound.operator == ">="]
                self.assertEqual(len(floors), 1)
                self.assertTrue(any(bound.operator == "<" for bound in dependency.specifier))
                self.assertTrue(all(version in dependency.specifier for version in locked))


class PoetryEnvironmentTest(unittest.TestCase):
    def test_checkout_and_cooldown_policy(self) -> None:
        configuration = _toml("poetry.toml")
        self.assertIs(configuration["virtualenvs"]["in-project"], True)
        self.assertEqual(configuration["solver"]["min-release-age"], _COOLDOWN_DAYS)
        groups = _poetry_table()["group"]
        for name in ("docs", "dashboard"):
            with self.subTest(group=name):
                self.assertIs(groups[name]["optional"], True)
        self.assertFalse(groups.get("dev", {}).get("optional", False))


class PoetryWorkflowTest(unittest.TestCase):
    def test_workflows_check_before_sync_or_export(self) -> None:
        requirement = _poetry_requirement()
        for name, command in zip(_WORKFLOWS, _INSTALL_COMMANDS, strict=True):
            workflow = (_ROOT / ".github" / "workflows" / name).read_text(encoding=_ENCODING)
            with self.subTest(workflow=name):
                self.assertIn(_workflow_version(workflow), requirement)
                order = [workflow.index(marker) for marker in ('pipx install "poetry==', _LOCK_CHECK, command)]
                if name != _AUDIT_WORKFLOW:
                    order.insert(1, workflow.index(_ENVIRONMENT_COMMAND))
                self.assertEqual(order, sorted(order))

    def test_audit_reads_all_pins(self) -> None:
        workflow = (_ROOT / ".github" / "workflows" / _AUDIT_WORKFLOW).read_text(encoding=_ENCODING)
        self.assertRegex(workflow, r'pipx inject poetry "poetry-plugin-export==\d+(?:\.\d+)+"')
        commands = (
            'pipx inject poetry "poetry-plugin-export==',
            "poetry export --all-groups --without-hashes -f requirements.txt",
            'pipx run "pip-audit>=2.9,<3"',
        )
        order = [workflow.index(command) for command in commands]
        self.assertEqual(order, sorted(order))
        self.assertIn("sed 's/ ;.*//'", workflow)
        self.assertIn("--no-deps --disable-pip --strict", workflow)

    def test_audit_export_requires_valid_output(self) -> None:
        export_step = re.search(
            r"      - name: Export every pin in poetry\.lock\n"
            r"        shell: bash\n"
            r"        run: \|\n(?P<script>(?:          .*\n)+)",
            (_ROOT / ".github" / "workflows" / _AUDIT_WORKFLOW).read_text(encoding=_ENCODING),
        )
        self.assertIsNotNone(export_step)
        for export_script, succeeds in (
            ("return 9", False),
            (r"printf 'example==1.0\n'; return 9", False),
            ("return 0", False),
            (r'printf "example==1.0 ; python_version >= \"3.12\"\n"', True),
        ):
            with self.subTest(export_script=export_script), TemporaryDirectory() as directory:
                completed = subprocess.run(
                    ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail"],
                    input=f"poetry() {{\n{export_script}\n}}\n{textwrap.dedent(export_step.group('script'))}",
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(completed.returncode == 0, succeeds)
                if succeeds:
                    self.assertEqual(
                        (Path(directory) / "pinned-requirements.txt").read_text(encoding=_ENCODING),
                        "example==1.0\n",
                    )
