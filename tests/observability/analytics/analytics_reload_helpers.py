# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Re-parse the analytics settings holder against a hermetic environment."""

from __future__ import annotations

import importlib
import os
from types import ModuleType
from unittest.mock import patch

from tests.support.import_world_helpers import CONFIG_MODULE, SETTINGS_MODULE


def _hermetic_env(extra: dict[str, str] | None) -> dict[str, str]:
    environment = {
        "ORCHESTRATOR_SKIP_DOTENV": "1",
        "ORCHESTRATOR_TOKEN_FILE": "/tmp/chipping-orchestrator-token-missing",
    }
    if extra:
        environment.update(extra)
    return environment


def reload_analytics(
    environment: dict[str, str] | None = None,
) -> tuple[ModuleType, ModuleType]:
    """Re-parse every analytics knob against `environment`.

    Hands back the `orchestrator.config` / settings-holder pair the owners
    read through, so a test can assert on the values an environment implies
    and patch one of them for the call it is about to make.

    The holder is reloaded *in place* rather than replaced: every owner
    resolves it by name inside the call, and the suite-wide fixture patches
    the two sink knobs on the object it captured at collection, so a second
    module object would leave half the process reading values nobody set.
    That same fixture restores all six knobs when the test ends, which is what
    keeps one test's environment out of the next one's.
    """
    config = importlib.import_module(CONFIG_MODULE)
    settings = importlib.import_module(SETTINGS_MODULE)
    with patch.dict(os.environ, _hermetic_env(environment), clear=True):
        importlib.reload(settings)
    return config, settings
