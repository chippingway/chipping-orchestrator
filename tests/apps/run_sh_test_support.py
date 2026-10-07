# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Filesystem and process fixtures for the development restart wrapper."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_TEXT_ENCODING = "utf-8"
_SIGINT_EXIT_CODE = 130
_INSTALLER = "poetry"
_DEPENDENCY_STAMP = ".venv/.poetry-dependencies"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(
        textwrap.dedent(text).lstrip(),
        encoding=_TEXT_ENCODING,
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _wrapper_copy(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy2(ROOT / "run.sh", root / "run.sh")
    (root / ".venv" / "bin").mkdir(parents=True)
    for name in ("pyproject.toml", "poetry.lock", "README.md"):
        (root / name).write_text(f"{name} before pull\n", encoding=_TEXT_ENCODING)
    signature = subprocess.run(
        ["git", "hash-object", "--", "pyproject.toml", "poetry.lock"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    (root / _DEPENDENCY_STAMP).write_text(signature, encoding=_TEXT_ENCODING)
    return root


def _env(fake_bin: Path, **extra: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(extra)
    # Only explicitly provided tools can run, including on hosts with system Poetry.
    environment["PATH"] = str(fake_bin)
    return environment


def _write_fake_git(fake_bin: Path) -> None:
    _write_executable(
        fake_bin / "git",
        r"""
        #!/usr/bin/env bash
        echo "$*" >> "$GIT_CALLS"
        if [ "$1" = "branch" ]; then
            printf '%s\n' "${GIT_BRANCH:-main}"
            exit 0
        fi
        if [ "$1" = "pull" ]; then
            if [ "${GIT_PULL_RC:-0}" = 0 ] && [ -n "${GIT_CHANGED_PATH:-}" ] && [ ! -f "$GIT_UPDATED" ]; then
                echo pulled-change >> "$GIT_CHANGED_PATH"
                echo updated > "$GIT_UPDATED"
            fi
            exit "${GIT_PULL_RC:-0}"
        fi
        if [ "$1" = "hash-object" ]; then
            exec "$SYSTEM_GIT" "$@"
        fi
        exit 0
        """,
    )


def _write_fake_python(root: Path, *exit_codes: int) -> None:
    codes = " ".join(
        str(code)
        for code in (exit_codes or (_SIGINT_EXIT_CODE,))
    )
    _write_executable(
        root / ".venv" / "bin" / "python",
        f"""
        #!/usr/bin/env bash
        echo "$*" >> "$PYTHON_CALLS"
        codes=({codes})
        count=0
        [ -f "$PYTHON_COUNT" ] && count=$(cat "$PYTHON_COUNT")
        idx=$count
        [ "$idx" -ge "${{#codes[@]}}" ] && idx=$((${{#codes[@]}} - 1))
        echo "$((count + 1))" > "$PYTHON_COUNT"
        exit "${{codes[$idx]}}"
        """,
    )


def _write_fake_tools(fake_bin: Path, *, installer_available: bool, record_sleep: bool) -> None:
    for name in ("bash", "cat", "date", "dirname", "env", "head", "sed", "sleep", "timeout", "tr"):
        if name != "sleep" or not record_sleep:
            (fake_bin / name).symlink_to(shutil.which(name))
    if installer_available:
        _write_executable(
            fake_bin / _INSTALLER,
            """
            #!/usr/bin/env bash
            echo "$*" >> "$INSTALLER_CALLS"
            [ -f "$PYTHON_CALLS" ] && echo after-launch >> "$INSTALLER_CALLS"
            codes=(${INSTALLER_RC:-0})
            count=0
            [ -f "$INSTALLER_COUNT" ] && count=$(cat "$INSTALLER_COUNT")
            idx=$count
            [ "$idx" -ge "${#codes[@]}" ] && idx=$((${#codes[@]} - 1))
            echo "$((count + 1))" > "$INSTALLER_COUNT"
            exit "${codes[$idx]}"
            """,
        )
    if record_sleep:
        _write_executable(
            fake_bin / "sleep",
            """
            #!/usr/bin/env bash
            echo "$*" >> "$SLEEP_CALLS"
            exit 0
            """,
        )


@dataclass(frozen=True)
class _WrapperScenario:
    root: Path
    fake_bin: Path
    git_calls: Path
    python_calls: Path
    python_count: Path
    sleep_calls: Path
    installer_calls: Path

    @property
    def dependency_stamp(self) -> Path:
        return self.root / _DEPENDENCY_STAMP

    @property
    def dependency_signature(self) -> str:
        return self.dependency_stamp.read_text(encoding=_TEXT_ENCODING)

    @property
    def installer_log(self) -> str:
        return self.installer_calls.read_text(encoding=_TEXT_ENCODING)

    @classmethod
    def create(
        cls,
        tmp_path: Path,
        *python_exit_codes: int,
        record_sleep: bool = False,
        installer_available: bool = True,
    ) -> _WrapperScenario:
        scenario = cls(
            root=_wrapper_copy(tmp_path),
            fake_bin=tmp_path / "bin",
            git_calls=tmp_path / "git-calls",
            python_calls=tmp_path / "python-calls",
            python_count=tmp_path / "python-count",
            sleep_calls=tmp_path / "sleep-calls",
            installer_calls=tmp_path / "installer-calls",
        )
        scenario.fake_bin.mkdir()
        _write_fake_git(scenario.fake_bin)
        _write_fake_python(scenario.root, *python_exit_codes)
        _write_fake_tools(scenario.fake_bin, installer_available=installer_available, record_sleep=record_sleep)
        return scenario

    def run(
        self,
        *,
        git_branch: str = "main",
        git_pull_rc: str = "0",
        changed_path: str = "",
        installer_rc: str = "0",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "run.sh"],
            cwd=self.root,
            env=_env(
                self.fake_bin,
                GIT_CALLS=str(self.git_calls),
                GIT_BRANCH=git_branch,
                GIT_PULL_RC=git_pull_rc,
                GIT_CHANGED_PATH=changed_path,
                GIT_UPDATED=f"{self.git_calls}.updated",
                SYSTEM_GIT=shutil.which("git"),
                PYTHON_CALLS=str(self.python_calls),
                PYTHON_COUNT=str(self.python_count),
                SLEEP_CALLS=str(self.sleep_calls),
                INSTALLER_CALLS=str(self.installer_calls),
                INSTALLER_RC=installer_rc,
                INSTALLER_COUNT=f"{self.installer_calls}.count",
            ),
            capture_output=True,
            text=True,
            start_new_session=True,
            timeout=5,
            check=False,
        )
