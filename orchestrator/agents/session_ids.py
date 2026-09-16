# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The session id a resume is issued against, read off any backend's output.

Which session a run belongs to is the one question asked of all supported CLIs, and it
is asked structurally: a UUID-shaped value at a known key, anywhere in the
event tree, whatever shape the backend wrapped it in. That is why the walk
lives apart from the `sessions` owner beside it -- those parsers read Claude's
stream schema by name, while this one is deliberately typed by no backend and
stays correct for output no supported CLI has published yet.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_PRIORITY_KEYS = ("session_id", "conversation_id", "thread_id", "session", "id")


def _first_nested_uuid(payload_nodes: Iterator[Any]) -> str | None:
    for payload_node in payload_nodes:
        found_uuid = _walk_for_uuid(payload_node)
        if found_uuid is not None:
            return found_uuid
    return None


def _walk_mapping_for_uuid(payload_node: dict[Any, Any]) -> str | None:
    priority_values = (
        payload_node[key]
        for key in _PRIORITY_KEYS
        if key in payload_node
    )
    priority_match = _first_nested_uuid(priority_values)
    if priority_match is not None:
        return priority_match
    return _first_nested_uuid(iter(payload_node.values()))


def _walk_for_uuid(payload_node: Any) -> str | None:
    if isinstance(payload_node, str):
        return payload_node if _UUID_RE.match(payload_node) else None
    if isinstance(payload_node, dict):
        return _walk_mapping_for_uuid(payload_node)
    if isinstance(payload_node, list):
        return _first_nested_uuid(iter(payload_node))
    return None


def parse_session_id(jsonl_output: str) -> str | None:
    """Return the first UUID at a known key anywhere in JSONL events."""
    for raw_line in jsonl_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event_payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = _walk_for_uuid(event_payload)
        if session_id:
            return session_id
    return None
