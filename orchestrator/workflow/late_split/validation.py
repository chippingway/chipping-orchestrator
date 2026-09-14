# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a generation has to prove before a record of it may be written.

The type annotations on the record are documentation; this is the enforcement.
Nothing stops a caller from building a generation whose "SHA" is a sentence,
whose phase is a string that was never a member, or whose restart target names
a label no restart may apply -- and every one of those would otherwise be
written verbatim into two append-only sinks, where an operator's `jq` filter
and a Postgres column would then carry it. So the gate runs at the one place a
record is built, and a generation that cannot satisfy it produces no record at
all.

Four rules, and every one of them fails closed:

- **Identity is required.** A record with no cycle, generation, root, or
  current issue cannot be joined to a pinned generation, a lineage, or another
  record of the same step, which is the whole reason the record exists. An
  empty generation is therefore not a thing this domain can report on.
- **A family gets what its own record is read for.** A measurement, and the
  verdict answering it, both have to carry the commits that were frozen and
  the measurement taken against them; a record of either that reported only an
  identity would be a row no threshold study could use. A transfer is held to
  the commits and to nothing else, since what it records is that a reading did
  not have to be taken at all. The other five
  describe reconciliation rather than size, and a restart's fresh cycle has
  deliberately let its commits go, so none of them is held to it.
- **Every other emitted field is checked for what it claims to be.** A commit
  field must be spelled like a git object id, a phase and a source stage must
  be members of their vocabularies rather than strings that resemble them, a
  count must be a real non-negative integer, and a restart target must be one
  of the two states a restart may put an issue back into.
- **A marker may not claim what its record cannot say.** A generation entered
  after publication is recorded as one only while it can still name the stage
  it came from, the pull request the work already had, and the head that pull
  request stood on. A hand-edited comment that leaves the marker over any of
  the three gone would otherwise put a post-publication record with no
  publication in it into both sinks. One family is held to the marker as well
  as to what it carries: a transfer happens only where a pull request the
  remote already carries has been pushed to, so a record of one that could
  not name that publication describes a move nothing could be attributed to.

The refusal never quotes the value it refused. A field rejected for carrying
prose would put that prose in the log line reporting it, which is the same
leak one level over; the field name and the type it arrived as are enough to
find the emitter that built it.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any

from orchestrator.workflow.late_split import events as _events, formats as _formats, restart as _restart
from orchestrator.workflow.late_split.generation_reading import MAX_LINEAGE_DEPTH
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.state import WorkflowLabel

# The identity a record is joined by, and the smallest value each may take. A
# generation counter of 0 is a cycle that has frozen a candidate without
# adjudicating it yet; there is no such thing as issue 0 or cycle 0.
_IDENTITY_FLOORS = MappingProxyType({
    "cycle_id": 1,
    "generation": 0,
    "root_issue": 1,
    "current_issue": 1,
})

# The pair every size-bearing record names: which commit, over which base.
# Spelled once because three families are read by it and the shape check
# below reads it too.
_FROZEN_PAIR = ("candidate_sha", "base_sha")

_SHA_FIELDS = (*_FROZEN_PAIR, "plan_pr_head", "published_sha")

# What a family's own record is read without. A measurement and the verdict
# answering it are the two an analysis joins on: which commits were frozen,
# what they were measured against, and what the measurement was. A record of
# either that could not say is one no threshold study can use, so it is not
# written. The rest describe reconciliation rather than size, and a restart's
# fresh cycle has deliberately let its commits go.
_FAMILY_CONTEXT = MappingProxyType({
    _events.LateEventFamily.MEASUREMENT: (
        *_FROZEN_PAIR, "threshold", "additions", "phase",
    ),
    _events.LateEventFamily.VERDICT: (
        *_FROZEN_PAIR, "threshold", "additions", "phase",
    ),
    # The pair a transfer moved a verdict ONTO. No threshold and no count:
    # what a transfer records is precisely that a reading did not have to be
    # taken, so holding it to one would refuse every record of the thing.
    _events.LateEventFamily.TRANSFER: _FROZEN_PAIR,
})

# The families whose record is about a pull request the remote already
# carries, and which may therefore not be written for a generation that
# cannot name one. It is not the same rule as the context list above: those
# fields are read off the generation whatever its marker says, while the
# publication group only reaches a payload under the marker that claims it --
# so a record that needs the group needs the marker with it.
_PUBLISHED_FAMILIES = frozenset((_events.LateEventFamily.TRANSFER,))

_COUNT_FIELDS = (
    "threshold",
    "additions",
    "plan_pr_number",
    "published_pr_number",
    "comment_watermark_id",
    "restart_cycle_id",
    "restart_predecessor",
)


def check_record(event: _events.LateEvent, generation: LateGeneration) -> None:
    """Raise unless this event and this generation may become a record.

    Three questions in the order they answer each other: whether the event
    describes its own family, whether the generation's fields are what they
    claim to be, and whether the generation carries what THIS family's record
    is supposed to be readable without.
    """
    event.check()
    check_generation(generation)
    _check_family_context(event.family, generation)


def check_generation(generation: LateGeneration) -> None:
    """Raise unless every field a record would carry is one it may carry."""
    _check_identity(generation)
    _check_shape(generation)
    _check_fields(generation)


def _check_family_context(family: Any, generation: LateGeneration) -> None:
    """Require what one family's record has to be self-contained about.

    The fields first, and then the MARKER for the families that only ever
    happen past a publication -- because the marker is what puts the group on
    a payload at all. A generation carrying a pull request and a head with the
    flag unset records neither, so a transfer that could not say which pull
    request it moved a verdict onto is a move nothing could be attributed to.
    """
    for name in _FAMILY_CONTEXT.get(family, ()):
        given = getattr(generation, name)
        _require(given is not None and given != "", name, given)
    if family in _PUBLISHED_FAMILIES:
        marked = generation.post_publication
        _require(
            bool(marked) and generation.has_publication_context,
            "post_publication",
            marked,
        )


def _check_identity(generation: LateGeneration) -> None:
    """Require the four identities every record is correlated by."""
    for name, floor in _IDENTITY_FLOORS.items():
        given = getattr(generation, name)
        _require(_formats.whole_number(given) and given >= floor, name, given)


def _check_shape(generation: LateGeneration) -> None:
    """Require the closed vocabularies, and the entry a marker claims.

    The marker is the one field asked what it stands over as well as what it
    is: a record saying a generation was entered on a publication it cannot
    name is exactly the record the reader on the far side would report as a
    post-publication entry with no publication in it.
    """
    depth = generation.lineage_depth
    _require(
        depth is None
        or (_formats.whole_number(depth) and 0 <= depth <= MAX_LINEAGE_DEPTH),
        "lineage_depth",
        depth,
    )
    phase = generation.phase
    _require(
        phase is None or isinstance(phase, LatePhase), "phase", phase,
    )
    stage = generation.source_stage
    _require(
        stage is None or isinstance(stage, WorkflowLabel),
        "source_stage",
        stage,
    )
    target = generation.restart_target
    _require(
        target is None or _restart.restart_target(target) is not None,
        "restart_target",
        target,
    )
    marked = generation.post_publication
    _require(
        isinstance(marked, bool)
        and (not marked or generation.has_publication_context),
        "post_publication",
        marked,
    )


def _check_fields(generation: LateGeneration) -> None:
    """Require the commits to be commits and the counts to be counts."""
    for sha_field in _SHA_FIELDS:
        given = getattr(generation, sha_field)
        _require(_formats.optional_commit_id(given), sha_field, given)
    for count_field in _COUNT_FIELDS:
        counted = getattr(generation, count_field)
        _require(_formats.optional_count(counted), count_field, counted)


def _require(allowed: bool, name: str, given: Any) -> None:
    """Raise for a field that is not what a record may carry.

    The value is reported by its type and never by its content, so refusing a
    field that arrived carrying prose does not write that prose into the log
    instead of the sink.
    """
    if not allowed:
        raise _formats.InvalidLateValue(
            f"{name} is not recordable ({type(given).__name__})",
        )
