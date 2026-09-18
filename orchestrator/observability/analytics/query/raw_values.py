# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reading one raw column back, and telling a cleared multiselect apart.

A driver hands back whatever the column held, and every projection that fills a
frozen result row narrows it here: a NULL stays `None` rather than becoming a
zero the dashboard would render as a measured value, and a column a short
fixture never carried is read positionally so an older row shape still
round-trips. A JSONB cell is the one a driver may hand back as either an adapted
Python object or the raw JSON text, so both decode to the same value here, and
an `extras` blob that is NULL, unparseable, or not an object reads as an empty
mapping: a row written before a field existed and a row whose blob is damaged
both carry nothing a reader can look up, and neither may take a read down.

`empty_filter_selected` is the other reading a raw row is judged by, on the
call side rather than the result side: a selection of `None` means the caller
never filtered, while an empty one means the caller deselected everything, and
no row can match that -- so a read short-circuits on it instead of asking the
database for a result it already knows is empty.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any


def int_or_none(raw: Any) -> int | None:
    """Narrow one column to an int, keeping a NULL as `None`."""
    if raw is None:
        return None
    return int(raw)


def float_or_none(raw: Any) -> float | None:
    """Narrow one column to a float, keeping a NULL as `None`."""
    if raw is None:
        return None
    return float(raw)


def row_int(row: Sequence[Any], index: int) -> int:
    """Read one positional count off a row that may be shorter than it."""
    if len(row) <= index:
        return 0
    return int(row[index] or 0)


def bool_or_none(raw: Any) -> bool | None:
    """Narrow one column to a bool, keeping a NULL as `None`."""
    if raw is None:
        return None
    return bool(raw)


def decoded_json(raw: Any) -> Any:
    """Decode a JSONB cell a driver may hand back as raw JSON text."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None
    return raw


def json_object(raw: Any) -> dict[str, Any]:
    """Narrow a JSONB object cell to a dict, anything else reading as empty."""
    decoded = decoded_json(raw)
    if not isinstance(decoded, dict):
        return {}
    return decoded


def empty_filter_selected(selection: Sequence[str] | None) -> bool:
    """True when a multiselect was cleared rather than left unfiltered."""
    if selection is None:
        return False
    return len(selection) == 0
