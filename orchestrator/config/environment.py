# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Environment resolution for the config package.

This module owns env-value parsing (shell-like agent-backend specs,
positive-integer controls, non-negative budgets, the terminal-artifact cleanup
window and its timezone, HITL handle lists, verify-command lists) and the
`_SettingsResolver` that drives the whole
pipeline: it loads the non-secret `.env` (via the `_dotenv` leaf), then reads
each `os.environ` key, validates it, and returns the resolved settings
mapping. `orchestrator.config` invokes the resolver on every import / reload
and binds the mapping as the package's public API; the abort-on-invalid /
warn-to-stderr diagnostics the resolver calls on bad input are injected from
that package's single configuration-failure funnel.
"""
from __future__ import annotations

import datetime
import re
import shlex
from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from orchestrator.config._dotenv import _TRUE_VALUES, load_dotenv
from orchestrator.config.credentials import resolve_github_token
from orchestrator.config.models import RepoSpec
from orchestrator.config.repositories import build_repo_specs

ConfigError = Callable[[str], NoReturn]
ConfigWarning = Callable[[str], None]

# Default value for boolean env knobs that ship enabled.
_DEFAULT_ENABLED = "on"
_CLAUDE = "claude"
_CODEX = "codex"
_DEFAULT_REPO = "chippingway/orchestrator"
_DEFAULT_HITL = "geserdugarov"

# Added lines a candidate may carry and still publish as one change. Spelled
# here beside the other defaults; what a value at or past it means is on the
# setting itself in `orchestrator/config/__init__.py`.
_DEFAULT_MAX_ADDED_LINES = 4000

# Agent runs one issue may spend over its whole life. Finite by default, so a
# runaway issue is bounded even when no per-stage budget catches it; what the
# number counts is on the setting itself in `orchestrator/config/__init__.py`.
_DEFAULT_MAX_AGENT_RUNS_PER_ISSUE = 50

# Seconds between two terminal-artifact maintenance passes -- a day, so a host
# spends the disk of a finished issue for one more day at most; what a pass is
# and what it costs is on the setting itself in
# `orchestrator/config/__init__.py`.
_DEFAULT_ARTIFACT_CLEANUP_INTERVAL_SECONDS = 86400

# Polling ticks between two passes over the open dependency walks; what a
# skipped tick defers and why is on the setting itself in
# `orchestrator/config/__init__.py`.
_DEFAULT_DEPENDENCY_POLL_EVERY_N_TICKS = 5

_CLEANUP_WINDOW_SETTING = "TERMINAL_ARTIFACT_CLEANUP_WINDOW"
_CLEANUP_TIMEZONE_SETTING = "TERMINAL_ARTIFACT_CLEANUP_TIMEZONE"

# One 24-hour `HH:MM` endpoint. The digit classes are spelled in ASCII because
# `\d` also admits other scripts' digits, which `datetime.time` would then be
# asked to read.
_CLOCK_ENDPOINT = "(?:[01][0-9]|2[0-3]):[0-5][0-9]"
_CLEANUP_WINDOW_PATTERN = re.compile(f"{_CLOCK_ENDPOINT}-{_CLOCK_ENDPOINT}")


def parse_agent_spec(
    setting_name: str,
    agent_spec: str,
    config_error: ConfigError,
) -> tuple[str, tuple[str, ...]]:
    """Parse a shell-like backend spec into (backend, extra_args).

    Accepts a bare backend (`claude`) or a backend with backend-CLI args
    (`codex -m gpt-5.5 -c 'model_reasoning_effort="xhigh"'`). Tokens are
    split with `shlex` so quoting works the same way an operator would
    type the command in a shell. The first token must be `codex` or
    `claude`; anything else aborts at import so a typo cannot silently
    fall back to a default backend on next restart.

    The same parser is reused at runtime by `orchestrator.workflow` to
    re-parse a spec that was previously persisted to pinned state, so a
    legacy bare-backend value (`"codex"` / `"claude"`) round-trips cleanly
    to `(backend, ())` and a full spec with args round-trips to its tokens.
    """
    raw_spec = (agent_spec or "").strip()
    if not raw_spec:
        config_error(
            f"orchestrator: {setting_name}={agent_spec!r} is empty; "
            "expected 'codex' or 'claude' (optionally followed by CLI args)",
        )
    try:
        spec_tokens = shlex.split(raw_spec)
    except ValueError as error:
        config_error(
            f"orchestrator: {setting_name}={agent_spec!r} is not a valid "
            f"shell-like command spec ({error}); expected 'codex' or "
            "'claude' (optionally followed by CLI args)",
        )
    if not spec_tokens:
        config_error(
            f"orchestrator: {setting_name}={agent_spec!r} parses to no "
            "tokens; expected 'codex' or 'claude' "
            "(optionally followed by CLI args)",
        )
    backend = spec_tokens[0].lower()
    if backend not in (_CODEX, _CLAUDE):
        config_error(
            f"orchestrator: {setting_name}={agent_spec!r} first token "
            f"{spec_tokens[0]!r} is invalid; expected 'codex' or 'claude'",
        )
    return backend, tuple(spec_tokens[1:])


class PositiveIntParser:
    """Callable positive-integer parser bound to the config error funnel."""

    def __init__(self, config_error: Callable[[str], NoReturn]) -> None:
        self._config_error = config_error

    def __call__(
        self,
        setting_name: str,
        raw_setting: str,
        default: int,
    ) -> int:
        stripped_setting = (raw_setting or "").strip()
        if not stripped_setting:
            return default
        try:
            parsed_setting = int(stripped_setting)
        except ValueError:
            self._config_error(
                f"orchestrator: {setting_name}={raw_setting!r} is not a "
                "valid integer; expected a positive integer (>= 1)",
            )
        if parsed_setting < 1:
            self._config_error(
                f"orchestrator: {setting_name}={raw_setting!r} must be >= 1 "
                "(zero or negative would block all work)",
            )
        return parsed_setting


class NonNegativeIntParser:
    """Callable non-negative-integer parser bound to the config error funnel.

    The shape a budget takes when zero is a value an operator means rather
    than a typo: `0` is that setting's own spelling of "unlimited", so only a
    negative -- a ceiling no run could ever come in under -- and a
    non-integer abort. `PositiveIntParser` above is the other shape, where a
    zero would block all work and is refused for exactly that reason.
    """

    def __init__(self, config_error: Callable[[str], NoReturn]) -> None:
        self._config_error = config_error

    def __call__(
        self,
        setting_name: str,
        raw_setting: str,
        default: int,
    ) -> int:
        stripped_setting = (raw_setting or "").strip()
        if not stripped_setting:
            return default
        try:
            parsed_setting = int(stripped_setting)
        except ValueError:
            self._config_error(
                f"orchestrator: {setting_name}={raw_setting!r} is not a "
                "valid integer; expected 0 (unlimited) or a positive integer",
            )
        if parsed_setting < 0:
            self._config_error(
                f"orchestrator: {setting_name}={raw_setting!r} must be >= 0 "
                "(0 means unlimited; a negative ceiling refuses every run)",
            )
        return parsed_setting


class CleanupWindowParser:
    """Callable terminal-artifact cleanup window parser bound to the funnel.

    Reads the window and its timezone as one pair, because the zone means
    nothing without a window: an unset or blank window is disabled and leaves
    the zone unread, so a stale zone beside a blanked window cannot abort a
    start, and both resolve to `None`. A set window resolves to its
    `(start, end)` clock times and demands a zone, which is resolved here so
    a name the host cannot find aborts at import rather than at the first
    pass that would read the clock in it.
    """

    def __init__(self, config_error: ConfigError) -> None:
        self._config_error = config_error

    def __call__(self, environ: Mapping[str, str]) -> dict[str, Any]:
        window = self._window(environ.get(_CLEANUP_WINDOW_SETTING, ""))
        return {
            _CLEANUP_WINDOW_SETTING: window,
            _CLEANUP_TIMEZONE_SETTING: None if window is None else self._timezone(
                environ.get(_CLEANUP_TIMEZONE_SETTING, ""),
            ),
        }

    def _window(
        self, raw_window: str,
    ) -> tuple[datetime.time, datetime.time] | None:
        stripped_window = raw_window.strip()
        if not stripped_window:
            return None
        if _CLEANUP_WINDOW_PATTERN.fullmatch(stripped_window) is None:
            self._config_error(
                f"orchestrator: {_CLEANUP_WINDOW_SETTING}={raw_window!r} is not "
                "a valid window; expected 24-hour HH:MM-HH:MM such as "
                "03:00-05:00",
            )
        start, end = (
            datetime.time.fromisoformat(endpoint)
            for endpoint in stripped_window.split("-")
        )
        if start == end:
            self._config_error(
                f"orchestrator: {_CLEANUP_WINDOW_SETTING}={raw_window!r} starts "
                "where it ends; expected distinct HH:MM-HH:MM endpoints (an "
                "end earlier than the start crosses midnight)",
            )
        return start, end

    def _timezone(self, raw_timezone: str) -> ZoneInfo:
        stripped_timezone = raw_timezone.strip()
        if not stripped_timezone:
            self._config_error(
                f"orchestrator: {_CLEANUP_TIMEZONE_SETTING}={raw_timezone!r} is "
                f"empty but {_CLEANUP_WINDOW_SETTING} is set; expected an IANA "
                "timezone such as Asia/Novosibirsk",
            )
        try:
            zone = ZoneInfo(stripped_timezone)
        except (ZoneInfoNotFoundError, ValueError, OSError) as error:
            self._config_error(
                f"orchestrator: {_CLEANUP_TIMEZONE_SETTING}={raw_timezone!r} is "
                f"not a resolvable IANA timezone ({error}); expected a name such "
                "as Asia/Novosibirsk",
            )
        return zone


def parse_hitl_handles(raw_handles: str) -> tuple[str, ...]:
    """Normalize, deduplicate, and preserve configured handle order."""
    handles: list[str] = []
    seen_handles: set[str] = set()
    for raw_handle in raw_handles.split(","):
        hitl_handle = raw_handle.strip().lstrip("@").strip()
        if not hitl_handle or hitl_handle in seen_handles:
            continue
        handles.append(hitl_handle)
        seen_handles.add(hitl_handle)
    return tuple(handles)


def parse_verify_commands(raw_commands: str) -> tuple[str, ...]:
    """Split newline/semicolon commands, dropping blanks and comments."""
    commands: list[str] = []
    for raw_line in raw_commands.replace(";", "\n").splitlines():
        command = raw_line.strip()
        if command and not command.startswith("#"):
            commands.append(command)
    return tuple(commands)


class _SettingsResolver:
    """Resolve every setting from a `.env`-loaded environment.

    One instance per config import / reload. `resolve` loads the non-secret
    `.env` (so a reload re-reads it), then reads and validates each
    `os.environ` key into a flat mapping the package binds as its public API.
    Grouping the reads into small section methods keeps each within the
    resolver's local-variable budget without changing any value's meaning,
    default, or abort/warning text.
    """

    def __init__(
        self,
        environ: MutableMapping[str, str],
        repo_root: Path,
        config_error: ConfigError,
        config_warning: ConfigWarning,
    ) -> None:
        self._environ = environ
        self._repo_root = repo_root
        self._config_error = config_error
        self._config_warning = config_warning

    def resolve(self) -> dict[str, Any]:
        """Load `.env` then resolve and validate every setting."""
        load_dotenv(self._repo_root, self._environ, self._config_warning)
        resolved = self._identity()
        resolved.update(self._controls())
        resolved.update(self._agents())
        resolved.update(self._repos(resolved))
        return resolved

    def _identity(self) -> dict[str, Any]:
        env = self._environ
        repo = env.get("REPO", _DEFAULT_REPO)
        agent_timeout = int(env.get("AGENT_TIMEOUT", "1800"))
        event_log_raw = env.get("EVENT_LOG_PATH", "").strip()
        return {
            "REPO": repo,
            "GITHUB_TOKEN": resolve_github_token(repo),
            "POLL_INTERVAL": int(env.get("POLL_INTERVAL", "60")),
            "AGENT_TIMEOUT": agent_timeout,
            "REVIEW_TIMEOUT": int(env.get("REVIEW_TIMEOUT", str(agent_timeout))),
            "CLOSED_ISSUE_SWEEP_EVERY_N_TICKS": max(
                1, int(env.get("CLOSED_ISSUE_SWEEP_EVERY_N_TICKS", "1")),
            ),
            "SHUTDOWN_GRACE_SECONDS": max(
                1, int(env.get("SHUTDOWN_GRACE_SECONDS", "30")),
            ),
            "LOG_DIR": Path(env.get("LOG_DIR", str(self._repo_root / "logs"))),
            "EVENT_LOG_PATH": Path(event_log_raw) if event_log_raw else None,
        }

    def _controls(self) -> dict[str, Any]:
        env = self._environ
        positive_int = PositiveIntParser(self._config_error)
        non_negative_int = NonNegativeIntParser(self._config_error)
        raw_guard = env.get("WORKFLOW_TRANSITION_GUARD", "")
        guard = raw_guard.strip().lower() or "warn"
        if guard not in ("off", "warn", "enforce"):
            self._config_error(
                f"orchestrator: WORKFLOW_TRANSITION_GUARD={raw_guard!r} is "
                "invalid; expected one of: off, warn, enforce",
            )
        return {
            "MAX_REVIEW_ROUNDS": int(env.get("MAX_REVIEW_ROUNDS", "3")),
            "MAX_CONFLICT_ROUNDS": int(env.get("MAX_CONFLICT_ROUNDS", "3")),
            "MAX_RETRIES_PER_DAY": int(env.get("MAX_RETRIES_PER_DAY", "3")),
            "DEV_SESSION_MAX_RESUMES": int(
                env.get("DEV_SESSION_MAX_RESUMES", "10"),
            ),
            "IN_REVIEW_DEBOUNCE_SECONDS": int(
                env.get("IN_REVIEW_DEBOUNCE_SECONDS", "600"),
            ),
            "VERIFY_TIMEOUT": int(env.get("VERIFY_TIMEOUT", "600")),
            "MAX_ADDED_LINES": positive_int(
                "MAX_ADDED_LINES",
                env.get("MAX_ADDED_LINES", ""),
                _DEFAULT_MAX_ADDED_LINES,
            ),
            "MAX_AGENT_RUNS_PER_ISSUE": non_negative_int(
                "MAX_AGENT_RUNS_PER_ISSUE",
                env.get("MAX_AGENT_RUNS_PER_ISSUE", ""),
                _DEFAULT_MAX_AGENT_RUNS_PER_ISSUE,
            ),
            "TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS": positive_int(
                "TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS",
                env.get("TERMINAL_ARTIFACT_CLEANUP_INTERVAL_SECONDS", ""),
                _DEFAULT_ARTIFACT_CLEANUP_INTERVAL_SECONDS,
            ),
            **CleanupWindowParser(self._config_error)(env),
            "DEPENDENCY_POLL_EVERY_N_TICKS": positive_int(
                "DEPENDENCY_POLL_EVERY_N_TICKS",
                env.get("DEPENDENCY_POLL_EVERY_N_TICKS", ""),
                _DEFAULT_DEPENDENCY_POLL_EVERY_N_TICKS,
            ),
            "VERIFY_COMMANDS": parse_verify_commands(env.get("VERIFY_COMMANDS", "")),
            "ORCHESTRATOR_BASE_BRANCH": env.get("ORCHESTRATOR_BASE_BRANCH", "main"),
            "WORKFLOW_TRANSITION_GUARD": guard,
            "DECOMPOSE": env.get(
                "DECOMPOSE", _DEFAULT_ENABLED,
            ).strip().lower() in _TRUE_VALUES,
            "SQUASH_ON_APPROVAL": env.get(
                "SQUASH_ON_APPROVAL", _DEFAULT_ENABLED,
            ).strip().lower() in _TRUE_VALUES,
            "PR_REF_IN_SUBJECT": env.get(
                "PR_REF_IN_SUBJECT", _DEFAULT_ENABLED,
            ).strip().lower() in _TRUE_VALUES,
            "EXPOSE_TRACKED_REPOS": env.get(
                "EXPOSE_TRACKED_REPOS", _DEFAULT_ENABLED,
            ).strip().lower() in _TRUE_VALUES,
        }

    def _agents(self) -> dict[str, Any]:
        env = self._environ
        handles = parse_hitl_handles(
            env.get("HITL_HANDLE", _DEFAULT_HITL),
        ) or (_DEFAULT_HITL,)
        resolved = self._one_agent("DEV_AGENT", _CLAUDE)
        resolved.update(self._one_agent("REVIEW_AGENT", _CODEX))
        resolved.update(self._one_agent("DECOMPOSE_AGENT", _CLAUDE))
        resolved.update({
            "CODEX_BIN": env.get("CODEX_BIN", _CODEX),
            "CLAUDE_BIN": env.get("CLAUDE_BIN", _CLAUDE),
            "AGENT_GIT_NAME": env.get("AGENT_GIT_NAME", "chipping-orchestrator"),
            "AGENT_GIT_EMAIL": env.get(
                "AGENT_GIT_EMAIL", "chipping-orchestrator@users.noreply.github.com",
            ),
            "HITL_HANDLES": handles,
            "HITL_HANDLE": ",".join(handles),
            "HITL_MENTIONS": " ".join(
                f"@{hitl_handle}" for hitl_handle in handles
            ),
            "ALLOWED_ISSUE_AUTHORS": parse_hitl_handles(
                env.get("ALLOWED_ISSUE_AUTHORS", ""),
            ),
        })
        return resolved

    def _repos(self, resolved: dict[str, Any]) -> dict[str, Any]:
        env = self._environ
        positive_int = PositiveIntParser(self._config_error)
        target_root = Path(env.get("TARGET_REPO_ROOT", str(self._repo_root)))
        default_spec = RepoSpec(
            slug=resolved["REPO"],
            target_root=target_root,
            base_branch=env.get("BASE_BRANCH", "main"),
            remote_name=env.get("REMOTE_NAME", "origin"),
            parallel_limit=positive_int(
                "MAX_PARALLEL_ISSUES_PER_REPO",
                env.get("MAX_PARALLEL_ISSUES_PER_REPO", ""),
                1,
            ),
        )
        return {
            "TARGET_REPO_ROOT": target_root,
            "WORKTREES_DIR": Path(
                env.get("WORKTREES_DIR", str(target_root.parent / "wt-orchestrator")),
            ),
            "BASE_BRANCH": default_spec.base_branch,
            "REMOTE_NAME": default_spec.remote_name,
            "MAX_PARALLEL_ISSUES_PER_REPO": default_spec.parallel_limit,
            "MAX_PARALLEL_ISSUES_GLOBAL": positive_int(
                "MAX_PARALLEL_ISSUES_GLOBAL",
                env.get("MAX_PARALLEL_ISSUES_GLOBAL", ""),
                3,
            ),
            "REPO_SPECS": build_repo_specs(
                env.get("REPOS", ""),
                default_spec=default_spec,
                config_error=self._config_error,
                config_warning=self._config_warning,
            ),
        }

    def _one_agent(self, setting_name: str, default: str) -> dict[str, Any]:
        spec = self._environ.get(setting_name, default)
        backend, arguments = parse_agent_spec(setting_name, spec, self._config_error)
        return {
            f"{setting_name}_SPEC": spec,
            setting_name: backend,
            f"{setting_name}_ARGS": arguments,
        }
