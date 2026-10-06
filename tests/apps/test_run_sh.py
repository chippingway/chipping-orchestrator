# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for the production restart wrapper."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.apps.run_sh_test_support import (
    _INSTALLER,
    _SIGINT_EXIT_CODE,
    _TEXT_ENCODING,
    _WrapperScenario,
    _write_executable,
)

_WARNING = "WARNING"
_LOCK_NAME = "poetry.lock"
_REFRESH_WARNING = "WARNING: dependency refresh failed -- the environment may be partially updated"
_INSTALLER_CALL = "install --no-interaction\n"
_INSTALLER_FAILURE = "'poetry install --no-interaction' failed or timed out (300s limit)."


def _assert_launches(
    scenario: _WrapperScenario,
    completed: subprocess.CompletedProcess[str],
    *,
    count: int,
) -> None:
    assert completed.returncode == _SIGINT_EXIT_CODE
    assert "command not found" not in completed.stderr
    assert scenario.python_calls.read_text(encoding=_TEXT_ENCODING) == (
        "-m orchestrator\n" * count
    )


def _assert_self_update_attempt(
    scenario: _WrapperScenario,
    *,
    expect_pull: bool,
) -> None:
    git_log = scenario.git_calls.read_text(encoding=_TEXT_ENCODING)
    if expect_pull:
        assert "pull --ff-only origin main" in git_log
    else:
        assert "pull" not in git_log
        assert "branch --show-current" in git_log


def _assert_warning(
    completed: subprocess.CompletedProcess[str],
    warning: str | None,
) -> None:
    if warning is None:
        assert _WARNING not in completed.stderr
    else:
        assert warning in completed.stderr
        assert "running existing code" in completed.stderr


@pytest.mark.parametrize(
    "git_branch, git_pull_rc, expect_pull, warn_substr",
    [
        ("skills-update", "0", False, "self-update skipped"),
        ("main", "9", True, "self-update failed"),
        ("main", "0", True, None),
    ],
)
def test_self_update_launches_without_crash_loop(
    tmp_path: Path,
    git_branch: str,
    git_pull_rc: str,
    expect_pull: bool,
    warn_substr: str | None,
) -> None:
    scenario = _WrapperScenario.create(tmp_path, _SIGINT_EXIT_CODE)
    completed = scenario.run(
        git_branch=git_branch,
        git_pull_rc=git_pull_rc,
    )

    _assert_launches(scenario, completed, count=1)
    _assert_self_update_attempt(scenario, expect_pull=expect_pull)
    _assert_warning(completed, warn_substr)
    if expect_pull and warn_substr:
        assert f"exited with code {git_pull_rc}" in completed.stderr
    assert not scenario.installer_calls.exists()


def test_self_restart_applies_clean_fast_forward(
    tmp_path: Path,
) -> None:
    scenario = _WrapperScenario.create(
        tmp_path,
        0,
        _SIGINT_EXIT_CODE,
        record_sleep=True,
    )
    completed = scenario.run()

    _assert_launches(scenario, completed, count=2)
    assert scenario.git_calls.read_text(
        encoding=_TEXT_ENCODING,
    ).splitlines() == [
        "branch --show-current",
        "pull --ff-only origin main",
        "hash-object -- pyproject.toml poetry.lock",
        "branch --show-current",
        "pull --ff-only origin main",
        "hash-object -- pyproject.toml poetry.lock",
    ]
    assert scenario.sleep_calls.read_text(encoding=_TEXT_ENCODING) == "1\n"
    assert (
        "orchestrator exited with code 0; restarting in 1s"
        in completed.stdout
    )
    assert _WARNING not in completed.stderr


class TestDependencyRefresh:
    @pytest.mark.parametrize(
        "changed_path, expect_install",
        [("pyproject.toml", True), (_LOCK_NAME, True), ("README.md", False)],
    )
    def test_refresh_for_pulled_changes(self, tmp_path: Path, changed_path: str, expect_install: bool) -> None:
        scenario = _WrapperScenario.create(tmp_path, _SIGINT_EXIT_CODE)
        previous_signature = scenario.dependency_signature
        completed = scenario.run(changed_path=changed_path)

        _assert_launches(scenario, completed, count=1)
        assert (scenario.dependency_signature != previous_signature) == expect_install
        assert completed.stderr == ""
        if expect_install:
            assert scenario.installer_log == _INSTALLER_CALL
        else:
            assert not scenario.installer_calls.exists()

    def test_refresh_preserves_launch_environment(self, tmp_path: Path) -> None:
        scenario = _WrapperScenario.create(tmp_path, _SIGINT_EXIT_CODE)
        launch_environment = tmp_path / "launch-environment"
        _write_executable(
            scenario.fake_bin / _INSTALLER,
            r"""
            #!/usr/bin/env bash
            echo "$*" >> "$INSTALLER_CALLS"
            printf '%s\n' "${VIRTUAL_ENV-unset}" "${CONDA_PREFIX-unset}" >> "$INSTALLER_CALLS"
            """,
        )
        _write_executable(
            scenario.root / ".venv" / "bin" / "python",
            r"""
            #!/usr/bin/env bash
            echo "$*" >> "$PYTHON_CALLS"
            printf '%s\n' "$CONDA_PREFIX" "$CONDA_DEFAULT_ENV" "$CONDA_SHLVL" >> "$LAUNCH_ENV_CAPTURE"
            exit 130
            """,
        )
        with patch.dict("os.environ", {
            "VIRTUAL_ENV": "/srv/other-project/.venv",
            "CONDA_PREFIX": "/opt/conda/envs/operator",
            "CONDA_DEFAULT_ENV": "operator",
            "CONDA_SHLVL": "1",
            "LAUNCH_ENV_CAPTURE": str(launch_environment),
        }):
            completed = scenario.run(changed_path=_LOCK_NAME)

        _assert_launches(scenario, completed, count=1)
        assert completed.stderr == ""
        assert scenario.installer_log == f"{_INSTALLER_CALL}unset\nunset\n"
        assert launch_environment.read_text(encoding=_TEXT_ENCODING) == "/opt/conda/envs/operator\noperator\n1\n"

    def test_missing_stamp_refreshes_without_pull(self, tmp_path: Path) -> None:
        scenario = _WrapperScenario.create(tmp_path, _SIGINT_EXIT_CODE)
        scenario.dependency_stamp.unlink()
        completed = scenario.run()

        _assert_launches(scenario, completed, count=1)
        assert scenario.installer_log == _INSTALLER_CALL
        assert scenario.dependency_stamp.is_file()
        assert _WARNING not in completed.stderr

    def test_rollback_refreshes_without_a_new_pull(self, tmp_path: Path) -> None:
        scenario = _WrapperScenario.create(tmp_path, _SIGINT_EXIT_CODE)
        previous_signature = scenario.dependency_signature
        scenario.run(changed_path=_LOCK_NAME)
        scenario.installer_calls.unlink()
        scenario.python_calls.unlink()
        (scenario.root / _LOCK_NAME).write_text("poetry.lock before pull\n", encoding=_TEXT_ENCODING)
        completed = scenario.run()

        _assert_launches(scenario, completed, count=1)
        assert scenario.installer_log == _INSTALLER_CALL
        assert scenario.dependency_signature == previous_signature
        assert _WARNING not in completed.stderr


class TestDependencyRefreshFailures:
    def test_failure_launches_environment(self, tmp_path: Path) -> None:
        scenario = _WrapperScenario.create(
            tmp_path, 1, 1, _SIGINT_EXIT_CODE,
            record_sleep=True,
        )
        previous_signature = scenario.dependency_signature
        completed = scenario.run(changed_path=_LOCK_NAME, installer_rc="9")

        _assert_launches(scenario, completed, count=3)
        assert completed.stderr.count(_REFRESH_WARNING) == 3
        assert scenario.dependency_signature == previous_signature
        assert completed.stderr.count(_INSTALLER_FAILURE) == 3
        assert scenario.installer_log == (
            "install --no-interaction\n"
            "install --no-interaction\nafter-launch\n"
            "install --no-interaction\nafter-launch\n"
        )

    def test_missing_installer_launches_environment(self, tmp_path: Path) -> None:
        scenario = _WrapperScenario.create(
            tmp_path, 1, 1, _SIGINT_EXIT_CODE,
            installer_available=False, record_sleep=True,
        )
        previous_signature = scenario.dependency_signature
        completed = scenario.run(changed_path=_LOCK_NAME)

        _assert_launches(scenario, completed, count=3)
        assert completed.stderr.count(_REFRESH_WARNING) == 3
        assert completed.stderr.count("The Poetry executable is not on PATH.") == 3
        assert scenario.dependency_signature == previous_signature
        assert not scenario.installer_calls.exists()

    def test_stalled_refresh_is_killed_and_retried(self, tmp_path: Path) -> None:
        scenario = _WrapperScenario.create(tmp_path, 1, _SIGINT_EXIT_CODE, record_sleep=True)
        fake_timeout = scenario.fake_bin / "timeout"
        fake_timeout.unlink()
        _write_executable(
            fake_timeout,
            f"""
            #!/usr/bin/env bash
            echo "$*" >> "$INSTALLER_CALLS"
            shift 3
            exec {shutil.which('timeout')} --foreground --kill-after=0.1s 0.1s "$@"
            """,
        )
        _write_executable(
            scenario.fake_bin / _INSTALLER,
            """
            #!/usr/bin/env bash
            trap '' TERM
            while true; do :; done
            """,
        )
        previous_signature = scenario.dependency_signature
        completed = scenario.run(changed_path=_LOCK_NAME)

        _assert_launches(scenario, completed, count=2)
        assert completed.stderr.count(_REFRESH_WARNING) == 2
        assert completed.stderr.count(_INSTALLER_FAILURE) == 2
        assert scenario.dependency_signature == previous_signature
        assert scenario.installer_log == (
            "--foreground --kill-after=10s 300s poetry install --no-interaction\n" * 2
        )

    @pytest.mark.parametrize("stop_signal, exit_code", [("INT", _SIGINT_EXIT_CODE), ("TERM", 143)])
    def test_signals_interrupt_refresh(self, tmp_path: Path, stop_signal: str, exit_code: int) -> None:
        scenario = _WrapperScenario.create(tmp_path, _SIGINT_EXIT_CODE)
        _write_executable(
            scenario.fake_bin / _INSTALLER,
            f"""
            #!/usr/bin/env bash
            echo "$*" >> "$INSTALLER_CALLS"
            # Foreground timeout keeps the installer in the wrapper's process group.
            kill -{stop_signal} 0
            echo interrupt-missed >> "$INSTALLER_CALLS"
            """,
        )
        previous_signature = scenario.dependency_signature
        completed = scenario.run(changed_path=_LOCK_NAME)

        assert completed.returncode == exit_code
        assert not scenario.python_calls.exists()
        assert scenario.installer_log == _INSTALLER_CALL
        assert scenario.dependency_signature == previous_signature

    def test_retries_until_success(self, tmp_path: Path) -> None:
        scenario = _WrapperScenario.create(tmp_path, 1, 0, _SIGINT_EXIT_CODE, record_sleep=True)
        previous_signature = scenario.dependency_signature
        completed = scenario.run(changed_path=_LOCK_NAME, installer_rc="9 0")

        _assert_launches(scenario, completed, count=3)
        assert completed.stderr.count(_REFRESH_WARNING) == 1
        assert scenario.installer_log == (
            "install --no-interaction\ninstall --no-interaction\nafter-launch\n"
        )
        assert scenario.dependency_signature != previous_signature
