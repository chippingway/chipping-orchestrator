# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The proof that a settled report's approved commit was squashed into the head a recorded rewrite replaced.

Every case starts from the journey that leaves the gap: a report settled about
the approved commit, the approval's squash carrying its evidence onto a commit
with the same tree, and a base rebase of that squash recording its report
debt. The squash's carry is the provenance, wherever the evidence records
still keep it, and the proof asks nothing about whether that evidence is
current. Equal trees, the squash's own recovery fields, a report, debt, or
carry that disagrees on any member, and a squash read as another tree prove
nothing; a tree nobody could read holds. Reading the proof writes nothing, so
the settled report keeps the commit it was written about.
"""
from __future__ import annotations

import copy
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_records as _report_records,
    report_rewrite_debt as _rewrite_debt,
    report_settlement_state as _settlement,
    report_squash_lineage as _lineage,
    verification_record_state as _evidence_record_state,
    verification_records as _evidence_records,
    verification_settlement_state as _evidence_settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidenceVerdict
from tests.workflow.engine import (
    verification_record_test_support as _record_support,
    verification_world_fixture as _world,
)
from tests.workflow.fixtures import _TEST_SPEC, SHA_LENGTH
from tests.workflow.git_owners import seam_patch

PR = _record_support.PR_NUMBER

BRANCH = _record_support.BRANCH

# The commit the settled report is about and the reviewer approved, the squash
# of it onto the same tree, and the base rebase of that squash.
APPROVED = _record_support.TESTED_SHA

SQUASHED = _world.SQUASHED_SHA

REBASED = _world.REBASED_SHA

# A second base advance over the rebase, and a commit earlier than the approved one.
ADVANCED = "e" * SHA_LENGTH

EARLIER = "1" * SHA_LENGTH

# A digest no record in these cases carries.
OTHER_DIGEST = "0" * len(_record_support.REQUIREMENTS)

SETTLED = _report_records.CurrentReport(
    subject=_report_records.ReportSubject(
        repo_slug=_record_support.SLUG,
        pr_number=PR,
        branch=BRANCH,
        source_sha=APPROVED,
        requirements_revision=_record_support.REQUIREMENTS,
    ),
    report_revision=_record_support.SUBJECT.report.report_revision,
    content_revision=_record_support.SUBJECT.report.content_revision,
    location=_record_support.SUBJECT.report.location,
    mode=_report_records.ReportMode.PUBLISH,
)

# The squash's carry: the run on the approved commit, for the approved review,
# answering for the squash.
CARRY = _record_support.binding().retargeted(SQUASHED)

DEBT = _rewrite_debt.RewriteDebt(
    pr_number=PR, branch=BRANCH, previous_head=SQUASHED, rewritten_head=REBASED,
)

_PROVED = ReportEvidenceVerdict.PROVED

_DEFER = ReportEvidenceVerdict.DEFER

_HOLD = ReportEvidenceVerdict.HOLD


def _settles(state: PinnedState, pending: _evidence_records.PendingEvidence) -> None:
    """Settle `pending` on `state`, as the reconciliation does once its artifact is posted."""
    state.data = _evidence_settlement.settled_state(
        state, pending, _record_support.ARTIFACT_COMMENT, _record_support.SETTLED_UNDER,
    ).data


def _invalidates(state: PinnedState, pending: _evidence_records.PendingEvidence) -> None:
    """Settle `pending` on `state`, then retire it into history as evidence the world moved past."""
    _settles(state, pending)
    _evidence_settlement.retire_current_evidence(state)


# Where the evidence records keep the carry: still owed, current, and in
# history -- invalidated once current, or abandoned before it settled.
_KEPT = (
    ("owed", lambda state, pending: None),
    ("current", _settles),
    ("invalidated", _invalidates),
    ("abandoned", _evidence_settlement.retire_pending_evidence),
)


def _journey(
    keeps=_settles,
    carry: _evidence_records.EvidenceBinding = CARRY,
    settled: _report_records.CurrentReport = SETTLED,
) -> PinnedState:
    """`settled`, `carry` recorded and kept by `keeps`, and the squash rebased."""
    state = PinnedState(comment_id=1, state_data={"pr_number": PR})
    _settlement.record_current_report(state, settled)
    pending = _evidence_record_state.mint_pending_evidence(
        state, _record_support.ISSUE_NUMBER, carry, (_record_support.ran(),),
    )
    if not _evidence_record_state.record_pending_evidence(state, pending):
        raise AssertionError("the carry was refused")
    keeps(state, pending)
    if not _rewrite_debt.records_rewrite(state, DEBT):
        raise AssertionError("the rebase's debt was refused")
    return state


class _LineageCase:
    """A checkout on this host whose commits read as `self.world` says."""

    def setUp(self) -> None:
        checkout = tempfile.TemporaryDirectory()
        self.addCleanup(checkout.cleanup)
        self.checkout = Path(checkout.name)
        self.world = _world.EvidenceWorld(path=self.checkout)

    def verdict(self, state: PinnedState, head: str = REBASED) -> ReportEvidenceVerdict:
        """What the proof answers for `state` with the pull request standing on `head`."""
        with (
            seam_patch("_worktree_path", lambda *_args: self.world.path),
            seam_patch("_commit_present", self.world.commit_present),
            seam_patch("_tree_sha", self.world.tree_sha),
        ):
            return _lineage.lineage_verdict(_TEST_SPEC, _record_support.ISSUE_NUMBER, state, head).verdict


class LineageProvedTest(_LineageCase, unittest.TestCase):
    """The squash's carry, kept anywhere, proves the settled report's lineage and changes nothing."""

    def test_a_carry_kept_anywhere_proves_it(self) -> None:
        for kept, keeps in _KEPT:
            with self.subTest(kept=kept):
                state = _journey(keeps)
                before = copy.deepcopy(state.data)

                self.assertEqual(self.verdict(state), _PROVED)

                self.assertEqual(state.data, before, "reading the proof wrote nothing")
                self.assertEqual(_settlement.read_current_report(state).subject.source_sha, APPROVED)

    def test_a_retargeted_debt_keeps_the_proof(self) -> None:
        state = _journey()

        self.assertTrue(_rewrite_debt.records_rewrite(state, replace(
            DEBT, previous_head=REBASED, rewritten_head=ADVANCED,
        )))

        self.assertEqual(
            _rewrite_debt.read_rewrite_debt(state),
            replace(DEBT, rewritten_head=ADVANCED),
            "the second advance keeps the squash as the head the rewrites replaced",
        )
        self.assertEqual(self.verdict(state, head=ADVANCED), _PROVED)


# Every reading of the pinned records that proves nothing, and how to make it:
# each answers False only where an owner refused to record it.
_DISAGREEING_RECORDS = (
    ("an earlier report", lambda state: _settlement.record_current_report(state, replace(
        SETTLED, subject=replace(SETTLED.subject, source_sha=EARLIER),
    ))),
    ("a later revision of the report", lambda state: _settlement.record_current_report(state, replace(
        SETTLED, report_revision=SETTLED.report_revision + 1, content_revision=OTHER_DIGEST,
    ))),
    ("the approved revision edited", lambda state: _settlement.record_current_report(state, replace(
        SETTLED, content_revision=OTHER_DIGEST,
    ))),
    ("other requirements", lambda state: _settlement.record_current_report(state, replace(
        SETTLED, subject=replace(SETTLED.subject, requirements_revision=OTHER_DIGEST),
    ))),
    ("a report on another pull request", lambda state: _settlement.record_current_report(state, replace(
        SETTLED,
        subject=replace(SETTLED.subject, pr_number=PR + 1),
        location=replace(SETTLED.location, pr_number=PR + 1),
    ))),
    ("a report on another branch", lambda state: _settlement.record_current_report(state, replace(
        SETTLED, subject=replace(SETTLED.subject, branch=f"{BRANCH}-2"),
    ))),
    ("no settled report", lambda state: state.data.pop(_report_records.CURRENT_REPORT)),
    ("a damaged settled report", lambda state: state.set(_report_records.CURRENT_REPORT, {"pr": PR})),
    ("a repointed pull request", lambda state: state.set("pr_number", PR + 1)),
    ("a debt on another pull request", lambda state: state.set(
        _rewrite_debt.REWRITE_DEBT, replace(DEBT, pr_number=PR + 1).recorded(),
    )),
    ("a debt on another branch", lambda state: state.set(
        _rewrite_debt.REWRITE_DEBT, replace(DEBT, branch=f"{BRANCH}-2").recorded(),
    )),
    ("a debt replacing another head", lambda state: state.set(
        _rewrite_debt.REWRITE_DEBT, replace(DEBT, previous_head=EARLIER).recorded(),
    )),
    ("a paid debt", lambda state: state.set(_rewrite_debt.REWRITE_DEBT, None)),
    ("a damaged debt", lambda state: state.set(_rewrite_debt.REWRITE_DEBT, {"pr": PR})),
    ("equal trees and the squash's recovery fields alone", lambda state: state.data.update({
        _evidence_records.CURRENT_EVIDENCE: None, "late_collapse_handoff_sha": SQUASHED,
    })),
    ("a damaged carry", lambda state: state.set(_evidence_records.CURRENT_EVIDENCE, {
        **state.get(_evidence_records.CURRENT_EVIDENCE), "tested": APPROVED[:-1],
    })),
)

# Every carry of the approved run that is not this squash of this report.
_DISAGREEING_CARRIES = (
    ("onto another head", _record_support.binding().retargeted(EARLIER)),
    ("in another repository", replace(CARRY, target=replace(
        CARRY.target, publication=replace(CARRY.target.publication, repo_slug="someone/else"),
    ))),
    ("on another pull request", replace(CARRY, target=_evidence_records.EvidenceTarget(
        publication=replace(CARRY.target.publication, pr_number=PR + 1),
        subject={**CARRY.target.subject, "pr": PR + 1},
    ))),
    ("on another branch", replace(CARRY, target=replace(
        CARRY.target, publication=replace(CARRY.target.publication, branch=f"{BRANCH}-2"),
    ))),
    ("under other requirements", replace(CARRY, target=_evidence_records.EvidenceTarget(
        publication=replace(CARRY.target.publication, requirements_revision=OTHER_DIGEST),
        subject={**CARRY.target.subject, "requirements": OTHER_DIGEST},
    ))),
    ("for a review of the squash", replace(CARRY, target=replace(
        CARRY.target, subject={**CARRY.target.subject, "sha": SQUASHED},
    ))),
)


class LineageRefusedTest(_LineageCase, unittest.TestCase):
    """Anything short of the squash's carry of this very report onto the replaced head proves nothing."""

    def test_disagreeing_records_prove_nothing(self) -> None:
        for named, breaks in _DISAGREEING_RECORDS:
            with self.subTest(named):
                state = _journey()

                self.assertIsNot(breaks(state), False, "the change was recorded")
                self.assertEqual(self.verdict(state), _DEFER)

    def test_disagreeing_carries_prove_nothing(self) -> None:
        for named, carry in _DISAGREEING_CARRIES:
            with self.subTest(named):
                self.assertEqual(self.verdict(_journey(carry=carry)), _DEFER)

    def test_a_head_the_debt_did_not_publish(self) -> None:
        self.assertEqual(self.verdict(_journey(), head=ADVANCED), _DEFER)

    def test_a_run_on_the_replaced_head_is_no_squash(self) -> None:
        state = _journey(
            carry=_record_support.binding(
                target=replace(CARRY.target, subject={**CARRY.target.subject, "sha": SQUASHED}),
                tested_sha=SQUASHED,
            ),
            settled=replace(SETTLED, subject=replace(SETTLED.subject, source_sha=SQUASHED)),
        )

        self.assertEqual(self.verdict(state), _DEFER)

    def test_a_damaged_history_proves_nothing(self) -> None:
        state = _journey(_invalidates)
        state.set(_evidence_records.EVIDENCE_HISTORY, [*state.get(_evidence_records.EVIDENCE_HISTORY), {}])

        self.assertEqual(self.verdict(state), _DEFER)


# What the checkout reads in place of the squash's trees, and what the proof answers.
_WORLDS = (
    ("a squash of another tree", lambda world: world.trees.update({SQUASHED: _world.REBASED_TREE}), _DEFER),
    ("both of another tree than the carry's", lambda world: world.trees.update({
        APPROVED: _world.REBASED_TREE, SQUASHED: _world.REBASED_TREE,
    }), _DEFER),
    ("no checkout on this host", lambda world: setattr(world, "path", world.path / "gone"), _HOLD),
    ("an approved commit nobody can read", lambda world: world.trees.pop(APPROVED), _HOLD),
    ("a squash nobody can read", lambda world: world.trees.pop(SQUASHED), _HOLD),
)


class LineageTreesTest(_LineageCase, unittest.TestCase):
    """A squash read as another tree proves nothing, and one nobody could read holds."""

    def test_trees_read_otherwise(self) -> None:
        for named, moves, expected in _WORLDS:
            with self.subTest(named):
                self.world = _world.EvidenceWorld(path=self.checkout)
                moves(self.world)

                self.assertEqual(self.verdict(_journey()), expected)
