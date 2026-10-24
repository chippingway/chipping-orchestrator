# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Worktree naming, creation, recovery, cleanup, inventory, and terminal owners.

Slug sanitization, branch and path derivation, the pinned / legacy branch
resolver, and the `issue-<n>` read that runs back the other way live in
``paths``; candidate-branch discovery and the unpushed-commit probes live in
``recovery``; the issue / PR worktree creators and the new-commit probe they
gate on live in ``creation``; the decomposer's scratch checkout lifecycle lives
in ``decomposition``; per-issue worktree removal and local branch deletion live
in ``cleanup``, and the question / PR-terminal teardowns that compose them live
in ``terminal``. The read-only scan that derives issue candidates from the
artifacts a host already holds lives in ``inventory``, over the branch listing
in ``branch_probes``, the checkout reads and the clone-identity read under them
in ``probes``, the branch-to-repository rules in ``attribution`` and the
checkout-to-repository ones in ``checkout_attribution``, and the answer they
fill in ``models``. The classification that decides which of those candidates
may be reclaimed lives in ``eligibility``, over the fail-closed local reads in
``evidence``, the issue, admitted pinned-state, and open-pull-request reads
in ``claims``, and the terminal pull request that accounts for one commit in
``commit_claims``. The maintenance pass that spends one of those
classifications lives in ``maintenance``, under the issue writer claim
``maintenance_guards`` takes, over the widening of that scan with what the
remote still carries in ``discovery`` and the three commit-pinned teardown
steps in ``reclaim``. Every worktree name is defined on one of these
owners, and callers import the owner they need directly, so this initializer
binds nothing and importing one owner never drags the others in.

No facade of this domain's own sits beside the package, and nothing above it
republishes these names either, so each answers on the owner that defines it
and a test intercepting one targets that owner: the stage handlers name it
just as the ``git/base_sync/`` and ``workflow/engine/`` callers do.
``attribution``, ``branch_probes``, ``checkout_attribution``, ``claims``,
``cleanup``, ``commit_claims``, ``creation``, ``decomposition``,
``discovery``, ``evidence``, ``inventory``, ``maintenance``, ``probes``,
``reclaim``, and ``terminal`` name their logger
``orchestrator.worktree_lifecycle`` rather than after this package, because
that is the name operator log filters select on.
"""
