# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a base-rewrite candidate refuses on, and what its landing says."""

from __future__ import annotations

import dataclasses
import typing
import unittest
from enum import StrEnum
from functools import partial
from types import MappingProxyType, NoneType

from orchestrator.git.base_sync.rewrite_handoffs import (
    _CheckoutReading,
    _LandedRewrite,
    _PushOutcome,
    _RewriteAttempt,
    _RewriteCandidate,
    _RewriteRefusal,
)
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.ref_transport import _RefRead
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.state import WorkflowLabel

_SHA_LENGTH = 40

ANCHOR = "a" * _SHA_LENGTH

REPLAY = "b" * _SHA_LENGTH

FOREIGN = "c" * _SHA_LENGTH

BRANCH = "orchestrator/acme__widget/issue-7"

PR_NUMBER = 42

_DIRTY = _WorktreeStatus(readable=True, paths=("loose.py",))

# Every reading a clean rebase hands over, by the name a case overrides it as.
_COMPLETE = MappingProxyType({
    "anchor": ANCHOR,
    "head": REPLAY,
    "original_tree": "1" * _SHA_LENGTH,
    "tree": "2" * _SHA_LENGTH,
    "status": _WorktreeStatus(readable=True),
    "base": _BranchDivergence(tip="d" * _SHA_LENGTH, ahead=1, readable=True),
    "remote": _RefRead(sha=ANCHOR),
})

# What the remote was last read at, and whether that shows the candidate landed.
_LANDINGS = (
    (_RefRead(sha=REPLAY), True),
    (_RefRead(sha=ANCHOR), False),
    (_RefRead(sha=""), False),
    (_RefRead(detail="fatal: unreachable"), False),
)

# What a handoff may be built from at all: text, counts, flags, and the closed
# vocabularies -- never a client, an issue, a pinned comment, or a callable.
_DATA_LEAVES = (str, int, bool, NoneType, Ellipsis)


def _candidate(**overrides: object) -> _RewriteCandidate:
    """A candidate a clean rebase would hand over, with `overrides` applied."""
    readings = {**_COMPLETE, **overrides}
    return _RewriteCandidate(
        attempt=_RewriteAttempt(
            anchor=readings["anchor"],
            pr_number=PR_NUMBER,
            stage=WorkflowLabel.VALIDATING,
        ),
        branch=BRANCH,
        original_tree=readings["original_tree"],
        checkout=_CheckoutReading(
            head=readings["head"],
            tree=readings["tree"],
            status=readings["status"],
            base=readings["base"],
        ),
        remote=readings["remote"],
    )


# One defect per case, and the refusal the candidate answers with; a candidate
# with none refuses nothing. The last two hold the order: a rebase that moved
# nothing is answered before its tree, and a dirty tree before a remote the
# lease would reject.
_REFUSALS = (
    (partial(_candidate), None),
    (partial(_candidate, anchor=""), _RewriteRefusal.UNREADABLE_HEAD),
    (partial(_candidate, head=""), _RewriteRefusal.UNREADABLE_HEAD),
    (partial(_candidate, head=ANCHOR), _RewriteRefusal.UNMOVED),
    (partial(_candidate, original_tree=""), _RewriteRefusal.UNREADABLE_TREE),
    (partial(_candidate, tree=""), _RewriteRefusal.UNREADABLE_TREE),
    (
        partial(_candidate, status=_WorktreeStatus(readable=False, paths=("hidden.py",))),
        _RewriteRefusal.UNREADABLE_TREE,
    ),
    (partial(_candidate, status=_DIRTY), _RewriteRefusal.DIRTY_TREE),
    (partial(_candidate, base=_BranchDivergence()), _RewriteRefusal.UNREADABLE_BASE),
    (
        partial(_candidate, remote=_RefRead(detail="fatal: unreachable")),
        _RewriteRefusal.UNREADABLE_REMOTE,
    ),
    (partial(_candidate, remote=_RefRead(sha=REPLAY)), _RewriteRefusal.PUBLISHED),
    (partial(_candidate, remote=_RefRead(sha=FOREIGN)), _RewriteRefusal.MOVED_REMOTE),
    (partial(_candidate, remote=_RefRead(sha="")), _RewriteRefusal.MOVED_REMOTE),
    (partial(_candidate, head=ANCHOR, status=_DIRTY), _RewriteRefusal.UNMOVED),
    (
        partial(_candidate, status=_DIRTY, remote=_RefRead(sha=FOREIGN)),
        _RewriteRefusal.DIRTY_TREE,
    ),
)


def _leaves(hint: object) -> tuple[object, ...]:
    """Every type a record's fields bottom out in, nested records opened up."""
    if dataclasses.is_dataclass(hint):
        nested = tuple(typing.get_type_hints(hint).values())
    else:
        nested = typing.get_args(hint)
    if not nested:
        return (hint,)
    return tuple(leaf for inner in nested for leaf in _leaves(inner))


class CandidateRefusalTest(unittest.TestCase):
    """A candidate refuses on the first reading that cannot stand behind a push."""

    def test_each_defect_names_its_refusal(self) -> None:
        for built, refusal in _REFUSALS:
            with self.subTest(defect=built.keywords):
                self.assertEqual(built().refusal, refusal)


class LandedRewriteTest(unittest.TestCase):
    """Only a reading of the remote on the candidate says it landed."""

    def test_landing_is_the_remote_on_the_candidate(self) -> None:
        for remote, landed in _LANDINGS:
            with self.subTest(remote=remote):
                landing = _LandedRewrite(
                    candidate=_candidate(),
                    outcome=_PushOutcome.UNCERTAIN,
                    remote=remote,
                )
                self.assertIs(landing.landed, landed)

    def test_an_unnamed_candidate_never_lands(self) -> None:
        # A head nobody could read is not "on" a branch the remote does not
        # carry, though both read as the empty string.
        landing = _LandedRewrite(
            candidate=_candidate(head=""),
            outcome=_PushOutcome.REFUSED,
            remote=_RefRead(sha=""),
            refusal=_RewriteRefusal.UNREADABLE_HEAD,
        )

        self.assertFalse(landing.landed)


class HandoffShapeTest(unittest.TestCase):
    """The handoffs are frozen data, with nothing in them to call back into."""

    def test_every_field_is_plain_data(self) -> None:
        for leaf in _leaves(_LandedRewrite):
            with self.subTest(leaf=leaf):
                is_vocabulary = isinstance(leaf, type) and issubclass(leaf, StrEnum)
                self.assertTrue(is_vocabulary or leaf in _DATA_LEAVES)

    def test_every_record_is_frozen(self) -> None:
        records = (
            _RewriteAttempt, _CheckoutReading, _RewriteCandidate,
            _LandedRewrite, _RefRead, _BranchDivergence, _WorktreeStatus,
        )
        for record in records:
            with self.subTest(record=record.__name__):
                self.assertTrue(record.__dataclass_params__.frozen)


if __name__ == "__main__":
    unittest.main()
