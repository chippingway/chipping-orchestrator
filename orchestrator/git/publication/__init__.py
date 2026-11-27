# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Branch-publication domain owners.

Branch geometry -- ahead/behind counts and the fork point a contribution is
read over -- lives in ``probes``; what a published subject line may say and
which one gets written -- the prefix vocabulary, the predicates over it, the
commit-subject reads they are applied to, and the inference and PR-title
selection above them -- lives in ``titles``; which ` (#N)` references a
published commit subject is left ending in -- the tracked issue's dropped
where a caller names one, this pull request's kept exactly once, everything
else untouched -- lives in ``pr_references``, along with the tracked-issue
removal on its own, exposed there for the title selection that runs before a
pull request exists to name; the
hardened envelope every orchestrator-made commit is created under, with the
message read and the bound, message-only replacement of the docs commit the
documenting stage publishes, lives in ``commits``; the
preconditions a squash is
planned from, the commit count among them and the decision they come to --
collapse a history, rewrite one commit's subject to the references a
publication leaves it ending in, or leave the branch alone -- live in
``planning``. ``rewrite`` checks checkout ownership before the soft reset, the
commit, and a mixed reset restoring the original head. ``resume`` verifies a
recorded collapse against local Git history. ``standing`` locates the original
commits for a refusal notice. The validating workflow composes these operations
and returns its publication outcome in the format defined by ``models``.

No facade of this domain's own sits beside the package, and nothing above it
republishes these names either, so each answers on the owner that defines it
and a test intercepting one targets that owner -- ``probes`` for base sync's
divergence check and for the ahead/behind and fork-point reads the
documenting, conflicts, and validating stages take, ``titles`` for the
first-commit subject behind a fresh dev PR and the two helpers that PR falls
back to, ``commits`` for the message the documenting stage reads and the
amendment it makes.
``orchestrator.branch_publication`` names only the logger ``rewrite`` reports
on -- an operator's filter prefix rather than a module path.
"""
