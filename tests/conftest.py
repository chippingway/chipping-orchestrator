# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pytest fixtures shared by the whole test suite.

Two autouse fixtures keep the suite off the operator's own files: one
disables the analytics sinks, and one gives every test its own issue
writer-claim namespace.

The first disables the analytics sinks for every test.
`_run_agent_tracked` on `workflow/engine/usage.py` appends a record per
tracked agent run, and the append reads `ANALYTICS_LOG_PATH` off the
analytics `settings` holder at call time; that knob defaults to
`<LOG_DIR>/analytics.jsonl` under the repo root, so any test that drives
a stage handler (directly or via the workflow mixin) would otherwise
scribble into the operator's real log directory. The autouse fixture
below patches the path to `None` (the documented "off" knob) so the
suite is hermetic by default.

The same handler also writes a redacted `agent_trajectory` record to
`TRAJECTORY_LOG_PATH` -- the opt-in trajectory sink. It defaults off
(unset env), but an operator who exported `TRAJECTORY_LOG_PATH` before
running `pytest` would have the resolved path live on that holder, so
every tracked-agent test would scribble trajectories into their real
file. The fixture pins it to `None` too, for the same hermeticity
reason.

Tests that need a sink (e.g. `AgentAnalyticsTest`, the trajectory
recording tests) override the patch inline -- nested `patch.object`
lets the inner temp path win for the duration of its context, then
unwinds back to `None`.

The fixture also puts all six knobs back when the test ends. A test that
re-parses the holder against its own environment reloads it in place, so
the values it lands would otherwise outlive it and decide what the next
test reads.

The second exists because every dispatched issue is taken under a
host-local writer claim, and the claim's namespace sits under
`WORKTREES_DIR` -- which, unset as it is here, is the directory beside the
checkout an operator's own orchestrator claims in. A test dispatching
`#7` there would contend with a live poller holding it, and would leave
its files behind. So each test claims in a directory of its own under one
session root, made only if the test takes a claim at all, and a claim a
test leaves held cannot reach the next one. A test that needs the real
namespace patches `_namespace` back for itself.
"""
from __future__ import annotations

import itertools
from importlib import import_module
from unittest.mock import patch

import pytest

from tests.support.bootstrap import normalize_test_environment

normalize_test_environment()

analytics_settings = import_module(
    "orchestrator.observability.analytics.settings",
)

writer_claims = import_module("orchestrator.scheduler.writer_claims")

_claim_namespaces = itertools.count()

_KNOBS = (
    "ANALYTICS_DB_URL",
    "ANALYTICS_LOG_PATH",
    "ANALYTICS_RETENTION_DAYS",
    "TRACK_SKILL_TRIGGERS",
    "TRAJECTORY_LOG_PATH",
    "TRAJECTORY_RETENTION_DAYS",
)


@pytest.fixture(autouse=True)
def _disable_analytics_sink():
    entering = {name: getattr(analytics_settings, name) for name in _KNOBS}
    try:
        with patch.object(analytics_settings, "ANALYTICS_LOG_PATH", None), \
                patch.object(analytics_settings, "TRAJECTORY_LOG_PATH", None):
            yield
    finally:
        for name, knob in entering.items():
            setattr(analytics_settings, name, knob)


@pytest.fixture(scope="session")
def _writer_claim_root(tmp_path_factory):
    return tmp_path_factory.mktemp("writer-claims")


@pytest.fixture(autouse=True)
def _isolate_writer_claims(_writer_claim_root):
    namespace = _writer_claim_root / str(next(_claim_namespaces))
    with patch.object(writer_claims, "_namespace", lambda: namespace):
        yield
