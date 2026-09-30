# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An issue inside a late lineage, handed back to the ordinary decomposer.

What reaches that decomposer in production is an issue a genuine edit rerouted
to `workflow:decomposing`: an umbrella a late split made, or a child one made.
Its pinned comment still carries everything the late path wrote -- the split's
own record where it split, the ancestry where a split made it -- and the
reroute has already cleared the manifest and recorded the edited content as
the baseline. That is the state seeded here, with every late group written
through its own owner, so the decomposing tick reads the wire shape a live
issue carries.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
    lineage as _lineage,
    models as _late_models,
    obligations as _obligations,
    phases as _late_phases,
    state as _late_state,
)
from orchestrator.workflow.stages.decomposition import run as _decomposing
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_DECOMPOSING, _agent, _manifest
from tests.workflow.patch_context import _patch_and_run
from tests.workflow.patch_models import _WorkflowRunContext

SHA_LENGTH = 40

# The issue the decomposer re-derives a manifest for, and the child its own
# late split made before the edit orphaned it.
PARENT = 41

ORIGINAL = 411

# The root above a descendant parent, and the adjudication that cut the
# parent from it.
ANCESTOR = 4

ANCESTOR_CYCLE = 2

# The parent's own split: cycle 3, generation 1, over candidate `a...`.
CYCLE = 3

GENERATION = 1

CANDIDATE_SHA = "a" * SHA_LENGTH

BASE_SHA = "b" * SHA_LENGTH

SNAPSHOT_REF = "refs/orchestrator/late-split/issue-41/cycle-3/gen-1"

# The pinned keys a replacement's seed and its parent's record are read back
# through.
KEY_PARENT_NUMBER = "parent_number"

KEY_CREATED_AT = "created_at"

KEY_CHILDREN = "children"

KEY_EXPECTED = "expected_children_count"

KEY_CONSUMERS = "late_consumers"

KEY_AWAITING_HUMAN = "awaiting_human"

# What the decomposer answers the edited issue with: the umbrella again, over
# this many replacements.
REPLACEMENT_COUNT = 2

REPLACEMENT_MANIFEST = _manifest(
    '{"decision": "split", "umbrella": true, "rationale": "re-planned", "children": ['
    '{"title": "A", "body": "the first half, as the edit now asks"}, '
    '{"title": "B", "body": "the second half, as the edit now asks"}]}'
)

# The same answer over one replacement, for the cases about one child: a
# count of one is reached by the first child the loop records.
ONE_REPLACEMENT_MANIFEST = _manifest(
    '{"decision": "split", "umbrella": true, "rationale": "re-planned", "children": ['
    '{"title": "A", "body": "the whole of it, as the edit now asks"}]}'
)

DECOMPOSER_SESSION = "replanned"

EDITED_BODY = "the issue, as a human last edited it"

PARK_EVENT = "park_awaiting_human"

# What a replacement of the root's split is born with: its lineage, and that
# lineage pointed at the snapshot the root's own split holds for it.
ROOT_LINEAGE = _ancestry.LateAncestry(
    root_issue=PARENT, lineage_depth=1, parent_issue=PARENT, cycle_id=CYCLE, generation=GENERATION,
)

ROOT_REPLACEMENT = replace(ROOT_LINEAGE, snapshot_ref=SNAPSHOT_REF, snapshot_sha=CANDIDATE_SHA, mirror_first=True)


def own_split(
    ref_state: _obligations.LateResourceState = _obligations.LateResourceState.RETAINED, **overrides,
) -> _late_models.LateGeneration:
    """The parent's settled split, as its retirement onto `umbrella` leaves it.

    The register, the consumer, and the child obligation are the one write
    the split records a child in, and the snapshot entry stands at
    `ref_state`. Rooted at the parent at depth 0 unless a case names the
    lineage a descendant's own split was minted in.
    """
    held = _obligations.LateResource(_obligations.LateResourceKind.SNAPSHOT_REF, SNAPSHOT_REF, ref_state)
    made = _obligations.LateResource(_obligations.LateResourceKind.CHILD, str(ORIGINAL))
    return replace(
        _late_models.LateGeneration(
            cycle_id=CYCLE,
            generation=GENERATION,
            root_issue=PARENT,
            current_issue=PARENT,
            lineage_depth=0,
            candidate_sha=CANDIDATE_SHA,
            base_sha=BASE_SHA,
            phase=_late_phases.LatePhase.CLEANING_UP,
            links_announced=True,
            split_children=(ORIGINAL,),
            obligations=_obligations.LateObligations(resources=(held, made), consumers=(ORIGINAL,)),
        ),
        **overrides,
    )


def cut_from_ancestor(depth: int = 1, parent: int = ANCESTOR) -> _ancestry.LateAncestry:
    """The ancestry a late split wrote on this issue, `depth` below the root.

    Pointed at the ref the split that made it minted, which is its parent's
    and not this issue's own.
    """
    return _ancestry.LateAncestry(
        root_issue=ANCESTOR,
        lineage_depth=depth,
        parent_issue=parent,
        cycle_id=ANCESTOR_CYCLE,
        generation=GENERATION,
        snapshot_ref=f"refs/orchestrator/late-split/issue-{parent}/cycle-{ANCESTOR_CYCLE}/gen-{GENERATION}",
        snapshot_sha=CANDIDATE_SHA,
        mirror_first=True,
        scope="the slice this issue was cut for",
    )


def late_parent(
    generation: _late_models.LateGeneration | None = None,
    ancestry: _ancestry.LateAncestry | None = None,
    body: str = EDITED_BODY,
    **extra_state,
) -> tuple[FakeGitHubClient, FakeIssue]:
    """The rerouted issue, carrying the late groups a case names.

    Baselined at its content as it stands, which is what the reroute that
    sent it here recorded -- so the decomposing tick runs the decomposer
    rather than meeting the edit a second time. `extra_state` lands over the
    groups as written, the way a hand edit or another binary's write would.
    """
    github = FakeGitHubClient()
    issue = make_issue(PARENT, label=LABEL_DECOMPOSING, body=body)
    github.add_issue(issue)
    recorded = PinnedState()
    if generation is not None:
        _late_state.write_late_generation(recorded, generation)
    if ancestry is not None:
        _lineage.write_late_ancestry(recorded, ancestry)
    recorded.set("user_content_hash", _content_hash._compute_user_content_hash(issue, set()))
    github.seed_state(PARENT, **{**recorded.data, **extra_state})
    return github, issue


def redecompose(github: FakeGitHubClient, issue: FakeIssue, answer: str = REPLACEMENT_MANIFEST):
    """One decomposing tick whose decomposer answers `answer`; the mocks it ran under."""
    return _patch_and_run(
        lambda: _decomposing._handle_decomposing(github, _TEST_SPEC, issue),
        _WorkflowRunContext(run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=answer)),
    )


def replacements(github: FakeGitHubClient) -> list[int]:
    """Every child issue a split on this client created, in creation order."""
    return [child.number for child in github.created_child_issues]


def parks(github: FakeGitHubClient) -> list:
    """What every park on the parent was filed under."""
    return [
        record.get("reason")
        for record in github.recorded_events
        if record.get("event") == PARK_EVENT and record.get("issue") == PARENT
    ]


def consumers(github: FakeGitHubClient) -> list:
    """The parent's recorded snapshot consumers, as pinned."""
    return github.pinned_data(PARENT).get(KEY_CONSUMERS) or []
