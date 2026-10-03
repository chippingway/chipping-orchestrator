# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An issue inside a late lineage, handed back to the ordinary decomposer.

What reaches that decomposer in production is an issue a genuine edit rerouted
to `workflow:decomposing`: an umbrella a late split made, or a child one made.
Its pinned comment still carries everything the late path wrote -- the split's
own record where it split, the ancestry where a split made it -- and the
reroute has already cleared the manifest and recorded the edited content as
the baseline. That is the state seeded here, through the record
`replacement_lineage_support` writes, so the decomposing tick -- and the
recovery, release, and dispatch hold behind it -- reads the wire shape a live
issue carries.
"""
from __future__ import annotations

from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.late_split import ancestry as _ancestry, models as _late_models
from orchestrator.workflow.stages.decomposition import run as _decomposing
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_DECOMPOSING, _agent, _manifest
from tests.workflow.patch_context import _patch_and_run
from tests.workflow.patch_models import _WorkflowRunContext
from tests.workflow.stages.decomposition import replacement_lineage_support as _lineage_support

# Whole ref names git would fetch that merely contain the parent's snapshot:
# two running on past it -- the second on a character prose ends sentences
# with -- and one nesting it under another namespace. None is on any ledger.
EXTENDED_REF = f"{_lineage_support.SNAPSHOT_REF}@foreign"

EXCLAIMED_REF = f"{_lineage_support.SNAPSHOT_REF}!"

# Git refuses only ASCII spaces in a ref name, so a non-breaking one runs the
# name on as surely as `!` does -- however much it reads like a word break.
SPACED_REF = f"{_lineage_support.SNAPSHOT_REF} foreign"

# Spellings whose wrapping is not the kind that is taken off: a refspec with a
# second `+` -- one is a forced refspec's, the other is the name's -- and a
# quote opened in front of the ref and never closed.
DOUBLED_REFSPEC = f"++{_lineage_support.SNAPSHOT_REF}"

UNCLOSED_REF = f"'{_lineage_support.SNAPSHOT_REF}"

NESTED_REF = f"refs/heads/{_lineage_support.SNAPSHOT_REF}"

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

# The same answer over two replacements, the second waiting on the first:
# released by a dependency poll after the split, not by the split itself.
DEPENDENT_MANIFEST = _manifest(
    '{"decision": "split", "umbrella": true, "rationale": "re-planned", "children": ['
    '{"title": "A", "body": "the groundwork, as the edit now asks"}, '
    '{"title": "B", "body": "the rest of it, on top", "depends_on": [0]}]}'
)

# The same answer over three replacements, the second and third both waiting
# on the first: released together, by one dependency poll, once it is done.
FANNED_MANIFEST = _manifest(
    '{"decision": "split", "umbrella": true, "rationale": "re-planned", "children": ['
    '{"title": "A", "body": "the groundwork, as the edit now asks"}, '
    '{"title": "B", "body": "one half of the rest, on top", "depends_on": [0]}, '
    '{"title": "C", "body": "the other half of the rest, on top", "depends_on": [0]}]}'
)

DECOMPOSER_SESSION = "replanned"

PARK_EVENT = "park_awaiting_human"


def late_parent(
    generation: _late_models.LateGeneration | None = None,
    ancestry: _ancestry.LateAncestry | None = None,
    body: str = _lineage_support.EDITED_BODY,
    **extra_state,
) -> tuple[FakeGitHubClient, FakeIssue]:
    """The rerouted issue, carrying the late groups a case names.

    Baselined at its content as it stands, which is what the reroute that
    sent it here recorded -- so the decomposing tick runs the decomposer
    rather than meeting the edit a second time. `extra_state` lands over the
    groups as written, the way a hand edit or another binary's write would.
    """
    github = FakeGitHubClient()
    issue = make_issue(_lineage_support.PARENT, label=LABEL_DECOMPOSING, body=body)
    github.add_issue(issue)
    recorded = _lineage_support.record(generation, ancestry)
    recorded.set("user_content_hash", _content_hash._compute_user_content_hash(issue, set()))
    github.seed_state(_lineage_support.PARENT, **{**recorded.data, **extra_state})
    return github, issue


def redecompose(
    github: FakeGitHubClient,
    issue: FakeIssue,
    answer: str = REPLACEMENT_MANIFEST,
    tick=_decomposing._handle_decomposing,
):
    """One tick whose agent answers `answer`; the mocks it ran under.

    The decomposing tick unless a case names another handler -- the parent
    poll that follows a split, or the pickup of a child it created.
    """
    return _patch_and_run(
        lambda: tick(github, _TEST_SPEC, issue),
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
        if record.get("event") == PARK_EVENT and record.get("issue") == _lineage_support.PARENT
    ]


def consumers(github: FakeGitHubClient) -> list:
    """The parent's recorded snapshot consumers, as pinned."""
    return github.pinned_data(_lineage_support.PARENT).get(KEY_CONSUMERS) or []
