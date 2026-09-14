# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tree discovery and clean-process import probes for observability."""
from __future__ import annotations

import subprocess
import sys
from functools import cache
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

_ROOT = "orchestrator.observability"
_ANALYTICS = f"{_ROOT}.analytics"

# The declared inventory. A new subpackage is a deliberate edit here, a
# mirrored directory under `tests/observability/`, and a paragraph in the
# module map -- which is what the surface checks compare the tree against.
_PACKAGES = (
    _ROOT,
    _ANALYTICS,
    f"{_ANALYTICS}.query",
    f"{_ANALYTICS}.recording",
    f"{_ANALYTICS}.sync",
    f"{_ANALYTICS}.trajectories",
    f"{_ROOT}.dashboard",
    f"{_ROOT}.dashboard.charts",
    f"{_ROOT}.trajectory_viewer",
    f"{_ROOT}.usage",
)

# The packages whose initializer publishes a public surface instead of staying
# a marker. A caller reaches the usage parsers, and the recorders a producer
# appends with, through their package, so each re-exports them under an
# `__all__` and an importer of one owner pays for the rest; every other
# initializer here still binds nothing.
_PUBLISHING_PACKAGES = frozenset((
    f"{_ANALYTICS}.recording",
    f"{_ROOT}.usage",
))

# What a publishing package pays for beyond its own owners: the siblings it
# composes. Recording is configured by the analytics `config` owner, writes its
# lines through the shared `sink` owner, meters a finished run through the
# `usage` parsers, and hands that run's second record to the `trajectories`
# writers, so naming it buys those four chains as well -- and nothing else,
# which is what keeps the query, sync, and page graphs out of the one analytics
# path the orchestrator process runs.
_COMPOSED_PACKAGES = MappingProxyType({
    f"{_ANALYTICS}.recording": (
        f"{_ANALYTICS}.config",
        f"{_ANALYTICS}.sink",
        f"{_ANALYTICS}.trajectories",
        f"{_ROOT}.usage",
    ),
})

_PACKAGE_ROOT = Path(import_module(_ROOT).__file__).parent

_IMPORT_ROOT = _PACKAGE_ROOT.parent.parent

_IMPORTED_MODULES_SCRIPT = """
import sys
import {module}
print(*sorted(name for name in sys.modules if name.startswith('orchestrator')))
"""


def _under(module: str, roots: tuple[str, ...]) -> bool:
    """Whether `module` is one of `roots` or lives beneath one of them."""
    return any(
        module == root or module.startswith(f"{root}.") for root in roots
    )


def _payable_import(package: str, imported: str) -> bool:
    """Whether a publishing package's import is one it pays for.

    Its own owners are, and so are the siblings declared above -- everything
    else is a chain an importer of the package did not ask for.
    """
    return _under(imported, (package,) + _COMPOSED_PACKAGES.get(package, ()))


def _dotted_name(path: Path) -> str:
    """Name the module at `path` is imported by."""
    parts = path.relative_to(_IMPORT_ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _observability_modules() -> tuple[str, ...]:
    """Every module in the tree, read off disk rather than declared.

    The checks that sweep this are the ones an owner has to satisfy the day
    it lands, so they discover their own subjects: a list maintained by hand
    would exempt exactly the module nobody remembered to add to it.
    """
    return tuple(sorted(
        _dotted_name(module_path)
        for module_path in _PACKAGE_ROOT.rglob("*.py")
    ))


def _observability_packages() -> tuple[str, ...]:
    """Names of the tree's directories that carry an initializer."""
    return tuple(sorted(
        _dotted_name(initializer)
        for initializer in _PACKAGE_ROOT.rglob("__init__.py")
    ))


def _run_import_probe(script: str) -> subprocess.CompletedProcess[str]:
    """Run `script` in a fresh interpreter and hand back what it reported."""
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


@cache
def _imported_orchestrator_modules(module: str) -> frozenset[str]:
    """Names of the orchestrator modules a fresh `import module` plants."""
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORTED_MODULES_SCRIPT.format(module=module)],
        capture_output=True,
        text=True,
        check=True,
    )
    return frozenset(completed.stdout.split())
