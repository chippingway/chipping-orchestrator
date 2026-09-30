# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Late-child scope, lineage, snapshot instructions, and receipt-safe issue content.

Each child names the exact preserved candidate and its declared budget.
Reserved receipt markers in proposed scope are refused before publication.
The reuse instructions are rendered off a child's pointed ancestry, so an
ordinary split that points a replacement at the same snapshot tells it the
same thing. What any issue text names in the snapshot namespace is read by one
reader, so a split refusing a slice and a recovery repairing a child hold that
text to the same answer -- and the names a kept snapshot may go by are read off
those instructions by the same reader, so no spelling they use is refused.
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


# Anything issue text names in the snapshot namespace: a remote ref, or a
# host's mirror of one -- as far as the path segments a ref is spelled with
# run, short of a full stop or slash that only ends the sentence around it.
# Each reads back as spelled. A mirror carries the repository segment it was
# fetched for, and one under another repository's segment is that
# repository's copy of the same three numbers: possibly other work, and kept
# by no ledger here. A mention that is no whole ref is no child's either.
_NAMED_SNAPSHOT = re.compile(
    rf"{re.escape(_snapshot_namespace.SNAPSHOT_NAMESPACE)}(?:-local)?(?:/[\w.-]*[\w-])*",
)


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


def _named_snapshots(*texts: object) -> frozenset[str]:
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
    anything else named here is a ref nothing keeps for the child.
    """
    return frozenset(
        match.group()
        for text in texts
        if isinstance(text, str)
        for match in _NAMED_SNAPSHOT.finditer(text)
    )


def _declared_scope(child: dict) -> str:
    """The slice this child owns, as the adjudication wrote it."""
    written = child.get(_BODY)
    if isinstance(written, str) and written.strip():
        return written.strip()
    return _WHOLE_ISSUE
