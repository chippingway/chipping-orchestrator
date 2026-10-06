# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What each ecosystem's Dependabot entry has to declare to GitHub.

The service labels stamped on every update PR let a reviewer select the
dependency queue by label rather than by reading titles: the shared one the
whole queue is filtered by, plus the one naming which ecosystem moved. The
cooldown windows hold a release for a stabilization period before an update PR
opens. GitHub Actions accepts only an ecosystem-wide default window, while
`pip` accepts SemVer-specific windows, so each entry is held against the policy
shape its ecosystem supports. The `pip` entry explicitly limits updates to
direct dependencies and requests lower-bound increases.

Nothing in the tree reads this config -- GitHub does -- so dropped labels,
rewritten cooldown windows, or a widened dependency scope would otherwise
surface only in the update PRs GitHub opens.

The check is a text match for the block each entry must carry rather than a
read of what it happens to declare: what GitHub has to receive is exact, so
matching it exactly is both the whole assertion and the reason no YAML reader
is needed here to make it. Only the comments are dropped first, so a line of
reasoning added beside a rule is not a failure.

The operator pages that tell a maintainer which label selects the dependency
queue spell the same strings out a second time, and a rename here would leave
them describing a filter that matches nothing, so they are checked against the
config rather than against a reader's memory of it.
"""
from __future__ import annotations

import unittest
from collections.abc import Iterable
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEPENDABOT_CONFIG = _REPO_ROOT / ".github" / "dependabot.yml"
_ECOSYSTEM_KEY = "  - package-ecosystem: "
_ENCODING = "utf-8"

# The labels every ecosystem's entry must declare, in file order.
_EXPECTED_LABELS = (
    ("github-actions", ("workflow:dependencies", "workflow:github_actions")),
    ("pip", ("workflow:dependencies", "workflow:python:pip")),
)
_SERVICE_LABELS = frozenset(
    label for _, labels in _EXPECTED_LABELS for label in labels
)
# GitHub Actions accepts only its ecosystem-wide window; `pip` can tier its
# stabilization windows by SemVer change.
_EXPECTED_COOLDOWNS = (
    ("github-actions", (("default-days", 30),)),
    (
        "pip",
        (
            ("default-days", 30),
            ("semver-major-days", 30),
            ("semver-minor-days", 14),
            ("semver-patch-days", 14),
        ),
    ),
)
# The `pip` entry restricts routine and security updates to direct dependencies.
_EXPECTED_PIP_ALLOW = (
    "dependency-type: direct",
)
_DOCUMENTING_PAGES = (
    Path("docs") / "configuration" / "operations.md",
    Path("docs") / "security.md",
)


def _block(key: str, declarations: Iterable[str]) -> str:
    """One `key:` block of an entry, as the entry has to spell it out."""
    lines = (f"      {declaration}" for declaration in declarations)
    return "\n".join((f"    {key}:", *lines))


def _entry_declarations(ecosystem: str) -> str:
    """One entry's lines, from its ecosystem key to where the next starts."""
    config = _DEPENDABOT_CONFIG.read_text(encoding=_ENCODING)
    below_key = config.partition(f"{_ECOSYSTEM_KEY}{ecosystem}\n")[2]
    return "\n".join(
        line
        for line in below_key.split(_ECOSYSTEM_KEY)[0].splitlines()
        if not line.lstrip().startswith("#")
    )


def _entry_block(ecosystem: str, key: str) -> str:
    """One complete declaration block from an ecosystem entry."""
    marker = f"    {key}:"
    below_key = _entry_declarations(ecosystem).partition(f"{marker}\n")[2]
    declarations = []
    for line in below_key.splitlines():
        if not line.startswith("      "):
            break
        declarations.append(line)
    return "\n".join((marker, *declarations))


class DependabotServiceLabelsTest(unittest.TestCase):
    def test_ecosystems_declare_their_labels(self) -> None:
        for ecosystem, labels in _EXPECTED_LABELS:
            declared = _block(
                "labels", (f'- "{label}"' for label in labels),
            )
            with self.subTest(ecosystem=ecosystem):
                self.assertIn(declared, _entry_declarations(ecosystem))


class DependabotCooldownPolicyTest(unittest.TestCase):
    def test_ecosystems_use_supported_cooldowns(self) -> None:
        for ecosystem, cooldown in _EXPECTED_COOLDOWNS:
            declared = _block(
                "cooldown",
                (f"{window}: {days}" for window, days in cooldown),
            )
            with self.subTest(ecosystem=ecosystem):
                self.assertEqual(
                    declared,
                    _entry_block(ecosystem, "cooldown"),
                )


class DependabotPipUpdatesTest(unittest.TestCase):
    def test_pip_allow_rules_and_floor_strategy(self) -> None:
        declared = _block(
            "allow", (f"- {rule}" for rule in _EXPECTED_PIP_ALLOW),
        )
        ecosystem = "pip"
        declarations = _entry_declarations(ecosystem)
        self.assertEqual(declared, _entry_block(ecosystem, "allow"))
        self.assertIn("    versioning-strategy: increase", declarations.splitlines())


class DocumentedServiceLabelsTest(unittest.TestCase):
    def test_pages_name_every_service_label(self) -> None:
        for page in _DOCUMENTING_PAGES:
            prose = (_REPO_ROOT / page).read_text(encoding=_ENCODING)
            for label in sorted(_SERVICE_LABELS):
                with self.subTest(page=page.name, label=label):
                    self.assertIn(f"`{label}`", prose)


if __name__ == "__main__":
    unittest.main()
