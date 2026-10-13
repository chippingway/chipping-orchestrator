# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One fenced block at the end of a decomposer reply, or a reason it is not one.

The decompose prompt promises exactly one `orchestrator-manifest` fence and
nothing after it, and this is where that promise is held to. The three answers
callers branch on are deliberate: a manifest, a manifest-shaped payload with a
reason it was rejected, and no fence at all. Only the middle one is the agent
getting it wrong; the last one is the agent asking a question, and the stage
parks those differently.

Both envelope rules exist because a decomposer message is prose around the
block. Taking the FIRST fence would let a manifest quoted from the prompt --
or from an earlier draft the agent talked itself out of -- override the answer
it actually settled on, so more than one fence is an error rather than a
choice; and content after the closing fence means the block was not the reply's
conclusion.

Both of those rules are answered by `_fenced_payload`, which the late mode's
parser beside this one asks about its own fence. What differs between the two
modes is not the envelope but what an ABSENT block means -- a question here, a
protocol failure there -- so the rule they share is spelled once and the
meaning each takes from it stays with its own caller.
"""
from __future__ import annotations

import json
import re

from orchestrator.workflow.stages.decomposition import validation as _validation

_MANIFEST_BLOCK = "orchestrator-manifest"

_MANIFEST_RE = re.compile(
    r"```orchestrator-manifest\s*\n(.*?)\n```",
    re.DOTALL,
)


def _fenced_payload(
    last_message: str,
    fence: re.Pattern,
    block_name: str,
) -> tuple[str | None, str | None]:
    """Extract the one final fenced payload of `block_name` from a reply.

    The envelope rules are the pattern's caller's, not the pattern's, so they
    are answered once here and the late mode beside this one asks the same
    question of its own fence: one block, and nothing after it.

    `(None, None)` is "no fence at all", which is not the same answer as a
    malformed one -- what each caller does with it is the caller's contract.
    """
    if not last_message:
        return None, None
    # The prompt requires exactly one final fenced block. Accepting the first
    # match would let a quoted sample manifest override the agent's answer.
    matches = list(fence.finditer(last_message))
    if not matches:
        return None, None
    if len(matches) > 1:
        return None, (
            f"expected exactly one {block_name} block, "
            f"found {len(matches)}"
        )
    manifest_match = matches[0]
    if last_message[manifest_match.end():].strip():
        return None, (
            f"{block_name} must be the final block; "
            "found content after the closing fence"
        )
    return manifest_match.group(1), None


def _extract_manifest_payload(
    last_message: str,
) -> tuple[str | None, str | None]:
    """Extract the one final fenced manifest payload from an agent reply."""
    return _fenced_payload(last_message, _MANIFEST_RE, _MANIFEST_BLOCK)


def _decode_manifest(
    payload: str,
) -> tuple[dict | None, str | None]:
    """Decode a manifest payload and require a JSON object."""
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as error:
        return None, f"invalid JSON: {error.msg}"
    if not isinstance(manifest, dict):
        return None, "manifest is not a JSON object"
    return manifest, None


def _manifest_validation_error(manifest: dict) -> str | None:
    """Validate the decision and its split-only payload when applicable."""
    decision = manifest.get("decision")
    if decision not in ("single", "split"):
        return "decision must be 'single' or 'split'"
    if decision == "single":
        return None
    return _validation._fresh_split_manifest_error(manifest)


def _parse_manifest(
    last_message: str,
) -> tuple[dict | None, str | None]:
    """Parse a fenced `orchestrator-manifest` block.

    Returns `(manifest, error_reason)`:
      * `(dict, None)` -- a valid manifest. `decision` is `"single"` or
        `"split"`; for `"split"`, `children` is non-empty and each entry has
        `title`/`body` and an explicit, structurally-valid `depends_on`
        index list (`[]` for no prerequisites). On
        `"single"` only `decision` is validated -- the optional context
        fields (`rationale`, `affected_files`, `notes`) pass through
        unvalidated and are sanitized where rendered.
      * `(None, error)` -- a fence was present but the payload was invalid.
        `error` is a short human-readable reason (used in the HITL park
        message).
      * `(None, None)` -- no fenced block at all. The caller treats this as
        "agent ended without a manifest" and parks as a question.
    """
    payload, payload_error = _extract_manifest_payload(last_message)
    if payload is None:
        return None, payload_error
    manifest, decode_error = _decode_manifest(payload)
    if manifest is None:
        return None, decode_error
    validation_error = _manifest_validation_error(manifest)
    if validation_error is not None:
        return None, validation_error
    return manifest, None
