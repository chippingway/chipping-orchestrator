# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import, package-surface, and inventory checks for the worktrees owners."""

from __future__ import annotations

import subprocess
import sys
import unittest
from importlib import import_module
from importlib.util import find_spec

from orchestrator.git import worktrees as _worktrees_package
from tests.git.inventory_test_support import inventory_modules

_CANDIDATES = 'candidates'
_MAINTENANCE_RESULTS = 'maintenance_results'
_INVENTORY_ROOTS = 'inventory_roots'
_LEGACY_INVENTORY = 'legacy_inventory'
_CANDIDATE_LAYOUT = 'candidate_layout'
_REMOTE_INVENTORY = 'remote_inventory'
_ANCHORING = 'anchoring'
_ATTRIBUTION = 'attribution'
_BRANCH_PROBES = 'branch_probes'
_CHECKOUT_ATTRIBUTION = 'checkout_attribution'
_CLAIMS = 'claims'
_CLEANUP = 'cleanup'
_COMMIT_CLAIMS = 'commit_claims'
_CREATION = 'creation'
_DECOMPOSITION = 'decomposition'
_DISCOVERY = 'discovery'
_ELIGIBILITY = 'eligibility'
_EVIDENCE = 'evidence'
_INVENTORY = 'inventory'
_MAINTENANCE = 'maintenance'
_MODELS = 'models'
_NAMING = 'naming'
_PATHS = 'paths'
_PROBES = 'probes'
_RECLAIM = 'reclaim'
_RECOVERY = 'recovery'
_TERMINAL = 'terminal'

_EVIDENCE_READS = "evidence_reads"

_TIP_EVIDENCE = "tip_evidence"

_ACTIVITY_EVIDENCE = "activity_evidence"

_CHECKOUT_LISTING = "checkout_listing"

_RETENTION_TIPS = "retention_tips"

_RETENTION_CHECKOUTS = "retention_checkouts"

_MAINTENANCE_GUARDS = "maintenance_guards"

_CHECKOUT_REMOVAL = "checkout_removal"

_BRANCH_REMOVAL = "branch_removal"

_PACKAGE = "orchestrator"

# The spelling that answers as a logger and nowhere else: nothing resolves at
# it as a module and no inventory in the package may name it as the module a
# hub reads a name off, but it is still the channel the owners report on.
_LIFECYCLE_SPELLING = "orchestrator.worktree_lifecycle"

# The aggregate spelling over every git domain at once, held to the same rule
# minus the logger.
_AGGREGATE_HUB = "orchestrator.worktrees"

_ABSENT_TARGETS = (_AGGREGATE_HUB, _LIFECYCLE_SPELLING)

_MODULES = (
    "orchestrator.git.worktrees.evidence_reads",
    "orchestrator.git.worktrees.tip_evidence",
    "orchestrator.git.worktrees.activity_evidence",
    "orchestrator.git.worktrees.checkout_listing",
    "orchestrator.git.worktrees.retention_tips",
    "orchestrator.git.worktrees.retention_checkouts",
    "orchestrator.git.worktrees.maintenance_guards",
    "orchestrator.git.worktrees.checkout_removal",
    "orchestrator.git.worktrees.branch_removal",

    "orchestrator.git.worktrees.remote_inventory",
    "orchestrator.git.worktrees.candidate_layout",
    "orchestrator.git.worktrees.legacy_inventory",
    "orchestrator.git.worktrees.inventory_roots",
    "orchestrator.git.worktrees.maintenance_results",
    "orchestrator.git.worktrees.candidates",
    "orchestrator.git.worktrees",
    "orchestrator.git.worktrees.anchoring",
    "orchestrator.git.worktrees.attribution",
    "orchestrator.git.worktrees.branch_probes",
    "orchestrator.git.worktrees.checkout_attribution",
    "orchestrator.git.worktrees.claims",
    "orchestrator.git.worktrees.cleanup",
    "orchestrator.git.worktrees.commit_claims",
    "orchestrator.git.worktrees.creation",
    "orchestrator.git.worktrees.decomposition",
    "orchestrator.git.worktrees.discovery",
    "orchestrator.git.worktrees.eligibility",
    "orchestrator.git.worktrees.evidence",
    "orchestrator.git.worktrees.inventory",
    "orchestrator.git.worktrees.maintenance",
    "orchestrator.git.worktrees.models",
    "orchestrator.git.worktrees.naming",
    "orchestrator.git.worktrees.paths",
    "orchestrator.git.worktrees.probes",
    "orchestrator.git.worktrees.reclaim",
    "orchestrator.git.worktrees.recovery",
    "orchestrator.git.worktrees.terminal",
)

# The module paths a second import site for these owners would take: the two
# spellings themselves, and the inventory and resolver hooks either one would
# be built from.
_FLAT_MODULES = (
    "orchestrator._worktree_lifecycle_export_manifest",
    "orchestrator._worktree_lifecycle_exports",
    "orchestrator._worktrees_export_manifest",
    "orchestrator._worktrees_exports",
    _AGGREGATE_HUB,
    _LIFECYCLE_SPELLING,
)

# The initializer binds nothing, so each name answers on the owner that defines
# it, never on the package itself.
_OWNER_ONLY_NAMES = (
    "ArtifactInventory",
    "ArtifactVerdict",
    "IssueArtifacts",
    "MaintenanceResult",
    "RetentionReason",
    "_branch_has_unpushed_commits",
    "_branch_name",
    "_checkout_identity",
    "_classify_artifacts",
    "_cleanup_terminal_branch",
    "_ensure_worktree",
    "_decompose_worktree_path",
    "_local_issue_inventory",
    "_maintained_candidates",
    "_maintenance_candidates",
    "_remove_issue_worktree",
    "_resolve_branch_name",
    "_sanitize_slug",
    "_terminal_retentions",
    "_worktree_path",
)

# Every name the owners define, paired with the owner that defines it: the slug
# pattern and the digest math behind it, the two sanitizers, the branch, root,
# and worktree-path derivations, the pinned / legacy resolver, the `issue-<n>`
# read that runs back the other way, and the two paths one issue can have been
# checked out at, the candidate-branch and commit-count reads behind the
# unpushed-commit probe, the two creators, the new-commit probe, the reported
# fetch and the start point a restore picks, the handoff anchor with the target
# choice, the ref move, and the revision read under it, and the `worktree` argv
# they run, the decomposer's path, creation, and removal, the per-issue removal
# and local branch deletion, the two teardowns composed from them, and the local
# artifact scan: the two records it answers with, the branch listing and the
# checkout reads under it, the flat pre-namespacing checkouts among them, the
# identity read that says which clone one of those is a worktree of, the
# attribution rule a branch name is put to, the two a directory is -- the
# grouping that says which entries derive one checkout directory, the flat path
# that is a root rather than a checkout, and the claim the clone identity
# settles, with the record carrying the owner it found beside the claimants
# nobody may act for and the reporting behind it -- the clone resolution, the
# grouping over it and the shape that grouping takes, the one filing what a
# repository holds apart from what it may not touch, and the per-clone,
# per-repository, and per-issue assembly. Then the classification
# over what that scan found: the three-answer probe vocabulary, the two records
# a verdict is made of and the commit it hands over when it clears one, the
# nine fail-closed reads -- the ignored-path one that answers for what a status
# leaves out among them, the one asking when a tree was last disturbed, over the
# checkout's own git directory and the two files in it a commit rewrites, and
# the one asking which branches a tree of the clone is standing on, counted
# against the clone's own worktree entries because git drops one whose backlink
# is missing without saying so -- and the two runners under them, the issue,
# pinned-state, and open-pull-request reads GitHub answers with and the
# boundaries around each of them, the accounting a terminal pull request gives
# for one commit the base does not carry and the boundary around that too, and
# the composition that turns all of it into one verdict per candidate, with
# every checkout read on its own against the base and the branch tips the whole
# candidate shares, that checkout's three-read order and the record carrying
# what it is measured against, the tables each of those is charged through, the
# tip read that falls back to the remote, the HEAD read spent twice, and the
# proof an eligible verdict is handed over as. Then the pass that spends one of
# those verdicts: the discovery over both halves at once -- the remote listing
# and the namespace pattern it asks for, the attribution and the grouping over
# it, the layout reading and the merge that widens one candidate, and the whole
# scan those produce -- the three commit-pinned teardown steps and the argv
# each runs, and the pass itself: the injected guard's type, the quiet period,
# the reason-to-outcome table, and every gate, step, and answer between them.
# Naming the whole surface makes a helper added to an owner an edit here rather
# than a definition site nothing checks.
_OWNER_DEFINED = (
    ("ActivityGuard", _MAINTENANCE_GUARDS),
    ("ArtifactInventory", _CANDIDATES),
    ("ArtifactVerdict", _MODELS),
    ("AttributedIssues", _ATTRIBUTION),
    ("BranchTip", _MODELS),
    ("CandidateKey", _DISCOVERY),
    ("CandidateLayout", _CANDIDATES),
    ("CheckoutClaim", _CHECKOUT_ATTRIBUTION),
    ("CloneGroups", _INVENTORY_ROOTS),
    ("IssueArtifacts", _CANDIDATES),
    ("IssueBranches", _ATTRIBUTION),
    ("IssueNumbers", _LEGACY_INVENTORY),
    ("LegacyCheckouts", _LEGACY_INVENTORY),
    ("MaintenanceCandidate", _CANDIDATES),
    ("MaintenanceOutcome", _MAINTENANCE_RESULTS),
    ("MaintenanceReason", _MAINTENANCE_RESULTS),
    ("MaintenanceResult", _MAINTENANCE_RESULTS),
    ("MaintenanceScan", _CANDIDATES),
    ("ProbeAnswer", _MODELS),
    ("ProvenTip", _MODELS),
    ("PublishedBranches", _REMOTE_INVENTORY),
    ("Retention", _MODELS),
    ("RetentionReason", _MODELS),
    ("TERMINAL_LABELS", _CLAIMS),
    ("_CLEANLINESS_REASONS", _RETENTION_CHECKOUTS),
    ("_CheckoutReads", _RETENTION_CHECKOUTS),
    ("_GIT_NEGATIVE", _TIP_EVIDENCE),
    ("_HEAD", _TIP_EVIDENCE),
    ("_HEAD_REFLOG", _ACTIVITY_EVIDENCE),
    ("_HIDDEN_REASONS", _RETENTION_CHECKOUTS),
    ("_IDENTITY_REASONS", _RETENTION_CHECKOUTS),
    ("_INDEX", _ACTIVITY_EVIDENCE),
    ("_ISSUE_SEGMENT_RE", _PATHS),
    ("_LISTED", _ATTRIBUTION),
    ("_LISTED", _CHECKOUT_ATTRIBUTION),
    ("_LOCAL_BRANCH_PREFIX", _BRANCH_PROBES),
    ("_LOCAL_REF_PREFIX", _TIP_EVIDENCE),
    ("_LOCAL_REF_PREFIX", _RECLAIM),
    ("_OPEN_PULL_REQUEST", _CLAIMS),
    ("_OPEN_PULL_REQUEST", _COMMIT_CLAIMS),
    ("_ORCHESTRATOR_BRANCH_REFS", _BRANCH_PROBES),
    ("_ORCHESTRATOR_REMOTE_REFS", _REMOTE_INVENTORY),
    ("_OUTCOMES", _MAINTENANCE_RESULTS),
    ("_QUIET_PERIOD_SECONDS", _MAINTENANCE_GUARDS),
    ("_REF_DELETE", _RECLAIM),
    ("_REF_SEPARATOR", _ATTRIBUTION),
    ("_REMOTE_BRANCH_PREFIX", _REMOTE_INVENTORY),
    ("_SAFE_CHAR", _NAMING),
    ("_SLUG_DIGEST_LEN", _NAMING),
    ("_SLUG_SAFE_RE", _NAMING),
    ("_VERIFY_QUIETLY", _TIP_EVIDENCE),
    ("_VERIFY_REF", _CREATION),
    ("_WORKTREE_ADD", _CREATION),
    ("_WORKTREE_ADMIN", _CHECKOUT_LISTING),
    ("_WORKTREE_BRANCH", _CHECKOUT_LISTING),
    ("_WORKTREE_RECORD", _CHECKOUT_LISTING),
    ("_WORKTREE_REMOVE", _RECLAIM),
    ("_WORKTREE_REMOVE_FORCE", _CREATION),
    ("_activity_reason", _MAINTENANCE_GUARDS),
    ("_all_worktrees_accounted", _CHECKOUT_LISTING),
    ("_anchor_pr_worktree", _ANCHORING),
    ("_anchor_target", _ANCHORING),
    ("_answered", _MAINTENANCE_RESULTS),
    ("_artifact_reading", _ELIGIBILITY),
    ("_artifact_verdict", _ELIGIBILITY),
    ("_attributed_issues", _ATTRIBUTION),
    ("_attributed_legacy", _LEGACY_INVENTORY),
    ("_base_anchor", _ANCHORING),
    ("_base_contains", _TIP_EVIDENCE),
    ("_branch_attribution", _ATTRIBUTION),
    ("_branch_commit_count", _RECOVERY),
    ("_branch_has_unpushed_commits", _RECOVERY),
    ("_branch_name", _NAMING),
    ("_branch_reasons", _RETENTION_TIPS),
    ("_branch_retentions", _RETENTION_TIPS),
    ("_branch_tip", _RETENTION_TIPS),
    ("_candidate_issue_branches", _RECOVERY),
    ("_candidate_keys", _DISCOVERY),
    ("_candidate_layout", _CANDIDATE_LAYOUT),
    ("_candidate_order", _DISCOVERY),
    ("_carrying_pull_request", _COMMIT_CLAIMS),
    ("_checked_out_branches", _CHECKOUT_LISTING),
    ("_checkout_clone", _PROBES),
    ("_checkout_entries", _PROBES),
    ("_checkout_git_dir", _ACTIVITY_EVIDENCE),
    ("_checkout_head", _RETENTION_CHECKOUTS),
    ("_checkout_identity", _EVIDENCE),
    ("_checkout_numbers", _PROBES),
    ("_checkout_reading", _RETENTION_CHECKOUTS),
    ("_checkout_reason", _RETENTION_CHECKOUTS),
    ("_checkout_retentions", _RETENTION_CHECKOUTS),
    ("_checkout_stop", _CHECKOUT_REMOVAL),
    ("_checkout_tip", _TIP_EVIDENCE),
    ("_checkout_tip_retentions", _RETENTION_CHECKOUTS),
    ("_claim_reason", _MAINTENANCE_GUARDS),
    ("_classified_candidates", _ELIGIBILITY),
    ("_classify_artifacts", _ELIGIBILITY),
    ("_clean_worktree", _EVIDENCE),
    ("_cleanup_decompose_worktree", _DECOMPOSITION),
    ("_cleanup_question_worktree", _TERMINAL),
    ("_cleanup_terminal_branch", _TERMINAL),
    ("_cleared_tips", _MAINTENANCE),
    ("_clone_read", _EVIDENCE_READS),
    ("_colliding_worktree_slugs", _CHECKOUT_ATTRIBUTION),
    ("_commit_accounting", _COMMIT_CLAIMS),
    ("_commit_count_from_stdout", _RECOVERY),
    ("_countable_legacy_checkouts", _CHECKOUT_ATTRIBUTION),
    ("_current_names", _CANDIDATE_LAYOUT),
    ("_decompose_worktree_path", _DECOMPOSITION),
    ("_delete_local_issue_branch", _CLEANUP),
    ("_delete_local_ref_at", _RECLAIM),
    ("_delete_remote_branch_at", _RECLAIM),
    ("_ended_retentions", _CLAIMS),
    ("_ensure_decompose_worktree", _DECOMPOSITION),
    ("_ensure_pr_worktree", _CREATION),
    ("_ensure_worktree", _CREATION),
    ("_fetch_for_restore", _ANCHORING),
    ("_fetched_issue", _CLAIMS),
    ("_file_claim", _LEGACY_INVENTORY),
    ("_group_published", _REMOTE_INVENTORY),
    ("_hardened_read", _EVIDENCE_READS),
    ("_has_new_commits", _CREATION),
    ("_head_is_own_branch", _EVIDENCE),
    ("_head_ref", _EVIDENCE),
    ("_held_checkouts", _INVENTORY),
    ("_issue_artifacts", _INVENTORY),
    ("_issue_branch_names", _NAMING),
    ("_issue_checkout_number", _PROBES),
    ("_issue_segment_number", _PATHS),
    ("_issue_worktree_paths", _PATHS),
    ("_kept_subject", _MAINTENANCE),
    ("_keyed_candidate", _DISCOVERY),
    ("_last_touched", _ACTIVITY_EVIDENCE),
    ("_legacy_checkout_claim", _CHECKOUT_ATTRIBUTION),
    ("_legacy_checkout_numbers", _PROBES),
    ("_legacy_claim", _LEGACY_INVENTORY),
    ("_legacy_branch_name", _NAMING),
    ("_legacy_names", _CANDIDATE_LAYOUT),
    ("_legacy_worktree_path", _PATHS),
    ("_local_branch_tip", _TIP_EVIDENCE),
    ("_local_issue_inventory", _INVENTORY),
    ("_local_orchestrator_branches", _BRANCH_PROBES),
    ("_maintained_candidate", _MAINTENANCE),
    ("_maintained_candidates", _MAINTENANCE),
    ("_maintenance_candidates", _DISCOVERY),
    ("_matching_owners", _ATTRIBUTION),
    ("_merged", _INVENTORY),
    ("_move_branch_onto", _ANCHORING),
    ("_nothing_ignored", _EVIDENCE),
    ("_open_pull_request_retentions", _CLAIMS),
    ("_pr_branch_start_point", _CREATION),
    ("_proven_tips", _ELIGIBILITY),
    ("_published_branches", _REMOTE_INVENTORY),
    ("_published_tip", _TIP_EVIDENCE),
    ("_quiet_checkout", _ACTIVITY_EVIDENCE),
    ("_read_artifacts", _ELIGIBILITY),
    ("_read_orchestrator_refs", _BRANCH_PROBES),
    ("_read_state", _CLAIMS),
    ("_reclaimed", _MAINTENANCE),
    ("_record_attribution", _ATTRIBUTION),
    ("_recorded_pull_request", _CLAIMS),
    ("_registered_worktrees", _CHECKOUT_LISTING),
    ("_remote_half", _REMOTE_INVENTORY),
    ("_remote_issue_branches", _REMOTE_INVENTORY),
    ("_remote_orchestrator_branches", _REMOTE_INVENTORY),
    ("_remove_issue_worktree", _CLEANUP),
    ("_remove_recognized_worktree", _RECLAIM),
    ("_repo_worktrees_root", _PATHS),
    ("_report_unsettled", _CHECKOUT_ATTRIBUTION),
    ("_resolve_branch_name", _NAMING),
    ("_resolved_commit", _ANCHORING),
    ("_resolved_root", _INVENTORY_ROOTS),
    ("_resolved_tip", _TIP_EVIDENCE),
    ("_root_inventory", _INVENTORY),
    ("_run_decompose_worktree_removal", _DECOMPOSITION),
    ("_run_issue_worktree_removal", _CLEANUP),
    ("_run_local_branch_deletion", _CLEANUP),
    ("_sanitize_branch_segment", _NAMING),
    ("_sanitize_slug", _NAMING),
    ("_scanned", _INVENTORY),
    ("_shared_repository", _EVIDENCE),
    ("_slug_digest", _NAMING),
    ("_slugs_by_worktrees_root", _CHECKOUT_ATTRIBUTION),
    ("_spec_inventory", _INVENTORY),
    ("_specs_by_clone", _INVENTORY_ROOTS),
    ("_still_there", _RECLAIM),
    ("_take_branch", _BRANCH_REMOVAL),
    ("_take_branches", _BRANCH_REMOVAL),
    ("_take_checkout", _CHECKOUT_REMOVAL),
    ("_take_checkouts", _CHECKOUT_REMOVAL),
    ("_take_local_branch", _BRANCH_REMOVAL),
    ("_take_remote_branch", _BRANCH_REMOVAL),
    ("_terminal_retentions", _CLAIMS),
    ("_tip_retentions", _RETENTION_TIPS),
    ("_unanchorable_branch_reading", _ANCHORING),
    ("_widened", _DISCOVERY),
    ("_workflow_members", _CLAIMS),
    ("_worktree_issue_numbers", _PROBES),
    ("_worktree_path", _PATHS),
)

# The owners that report, each binding the channel an operator's level and
# handler selection is keyed on.
_REPORTING_OWNERS = (
    _EVIDENCE_READS,
    _TIP_EVIDENCE,
    _ACTIVITY_EVIDENCE,
    _CHECKOUT_LISTING,
    _MAINTENANCE_GUARDS,

    _ANCHORING,
    _ATTRIBUTION, _BRANCH_PROBES, _CHECKOUT_ATTRIBUTION, _CLAIMS, _CLEANUP,
    _COMMIT_CLAIMS, _CREATION, _DECOMPOSITION, _EVIDENCE,
    _MAINTENANCE, _PROBES, _RECLAIM, _TERMINAL,
    _INVENTORY_ROOTS, _REMOTE_INVENTORY,
)


class CleanProcessImportTest(unittest.TestCase):
    """Each owner imports standalone in a fresh interpreter.

    Every owner depends only on config, pinned state, the git command /
    lock / branch-transport owners, and its in-package siblings, so importing
    any one of them first must not need a name a half-run module has not
    defined yet. A subprocess per module gives each a clean `sys.modules` no
    other test has already populated, exposing an import-order cycle a
    package-first suite run would mask.
    """

    def test_each_module_imports_standalone(self) -> None:
        for module in _MODULES:
            with self.subTest(module=module):
                completed = subprocess.run(
                    [sys.executable, "-c", f"import {module}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, msg=completed.stderr)


class PackageSurfaceTest(unittest.TestCase):
    """The initializer binds nothing and every name answers on its owner."""

    def test_initializer_exposes_no_owner_names(self) -> None:
        for owner_only_name in _OWNER_ONLY_NAMES:
            with self.subTest(name=owner_only_name), self.assertRaises(AttributeError):
                getattr(_worktrees_package, owner_only_name)

    def test_every_name_is_defined_on_its_owner(self) -> None:
        # A helper lifted onto a sibling would still resolve for its callers,
        # so the defining module is what a patch aimed at the teardown ordering
        # or the digest math behind a slug has to land on.
        for owner_name, module in _OWNER_DEFINED:
            owner = import_module(f"orchestrator.git.worktrees.{module}")
            with self.subTest(name=owner_name):
                self.assertIn(owner_name, owner.__dict__)


class OwnerImportSiteTest(unittest.TestCase):
    """No surface over these owners sits beside them."""

    def test_no_flat_module_exists(self) -> None:
        # Anything importable at these paths would be a second identity for the
        # branch and path derivations every worktree is created and torn down
        # by -- free to drift from the owner silently and invisible to a patch
        # aimed at it. Resolving the spec rather than stat-ing one path catches
        # a copy planted anywhere the interpreter would find it.
        for module in _FLAT_MODULES:
            with self.subTest(module=module):
                self.assertIsNone(find_spec(module))

    def test_no_inventory_targets_an_absent_spelling(self) -> None:
        # Nothing resolves at either spelling, so an inventory naming one is a
        # dead target that stays quiet until whichever caller reads that name
        # runs. Scanning every inventory in the package is what surfaces it
        # before then.
        for inventory_name in inventory_modules(_PACKAGE):
            inventory = import_module(inventory_name)
            targets = {target.module_name for target in inventory.EXPORTS}
            for absent in _ABSENT_TARGETS:
                with self.subTest(inventory=inventory_name, target=absent):
                    self.assertNotIn(absent, targets)


class ReportingChannelTest(unittest.TestCase):
    """Every owner that logs reports on the operator-facing channel.

    Operators filter on the rendered prefix and attach handlers to it, so a
    logger renamed after its own module path would silently drop that
    owner's worktree and branch teardown lines out of their filters.
    """

    def test_owners_keep_the_operator_name(self) -> None:
        for module in _REPORTING_OWNERS:
            owner = import_module(f"orchestrator.git.worktrees.{module}")
            with self.subTest(owner=owner.__name__):
                self.assertEqual(owner.log.name, _LIFECYCLE_SPELLING)


if __name__ == "__main__":
    unittest.main()
