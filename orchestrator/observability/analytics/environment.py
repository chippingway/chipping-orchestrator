# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the six analytics knobs parse to, in the spellings an operator writes.

One owner for the environment the analytics and trajectory sinks are
configured by: where each JSONL file is written and whether it is written at
all, how long the records in it are kept, whether a tracked run's skill
evidence is parsed, and the libpq URL the Postgres surfaces dial. The disable
vocabulary is shared -- an empty value and the sentinels `off` / `disabled` /
`none` (case-insensitive) turn a knob off wherever it appears -- so what "off"
spells and what it costs are settled together rather than agreeing by
coincidence across separate leaves.

Every parse reads the environment inside the call, never at this module's
import, so a holder rebuilt against a patched environment resolves to what
that environment implies. Where the parsed values are *bound* is the
`settings` owner, which calls each parse below once at its own import; how an
adapter reads one of them back afterwards is the `config` owner's question,
not this one's.
"""

from __future__ import annotations

import os
from pathlib import Path

_DISABLED_SENTINELS = ("off", "disabled", "none")

_TRUTHY_SPELLINGS = ("1", "true", "on", "yes")


def _explicit_path(raw: str | None) -> Path | None:
    """Read one path knob whose value is an operator's explicit opt-in.

    Disabled for an unset variable, an empty value, or a disable sentinel. The
    two path knobs differ only in what an *unset* variable means, so the rest
    of the vocabulary is settled here once.
    """
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped or stripped.lower() in _DISABLED_SENTINELS:
        return None
    return Path(stripped)


def parse_log_path() -> Path | None:
    """Resolve `ANALYTICS_LOG_PATH` from the environment.

    Unset -> default under `config.LOG_DIR` (already covered by the `logs/`
    .gitignore rule). Empty value and the sentinels `off` / `disabled` /
    `none` (case-insensitive) disable the sink entirely; `append_record` and
    `prune_old_records` become silent no-ops in that mode and no file is ever
    opened.

    `config` is imported inside the call rather than bound at module import so
    the default follows whichever `orchestrator.config` is current: a test that
    pops and re-imports it beside the `settings` holder to land a patched
    `LOG_DIR` sees the patched one.
    """
    from orchestrator import config

    raw = os.environ.get("ANALYTICS_LOG_PATH")
    if raw is None:
        return config.LOG_DIR / "analytics.jsonl"
    return _explicit_path(raw)


def parse_retention_days() -> int:
    """Resolve `ANALYTICS_RETENTION_DAYS` from the environment.

    Default 90 days. 0 (or any non-positive value) keeps raw data
    indefinitely -- `prune_old_records` becomes a no-op so operators can opt
    out of cleanup without disabling the sink itself.
    """
    return int(os.environ.get("ANALYTICS_RETENTION_DAYS", "90"))


def parse_db_url() -> str | None:
    """Resolve `ANALYTICS_DB_URL` from the environment.

    Unset / empty value and the sentinels `off` / `disabled` / `none`
    (case-insensitive) disable the Postgres surfaces (sync + read model)
    entirely; a real URL passes through verbatim so a libpq connection string
    is the single-knob endpoint contract. The orchestrator's polling tick does
    not read this var, so an unset value has no effect on workflow
    correctness. Matches `ANALYTICS_LOG_PATH`'s disable knob so the two can be
    turned off together with parallel spellings.
    """
    raw = os.environ.get("ANALYTICS_DB_URL", "").strip()
    if not raw or raw.lower() in _DISABLED_SENTINELS:
        return None
    return raw


def parse_track_skill_triggers() -> bool:
    """Resolve `TRACK_SKILL_TRIGGERS` from the environment.

    Default off. When on, `record_agent_exit` runs the skill-trigger extractor
    (`observability/usage/skills.py`) and folds `skills_triggered` /
    `skills_triggered_count` / `skills_available` / `skills_evidence` /
    `skills_incidental` / `skills_incidental_count` into the `agent_exit`
    record. The switch defaults off *because* the sink itself is default-on
    (`ANALYTICS_LOG_PATH` -> `LOG_DIR/analytics.jsonl`): an on-by-default
    switch would silently add skill fields to every default install's records,
    breaking the "absent opt-in -> today's record shape" guarantee. Truthy
    spellings match `orchestrator.config`'s other boolean knobs: `1` / `true` /
    `on` / `yes` (case-insensitive).
    """
    raw = os.environ.get("TRACK_SKILL_TRIGGERS", "off")
    return raw.strip().lower() in _TRUTHY_SPELLINGS


def parse_trajectory_log_path() -> Path | None:
    """Resolve `TRAJECTORY_LOG_PATH` from the environment.

    Opt-in / default off: unlike `ANALYTICS_LOG_PATH` (which defaults to a
    path under `config.LOG_DIR`), an *unset* `TRAJECTORY_LOG_PATH` disables
    the trajectory sink. Empty value and the sentinels `off` / `disabled` /
    `none` (case-insensitive) also disable it; any other value is the explicit
    opt-in path. When disabled, `append_trajectory_record` and
    `prune_trajectory_records` are silent no-ops and no file is ever opened.
    """
    return _explicit_path(os.environ.get("TRAJECTORY_LOG_PATH"))


def parse_trajectory_retention_days() -> int:
    """Resolve `TRAJECTORY_RETENTION_DAYS` from the environment.

    Default 90 days, matching `ANALYTICS_RETENTION_DAYS`. 0 (or any
    non-positive value) keeps trajectories indefinitely --
    `prune_trajectory_records` becomes a no-op so operators can opt out of
    cleanup without disabling the sink itself.
    """
    return int(os.environ.get("TRAJECTORY_RETENTION_DAYS", "90"))
