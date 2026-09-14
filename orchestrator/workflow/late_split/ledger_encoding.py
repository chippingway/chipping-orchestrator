# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the two external ledgers are written back as.

The one pair of fields a generation write does not rewrite from the typed
record, which is why the encoder for them sits apart from the one that spells
every other field. A ledger the reader could not fully type comes back
verbatim beside the typed view, and the verbatim copy is what is written: an
obligation an older or newer binary recorded is still owed, and a write that
reduced the ledger to the entries this binary understood would delete it --
leaving a cleanup looking complete and a snapshot looking reclaimable.

It is also the half of the ledger contract a clear does not reach. A record
with no cycle identity is not a generation, so the write beside this one drops
every other late field rather than recording a half-record no later tick could
correlate; an obligation the remote is owed does not stop being owed because
the identity beside it was damaged, and dropping it would leave a snapshot or
a branch with nothing on the issue to reclaim it by.

The wire spellings an entry is composed from are the `ledgers` owner's, beside
the reader that parses them back.
"""
from __future__ import annotations

import json
from typing import Any

from orchestrator.workflow.late_split import keys as _keys, ledgers as _ledgers
from orchestrator.workflow.late_split.obligations import LateObligations


def ledger_fields(obligations: LateObligations) -> dict[str, Any]:
    """Return what the two external ledgers are written back as, unset out."""
    owed = {
        _keys.RESOURCES: _ledger_written(
            obligations.opaque_resources,
            _resource_payloads(obligations.resources),
        ),
        _keys.CONSUMERS: _ledger_written(
            obligations.opaque_consumers, list(obligations.consumers),
        ),
    }
    return {key: ledger for key, ledger in owed.items() if ledger is not None}


def _ledger_written(opaque: str | None, typed: list) -> Any:
    """Return what one external ledger is written back as.

    The verbatim copy outranks the typed view wherever there is one: the typed
    view is only the entries this binary could make sense of, and writing that
    in place of the ledger is how an obligation nobody here understands would
    disappear from the issue that still owes it.
    """
    if opaque is not None:
        return json.loads(opaque)
    return typed or None


def _resource_payloads(resources: tuple) -> list:
    """Return the JSON entries a typed obligation ledger is written as."""
    return [
        {
            _ledgers.KIND_KEY: str(resource.kind),
            _ledgers.TARGET_KEY: resource.target,
            _ledgers.STATE_KEY: str(resource.resource_state),
        }
        for resource in resources
    ]
