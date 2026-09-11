# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The children a late split creates, and what each is born knowing.

The initial decomposer's children start from nothing: an issue, a scope, and a
base branch. These start from work that already exists, and everything here is
about handing that work over without handing over the branch it was committed
on -- which is about to be superseded and closed.

**What a child is told.** Its own declared scope, in the words the adjudication
used; the addition budget that slice was proposed at, and that the estimate
covers every path the child commits; the base branch it targets; the snapshot
ref and the exact commit under it; and where it sits in the lineage. The
budget is added BESIDE the declared scope rather than folded into it: what the
adjudication wrote about a slice is what the developer implementing it is owed
in full, and a size stated in this binary's own words is not part of it.

Selective reuse is spelled out because the alternative has to be ruled out in
writing: a child may cherry-pick a coherent commit or copy selected paths, and
may not mechanically split hunks to hit a size target. File and hunk boundaries
do not express issue scope, so a change partitioned along them is one nobody
can build or review -- the judgment about what belongs to a slice stays with
the developer who implements it.

**What a child is born with.** The same parent link and creation stamp every
split child gets, plus the ancestry: the lineage this child continues, the
adjudication that created it, and the snapshot it may reuse. That record is
what the child's own size gate reads when it mints a generation, so automatic
splitting stops at the same bound three generations down as it does at the
root, and what its own late prompt states as the declared scope is the slice
written here rather than an issue body somebody has since edited.

**The order children are created in.** The initial mode's crash-safe sequence,
extended by one write: the count and the umbrella flag go down before the first
child exists, and each child's number is recorded in the parent -- in the
children list, in the direct-consumer ledger, and as an obligation of its own
-- in one write, before anything else is done with it. A crash in that window
costs an orphan child an operator can see, never a duplicate the retry would
create, and never a consumer the snapshot's reclamation would fail to wait for.

**Re-entry is a reuse, not a repeat.** A retry walks the same manifest and
adopts every child this GENERATION already records rather than creating a
second one, then re-seeds it: the seed is the one step that can have been lost
after the number was durable, and writing it again costs a read and changes
nothing on a child that already carries it. The child's own state is read and
added to rather than replaced, because by the time a retry runs, a child may
already be implementing.

The register it adopts from is the generation's own `split_children`, not the
stage's shared `children` list, and that distinction is load-bearing. An issue
that was decomposed, saw its children resolve, flipped back to `ready`, and
implemented an oversized candidate still carries the earlier decomposition's
`children` -- so a walk reading that list would adopt COMPLETED issues by
manifest index, reseed them with an ancestry they have nothing to do with, and
activate them. The stage list is written FROM the register instead, which is
also what drops the earlier decomposition's dependency graph rather than
leaving a stale one over the new children.

The one window an ordered register cannot close on its own is the crash
between `create_child_issue` returning and the write recording it: nothing
outside GitHub knows the number yet. So every child is created carrying a
hidden marker naming this ISSUE, this cycle, this generation, and its slice
index, and a walk about to create looks for that marker among the open issues
on the child's own workflow label first. The issue is in there because a cycle
identity is minted per issue and repeats across them -- two parents on their
first candidate are both cycle 1 -- while the lookup walks a label rather than
one parent's children, so without it one parent would adopt another's. The
lookup is taken only where something has to be created, so a fully-adopted
resume pays nothing for it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from github.Issue import Issue

from orchestrator.git.snapshots import refs as _snapshot_refs
from orchestrator.github import comments as _github_comments, issues as _github_issues
from orchestrator.workflow.engine import usage as _usage
from orchestrator.workflow.late_split import formats as _formats, identity as _identity, lineage as _lineage
from orchestrator.workflow.late_split.models import (
    MAX_LINEAGE_DEPTH,
    LateFailure,
    LatePhase,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from orchestrator.workflow.stages.decomposition import (
    late_budget as _budget,
    late_outcome as _late_outcome,
    late_owner as _late_owner,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    split as _split,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.models import _SplitPlan

log = logging.getLogger("orchestrator.workflow")

_EXPECTED_CHILDREN = "expected_children_count"

_DEP_GRAPH = "dep_graph"

_WHOLE_ISSUE = "(the whole issue)"

# The two keys a declared slice is read through.
_TITLE = "title"

_BODY = "body"


class _StrandedChild(Exception):
    """An issue this walk found for a slice and may not take over.

    Carries the sentence the park is made of, because the two reasons a
    candidate is refused are different things to tell a human: one is an
    issue a human acted on, the other is an issue whose receipt does not say
    which slice it belongs to.
    """

    def __init__(self, number: int, described: str) -> None:
        super().__init__(described)
        self.number = number
        self.described = described


_STRANDED_CHILD = (
    "child #{number}, created by an earlier pass of this split and never "
    "recorded on this issue"
)

_AMBIGUOUS_RECEIPT = (
    "issue #{number}, which carries the receipt for slice {index} of this "
    "split beside another slice's -- so nothing here can say which slice it "
    "was created for, and adopting it would attribute one issue to two"
)

_FORGED_RECEIPT = (
    "slice {index} ({title!r}) declares scope carrying an orchestrator "
    "receipt marker"
)

_CHILD_CREATE_PARK = (
    "the committed candidate for this issue was adjudicated as a split and "
    "its snapshot is safe, but {child} could not be created, recorded, or "
    "seeded. The snapshot ref and every child already created are recorded on "
    "this issue; the next tick adopts them and continues from the same "
    "manifest without re-running any agent."
)

# What one slice's issue says about the size it was proposed at. The paths
# the estimate covers are named because it covers all of them: a developer who
# read it as implementation alone would leave out the tests and documentation
# the same slice owes, and come back with a change nobody can review on its
# own. What it is not is a limit -- what decides that a child is oversized is
# the measurement of its own diff -- so the sentence saying so is here rather
# than left for a developer to infer from a number in a heading.
_BUDGET_BLOCK = """---

## Estimated all-path addition budget: {budget} lines

That is the size this slice was proposed at, counted over **all** of its paths:
implementation, tests, documentation, fixtures, generated files -- everything
this issue commits. No path is excluded from it.

The number binds nothing and excuses nothing: what decides whether the change
this issue produces is oversized is the cumulative measurement of its own diff,
taken exactly as the parent's was. A slice that lands past this repository's
ceiling is adjudicated and split again however it was sized here."""

_REUSE_BLOCK = """---

## Reusing the work already committed for #{parent}

A developer already implemented issue #{parent} and committed the result. That
change measured past this repository's size ceiling, so it was split and you
own the slice above. The commit is preserved on an immutable snapshot ref --
its branch is superseded and its pull request is closed, so the snapshot is the
only place to read it from.

- ancestor snapshot ref, on the remote: `{ref}`
- the same snapshot, once fetched here: `{mirror}`
- exact snapshot commit: `{sha}`
- the base it was cut against: `{base_sha}`
- target base branch: `{base_branch}`
- lineage: root #{root}, parent #{parent}, depth {depth} of at most {bound}
- adjudication: cycle {cycle}, generation {generation}

Read it, from this repository:

```sh
git fetch {remote} '+{ref}:{mirror}'       # only if the ref is not here yet
git log --oneline {base_sha}..{sha}
git diff {base_sha}...{sha}                # three dots: what it ADDS
```

Reuse only what your scope covers, and do it one of two ways:

- **cherry-pick a coherent commit** -- `git cherry-pick <commit>` -- when a
  whole commit belongs to your slice; or
- **copy selected paths** -- `git checkout {mirror} -- <path>` -- when it does
  not, and then finish the slice by hand.

Do **not** split hunks mechanically to make the change smaller. File and hunk
boundaries do not express issue scope, and a change partitioned along them is
one nobody can build or review. Where your slice needs part of a file, write
that part; where it needs none of it, leave the file out. Anything the snapshot
does not cover, implement normally.
"""


@dataclass
class _ChildWalk:
    """One pass over a split manifest, and what the parent already records.

    `known` is read once, before the walk, and never again: it is both the
    register a resumed pass adopts from and the floor its writes may not go
    below. Re-reading it per child would read the walk's own partial write --
    the second index would find only the first child recorded, decide the
    slice it is on has none, and create a duplicate beside the one that
    exists.
    """

    plan: _SplitPlan
    known: tuple[int, ...]
    snapshot_ref: str
    resumed: bool

    # Whether no child of this generation exists that the register does not
    # name. True from the start of a walk nobody resumed -- no earlier attempt
    # could have created anything -- and set once this one has passed the
    # first UNRECORDED index: to have created the index after that, an earlier
    # attempt would have had to record this one, and it did not. Until then a
    # resumed walk cannot say it, which is what keeps a create-before-record
    # crash from being sealed over.
    orphans_ruled_out: list[bool] = field(default_factory=list)

    def past_the_unrecorded(self) -> None:
        """Say the first index no attempt had recorded has been answered."""
        self.orphans_ruled_out.append(True)

    @property
    def every_child_is_recorded(self) -> bool:
        """Whether the register names every child this generation made."""
        return not self.resumed or bool(self.orphans_ruled_out)

    def recorded_numbers(self) -> tuple[int, ...]:
        """The children this generation records once this step is durable.

        Monotonic on purpose. What the walk has placed so far, extended by
        whatever the previous pass recorded beyond it, so a crash in the
        middle of a resumed pass can never leave the parent knowing about
        fewer children than exist on GitHub.
        """
        placed = tuple(number for number, _ in self.plan.created)
        return placed + self.known[len(placed):]


def _create_late_children(
    context: _LateContext, manifest: tuple, snapshot_ref: str,
) -> _SplitPlan | None:
    """Create or adopt every child of this split, in the crash-safe order.

    Returns the populated plan, or None when the loop stopped early -- a
    child that could not be created, recorded, or seeded, or an owner the
    close-check below found closed or unreadable. Either way the caller
    creates nothing further; which of the two it was is on the record.

    The owner is re-read before every child, the first included, because a
    create, a record, and a seed stand between each child and the next -- and
    the write that forces this issue to be an umbrella stands ahead of the
    first -- so a human can close the issue in any of those gaps. A close
    observed by the poll while this worker holds the issue reaches no other
    pass -- the scheduler admits no second worker for it -- so this loop is
    what stops the next child being opened against an issue somebody has
    ended.

    The read at the top of each turn is not the last word, either. Adopting
    a slice that was created and never recorded means walking the whole
    repository for its marker, which is minutes of remote work on a resumed
    pass, so the latch is asked ONE more time immediately before the create
    itself -- the one step here nothing takes back.
    """
    # Read before `_prepared` writes it: a count already there is the only
    # evidence a previous pass got as far as creating anything, and it is what
    # decides whether the orphan lookup below is worth a repository walk.
    resumed = context.state.get(_EXPECTED_CHILDREN) is not None
    _prepared(context, manifest)
    walk = _ChildWalk(
        plan=_SplitPlan.start(list(manifest), True),
        known=context.generation.split_children,
        snapshot_ref=snapshot_ref,
        resumed=resumed,
    )
    for index, child in enumerate(manifest):
        # Index 0 gets its own reading too, rather than borrowing the
        # caller's: `_prepared` above is a remote write, and a close landing
        # inside it would otherwise still open the first child.
        if _stopped(context, index):
            _sealed(context, walk)
            return None
        if not _placed(context, walk, index, child):
            _sealed(context, walk)
            return None
    return walk.plan


def _sealed(context: _LateContext, walk: _ChildWalk) -> None:
    """Close the consumer ledger of a split a CANCELLATION stopped.

    The count this transaction wrote before its first create is what tells a
    partial split from a finished one, and a cancelled loop can never reach
    it: the children it did not make are ones nothing is ever going to make.
    Left unsealed, the ref those children were cut from is one no pass could
    release -- every consumer could end and the proof would still be short of
    the count -- so the owner would hold a snapshot and its terminal forever.

    What makes the ledger final rather than short is the cancellation itself.
    Every exit that reaches here with the mark down is one where the child in
    hand was already RECORDED: the create, the record, and the seed are three
    steps in that order, and each barrier between them is asked after the
    write that names the child. So the register accounts for every child that
    exists, and no further one will ever be opened.

    Except where an EARLIER attempt could have created one this walk has not
    reached: a create is a request and the write recording it is another, so a
    pass that died between them left a child on GitHub with nothing naming it.
    That is what the adoption lookup answers, and until this walk has passed
    the first unrecorded index a resumed one cannot say it -- so it does not,
    and the ref stays held on the count exactly as before.

    Written as the CYCLE it is a fact about, not as a flag. Nothing that ends
    a generation drops this key, so a seal left saying only "yes" would be
    read by the next cycle on the same issue as proof about a register it
    never wrote -- and a later split stopped mid-loop, on a resumed walk that
    seals nothing of its own, would release the ref its unrecorded children
    were cut from.

    Written once, and only over a record that does not already say it.
    """
    if not context.generation.cancelled:
        return
    if not walk.every_child_is_recorded:
        log.info(
            "issue=#%d was cancelled mid-split on a resumed walk; leaving "
            "its consumer ledger open, since a child an earlier attempt "
            "created and never recorded would not be on it",
            context.issue.number,
        )
        return
    cycle = context.generation.cycle_id
    if _state._ledger_is_sealed(
        context.state.get(_state._SPLIT_LEDGER_SEALED), cycle,
    ):
        return
    log.warning(
        "issue=#%d was cancelled with %d of %s children made; sealing cycle "
        "%d's consumer ledger, since the rest are children nothing will "
        "create",
        context.issue.number, len(walk.recorded_numbers()),
        context.state.get(_EXPECTED_CHILDREN), cycle,
    )
    context.state.set(_state._SPLIT_LEDGER_SEALED, cycle)
    _late_park_state._persist(context)


def _placed(
    context: _LateContext, walk: _ChildWalk, index: int, child: dict,
) -> bool:
    """Establish one slice's child, in the order a crash in it is safe in.

    Create or adopt, then record, then seed -- and False anywhere means the
    loop creates nothing further, with the record saying whether that was a
    park or the cancellation a latched close earned.
    """
    created = _child_issue(context, walk, index, child)
    if created is None:
        return False
    if not _recorded(context, walk, index, created, child):
        return False
    if _stopped_seeding(context, created):
        return False
    return _seeded(context, walk, created, child)


def _stopped_seeding(context: _LateContext, created: Issue) -> bool:
    """Whether a close latched inside the create stops this child's seed.

    The create is a request, so the close can land inside it -- and what it
    leaves is a real issue on GitHub. Recording that issue is not optional
    and is not touching it: the parent's own account is what makes the child
    reclaimable at all, and a child nothing names is the one state no pass
    can clean up. The SEED is a write to the child, and a cancelled cycle
    owes its children nothing -- they are not closed, not relabelled, and not
    written to, because what happens to them next is a human's decision.

    A child recorded and never seeded is a state the record already
    describes: the body carries the marker the create stamped into it, and
    the child's pinned comment carries nothing.
    """
    if _late_owner._latch_stops(context) is None:
        return False
    log.warning(
        "issue=#%d was observed closed while child #%d was being created; "
        "recording it and writing nothing to it",
        context.issue.number, created.number,
    )
    return True


def _stopped(context: _LateContext, index: int) -> bool:
    """Whether this issue has stopped wanting the children from here on.

    The reading is the guard's own and so is what it writes: a closed owner
    is marked cancelled where the loop stands, an unreadable one parks with
    the read owed, and only an open one lets the next child be opened.
    """
    if _late_owner._still_wanted(context) is None:
        return False
    log.warning(
        "issue=#%d is no longer known to want its split; creating none of "
        "its children from slice %d on", context.issue.number, index,
    )
    return True


def _prepared(context: _LateContext, manifest: tuple) -> None:
    """Force this issue to be an umbrella, before a single child exists.

    Both fields are what a tick that died mid-loop is read back through: the
    count tells a partial split from a finished one, and the umbrella flag
    says the parent has no implementation of its own to return to. A split
    that recorded neither would leave a parent nobody could finish.

    The flag rather than the label. The label is the last thing this
    transaction writes, because a live generation pins `workflow:decomposing`
    and an issue relabelled ahead of its own retirement is one the guard puts
    straight back.
    """
    context.state.set(_EXPECTED_CHILDREN, len(manifest))
    context.state.set(_state._UMBRELLA, True)
    context.generation = replace(
        context.generation, phase=LatePhase.SPLITTING,
    )
    _late_park_state._persist(context)


def _child_issue(
    context: _LateContext, walk: _ChildWalk, index: int, child: dict,
) -> Issue | None:
    """Adopt the child this index already has, or create it exactly once.

    Adoption is what keeps a retry from opening a second issue for a slice
    that already has one: the parent's own recorded list is the register, and
    it is written in the same durable step the creation is.

    None is "create nothing further", and the record says which of the two
    reasons it was: a park this step could not get past, or a cancellation a
    latched close earned while the lookup was running.
    """
    try:
        return _adopted_or_created(context, walk, index, child)
    except _StrandedChild as stranded:
        log.error(
            "issue=#%d may not take #%d over for slice %d: %s",
            context.issue.number, stranded.number, index, stranded.described,
        )
        _parked(context, stranded.described)
        return None
    except Exception:
        log.exception(
            "issue=#%d could not establish late split child %d (%r)",
            context.issue.number, index, child.get(_TITLE),
        )
        _parked(context, f"child {index} ({child.get('title')!r})")
        return None


def _adopted_or_created(
    context: _LateContext, walk: _ChildWalk, index: int, child: dict,
) -> Issue | None:
    """Return the child at this index, opening one only where none exists.

    Three answers in order, and the middle one is the whole point. A number
    this generation already recorded is the ordinary resume. A marker still
    on GitHub with no number beside it is the crash between the create and
    the write that would have recorded it -- adopted rather than duplicated,
    which is the only recovery for a create nothing outside GitHub knows
    about. Only past both is an issue actually opened.

    None is a fourth answer and it belongs to the create alone: the lookup
    above walks the repository, so the latch is asked again against the step
    that would open a real issue somebody then works. The mark it leaves is
    what tells the loop this was a cancellation rather than a park.
    """
    if index < len(walk.known):
        return context.gh.get_issue(walk.known[index])
    # Past here the first UNRECORDED index has been answered, so nothing an
    # earlier attempt made is left for the register to be missing.
    walk.past_the_unrecorded()
    orphan = _orphan_for(context, walk, index)
    if orphan is not None:
        log.warning(
            "issue=#%d adopting orphan child #%d for slice %d: it was created "
            "and never recorded",
            context.issue.number, orphan.number, index,
        )
        return orphan
    if _late_owner._latch_stops(context) is not None:
        log.warning(
            "issue=#%d was observed closed while slice %d was being looked "
            "up; opening no issue for it",
            context.issue.number, index,
        )
        return None
    return context.gh.create_child_issue(
        title=child[_TITLE],
        body=_child_body(context, child, walk.snapshot_ref, index),
        parent_number=context.issue.number,
        labels=_split._child_initial_labels(),
    )


def _orphan_for(
    context: _LateContext, walk: _ChildWalk, index: int,
) -> Issue | None:
    """The issue an earlier pass created for this slice and never recorded.

    Asked only on a resumed pass. The lookup is a walk over the repository's
    issues in every state, which is what a marker nobody indexed costs -- and
    a first pass has nothing to find, since no earlier one has run. What says
    an earlier one did is the expected count already standing on the parent
    before this pass wrote its own.

    A candidate a human has since closed, or moved off the label a child is
    born on, is refused rather than adopted. Reopening or re-labelling it
    would undo a deliberate act on an issue this orchestrator had not even
    attributed yet, and creating a second one beside it would be worse -- so
    the transaction parks and lets them say which they meant.
    """
    if not walk.resumed:
        return None
    marker = _child_marker(context.generation, index)
    orphan = context.gh.find_issue_carrying(marker)
    if orphan is None:
        return None
    if not _sole_receipt(orphan, marker):
        raise _StrandedChild(
            orphan.number,
            _AMBIGUOUS_RECEIPT.format(number=orphan.number, index=index),
        )
    if _github_issues.issue_is_closed(orphan) or _moved_off_blocked(context, orphan):
        raise _StrandedChild(
            orphan.number, _STRANDED_CHILD.format(number=orphan.number),
        )
    return orphan


def _sole_receipt(orphan: Issue, marker: str) -> bool:
    """Whether this candidate carries THIS receipt and no other slice's.

    The lookup that found it matches a marker as a substring, which is all a
    body search can do -- and a body carries agent-declared scope above the
    marker this transaction stamped in. An issue whose body holds two child
    receipts answers the search for either slice, so adopting on the strength
    of the match alone lets one issue be recorded as two children of the same
    split, each seeded with the other's scope.

    Declared scope carrying a receipt is refused where it is declared, so this
    can only be an issue an older binary created or a human edited. It is
    still asked, because those are exactly the issues nothing else vouches
    for. A body that could not be read carries no receipt this can point at
    and is refused the same way.
    """
    body = getattr(orphan, "body", "") or ""
    return marker in body and body.count(_lineage.CHILD_RECEIPT) == 1


def _forged_receipt(children: tuple) -> str | None:
    """The first declared slice carrying a receipt marker of ours, described.

    Asked of the whole manifest before the transaction creates anything,
    because a slice that carries another slice's receipt is not a problem for
    the slice that declares it -- it is one for whichever slice's lookup finds
    it afterwards, by which time both exist. Refusing the manifest is also the
    recoverable answer: nothing has been pushed yet, so the adjudication can
    be re-asked rather than reconciled by hand.
    """
    for index, child in enumerate(children):
        declared = (child.get(_TITLE), child.get(_BODY))
        if any(_github_comments.carries_reserved_marker(text) for text in declared):
            return _FORGED_RECEIPT.format(
                index=index, title=child.get(_TITLE),
            )
    return None


def _moved_off_blocked(context: _LateContext, orphan: Issue) -> bool:
    """Whether somebody has taken this child off the label it was born on."""
    return context.gh.workflow_label(orphan) != _split._child_initial_labels()[0]


def _recorded(
    context: _LateContext,
    walk: _ChildWalk,
    index: int,
    child_issue: Issue,
    child: dict,
) -> bool:
    """Record this child as a child, a consumer, and an obligation, at once.

    One write, because the three say the same thing to different readers: the
    parent's walk drives the tree, the consumer ledger is what decides whether
    the snapshot may ever be reclaimed, and the obligation entry is what a
    cleanup asks GitHub about. A child recorded as one and not the others is a
    child the snapshot would stop waiting for.

    It is also the durable step that has to precede activation, which is why
    it is here rather than folded into the final write: a runnable child whose
    slot the ledger never took is one a reclamation could delete the snapshot
    out from under.
    """
    walk.plan.record(index, child_issue.number, child)
    try:
        owed = context.generation.with_consumers(
            (child_issue.number,),
        ).with_resource(LateResource(
            kind=LateResourceKind.CHILD,
            target=str(child_issue.number),
            resource_state=LateResourceState.PENDING,
        ))
    except _formats.InvalidLateValue:
        log.exception(
            "issue=#%d cannot record child #%d on its ledgers",
            context.issue.number, child_issue.number,
        )
        _parked(context, f"child #{child_issue.number} ({child.get('title')!r})")
        return False
    recorded = walk.recorded_numbers()
    context.generation = replace(
        owed.with_split_children(recorded), phase=LatePhase.SPLITTING,
    )
    # The stage's own list is written FROM the register rather than appended
    # to, so an earlier decomposition's children and dependency graph are
    # replaced by this generation's rather than left standing over them.
    context.state.set(_state._CHILDREN, list(recorded))
    context.state.set(_DEP_GRAPH, walk.plan.dep_graph or None)
    _late_park_state._persist(context)
    return True


def _seeded(
    context: _LateContext,
    walk: _ChildWalk,
    child_issue: Issue,
    child: dict,
) -> bool:
    """Give this child its parent link, its stamp, and its ancestry.

    The child's own state is read and added to rather than written fresh, for
    the case this step exists to repair: a retry reaches a child that was
    already created, and by then it may be implementing. Writing a fresh
    record over it would take its work with it.

    False is either of the two ways this child is the last one: a write that
    could not be made, which parks, and the cancellation a close latched
    inside the read earned, which is on the record already. Both stop the
    loop where it stands, and the cancellation has to -- reporting success
    would let the loop go on opening real issues against an ended cycle, and
    would leave the barriers behind it marking a cancellation that is already
    marked.
    """
    try:
        return _seed_child_state(context, walk, child_issue, child)
    except Exception:
        log.exception(
            "issue=#%d could not seed child #%d with its ancestry",
            context.issue.number, child_issue.number,
        )
        _parked(context, f"child #{child_issue.number} ({child.get('title')!r})")
        return False


def _seed_child_state(
    context: _LateContext,
    walk: _ChildWalk,
    child_issue: Issue,
    child: dict,
) -> bool:
    """Add the parent link, the stamp, and the ancestry to a child's state.

    The park an unattributed child took goes with the link that attributes it,
    exactly as the initial mode's orphan repair does. A child created into a
    crash is on GitHub with no parent recorded, and the poll order is the
    repository's rather than this transaction's -- GitHub sorts by most
    recently updated, so the child it just created can be dispatched before
    the write that records it -- and a `blocked` issue nobody claims is parked
    for a human. Leaving that park standing would hand the child an
    `awaiting_human` it never earned: the parent activates it, the implementing
    stage reads the flag, and it waits for a reply nobody owes it.

    Cleared only where this write is the one that first attributes the child.
    A child that already records a parent has been attributed, so any park on
    it is its own -- something it hit while running -- and not this
    transaction's to take back.

    The read is a request, so the poll can observe the close inside it -- and
    what stands immediately behind it is the one write this transaction makes
    to a child's OWN pinned comment. A cancelled cycle leaves every child that
    already exists entirely untouched, so the latch is asked between the two,
    and the answer travels back rather than stopping here: this is the LAST
    step of one child's turn, so a caller told it succeeded would open the
    next slice's issue against a cycle that has just ended.
    """
    child_state = context.gh.read_pinned_state(child_issue)
    if _late_owner._latch_stops(context) is not None:
        log.warning(
            "issue=#%d was observed closed while child #%d was being read; "
            "writing nothing to it", context.issue.number, child_issue.number,
        )
        return False
    if not child_state.get(_state._PARENT_NUMBER):
        child_state.set(_state._PARENT_NUMBER, context.issue.number)
        child_state.set(_state._AWAITING_HUMAN, False)
        child_state.set(_state._PARK_REASON, None)
    if child_state.get(_state._CREATED_AT) is None:
        child_state.set(_state._CREATED_AT, _usage._now_iso())
    _lineage.write_late_ancestry(
        child_state, _child_ancestry(context, child, walk.snapshot_ref),
    )
    context.gh.write_pinned_state(child_issue, child_state)
    return True


def _child_ancestry(
    context: _LateContext, child: dict, snapshot_ref: str,
) -> _lineage.LateAncestry:
    """What this child inherits from the generation that created it.

    The depth is asked of the lineage owner rather than incremented here, so
    the bound is enforced at the one place a child's depth is computed. The
    caller has already refused a split the lineage forbids; asking again costs
    nothing and means no path here can produce a child past the cap.

    The pointer is stamped with the ordering the reclamation that can take it
    runs under, because the child's guard reads a surviving local copy of the
    ref as proof no reclamation has happened -- and that is only true of a
    reclamation which takes this host's copy down first. The stamp is written
    HERE, by the binary that would do the reclaiming, so it says something
    about the world this pointer was created into rather than something about
    the reader.
    """
    generation = context.generation
    return _lineage.LateAncestry(
        root_issue=generation.root_issue,
        lineage_depth=_identity.child_lineage_depth(generation.lineage_depth),
        parent_issue=generation.current_issue,
        cycle_id=generation.cycle_id,
        generation=generation.generation,
        snapshot_ref=snapshot_ref,
        snapshot_sha=generation.candidate_sha,
        mirror_first=True,
        base_branch=context.spec.base_branch,
        scope=_declared_scope(child),
    )


def _child_marker(generation, index: int) -> str:
    """The hidden marker naming this issue, adjudication, and slice."""
    return _lineage.child_marker(
        issue=generation.current_issue,
        cycle=generation.cycle_id,
        generation=generation.generation,
        index=index,
    )


def _child_body(
    context: _LateContext, child: dict, snapshot_ref: str, index: int,
) -> str:
    """The issue body one child is created with.

    The manifest's own body first, because that is the slice a human reads,
    and the reuse block after it -- so an issue whose snapshot has since been
    reclaimed still opens as a description of work rather than as instructions
    for a ref that is gone. The budget the adjudication sized this slice at
    goes between them, where a developer meets it with the scope it is about.

    A slice that declared no budget states none. That is what a manifest
    recorded before this domain kept budgets reads back as, and those still
    create children -- so the section is dropped rather than written with a
    number nobody estimated.
    """
    generation = context.generation
    sections = (
        _declared_scope(child),
        _budget_block(child),
        _child_marker(generation, index),
        _REUSE_BLOCK.format(
            parent=generation.current_issue,
            ref=snapshot_ref,
            mirror=_snapshot_refs.local_snapshot_ref(
                context.spec, snapshot_ref,
            ),
            sha=generation.candidate_sha,
            base_sha=generation.base_sha,
            base_branch=context.spec.base_branch,
            remote=context.spec.remote_name,
            root=generation.root_issue,
            depth=_identity.child_lineage_depth(generation.lineage_depth),
            bound=MAX_LINEAGE_DEPTH,
            cycle=generation.cycle_id,
            generation=generation.generation,
        ),
    )
    return "\n\n".join(section for section in sections if section)


def _budget_block(child: dict) -> str:
    """What this slice was sized at, or nothing where nobody sized it."""
    budget = _budget.declared_budget(child)
    if budget is None:
        return ""
    return _BUDGET_BLOCK.format(budget=budget)


def _declared_scope(child: dict) -> str:
    """The slice this child owns, as the adjudication wrote it."""
    written = child.get(_BODY)
    if isinstance(written, str) and written.strip():
        return written.strip()
    return _WHOLE_ISSUE


def _parked(context: _LateContext, described: str) -> None:
    """Hand the issue back, naming the child that could not be established."""
    _late_outcome._emit_failure(context, LateFailure.CHILD_CREATE_FAILED)
    _late_parks._park(
        context,
        _CHILD_CREATE_PARK.format(child=described),
        reason=_late_park_state.PARK_CHILDREN_FAILED,
    )
