# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Base-synchronization domain owners.

The frozen contexts, requests, snapshots, and decisions one auto-rebase attempt
is threaded through live in ``models``; the pinned-state keys, park reasons,
detour labels, and the shared logger those attempts read and write live in
``state``; the parks every failure ends in and the reset-and-park tail a
rollback takes live in ``persistence``, and the parks a verified recovery
comparison that cannot go on produces live in ``outcomes``. The reads that
comparison is built from -- the authenticated branch fetch, the local and
remote head SHAs, and the divergence counts -- live in ``snapshot``, and the
context a recovery resumes an interrupted attempt in is bound by ``recovery``.
The per-tick refresh that drives one tick's base fetch, the scheduler and
dirty-tree refusals, the issue writer claim each worktree's sync is held under,
the base-lag probe, and the per-worktree routing is the workflow's
(``workflow/engine/base_refresh``), and so is the order a pushed branch's
synchronization asks the owners here in (``workflow/engine/base_rewrite``) and
the order a crash recovery's reads, refusals, and answers are asked in
(``workflow/engine/rewrite_recovery``). ``refresh_selection`` is what that
refresh asks before any of it reaches a checkout -- which discovered
directories name an issue, whether that issue reads at all, and the order the
refusals that hold a branch still are put in -- and ``frozen`` is where those
refusals are spelled out: the records that hold a branch still by their
presence, the two parks that hold one with no record behind them, the two that
hold one only while the checkout still stands on the commit they name, and the
rule each of those freezes ends by. ``pre_pr`` owns the hardened rebase the
refresh runs on a branch nobody has pushed yet. The owners a pushed branch's
synchronization is asked through are ``eligibility`` for the label, park,
PR-state, and clean-tree gates a PR-having worktree clears before any rewrite
is attempted, and ``startup`` for the pre-rebase anchor and terms its rebase is
begun from and the abort / route / park its failure takes. What one attempt
records ABOUT itself -- the head its replay produced, the mark a finish leaves
of its own announcement, and the reading that tells a record nobody wrote from
one something took apart -- lives in ``attempts``, beside the clear every step
that ends an attempt goes through, because the write that makes a member and
the step that drops it are several roads over one record. The typed, data-only
handoffs an automatic PR base rewrite crosses the git boundary as live in
``rewrite_handoffs``, read off the checkout and the remote by ``rewrite_facts``
and published or observed by ``rewrite_transport``: the workflow's ordinary
publication of a clean rebase (``workflow/engine/rewrite_publication``) reads
its candidate and pushes it through the first two, its retry of a replay a
crash kept off the pull request (``workflow/engine/rewrite_retry``) reads its
candidate through ``recovery_push`` and pushes it the same way, and its
recovery of a push that already landed (``workflow/engine/rewrite_landed``)
reads the same candidate and observes the landing -- or proves it with the
leased no-op an outstanding transfer settles through -- with
``landed_recovery`` naming why one may not be finished. Every finish of what
landed is the workflow's. The refusals and parks that publication ends an
attempt with live in ``guards``, and the relabel, notice, and audit event a
rebase that really conflicted is handed to its stage with live in
``conflicts``. Every base-sync name is defined on one of these owners, and
callers import the owner they need directly, so this initializer binds nothing
and importing ``state`` or ``pre_pr`` never drags the PyGithub types
``models``, ``refresh_selection``, and ``startup`` annotate their fields with
in.

No facade of this domain's own sits beside the package, and nothing above it
republishes these names either, so each answers on the owner that defines it:
the workflow's refresh names ``refresh_selection`` and ``pre_pr``, its
base-rewrite coordinator names ``eligibility``, ``startup``, and
``recovery_holds``, its ordinary publication names ``attempts``, ``guards``,
``rewrite_facts``, ``rewrite_transport``, and ``transfer_evidence``, its
recovery coordinator names ``recovery``, ``snapshot``, ``replay_cleanup``,
``replay_refusals``, ``replay_evidence``, ``transfers``, and ``outcomes``, its
retry names ``recovery_push``, ``transfer_evidence``, ``transfer_permits``,
``transfers``, ``replay_transfer_parks``, and ``outcomes``, its landed road
names ``landed_recovery``, ``recovery_push``, ``replay_evidence``,
``replay_publication_parks``, ``replay_transfer_parks``, ``rewrite_transport``,
``transfer_permits``, and ``transfers``, its finish names ``attempts``,
``attempt_records``, ``replay_evidence``, and ``state``, the conflicts owners
name ``pre_pr``, and every stage that must leave an auto-rebase park alone
names ``state``, so a mock lands there. ``state`` names its logger
``orchestrator.base_sync`` rather than after this package, because that is the
name operator log filters select on.
"""
