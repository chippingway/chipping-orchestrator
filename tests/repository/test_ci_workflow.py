# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the CI workflow declares beyond the commands it runs.

Three of its decisions are invisible to every other check here, and each one
changes what a green run means.

The concurrency block decides which run survives. A pull request is grouped by
its ref and cancelled in progress, so a second push drops the run its own
earlier push started instead of leaving it racing the head that replaced it.
Every other run is grouped by its run id, which is what makes a push to `main`
uncancellable: `cancel-in-progress: false` protects a run that has started,
but GitHub holds one pending run per group and cancels the one a newcomer
replaces, so a shared group would still let a third push evict a queued `main`
run. A run there is the record of what the merged commit does, and a group
nothing else can enter is what keeps it.

The interpreter matrix decides what "the tests passed" covers. It names the
versions a run proves rather than the ones the distribution admits --
`requires-python` sets a floor and no ceiling -- so the floor is the one end
held against the manifest below.

The packaging steps decide whether the distribution works at all. The steps
above them reach the console script through an editable install of the source
tree, which says nothing about what the build backend packaged, so a wheel
that ships no package, an entry point naming a module it does not carry, or a
runtime dependency only the lockfile supplies stays green until someone
installs the distribution.

Nothing in the tree runs this file -- GitHub does -- so each decision is held
as the text GitHub has to receive.
"""
from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_MANIFEST = _REPO_ROOT / "pyproject.toml"
_ENCODING = "utf-8"

# Every interpreter the workflow installs, lints, tests, and smoke-tests the
# wheel under, in matrix order. The first is the floor `requires-python`
# declares; the last is simply the newest one a run covers.
_PYTHON_VERSIONS = ("3.12", "3.13", "3.14")

# The ref keys a pull request's lane; the run id gives every other run a lane
# of its own, which no later run can be queued into and evict it from.
_CONCURRENCY_BLOCK = "\n".join((
    "concurrency:",
    "  group: ${{ github.workflow }}-"
    + "${{ github.event_name == 'pull_request' && github.ref || github.run_id }}",
    "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
))

_BUILD_COMMAND = "run: uv build"
# The invocation that proves the built wheel: an environment holding that
# wheel and the dependencies it declares and nothing else -- no project, no
# lockfile, no dev group -- running the console script out of it.
_WHEEL_SMOKE = (
    'wheel="$(ls dist/*.whl)"',
    "uv run --no-project --isolated",
    '--with "${wheel}" chipping-orchestrator --help',
)

# The pages that state the tested versions in prose.
_DOCUMENTING_PAGES = (
    Path("README.md"),
    Path("docs") / "configuration.md",
    Path("docs") / "configuration" / "operations.md",
    Path("docs") / "security.md",
)


def _workflow() -> str:
    return _CI_WORKFLOW.read_text(encoding=_ENCODING)


def _matrix_line() -> str:
    """The matrix entry as the workflow has to spell it out."""
    versions = ", ".join(f'"{version}"' for version in _PYTHON_VERSIONS)
    return f"        python-version: [{versions}]"


class CiConcurrencyTest(unittest.TestCase):
    def test_only_a_pull_request_run_is_superseded(self) -> None:
        self.assertIn(_CONCURRENCY_BLOCK, _workflow())


class CiPythonMatrixTest(unittest.TestCase):
    def test_the_matrix_names_every_tested_version(self) -> None:
        self.assertIn(_matrix_line(), _workflow())

    def test_the_matrix_starts_at_the_declared_floor(self) -> None:
        """The oldest version installable is the oldest version run.

        `requires-python` is what an installer reads, so its floor and the
        first matrix entry are the same statement made twice; a floor raised
        past the leg that checks it would leave the range open at the bottom.
        """
        manifest = tomllib.loads(_MANIFEST.read_text(encoding=_ENCODING))
        self.assertEqual(
            manifest["project"]["requires-python"],
            f">={_PYTHON_VERSIONS[0]}",
        )


class CiWheelSmokeTest(unittest.TestCase):
    def test_the_run_launches_the_wheel_it_builds(self) -> None:
        workflow = _workflow()
        self.assertIn(_BUILD_COMMAND, workflow)
        for fragment in _WHEEL_SMOKE:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, workflow)


class DocumentedPythonVersionsTest(unittest.TestCase):
    def test_pages_name_every_tested_version(self) -> None:
        """Prose naming a narrower range describes a gate that does not exist.

        The operator pages are where a maintainer reads which interpreters a
        merge was proven on, and nothing else would notice them drifting from
        the matrix.
        """
        for page in _DOCUMENTING_PAGES:
            prose = (_REPO_ROOT / page).read_text(encoding=_ENCODING)
            for version in _PYTHON_VERSIONS:
                with self.subTest(page=page.name, version=version):
                    self.assertIn(version, prose)


if __name__ == "__main__":
    unittest.main()
