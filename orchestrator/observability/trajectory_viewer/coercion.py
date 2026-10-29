# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Narrowing an untyped JSON value to the type a model field declares.

The file behind the viewer is append-only and was written by whichever
orchestrator version was running at the time, so a field can be absent, spelled
as a string, or a scalar where an array belongs. Each helper answers with the
declared type or that type's empty value, never an exception, because a record
the reader cannot fully understand still has to render as a smaller row rather
than break the page.

``bool`` is refused ahead of ``int`` because it is one in Python: a ``true``
where a token count belongs is a corrupt record, not a 1.
"""

from __future__ import annotations

from typing import Any


def coerce_int(raw_value: Any) -> int | None:
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str):
        try:
            return int(raw_value.strip())
        except ValueError:
            return None
    return None


def coerce_str(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    if isinstance(raw_value, str):
        return raw_value
    return str(raw_value)


def coerce_str_tuple(raw_value: Any) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        return ()
    return tuple(coerce_str(name) for name in raw_value if name is not None)


def as_list(raw_value: Any) -> list[Any]:
    return raw_value if isinstance(raw_value, list) else []
