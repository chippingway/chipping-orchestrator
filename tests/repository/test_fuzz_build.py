# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ClusterFuzzLite build under `.clusterfuzzlite/` and the context it is built from.

ClusterFuzzLite builds `.clusterfuzzlite/Dockerfile` from the checkout's root
and runs `build.sh` in it; nothing in this tree runs either, so what each has
to declare is held as text. The image pins what it builds with -- the base
image by digest, a CPython inside `requires-python` checked against its
release digest, the Poetry every workflow pins -- and the build installs from
the lock it checks first and packages every entry point under `fuzz/` beside
its seed corpus, its dictionary, and libFuzzer limits its seeds fit inside.

The context is asked of Docker itself where a daemon with BuildKit answers: a
copy of the tracked tree, planted with what a working checkout carries beside
it -- `.env` files, a token, `.venv/`, caches, logs, worktrees, fuzzer
artifacts, and an `analytics-db/data/` nobody may read -- is sent to a build
that copies its context out, and exactly the allowlisted tracked files arrive.
A context that walked into the unreadable directory fails the build instead.
"""
from __future__ import annotations

import configparser
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from packaging.specifiers import SpecifierSet
from packaging.version import Version

_ROOT = Path(__file__).resolve().parents[2]
_FUZZ = _ROOT / "fuzz"
_ENCODING = "utf-8"
_DOCKER = shutil.which("docker")
_SKIP_REASON = "A Docker daemon with BuildKit is required to build the fuzzing context"
_TIMEOUT_SECONDS = 300
# How much of a failed build's output a failure quotes.
_TAIL_CHARACTERS = 4000
_LIMITS = "libfuzzer"

# A daemon that answers, and a client that builds with BuildKit, which is what
# copies a context out to a directory.
_DOCKER_PROBES = (
    (_DOCKER, "version", "--format", "{{.Server.Version}}"),
    (_DOCKER, "buildx", "version"),
)

# What the fuzz build reads, as `.dockerignore` lets it back in: three
# directories, and the files Poetry installs the checkout from.
_CONTEXT_DIRECTORIES = (".clusterfuzzlite/", "fuzz/", "orchestrator/")
_CONTEXT_FILES = ("LICENSE", "README.md", "poetry.lock", "poetry.toml", "pyproject.toml")

# What a working checkout carries beside its tracked files, none of which may
# reach the daemon, wherever it sits.
_PLANTED = (
    ".env",
    "orchestrator/.env",
    "fuzz/.env.local",
    "token",
    ".git/config",
    ".venv/bin/python",
    "logs/orchestrator.log",
    "worktrees/chippingway__chipping-orchestrator/issue-1/README.md",
    "orchestrator/__pycache__/cli.cpython-312.pyc",
    "fuzz/crash-0123456789abcdef",
    "fuzz/corpus/manifest_fuzzer/timeout-0123456789abcdef",
)
_RUNTIME_DATA = "analytics-db/data"
_OWNER_ONLY = 0o700
_NO_ACCESS = 0


def _read(relative: str) -> str:
    return (_ROOT / relative).read_text(encoding=_ENCODING)


def _docker_builds() -> bool:
    """Whether every probe answers, in time and without an error."""
    for probe in _DOCKER_PROBES:
        try:
            answer = subprocess.run(probe, capture_output=True, check=False, timeout=_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return False
        if answer.returncode:
            return False
    return True


def _tracked() -> list[str]:
    """The files the index tracks, read without walking the working tree."""
    listed = subprocess.run(
        ("git", "ls-files", "-z", "--cached"),
        cwd=_ROOT, capture_output=True, text=True, check=True, timeout=_TIMEOUT_SECONDS,
    ).stdout.split("\0")
    return [
        relative for relative in listed
        if relative and (_ROOT / relative).is_file()
    ]


def _plant(checkout: Path, tracked: list[str]) -> Path:
    """Copy the tracked tree into `checkout`, plant what a working one carries, and return the unreadable data."""
    for relative in (*tracked, ".dockerignore"):
        (checkout / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_ROOT / relative, checkout / relative)
    for planted in (*_PLANTED, f"{_RUNTIME_DATA}/PG_VERSION"):
        (checkout / planted).parent.mkdir(parents=True, exist_ok=True)
        (checkout / planted).write_text("planted\n", encoding=_ENCODING)
    (checkout / _RUNTIME_DATA).chmod(_NO_ACCESS)
    return checkout / _RUNTIME_DATA


def _send(checkout: Path, received: Path) -> subprocess.CompletedProcess[str]:
    """Build `checkout` with a Dockerfile beside it that copies its whole context out to `received`."""
    dockerfile = received.parent / "Dockerfile"
    dockerfile.write_text("FROM scratch\nCOPY . /\n", encoding=_ENCODING)
    destination = f"type=local,dest={received}"
    return subprocess.run(
        (_DOCKER, "build", "--quiet", "--output", destination, "--file", str(dockerfile), str(checkout)),
        capture_output=True, text=True, check=False, timeout=_TIMEOUT_SECONDS,
    )


class FuzzBuildDeclarationTest(unittest.TestCase):
    def test_project_builds_python(self) -> None:
        lines = _read(".clusterfuzzlite/project.yaml").splitlines()
        declared = [line for line in lines if not line.startswith("#")]
        self.assertEqual(declared, ["language: python"])

    def test_image_pins_its_toolchain(self) -> None:
        dockerfile = _read(".clusterfuzzlite/Dockerfile")
        self.assertRegex(dockerfile, r"(?m)^FROM gcr\.io/oss-fuzz-base/base-builder-python@sha256:[0-9a-f]{64}$")
        python = re.search(r"(?m)^ARG FUZZ_PYTHON_VERSION=(\S+)$", dockerfile).group(1)
        self.assertIn(Version(python), SpecifierSet(">=3.12"))
        self.assertRegex(dockerfile, r"(?m)^ARG FUZZ_PYTHON_SHA256=[0-9a-f]{64}$")
        self.assertIn("sha256sum --check --strict", dockerfile)
        workflow_pins = re.findall(r'pipx install "poetry==([^"]+)"', _read(".github/workflows/ci.yml"))
        self.assertEqual(set(re.findall(r'"poetry==([^"]+)"', dockerfile)), set(workflow_pins))

    def test_build_packages_every_entry_point(self) -> None:
        build = _read(".clusterfuzzlite/build.sh")
        targets = re.search(r"(?m)^targets=\(([^)]*)\)$", build).group(1).split()
        entries = [entry.stem for entry in _FUZZ.glob("*_fuzzer.py")]
        self.assertEqual(sorted(targets), sorted(entries))
        self.assertLess(build.index('"$poetry" check --lock'), build.index('"$poetry" sync --only main,fuzz'))
        for target in targets:
            with self.subTest(target=target):
                self._check_packaged(target)

    def _check_packaged(self, target: str) -> None:
        """A target ships a dictionary, limits it is held to, and seeds inside those limits."""
        self.assertTrue((_FUZZ / f"{target}.dict").is_file())
        limits = configparser.ConfigParser()
        limits.read(_FUZZ / f"{target}.options", encoding=_ENCODING)
        self.assertGreater(limits.getint(_LIMITS, "rss_limit_mb"), 0)
        self.assertGreater(limits.getint(_LIMITS, "timeout"), 0)
        seeds = (_FUZZ / "corpus" / target).iterdir()
        sizes = [seed.stat().st_size for seed in seeds]
        self.assertLessEqual(max(sizes), limits.getint(_LIMITS, "max_len"))


@unittest.skipUnless(_DOCKER, _SKIP_REASON)
class FuzzBuildContextTest(unittest.TestCase):
    def test_context_carries_the_build_alone(self) -> None:
        if not _docker_builds():
            self.skipTest(_SKIP_REASON)
        scratch = Path(self.enterContext(TemporaryDirectory()))
        tracked = _tracked()
        self.addCleanup(_plant(scratch / "checkout", tracked).chmod, _OWNER_ONLY)
        built = _send(scratch / "checkout", scratch / "received")
        self.assertEqual(built.returncode, 0, built.stderr[-_TAIL_CHARACTERS:])
        received = sorted(
            arrived.relative_to(scratch / "received").as_posix()
            for arrived in (scratch / "received").rglob("*") if arrived.is_file()
        )
        expected = [
            relative for relative in tracked
            if relative in _CONTEXT_FILES or relative.startswith(_CONTEXT_DIRECTORIES)
        ]
        self.assertEqual(received, sorted(expected))


if __name__ == "__main__":
    unittest.main()
