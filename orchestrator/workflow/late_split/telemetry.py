# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dual emission one late event is written to both sinks by.

One call, two independent writes: the audit stream through the client's own
`emit_event`, and the analytics stream through the recording package's
envelope and append. Both carry the identical bounded payload the `records`
owner built, so an operator analyzing the JSONL audit copy offline reaches the
same answers as the database over the analytics sink -- which is the point of
writing twice rather than choosing one.

Neither write may change what the workflow does. The two sinks already
swallow a filesystem refusal, and each call here additionally rides its own
guard, so a bug or a client that raises costs the record and nothing else: a
late generation is reconciled from its pinned state, never from what a sink
accepted. For the same reason a failed first write does not skip the second --
they are separate observability surfaces, and one being unavailable is not a
reason to lose the other.

Building the payload rides the same guard, and for the stricter reason. The
`records` owner refuses to describe a generation or an event that cannot
satisfy the contract, and that refusal has to end here: nothing is written,
the refusal is logged where an operator will see it, and the tick that asked
carries on. A record nobody should have written and a tick broken by the
attempt to write it are both failures; only the first one is recoverable.

What a refusal is allowed to say is bounded for the same reason the record
is. The values it reports are exactly the ones that just failed to prove
themselves, so an issue number that is not one and a family that is not a
member are reported as a sentinel rather than as they arrived -- a log line is
the same surface one step over, and the boundary would be worth nothing if
prose refused from a sink were written into it instead. That is also why the
failure is named rather than raised into the log: `log.exception` renders the
exception's own text and traceback, and only this domain's refusals are built
to be repeatable. One raised anywhere below is reported by its type alone.

`stage` is bounded here rather than passed through, because it is the one
field of the envelope this owner supplies and the sinks would carry anything.
It is resolved against the workflow label vocabulary and written as the bare
stage tag every other emitter on those sinks records, so a caller may name
either spelling and nothing else -- a "stage" carrying a path or an
adjudication's rationale is refused with the record it came with.
"""
from __future__ import annotations

import logging
from typing import Any

from orchestrator.github.client import GitHubClient
from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.workflow import label_reading as _label_reading, state as _workflow_state
from orchestrator.workflow.late_split import (
    events as _events,
    formats as _formats,
    payloads as _payloads,
    records as _records,
)
from orchestrator.workflow.late_split.models import LateGeneration

log = logging.getLogger("orchestrator.workflow")

# What a refusal reports in place of a value that did not validate. An issue
# number or a family this domain cannot vouch for is not written into a log
# line either, so the line names the shape of the failure and nothing else.
def emit_late_event(
    gh: GitHubClient,
    event: _events.LateEvent,
    generation: LateGeneration,
    *,
    stage: str | None = None,
) -> dict[str, Any]:
    """Write one late event to the audit and analytics sinks, and return it.

    `stage` is the state the issue sits in, named as either the workflow label
    or the bare tag under it; what reaches the sinks is always the tag, which
    is what every other emitter on them records and what a filter matches on.

    Returns the payload both sinks were handed, or an empty one when the
    contract refused it and nothing was written.
    """
    try:
        recordable = _recordable(event, generation, stage)
    except Exception as refused:  # noqa: BLE001 - a refused record may not break the tick that emitted it
        _report_refusal(event, generation, refused)
        return {}
    payload, tag = recordable
    family = str(event.family)
    _emit_audit(gh, family, generation.current_issue, tag, payload)
    _emit_analytics(gh, family, generation.current_issue, tag, payload)
    return payload


def _report_refusal(
    event: _events.LateEvent,
    generation: LateGeneration,
    refused: Exception,
) -> None:
    """Log a refused record without quoting what it was refused for.

    The refusal is reported for a generation and an event that just failed to
    prove themselves, so nothing here may be interpolated as it arrived: an
    issue number that is not one, and a family that is not a member, are
    exactly the values the sinks were about to be protected from, and a log
    line is the same surface one step over. Each is reported only if it
    validates, and as a sentinel otherwise.

    The failure itself is reported through `_reported` rather than by
    `log.exception`, which would render the raised exception's own text and
    traceback -- and an exception this domain did not build is free to carry
    whatever it was handed in its message.
    """
    issue_number = _payloads.as_identity(
        getattr(generation, "current_issue", None),
    )
    family = getattr(event, "family", None)
    log.error(
        "issue=#%s: %s refused as a late record (%s); nothing emitted",
        issue_number or _formats.UNNAMED,
        family if isinstance(family, _events.LateEventFamily) else _formats.UNNAMED,
        _reported(refused),
    )


def _reported(refused: Exception) -> str:
    """What a refusal may say about why it happened.

    This domain's own refusals are built from field names, vocabularies, and
    type names, so their message is safe to repeat and is the useful half of
    the line. Anything else is named by its type alone: a `KeyError` raised
    somewhere below carries whatever key it was handed, and that key can be
    the value the record was refused for.
    """
    if isinstance(refused, _formats.InvalidLateValue):
        return str(refused)
    return type(refused).__name__


def _recordable(
    event: _events.LateEvent,
    generation: LateGeneration,
    stage: str | None,
) -> tuple:
    """The payload and the stage tag, or the refusal one of them raises."""
    return (
        _records.build_late_payload(event, generation), _stage_tag(stage),
    )


def _stage_tag(stage: str | None) -> str | None:
    """Return the bare stage tag a caller named, or refuse anything else.

    Resolved through the label vocabulary rather than trusted, so the closed
    set of workflow states is the whole of what either sink can be told an
    issue was in. Both spellings resolve -- the namespaced label and the tag
    under it -- and everything else, prose included, is refused.
    """
    if stage is None:
        return None
    resolved = _label_reading.label_for_name(stage)
    if resolved is None:
        raise _formats.InvalidLateValue(
            f"stage is not a workflow state ({type(stage).__name__})",
        )
    return _workflow_state.stage_name(resolved)


def _emit_audit(
    gh: GitHubClient,
    family: str,
    issue_number: int,
    stage: str | None,
    payload: dict[str, Any],
) -> None:
    try:
        gh.emit_event(
            family,
            issue_number=issue_number,
            stage=stage,
            **payload,
        )
    except Exception:
        log.exception(
            "issue=#%s: %s audit emission failed; continuing",
            issue_number,
            family,
        )


def _emit_analytics(
    gh: GitHubClient,
    family: str,
    issue_number: int,
    stage: str | None,
    payload: dict[str, Any],
) -> None:
    try:
        _recording_events.append_record(
            _recording_events.build_record(
                repo=getattr(gh, "_repo_slug", None) or "",
                issue=issue_number,
                event=family,
                stage=stage,
                **payload,
            ),
        )
    except Exception:
        log.exception(
            "issue=#%s: %s analytics record failed; continuing",
            issue_number,
            family,
        )
