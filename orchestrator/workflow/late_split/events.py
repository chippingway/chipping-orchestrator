# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one late event is, and what its family is allowed to say.

Eight families describe a late generation's whole life -- what a candidate
measured, what the adjudication decided, which typed step failed, what happened
to a snapshot, what a cleanup reconciled, that the owner was cancelled, that a
restart was taken, and that an adjudication's exemption was carried onto the
commit a workflow rewrite replaced it with. Each carries the generation's own
correlation, plus
only the detail its family owns, and the record enforces that rather than
trusting the emitter: `_FAMILY_FIELDS` says which fields a family requires and
which it may carry, and anything else raises `InvalidLateValue` where the event
is built. What that refusal says is bounded too -- it names the family only
when the family is a member, because the message is read by a log and a value
refused from both sinks may not arrive there instead. A measurement that
arrives claiming a verdict, or a verdict with no verdict on it, is a bug in an
emitter -- refusing it at construction is what keeps a record that means
nothing out of both sinks and out of every analysis over them.

The type of each detail is checked, not merely annotated. A `StrEnum` member
and the string that spells it compare equal, so `verdict="question"` would
satisfy every comparison here and be written verbatim -- and so would
`category="rationale: inspect /srv/private/key"`. Only an actual member is
accepted, which is what makes the closed vocabularies closed and leaves prose
no field to travel in. `check` re-runs the whole contract, so the record
builder can ask an event it did not construct.

The verdict's two companions are the same rule one level down, and they are
not symmetric because the questions they answer are not. A child count
describes a split and only a split. A category explains where an adjudication
landed: it is required of a `question`, because a question that cannot say
what it is asking about is not analyzable, and it is optional on the other two
-- which is what makes the artifact-dominated `single` verdict a thing
telemetry can count rather than a claim nobody can check.

The transfer family is the one whose subject is a pair of commits rather than
one, so the four ends it is read by are split between it and the generation
under it: the rewritten commit and the base it was read over are that
generation's own frozen pair, and the accepted commit the exemption came OFF
-- with the base that one was read over -- are two fields the family adds.
Both are held to the shape a commit takes rather than to a vocabulary, because
an end that is not a whole object id is not one a reader could re-derive the
equality from. It carries no verdict, and deliberately so: a transfer moves a
decision a human already made onto the object that replaced the one they made
it about, and a second `single` on the stream would read as a second
adjudication of work nobody was asked about twice.

`category` is a closed vocabulary, not a label an agent writes. The late
decomposer's answer is mapped onto these members by `verdict_category`, which
answers `UNKNOWN` for everything it does not recognize, so an adjudication's
rationale -- the sentences, the file names in them -- has no path into a record
at all. That is deliberate: the vocabulary can be widened here, in a review,
and cannot be widened by what an agent happened to write.

The failure family has two companions of its own, and both are optional
because most of its members answer for a step that took no reading at all. A
size measurement that did not happen carries `measurement_failure` -- the git
layer's own vocabulary for WHICH step it stopped at -- so an analysis can tell
a base the remote would not name from a diff nothing here can pin, both of
which reach the sinks as `measurement_failed` and neither of which is the same
operator's next move. Beside it `detail` carries the one line that step wrote
for itself: free text, and the only field in this domain that is, because the
member says which step and nothing whatever about why. It is bounded rather
than trusted -- one line, capped, and already scrubbed of the credential by
the transport that produced it -- and `measurement_failure_event` is the one
constructor that shapes a raw diagnostic into what the contract will accept,
so an emitter cannot widen the field by handing over more than it holds.

Both are pinned to `measurement_failed` and the line to the step, because a
field allowed beside every member describes none of them. A snapshot the
remote refused and a restart GitHub declined took no reading, so neither has
a step to name or a line to carry; and the roads that refuse a RECORD rather
than a reading -- a pinned comment too damaged to act on, a debt no push can
pay -- hold a sentence written for a human instead, which is exactly the prose
this domain gives no field to. So the contract refuses the companions on any
other failure, and refuses a line with no step over it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.late_split.models import LateFailure, LateVerdict
from orchestrator.workflow.late_split.obligations import (
    MAX_RESOURCE_TARGET,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from orchestrator.workflow.late_split.rewrite_values import LateRewriteKind, LateRewriteProof

_REQUIRES = "requires"
_NOT_CARRIED = "does not carry"
_NOT_TYPED = "was not given a member for"

_FAMILY = "family"
_VERDICT = "verdict"
_CATEGORY = "category"
_CHILD_COUNT = "child_count"
_FAILURE = "failure"
_MEASUREMENT_FAILURE = "measurement_failure"
_DETAIL = "detail"
_RESOURCE = "resource"
_RESTART_STEP = "restart_step"
_REWRITE_KIND = "rewrite_kind"
_TRANSFER_PROOF = "transfer_proof"
_TRANSFERRED_FROM_SHA = "transferred_from_sha"
_TRANSFERRED_FROM_BASE_SHA = "transferred_from_base_sha"

# Every detail field a family can own, in the order a refusal reports them.
_DETAIL_FIELDS = (
    _VERDICT,
    _CATEGORY,
    _CHILD_COUNT,
    _FAILURE,
    _MEASUREMENT_FAILURE,
    _DETAIL,
    _RESOURCE,
    _RESTART_STEP,
    _REWRITE_KIND,
    _TRANSFER_PROOF,
    _TRANSFERRED_FROM_SHA,
    _TRANSFERRED_FROM_BASE_SHA,
)

# How much of a failed step's own line a record may carry. Long enough for the
# sentence git leads with -- which is where it names the fault -- and short
# enough that a field no vocabulary bounds cannot become a transcript in two
# append-only sinks.
MAX_FAILURE_DETAIL = 200


class LateEventFamily(StrEnum):
    """The event kind each family is written to both sinks under."""

    MEASUREMENT = "late_measurement"
    VERDICT = "late_verdict"
    FAILURE = "late_failure"
    SNAPSHOT = "late_snapshot"
    CLEANUP = "late_cleanup"
    CANCELLATION = "late_cancellation"
    RESTART = "late_restart"
    TRANSFER = "late_transfer"


class LateVerdictCategory(StrEnum):
    """What an adjudication says about where it landed.

    Closed on purpose: these are the answers telemetry can group by -- how
    often a repository's oversized candidates turn out to be dominated by
    generated artifacts, and what the questions humans are asked are about --
    and a category outside them is `UNKNOWN` rather than a new label an agent
    introduced into the record.
    """

    GENERATED_ARTIFACTS = "generated_artifacts"
    SCOPE_AMBIGUOUS = "scope_ambiguous"
    UNSAFE_SPLIT = "unsafe_split"
    LINEAGE_BOUND = "lineage_bound"
    UNKNOWN = "unknown"


class LateRestartStep(StrEnum):
    """Which half of the two-phase restart a record describes."""

    PENDING = "pending"
    RECONCILED = "reconciled"


# Per family: what it requires, and what it may also carry. A family with
# neither says everything about its generation and nothing of its own.
_FAMILY_FIELDS = MappingProxyType({
    LateEventFamily.MEASUREMENT: ((), ()),
    LateEventFamily.VERDICT: ((_VERDICT,), (_CATEGORY, _CHILD_COUNT)),
    LateEventFamily.FAILURE: ((_FAILURE,), (_MEASUREMENT_FAILURE, _DETAIL)),
    LateEventFamily.SNAPSHOT: ((_RESOURCE,), ()),
    LateEventFamily.CLEANUP: ((_RESOURCE,), ()),
    LateEventFamily.CANCELLATION: ((), ()),
    LateEventFamily.RESTART: ((_RESTART_STEP,), ()),
    LateEventFamily.TRANSFER: (
        (
            _REWRITE_KIND,
            _TRANSFER_PROOF,
            _TRANSFERRED_FROM_SHA,
            _TRANSFERRED_FROM_BASE_SHA,
        ),
        (),
    ),
})

# What each detail field has to be: a member of one vocabulary, a real
# count, one bounded line, or -- where the shape is a bound rather than a
# class -- hex of exactly the lengths named here.
_DETAIL_TYPES = MappingProxyType({
    _VERDICT: LateVerdict,
    _CATEGORY: LateVerdictCategory,
    _CHILD_COUNT: int,
    _FAILURE: LateFailure,
    _MEASUREMENT_FAILURE: MeasurementFailure,
    _DETAIL: str,
    _RESOURCE: LateResource,
    _RESTART_STEP: LateRestartStep,
    _REWRITE_KIND: LateRewriteKind,
    _TRANSFER_PROOF: LateRewriteProof,
    _TRANSFERRED_FROM_SHA: _formats.COMMIT_LENGTHS,
    _TRANSFERRED_FROM_BASE_SHA: _formats.COMMIT_LENGTHS,
})

# The verdict a child count belongs to and only to, and the one a category is
# required of. Nothing forbids a category elsewhere: a `single` verdict
# explaining itself is the artifact-dominated signal the telemetry exists for.
_COUNTED_VERDICT = LateVerdict.SPLIT

_CATEGORIZED_VERDICT = LateVerdict.QUESTION

# The failure the two measurement companions belong to and only to. Every
# other member of that vocabulary names a step that took no reading -- a
# snapshot the remote refused, a hold nobody could release, a restart GitHub
# declined -- so one of them carrying `base_absent` would report a measurement
# stopping where no measurement was taken.
_MEASURING_FAILURE = LateFailure.MEASUREMENT_FAILED


@dataclass(frozen=True)
class LateEvent:
    """One family, plus the little that family adds to its generation.

    Everything else a record carries is read off the generation, so an emitter
    cannot describe a step in terms the pinned state does not agree with.
    """

    family: LateEventFamily
    verdict: LateVerdict | None = None
    category: LateVerdictCategory | None = None
    child_count: int | None = None
    failure: LateFailure | None = None
    measurement_failure: MeasurementFailure | None = None
    detail: str | None = None
    resource: LateResource | None = None
    restart_step: LateRestartStep | None = None
    rewrite_kind: LateRewriteKind | None = None
    transfer_proof: LateRewriteProof | None = None
    transferred_from_sha: str | None = None
    transferred_from_base_sha: str | None = None

    def __post_init__(self) -> None:
        self.check()

    def check(self) -> None:
        """Refuse an event whose fields do not describe its family.

        Published so the record builder can ask the same question of an event
        it did not construct: the boundary a payload crosses is the last place
        anything can still refuse, and it does not get to assume the object
        reaching it came through this constructor.
        """
        self._check_family()
        self._check_companions()
        self._check_types()

    def _check_family(self) -> None:
        """Refuse a field this family does not own, or one it is missing."""
        if not isinstance(self.family, LateEventFamily):
            self._refuse({_FAMILY}, _NOT_TYPED)
        required, optional = _FAMILY_FIELDS[self.family]
        supplied = self._supplied_fields()
        self._refuse(supplied - set(required) - set(optional), _NOT_CARRIED)
        self._refuse(set(required) - supplied, _REQUIRES)

    def _check_companions(self) -> None:
        """Refuse a companion field paired with the wrong member.

        Two families qualify one of their own required fields, and in both
        the pairing is exact rather than merely permitted -- a field allowed
        beside every member says nothing about which one it describes.

        A child count is a split's and nobody else's, in both directions. A
        category is required of a question and allowed of any verdict, because
        why a candidate stayed one change is exactly as worth counting as why
        a human was asked.

        The failure's two describe a MEASUREMENT that did not happen, so they
        belong to that member alone, and the line belongs to the step rather
        than to the family: a refusal naming no step took no reading whose
        line this could be, and what those roads have instead is their own
        prose about which part of a record a human has to repair. Allowed
        loose, that sentence is a field for prose to reach two append-only
        sinks through.
        """
        supplied = self._supplied_fields()
        if self.verdict == _COUNTED_VERDICT:
            self._refuse({_CHILD_COUNT} - supplied, _REQUIRES)
        else:
            self._refuse({_CHILD_COUNT} & supplied, _NOT_CARRIED)
        if self.verdict == _CATEGORIZED_VERDICT:
            self._refuse({_CATEGORY} - supplied, _REQUIRES)
        if self.failure != _MEASURING_FAILURE:
            self._refuse({_MEASUREMENT_FAILURE, _DETAIL} & supplied, _NOT_CARRIED)
        elif _MEASUREMENT_FAILURE not in supplied:
            self._refuse({_DETAIL} & supplied, _NOT_CARRIED)

    def _check_types(self) -> None:
        """Refuse a detail that is a lookalike rather than a member."""
        for name, wanted in _DETAIL_TYPES.items():
            given = getattr(self, name)
            if given is not None and not _is_typed(given, wanted):
                self._refuse({name}, _NOT_TYPED)

    def _supplied_fields(self) -> set[str]:
        """The detail fields this event actually carries."""
        return {
            name for name in _DETAIL_FIELDS
            if getattr(self, name) is not None
        }

    def _refuse(self, names: set[str], reason: str) -> None:
        """Raise for a non-empty set of fields, naming the family and them.

        The family is named only when it IS one. An event refused for having
        a family that is not a member is refused over exactly the value that
        must not be repeated -- the message ends up in a log, and prose
        offered as a family would reach it there having been kept out of both
        sinks. The field names beside it are this module's own literals.
        """
        if names:
            listed = ", ".join(sorted(names))
            named = self.family
            if not isinstance(named, LateEventFamily):
                named = _formats.UNNAMED
            raise _formats.InvalidLateValue(f"{named!s} {reason}: {listed}")


def measurement_failure_event(asked: Any, detail: Any = "") -> LateEvent:
    """The `late_failure` one refused size reading is recorded as.

    The single constructor for the family's widened shape, published here
    rather than left to each seam that measures, because every one of them
    holds the same two raw values and none of them owns what the record may
    say about them. Both are reduced to what the contract accepts rather than
    offered as they arrived: an unbounded diagnostic refused at construction
    would cost the whole record, and the record is the only account there is
    of a reading that did not happen.

    `asked` is the step the git layer stopped at, and it is recorded only when
    it IS a member. The size gate parks on refusals that name no measurement
    at all -- a pinned record too damaged to act on, a debt nothing can pay --
    and those are still `measurement_failed` on both sinks, saying nothing
    about a step no reading reached.

    The line goes with the step and never without it. A refusal that named no
    step took no reading whose line this could be, and what those roads hold
    instead is the sentence they were about to tell a human -- which is prose,
    and prose has no field on a late record. So the two are recorded together
    or not at all, and the contract refuses the pair the other way round.
    """
    step = asked if isinstance(asked, MeasurementFailure) else None
    return LateEvent(
        family=LateEventFamily.FAILURE,
        failure=LateFailure.MEASUREMENT_FAILED,
        measurement_failure=step,
        detail=(
            None if step is None
            else _formats.bounded_line(detail, MAX_FAILURE_DETAIL)
        ),
    )


def verdict_category(asked: str | None) -> LateVerdictCategory:
    """Map a parsed adjudication category onto the closed vocabulary.

    Never answers None, so the emitter always has the category a `question`
    verdict requires, and never answers anything the vocabulary does not
    already contain, so what the agent wrote cannot become the record. A
    spelling this binary does not know -- an agent's own words, a category a
    newer prompt introduced -- is `UNKNOWN`, which groups those together
    visibly instead of silently widening the field.
    """
    try:
        recognized = asked.strip().lower().replace(" ", "_")
    except AttributeError:
        return LateVerdictCategory.UNKNOWN
    try:
        return LateVerdictCategory(recognized)
    except ValueError:
        return LateVerdictCategory.UNKNOWN


def _is_typed(given: Any, wanted: Any) -> bool:
    """Whether one detail is the member, count, text, commit, or resource it claims.

    `wanted` is a class wherever membership is the whole test, and a set of
    lengths where the shape is a bound instead: a commit is a bounded string
    rather than a vocabulary, so what the table names for one is the lengths
    the domain's own object-id reader holds it to.

    A resource is checked through to its own fields, because the kind is what
    a record reports: a `LateResource` built with a string for its kind would
    otherwise put that string in the payload under the field named for the
    vocabulary.

    Free text is the one field with no vocabulary behind it, so what stands in
    for membership is the bound: one line, capped, and nothing trailing. A
    diagnostic that arrived as a transcript is refused here rather than
    written, which is why the emitters reduce theirs through
    `measurement_failure_event` instead of handing over what they were given.

    A recorded end of a rewrite is bounded the same way one field over: a
    commit is a whole object id and nothing else, so an abbreviation, a
    branch name, or prose offered as the commit an exemption came off is
    refused with the record it arrived on.
    """
    if wanted is int:
        return _formats.whole_number(given) and given >= 0
    if wanted is str:
        return _formats.is_bounded_text(given, MAX_FAILURE_DETAIL)
    if isinstance(wanted, frozenset):
        return _formats.is_hex_of(given, wanted)
    if not isinstance(given, wanted):
        return False
    return wanted is not LateResource or (
        isinstance(given.kind, LateResourceKind)
        and isinstance(given.resource_state, LateResourceState)
        and _formats.is_bounded_text(given.target, MAX_RESOURCE_TARGET)
    )
