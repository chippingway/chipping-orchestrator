# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The bounded record both observability sinks carry for a late event.

One payload is built for both streams, so an operator with only the audit
JSONL answers what the analytics database answers: whether a lineage is
approaching the depth bound, which repositories keep producing
artifact-dominated `single` verdicts, and whether the configured threshold
creates more adjudication than it prevents.

It is bounded four times over, because a type annotation bounds nothing at
runtime. The payload is assembled from a frozen generation and a family-typed
event and from nothing else, so there is no argument through which a file
path, a diff, a prompt, an agent's rationale, or its output could arrive; the
event is asked to prove its own contract again here, so a `verdict` that is a
lookalike string rather than a member never reaches the dict; the generation
is put through the `validation` gate beside this owner, so a "SHA" carrying
prose, a phase that was never a member, a count that is not one, a generation
with no correlating identity at all, and a measurement or verdict that cannot
say which commits it was about each produce no record rather than a record
nobody should have written; and what survives is filtered
through `LATE_PAYLOAD_FIELDS`, so a field added to the builder reaches a sink
only once it has been added to the declared contract as well. A resource's own
name is deliberately not among them -- the record names its kind and carries
`resource_id`, the bounded fingerprint from the `identity` owner, which is
what tells two cleanups of two different children apart without saying which
children they were.

`detail` is the one field on that list a vocabulary does not close, and it is
the size gate's alone. A reading that did not happen reaches both sinks as
`measurement_failed` however it failed, so the record carries the git layer's
own `measurement_failure` beside it to say WHICH step stopped -- and the
member says which step and nothing about why. A base the remote would not name
is an expired token, a repository this installation cannot see, or a host that
was down, and the only thing that ever told them apart is the line the
transport wrote. So that line travels, bounded by the event contract to a
single capped one and scrubbed of the credential by the transport that
produced it, and nothing else free-form joins it.

Which side of publication a generation was entered on is on every family's
record, because every one of them describes a different step depending on the
answer: a `late_cleanup` reconciling a snapshot of an initial publication and
one reconciling a pull request the remote already carries are the same family
telling two stories. The answer is projected onto a closed pair here rather
than carried as the pinned flag, so both halves are spelled and an analysis
groups on the field instead of on whether it is present. The context beside it
travels only under the marker that claims it -- the stage the gate took the
issue out of, the pull request the work already had, and the head it was left
standing on -- so a record that says it was entered before publication cannot
also carry a publication's context. What that context may be is bounded before
it arrives: the stage is a workflow state written as the bare tag the envelope
spells, the pull request an identity, and the head a whole object id. The
pull request's own body is not any of them and is not here -- a record says
which pull request overflowed, never what it says.

The transfer family is the one whose record is about two contributions rather
than one measurement. Which commit it moved a verdict ONTO is the generation's
own `source_sha` and `base_sha`, since that is the pair a later measurement of
the same work would be joined on; which commit it moved that verdict OFF is
`transferred_from_sha` and `transferred_from_base_sha`, and those are the
family's own because nothing else on a record could name a commit the branch
no longer carries. `rewrite_kind` says which rewrite this workflow made to
produce the first out of the second, and `transfer_proof` says what proved the
push behind it landed -- the two readings a recovery has to tell apart, and
the whole of what makes an exemption safe to move.

`correlation_key` is the other half of the contract. Records are emitted
before the step they describe is durable, so a crash can produce the same
record twice; a consumer deduplicates on these fields rather than on delivery,
because nothing about workflow disposition may depend on a sink. The key is
therefore the whole record apart from its timestamp: a retried step writes
every field again identically, so `ts` is the only thing that can differ
between one step's two emissions, and any other difference is a different step
-- two splits of one candidate into two children and into seven, two questions
asked under different categories, two restarts aimed at different states, two
measurements against different bases, an initial publication and the overflow
of a pull request that already exists. Listing the distinguishing fields by
hand instead is what let pairs like those collide, because the list has to be
remembered every time the payload grows.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from orchestrator.workflow import state as _workflow_state
from orchestrator.workflow.late_split import events as _events, identity as _identity, validation as _validation
from orchestrator.workflow.late_split.models import LateGeneration

# The field both halves of that answer are written under, spelled once for
# the contract that declares it and the builder that fills it.
_PUBLICATION = "publication"


class LatePublication(StrEnum):
    """Which side of publication one generation was entered on.

    A pair rather than a marker, because a record has to answer for both: the
    gate a candidate meets before anything is published, and the one an
    already-published pull request meets when a later commit takes its
    cumulative diff past the ceiling. Both are late generations, and every
    family's record means a different thing under each.
    """

    PRE = "pre_publication"
    POST = "post_publication"


# What a payload may carry. Correlation first -- the identities that join a
# record to a pinned generation, a lineage, and the commits it froze, and the
# publication the generation was entered on -- then the measurement it is
# analyzed by, then the fields one family adds. Nothing outside this tuple is
# written, so widening the record is a deliberate edit here rather than a
# keyword somebody passed.
LATE_PAYLOAD_FIELDS = (
    "cycle_id",
    "generation",
    "root_issue",
    "lineage_depth",
    "phase",
    _PUBLICATION,
    "source_stage",
    "published_pr_number",
    "published_sha",
    "source_sha",
    "base_sha",
    "threshold",
    "additions",
    "verdict",
    "category",
    "child_count",
    "failure",
    "measurement_failure",
    "detail",
    "resource",
    "resource_id",
    "outcome",
    "restart_step",
    "restart_target",
    "predecessor_cycle_id",
    "rewrite_kind",
    "transfer_proof",
    "transferred_from_sha",
    "transferred_from_base_sha",
)

# What a duplicate-tolerant consumer groups on: everything a record carries
# except when it was written. Naming the distinguishing fields one by one is
# what let two records of different steps collide -- two restarts targeting
# different states, two measurements against different bases -- because the
# list has to be remembered every time the payload grows. A retried step
# repeats every field it wrote, so only `ts` can differ between one step's two
# emissions, and anything else differing is a different step by construction.
_ENVELOPE_FIELDS = ("repo", "issue", "event", "stage")

CORRELATION_FIELDS = (*_ENVELOPE_FIELDS, *LATE_PAYLOAD_FIELDS)


def build_late_payload(
    event: _events.LateEvent,
    generation: LateGeneration,
) -> dict[str, Any]:
    """Return the bounded fields both sinks carry for one late event.

    The envelope each sink builds for itself -- timestamp, repository, issue,
    event kind, stage -- is not here: this is what the two of them share, so a
    record read out of either answers the same questions.

    Raises `InvalidLateValue` rather than returning a partial record: a
    generation or an event that cannot satisfy the contract has nothing this
    domain is willing to say about it, and the emitter above turns the refusal
    into a logged non-emission so the workflow is unaffected either way.
    """
    _validation.check_record(event, generation)
    fields = {**_correlation_of(generation), **_details_of(event)}
    return {
        name: recorded
        for name, recorded in fields.items()
        if recorded is not None and name in LATE_PAYLOAD_FIELDS
    }


def correlation_key(record: dict[str, Any]) -> tuple:
    """Return the fields a consumer deduplicates one record on."""
    return tuple(record.get(name) for name in CORRELATION_FIELDS)


def _correlation_of(generation: LateGeneration) -> dict[str, Any]:
    """What every family says about the generation it describes."""
    return {
        "cycle_id": generation.cycle_id,
        "generation": generation.generation,
        "root_issue": generation.root_issue,
        "lineage_depth": generation.lineage_depth,
        "phase": _name_of(generation.phase),
        **_publication_of(generation),
        "source_sha": generation.candidate_sha or None,
        "base_sha": generation.base_sha or None,
        "threshold": generation.threshold,
        "additions": generation.additions,
        "restart_target": generation.restart_target,
        "predecessor_cycle_id": generation.restart_predecessor,
    }


def _publication_of(generation: LateGeneration) -> dict[str, Any]:
    """Which side of publication this generation was entered on, and on what.

    The context travels under the marker and only under it, so a record that
    reports an initial publication cannot also carry the stage, the pull
    request, and the head an overflow of an existing one would name. What the
    marked half carries has already been proved by the gate beside this owner
    -- a marker that cannot name all three is refused rather than recorded --
    so the stage here is a workflow state and is written as the bare tag the
    envelope's own `stage` is, which is what lets a filter compare them.
    """
    if not generation.publication.post_publication:
        return {_PUBLICATION: str(LatePublication.PRE)}
    return {
        _PUBLICATION: str(LatePublication.POST),
        "source_stage": _workflow_state.stage_name(generation.publication.source_stage),
        "published_pr_number": generation.publication.published_pr_number,
        "published_sha": generation.publication.published_sha,
    }


def _details_of(event: _events.LateEvent) -> dict[str, Any]:
    """What one family adds, with the resource reduced to kind and print.

    The two the failure family may add are read straight off the event, since
    the contract it was just re-checked against is what bounds them: the step
    is a member or absent, and the line beside it is one bounded single line
    or absent.

    The transfer's own four read the same way, and the pair of them naming
    commits is why the family's other pair is not here: the rewritten commit
    and the base it was read over ARE the generation's frozen pair, so
    recording them again would put the same two ids on one record under two
    names and leave an analysis to work out which pair it was joining on.
    """
    resource = event.resource
    return {
        "verdict": _name_of(event.verdict),
        "category": _name_of(event.category),
        "child_count": event.child_count,
        "failure": _name_of(event.failure),
        "measurement_failure": _name_of(event.measurement_failure),
        "detail": event.detail,
        "resource": None if resource is None else str(resource.kind),
        "resource_id": (
            None if resource is None
            else _identity.resource_fingerprint(resource)
        ),
        "outcome": (
            None if resource is None else str(resource.resource_state)
        ),
        "restart_step": _name_of(event.restart_step),
        "rewrite_kind": _name_of(event.rewrite_kind),
        "transfer_proof": _name_of(event.transfer_proof),
        "transferred_from_sha": event.transferred_from_sha,
        "transferred_from_base_sha": event.transferred_from_base_sha,
    }


def _name_of(member: StrEnum | None) -> str | None:
    """Return the wire spelling of a vocabulary member, or None."""
    return None if member is None else str(member)
