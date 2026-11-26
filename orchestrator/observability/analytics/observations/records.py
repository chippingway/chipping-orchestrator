# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The versioned JSONL payloads an observation and its diagnostics are written as.

Two event kinds share the analytics envelope (`sink.build_record`) and one
payload version, `observation_version`, which moves whenever a field here
changes meaning; the attachment a snapshot was read from carries its own
(`attachment_version`). Every record names its `source`: the agent
invocation the reply came back from, encoded field for field as the tracked
spawn minted it -- repository, issue, the pinned comment its charge was
written on, the workflow cycle, the charge's lifetime ordinal, and the
random nonce -- so a record joins the run's own records by identity rather
than by a session id or a round counter, neither of which names one
process. `route` is the road the run came down, and `report_outcome` the
verdict the workflow reached on the reply it reads -- `ready`, `verified`,
`malformed`, or `no_marker` -- where the recording got as far as reading it.

* `task_snapshot` is a developer's description of its task, bounded, beside
  the requirements revision its conversation was handed and the task
  reference (`task_reference`) a later reader names it by: spelled from the
  revision the run's report is stamped with, which a reviewer handed that
  report is told. The two differ only where a retry re-grounded a fresh
  conversation on an edit the report's stamp leaves owed.
* `observation_diagnostic` is why a reply yielded no observation: the item
  it is about, the category, the counts the collection reached -- the
  attachment lines `found`, and how many were `readable` as a snapshot, which
  says nothing about what reached the sink -- and a bounded excerpt of the
  refused lines where there are any.

Identifiers are written whole and never cut; only a text is bounded, and the
record limit drops texts rather than identifiers (`serialized`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from orchestrator.observability.analytics import sink
from orchestrator.observability.analytics.observations import attachments, bounds

if TYPE_CHECKING:
    from orchestrator.agents.models import AgentInvocation

TASK_SNAPSHOT_EVENT = "task_snapshot"

DIAGNOSTIC_EVENT = "observation_diagnostic"

OBSERVATION_VERSION = 1

# The fields a record carries a bounded text in, which the record limit drops.
_TEXTS = (attachments.DESCRIPTION, "excerpt")


@dataclass(frozen=True)
class ObservedRun:
    """The one invocation an observation is about, and what its road handed it.

    `invocation` is the process the reply came back from, `stage` the bare
    stage tag its records are attributed to, `route` the road it ran on, and
    `requirements_revision` the requirements the conversation the attempt ran
    in was handed -- None where the road holds none. `report_requirements`
    is the revision the run's report is stamped with -- the road's own,
    which a reviewer handed that report names -- and spells the task
    reference. `report_outcome` is the verdict the workflow reached on the
    reply it reads, set once the recorder has framed it and None before.
    """

    invocation: AgentInvocation
    stage: str | None
    route: str
    requirements_revision: str | None
    report_requirements: str | None = None
    report_outcome: str | None = None


def source_fields(invocation: AgentInvocation) -> dict:
    """An invocation identity as a record carries it: each field whole, a damaged one as null."""
    return {
        "repo": invocation.repo,
        "issue": invocation.issue,
        "comment": invocation.comment,
        "cycle": invocation.cycle,
        "ordinal": invocation.ordinal,
        "nonce": invocation.nonce,
    }


def task_reference(repo: str, issue: int, requirements_revision: str | None) -> str | None:
    """The reference a task snapshot is named by: `<repo>#<issue>@<requirements revision>`, or None.

    None where the repository or the revision is unknown: a reference
    missing either half names no task anybody could ask for.
    """
    if not repo or not requirements_revision:
        return None
    return f"{repo}#{issue}@{requirements_revision}"


def task_snapshot_record(run: ObservedRun, description: bounds.BoundedText) -> dict:
    """The `task_snapshot` record one attachment's description becomes."""
    return _observation(
        run,
        TASK_SNAPSHOT_EVENT,
        attachment_version=attachments.TASK_SNAPSHOT_VERSION,
        description=description.fields(),
    )


def diagnostic_record(
    run: ObservedRun,
    category: str,
    counts: dict,
    excerpt: bounds.BoundedText | None = None,
    error: str | None = None,
) -> dict:
    """The `observation_diagnostic` record one problem becomes; `error` names a failed step's exception type."""
    return _observation(
        run,
        DIAGNOSTIC_EVENT,
        item=attachments.TASK_SNAPSHOT,
        category=category,
        counts=counts,
        excerpt=None if excerpt is None else excerpt.fields(),
        error=error,
    )


def serialized(record: dict) -> str:
    """One record as its JSONL line, held to `bounds.RECORD_BYTES` by dropping its texts whole.

    Encoded exactly as the sink writes every other record, so the content
    hash the sync deduplicates by is the one it computes over the line. A
    record still past the limit with every text dropped is refused.
    """
    line = json.dumps(record, sort_keys=True)
    if len(line) <= bounds.RECORD_BYTES:
        return line
    textless = {
        key: bounds.dropped(field) if key in _TEXTS else field
        for key, field in record.items()
    }
    line = json.dumps(textless, sort_keys=True)
    if len(line) > bounds.RECORD_BYTES:
        raise ValueError(f"an observation record takes {len(line)} bytes with its texts dropped")
    return line


def _observation(run: ObservedRun, event: str, **fields: object) -> dict:
    """The envelope and the source every observation record carries, around `fields`."""
    invocation = run.invocation
    return sink.build_record(
        repo=invocation.repo,
        issue=invocation.issue,
        event=event,
        stage=run.stage,
        observation_version=OBSERVATION_VERSION,
        source=source_fields(invocation),
        route=run.route,
        report_outcome=run.report_outcome,
        requirements_revision=run.requirements_revision,
        task_ref=task_reference(invocation.repo, invocation.issue, run.report_requirements),
        **fields,
    )
