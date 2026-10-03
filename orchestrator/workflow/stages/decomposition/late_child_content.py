# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Late-child scope, lineage, snapshot instructions, and receipt-safe issue content.

Each child names the exact preserved candidate and its declared budget.
Reserved receipt markers in proposed scope are refused before publication.
The reuse instructions are rendered off a child's pointed ancestry, so an
ordinary split that points a replacement at the same snapshot tells it the
same thing. What any issue text names in the snapshot namespace is read by one
reader, so every caller holding a slice or a child's text to a snapshot gets
the same answer -- and the names a kept snapshot may go by are read off those
instructions by the same reader, so no spelling they use is refused. The
replacement lineage renders those instructions for every replacement an
ordinary split points at its parent's snapshot, and holds both a slice before
creation and a recorded child before release to that reader.
"""
from __future__ import annotations

import re

from orchestrator.config import models as _config_models
from orchestrator.git.snapshots import mirrors as _snapshot_mirrors, namespace as _snapshot_namespace
from orchestrator.github import comments as _github_comments
from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
    identity as _identity,
    models as _late_models,
)
from orchestrator.workflow.stages.decomposition import (
    late_budget as _budget,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext

_WHOLE_ISSUE = "(the whole issue)"

# The two keys a declared slice is read through.
_TITLE = "title"

_BODY = "body"

_FORGED_RECEIPT = (
    "slice {index} ({title!r}) declares scope carrying an orchestrator "
    "receipt marker"
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


# What a git ref name may be spelled with: anything but an ASCII space or
# control character and the few characters git refuses anywhere in one. Git
# refuses bytes, not Unicode classes, so a non-breaking or any other non-ASCII
# space is part of a name it would fetch -- and is read as part of one here.
# A `*` is read as part of a name too, though git refuses it in one: a refspec
# spelled with it is a pattern git fetches every ref it matches through, so
# `...gen-1*` names `...gen-10` as well, and is no spelling of `...gen-1`.
_REF_CHARACTER = r"[^\x00-\x20\x7f~^:?\[\\]"

# Anything issue text names in the snapshot namespace -- a remote ref, or a
# host's mirror of one -- read as the whole ref name it could be: as far as
# ref characters run on EITHER side of the namespace, so a name that merely
# contains an allowed ref (`...gen-1@foreign`, `...gen-1!`,
# `refs/heads/refs/...`) reads as the different ref it is. The quotes,
# backticks, or brackets that open the mention are `lead`, and one `+` behind
# them is a forced refspec's; a second `+` is part of the name. A refspec is
# one mention with the namespace on either side of its colon, so wrapping
# opened before its source may close after its destination, the way the reuse
# instructions quote theirs. Only a whole refspec is forced, so the `side` a
# destination is read as keeps the `+` that opens it: git takes that `+` as
# the first character of a different ref. A mirror carries the repository
# segment it was fetched for, and one under another repository's segment is
# that repository's copy of the same three numbers: possibly other work, and
# kept by no ledger here. A mention that is no whole ref is no child's either.
_NAMED_SNAPSHOT = re.compile(
    rf"(?<!{_REF_CHARACTER})(?P<spelled>(?P<lead>[`'\"(<\[]*)"
    rf"(?=(?:{_REF_CHARACTER}*:)?{_REF_CHARACTER}*?{re.escape(_snapshot_namespace.SNAPSHOT_NAMESPACE)})"
    rf"(?P<side>\+?(?P<name>{_REF_CHARACTER}*)))(?::(?P<destination>{_REF_CHARACTER}*))?",
)

# What closes each opening a mention may lead with. A lead is wrapping only
# where the mention ends on exactly the closers it calls for, in the order it
# calls for them; one left open is part of the name, as is any other character
# a ref may contain, however much it looks like punctuation.
_CLOSER_OF = str.maketrans("`'\"(<[", "`'\")>]")

# What no ref name may end in, so a mention ending in one is the sentence
# around it rather than the ref.
_NEVER_ENDS_A_REF = "./"


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


def _child_ancestry(
    context: _LateContext, child: dict, snapshot_ref: str,
) -> _ancestry.LateAncestry:
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
    return _ancestry.LateAncestry(
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
    return _ancestry.child_marker(
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
    budget = _budget.declared_budget(child)
    sections = (
        _declared_scope(child),
        "" if budget is None else _BUDGET_BLOCK.format(budget=budget),
        _child_marker(generation, index),
        _reuse_block(context.spec, _child_ancestry(context, child, snapshot_ref), generation.base_sha),
    )
    return "\n\n".join(section for section in sections if section)


def _reuse_block(spec: _config_models.RepoSpec, pointed: _ancestry.LateAncestry, base_sha: str) -> str:
    """How a child reads the snapshot its ancestry points it at, and what it may reuse.

    Everything named comes off the pointer and the lineage beside it -- the
    owner, the ref, the commit, the root, the depth, and the adjudication --
    so the instructions and the record a child's own guard reads can never
    name two different snapshots. `base_sha` is what the preserved candidate
    was cut against, which no ancestry records.
    """
    return _REUSE_BLOCK.format(
        parent=pointed.parent_issue,
        ref=pointed.snapshot_ref,
        mirror=_snapshot_mirrors.local_snapshot_ref(spec, pointed.snapshot_ref),
        sha=pointed.snapshot_sha,
        base_sha=base_sha,
        base_branch=spec.base_branch,
        remote=spec.remote_name,
        root=pointed.root_issue,
        depth=pointed.lineage_depth,
        bound=_late_models.MAX_LINEAGE_DEPTH,
        cycle=pointed.cycle_id,
        generation=pointed.generation,
    )


def _named_snapshots(*texts: object, forced: bool = True) -> frozenset[str]:
    """Every snapshot ref the given issue texts name, each as it is spelled.

    Asked of a title and a body together, because both are what an
    implementer reads. Not only the line the reuse instructions spell a ref
    on: a ref copied into prose, a line ending the instructions were not
    written with, or a mirror name all tell a child where a snapshot is, and
    a reader that saw only one spelling would let the rest through. Read back
    rather than remembered, since a child's body is written before the record
    that protects it.

    A mirror is not read as the remote ref it mirrors, because only this
    repository's own segment makes it that: which names a kept snapshot may
    go by is the lineage's answer -- see `ReplacementLineage.told` -- and
    anything else named here is a ref nothing keeps for the child. Nor is a
    ref read out of a longer name that contains it, or out of a pattern
    spelling it with a `*`: git would fetch that longer name, or every ref the
    pattern matches, so that is what the text tells a child to reuse. Only
    wrapping closed on both sides and a single refspec `+` are taken off --
    `` `ref` ``, `(ref)`, `[ref]`, and `+ref` name `ref`, while `` `ref!` ``,
    `ref,`, `'ref`, `ref]`, `ref*`, and `++ref` name the refs spelled that
    way. A refspec names each of its sides, and wrapping its source leaves
    open may close after its destination instead: `'+ref:mirror'` -- the
    fetch as the reuse instructions quote it, in every child already
    published too -- and `+ref:'mirror'` both name `ref` and `mirror`. A `+`
    forces only the whole refspec, so a destination is read with `forced`
    false, keeping the `+` that opens it: `ref:+mirror` and `ref:'+mirror'`
    name `ref` and `+mirror`.
    """
    named = set()
    # One text per line, so no mention runs from one into the next.
    for mention in _NAMED_SNAPSHOT.finditer(
        "\n".join(text for text in texts if isinstance(text, str)),
    ):
        closers = "".join(reversed(mention.group("lead"))).translate(_CLOSER_OF)
        name = mention.group("name" if forced else "side").rstrip(_NEVER_ENDS_A_REF)
        destination = (mention.group("destination") or "").rstrip(_NEVER_ENDS_A_REF)
        if name.endswith(closers):
            named.add(name.removesuffix(closers).rstrip(_NEVER_ENDS_A_REF))
        elif destination.endswith(closers):
            named.add(name)
            destination = destination.removesuffix(closers)
        else:
            named.add(mention.group("spelled").rstrip(_NEVER_ENDS_A_REF))
        named.update(_named_snapshots(destination, forced=False))
    return frozenset(spelled for spelled in named if _snapshot_namespace.SNAPSHOT_NAMESPACE in spelled)


def _declared_scope(child: dict) -> str:
    """The slice this child owns, as the adjudication wrote it."""
    written = child.get(_BODY)
    if isinstance(written, str) and written.strip():
        return written.strip()
    return _WHOLE_ISSUE
