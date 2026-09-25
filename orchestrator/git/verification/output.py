# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The redact-then-truncate pass every captured verify output goes through.

Both classification paths -- the timeout drain's partial bytes and a completed
command's merged stdout/stderr -- reach `VerifyCommandOutcome.output` through
this owner, and a refused run's `VerifyResult.output` restates the refusing
command's, so the ordering the park comment depends on is stated once. It sits
below the process and runner owners and reaches the credentials owner directly
because redaction is a settings-layer concern, not a subprocess one.
"""
from __future__ import annotations

from orchestrator.config import credentials as _credentials
from orchestrator.git.verification import models as _models

# What the budget is counted in. `_VERIFY_OUTPUT_BUDGET` is a byte count, and
# a character count would let multi-byte output run to four times it.
_OUTPUT_ENCODING = "utf-8"


def _truncate_verify_output(text: str) -> str:
    """Redact secrets, then keep the tail within `_VERIFY_OUTPUT_BUDGET` bytes.

    Redaction MUST happen before the truncation. `redact_secrets` does a
    full-string `str.replace(value, "***")` against each candidate env
    value; if the truncation cut sliced a secret in half first, the
    surviving partial would no longer match the replace and would leak
    verbatim in the park comment. Redacting first collapses any matched
    secret to `***` before its bytes can straddle the cut.

    The tail typically carries the actual failure (stack trace, assertion
    diff, linter summary); the head is build noise. Identical convention
    to `_format_stderr_diagnostics`.

    The budget is UTF-8 bytes, so the cut is taken on the encoded text: 4096
    emoji are 16384 bytes, and a tail of them keeps 1024. A character the cut
    lands inside loses its leading bytes, and the continuation bytes left over
    decode to nothing, so the tail opens on the first whole character rather
    than on a replacement mark. `surrogatepass` keeps a lone surrogate from
    raising while the text is measured; it is dropped with the partial bytes.
    """
    if not text:
        return ""
    redacted = _credentials.redact_secrets(text)
    encoded = redacted.encode(_OUTPUT_ENCODING, errors="surrogatepass")
    if len(encoded) <= _models._VERIFY_OUTPUT_BUDGET:
        return redacted
    tail = encoded[-_models._VERIFY_OUTPUT_BUDGET:]
    return tail.decode(_OUTPUT_ENCODING, errors="ignore")
