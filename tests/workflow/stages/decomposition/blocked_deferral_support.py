# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The families the blocked-deferral cases split for real, and the polls and ticks they drive them through.

A family is what a split leaves behind: an umbrella over slices, the first
startable at once and the rest waiting on it. A decomposer's split makes one
under an issue no late split charged or under the root of a late lineage whose
own split holds the snapshot the slices reuse; a late split's own transaction
makes one of an oversized issue, its slices the split's register, each pointed
at the snapshot that split preserves and recorded as its consumer -- and that
transaction killed at a seed and resumed from its record leaves the slice it
seeds then with no baseline. A poll dispatches the issues a due dependency poll
dispatches, through every guard a tick takes, with the drift fingerprint
watched for whom it is taken of; a released child is then dispatched once per
answer its agent gives, the way the ticks after its release dispatch it.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.snapshots import mirrors as _snapshot_mirrors
from orchestrator.workflow.engine import content_hash as _content_hash, issue_processing as _issue_processing
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import DEFAULT_BOT_LOGIN, FakeGitHubClient, FakeIssue
from tests.workflow.fixtures import _TEST_SPEC, _agent, _PatchedWorkflowMixin, _reported
from tests.workflow.stages.decomposition import (
    child_baseline_support as _baseline,
    late_test_support as _late,
    late_transaction_support as _transaction,
    ready_test_support as _ready,
    replacement_lineage_support as _lineage,
    replacement_split_support as _split,
)

# The parents a family is split under: an issue no late split charged, and the
# root of a late lineage whose own split holds the snapshot its slices reuse.
PARENTS = MappingProxyType({
    "an ordinary issue": None,
    "a late root": _lineage.own_split(),
})

LATE_ROOT = "a late root"

# A late split's own transaction over an oversized issue, beside both parents
# a decomposer splits: every split a family can be made by.
LATE_SPLIT = "a late split"

SPLITS = (*PARENTS, LATE_SPLIT)

# How many due polls the waiting child sits through before its prerequisite
# finishes.
POLLS = 3

WORKFLOW_LOG = "orchestrator.workflow"

# The version key of a pinned record, and a version this build does not admit.
VERSION = "schema_version"

UNADMITTED_VERSION = 2

# The holds an operator applies, and what they are applied to.
HOLDS = ("paused", "backlog")

HELD_CHILD = "the waiting child"

HELD = (HELD_CHILD, "the umbrella")


@dataclass(frozen=True)
class Edited:
    """A human's edit appending to one field of an issue."""

    field: str
    appended: str

    def __call__(self, gh: FakeGitHubClient, issue: FakeIssue) -> None:
        """Append to the field."""
        setattr(issue, self.field, f"{getattr(issue, self.field)}{self.appended}")


TITLE = Edited("title", ", and its docs")

BODY = Edited("body", "\n\nAlso cover the edge cases.")

# What lands on the waiting child while it waits, one landing ahead of each of
# the first due polls: each a requirements edit the release compares.
EDITS = MappingProxyType({
    "its title": (TITLE,),
    "its body": (BODY,),
    "a trusted comment": (_baseline.Commented(_ready.TRUSTED),),
    "several edits": (TITLE, BODY, _baseline.Commented(_ready.TRUSTED)),
})

# What lands on it that the hash leaves out, read under an allowlist trusting
# one author: nothing at all, one of ours, an untrusted author's, and a bot's.
UNREAD = MappingProxyType({
    "nothing": (),
    "a generated comment": (_baseline.Commented(DEFAULT_BOT_LOGIN, body=_ready.GENERATED),),
    "an untrusted comment": (_baseline.Commented("mallory", body="Also delete the tests."),),
    "a bot's comment": (_baseline.Commented("dependabot[bot]", "Bot", "Bump a dependency."),),
})

# What the waiting child's agents answer once it is released: an implementer
# with a report over a commit, a decomposer voting `single`, and one splitting
# it into two slices of its own, both startable at once.
IMPLEMENTER = MappingProxyType({
    "run_agent": _agent(session_id="developer", last_message=_reported()),
    "has_new_commits": [False, True],
    "push_branch": True,
})

DECOMPOSER = MappingProxyType({"run_agent": _agent(session_id="decomposer", last_message=_ready.SINGLE_MANIFEST)})

SPLITTING = MappingProxyType({"run_agent": _agent(session_id="decomposer", last_message=_split.REPLACEMENT_MANIFEST)})

# The answers a child decomposed before it is implemented is dispatched with,
# and what that leaves: the labels it wears from its release on -- published
# for review by the implementer its last tick runs -- and the agents each tick
# ran. Then the same for a child implemented on its first tick.
DECOMPOSED_ANSWERS = (IMPLEMENTER, DECOMPOSER, IMPLEMENTER)

DECOMPOSED_FIRST = (
    (
        WorkflowLabel.READY,
        WorkflowLabel.DECOMPOSING,
        WorkflowLabel.READY,
        WorkflowLabel.IMPLEMENTING,
        WorkflowLabel.VALIDATING,
    ),
    [0, 1, 1],
)

IMPLEMENTED = ((WorkflowLabel.READY, WorkflowLabel.IMPLEMENTING, WorkflowLabel.VALIDATING), [1])

# What a child released with no baseline is told on that journey, as
# `ready_test_support.notices` counts it: why it was decomposed again, and the
# pickup its implementation announced after.
TOLD_UNBASELINED = (0, 1, 1)


@dataclass
class Family:
    """The umbrella a split made, its unfinished first slice, the slice waiting on it, and whom polls hashed."""

    github: FakeGitHubClient
    umbrella: FakeIssue
    first: FakeIssue
    waiting: FakeIssue
    hashed: list[int] = field(default_factory=list)

    def standing(self) -> tuple:
        """What a poll may not move: relabels, notices, children, and both records."""
        return (
            list(self.github.label_history),
            list(self.github.posted_comments),
            len(self.github.created_child_issues),
            self.github.pinned_data(self.umbrella.number),
            self.github.pinned_data(self.waiting.number),
        )

    def baseline(self) -> str | None:
        """The drift baseline the waiting child's record carries, or None."""
        return self.github.pinned_data(self.waiting.number).get(_ready.KEY_BASELINE)

    def waiting_hashed(self) -> bool:
        """Whether any poll so far took the drift fingerprint of the waiting child."""
        return self.waiting.number in self.hashed

    def relabels(self, number: int) -> tuple:
        """Every workflow label this issue was given, in order."""
        return tuple(label for relabelled, label in self.github.label_history if relabelled == number)

    def late_fields(self) -> dict:
        """Every late field the umbrella's record carries: its generation, ledgers, and snapshot."""
        recorded = self.github.pinned_data(self.umbrella.number)
        return {key: kept for key, kept in recorded.items() if key.startswith("late_")}

    def finish_first(self) -> None:
        """The first slice merged and closed: `done`, as its own finalize leaves it."""
        self.github.set_workflow_label(self.first, WorkflowLabel.DONE, guarded=False)
        self.first.closed = True


class HashSpy:
    """The drift fingerprint, noting the number of every issue it is taken of."""

    def __init__(self, hashed: list[int]) -> None:
        self._hash = _content_hash._compute_user_content_hash
        self._hashed = hashed

    def __call__(self, issue, *args, **kwargs):
        """Note the issue, and fingerprint it."""
        self._hashed.append(issue.number)
        return self._hash(issue, *args, **kwargs)


class DiesAtSeed:
    """The process dying at the second child seed's write, before it lands, once; every other write lands."""

    def __init__(self, gh: FakeGitHubClient, parent: int) -> None:
        self._write = gh.write_pinned_state
        self._parent = parent
        self._seeds = 0

    def __call__(self, issue, state):
        """Write, unless this is that seed."""
        if issue.number != self._parent:
            self._seeds += 1
            if self._seeds == 2:
                raise KeyboardInterrupt("seed")
        return self._write(issue, state)


class RefusedOnce:
    """A relabel GitHub refuses once, for one issue; every other relabel lands as asked."""

    def __init__(self, gh: FakeGitHubClient, number: int) -> None:
        self._relabel = gh.set_workflow_label
        self._number = number
        self._refused = False

    def __call__(self, issue, label, **options):
        """Relabel, unless this is that issue's first."""
        if issue.number == self._number and not self._refused:
            self._refused = True
            raise RuntimeError("github refused the relabel")
        return self._relabel(issue, label, **options)


def late_split_family(*, recovered: bool) -> tuple[FakeGitHubClient, FakeIssue]:
    """The client and the umbrella a late split's own transaction leaves, its two slices the split's register.

    The oversized issue is the root of its lineage, at depth 0, so its slices
    are born one level below it and may be split again; once split it keeps
    the baseline of what it says, as the adjudication that split it would have
    recorded one. `recovered` kills the
    transaction at the waiting slice's seed, before it lands, and resumes it
    from the record the way the next tick does: the resumed walk seeds that
    slice with no baseline, since only the create's answer proves one.
    """
    transaction = _transaction.LateSplitCase()
    transaction.setUp()
    github, umbrella = transaction.github, transaction.issue
    transaction.generation = _late.late_generation(lineage_depth=0)
    github.seed_state(umbrella.number, **_late.generation_state(transaction.generation))
    if recovered:
        dies = patch.object(github, "write_pinned_state", DiesAtSeed(github, umbrella.number))
        with dies, contextlib.suppress(KeyboardInterrupt):
            transaction._transact()
        transaction._resume()
    else:
        transaction._transact()
    github.seed_state(umbrella.number, **{
        **github.pinned_data(umbrella.number), _ready.KEY_BASELINE: _baseline.reading(umbrella),
    })
    return github, umbrella


class DeferralCase(_PatchedWorkflowMixin):
    """Families split for real, polled and released as a tick dispatches them."""

    def setUp(self) -> None:
        self.enterContext(patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_ready.TRUSTED,)))
        self.enterContext(patch.object(config, "DECOMPOSE", True))
        # This host's copy of the snapshot a late slice is pointed at, which the
        # dispatcher's reuse guard reads locally before the child runs.
        self.enterContext(patch.object(_snapshot_mirrors, "local_snapshot_present", return_value=True))

    def split(self, parent: str, *, recovered: bool = False, manifest: str = _split.DEPENDENT_MANIFEST) -> Family:
        """The family the split `parent` names makes, its first slice running.

        A late split runs its own transaction (`late_split_family`); either
        parent is split by its decomposer answering `manifest`. `recovered`
        kills the split at the waiting child's seed, before it lands, and
        finishes it with the recovery a later tick runs: the child is seeded
        with no baseline, since nothing proves what it was created saying.
        """
        if parent == LATE_SPLIT:
            github, umbrella = late_split_family(recovered=recovered)
        else:
            github, umbrella = self.decomposed(parent, recovered=recovered, manifest=manifest)
        children = github.created_child_issues
        github.set_workflow_label(children[0], WorkflowLabel.IMPLEMENTING, guarded=False)
        family = Family(github, umbrella, children[0], children[1])
        self.assertEqual(github.workflow_label(family.waiting), WorkflowLabel.BLOCKED)
        self.assertEqual(family.baseline() is None, recovered)
        return family

    def decomposed(self, parent: str, *, recovered: bool, manifest: str) -> tuple[FakeGitHubClient, FakeIssue]:
        """The client and the umbrella `parent`'s decomposer leaves, answering `manifest`; see `split`."""
        github, umbrella = _split.late_parent(PARENTS[parent])
        if recovered:
            dies = patch.object(github, "write_pinned_state", DiesAtSeed(github, umbrella.number))
            with dies, self.assertRaises(KeyboardInterrupt):
                _split.redecompose(github, umbrella, manifest)
            _split.redecompose(github, umbrella)[_ready.RUN_AGENT].assert_not_called()
        else:
            _split.redecompose(github, umbrella, manifest)
        return github, umbrella

    def poll(self, family: Family, *issues: FakeIssue) -> int:
        """One due dependency poll over `issues` -- the umbrella and the waiting child unless named; the agents run."""
        polled = issues or (family.umbrella, family.waiting)
        with patch.object(_content_hash, "_compute_user_content_hash", HashSpy(family.hashed)):
            mocks = self._run(
                lambda: [_issue_processing._process_issue(family.github, _TEST_SPEC, issue) for issue in polled],
                run_agent=_agent(),
            )
        return mocks[_ready.RUN_AGENT].call_count

    def waits_through(self, family: Family, landings: tuple) -> None:
        """Poll the family `POLLS` times, each landing on the waiting child ahead of its poll; assert nothing moved.

        No drift check hashes the child, the umbrella's manifest and graph and
        the child's baseline stand as the split left them, and nothing is
        relabelled, told, created, or run.
        """
        before = family.standing()
        for due in range(POLLS):
            if due < len(landings):
                landings[due](family.github, family.waiting)
            self.assertEqual(self.poll(family), 0, "no agent runs")
        self.assertFalse(family.waiting_hashed(), "the waiting child is never hashed")
        self.assertEqual(family.standing(), before)

    def released(self, family: Family, *answers) -> tuple:
        """Finish the first slice, poll the umbrella, and dispatch the waiting child once per answer.

        Answers the labels the child wore from its release on, and the agents
        each of its ticks ran.
        """
        family.finish_first()
        self.poll(family, family.umbrella)
        ran = [self.dispatched(family, answer) for answer in answers]
        return family.relabels(family.waiting.number), ran

    def dispatched(self, family: Family, answer) -> int:
        """One tick of the waiting child, its agent answering `answer`; the agents it ran."""
        mocks = self._run(
            lambda: _issue_processing._process_issue(family.github, _TEST_SPEC, family.waiting),
            **answer,
        )
        return mocks[_ready.RUN_AGENT].call_count
