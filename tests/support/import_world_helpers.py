# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Keep one `orchestrator.config` object installed across a reload test.

A reload test pops modules so a re-import re-runs against a patched
environment. What it must not leave behind is a rebuilt `orchestrator.config`:
dozens of unrelated modules bind that module object once, at their own import
time, so a swap splits them into two camps -- whoever imported before the swap
holds one object, whoever imports after holds the other. A
`patch.object(config, ...)` then reaches only one camp and the other keeps
answering with the real settings. Which module lands in which camp depends on
when it happened to be first imported, so the symptom is a test that passes
alone and fails in a full run.

The analytics settings holder is never swapped for the same reason, which is
why it is named here but not restored: a re-parse reloads it in place (see
`tests/observability/analytics/analytics_reload_helpers.py`), so every owner
keeps the one object the suite-wide fixture patches.

The reloaded modules themselves are still what the test drives; only the
process-wide bindings are put back. Restoring `sys.modules` alone would not do
it: importing `orchestrator.config` also rebinds `config` on the persistent
`orchestrator` package object, so a later `from orchestrator import config`
would resolve the discarded reload straight out of the package namespace.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

CONFIG_MODULE = "orchestrator.config"

ANALYTICS_OWNERS = "orchestrator.observability.analytics"

SETTINGS_ATTRIBUTE = "settings"

SETTINGS_MODULE = f"{ANALYTICS_OWNERS}.{SETTINGS_ATTRIBUTE}"

_PACKAGE = "orchestrator"

_ATTRIBUTE = "config"

_MISSING = object()


def _reinstate(saved_module: object, saved_attribute: object) -> None:
    """Drop whatever the body installed and put the entering module back."""
    package = sys.modules[_PACKAGE]
    sys.modules.pop(CONFIG_MODULE, None)
    package.__dict__.pop(_ATTRIBUTE, None)
    if saved_module is not _MISSING:
        sys.modules[CONFIG_MODULE] = saved_module
    if saved_attribute is not _MISSING:
        package.__dict__[_ATTRIBUTE] = saved_attribute


@contextmanager
def restored_import_world() -> Iterator[None]:
    """Reinstate the entering `orchestrator.config` module when the body ends.

    The body is free to pop and re-import it; whatever it installs is what the
    body returns, but the module the rest of the session resolves is the one it
    started with.
    """
    saved_module = sys.modules.get(CONFIG_MODULE, _MISSING)
    saved_attribute = sys.modules[_PACKAGE].__dict__.get(_ATTRIBUTE, _MISSING)
    try:
        yield
    finally:
        _reinstate(saved_module, saved_attribute)
