# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Branch-publication domain owners.

Branch geometry -- ahead/behind counts and the fork point a contribution is
read over -- lives in ``probes``; what a published subject line may say and
which one gets written -- the prefix vocabulary, the predicates over it, the
commit-subject reads they are applied to, and the inference and PR-title
selection above them -- lives in ``titles``; the ` (#N)` pull-request
reference a published commit subject ends in lives in ``pr_references``; the
hardened envelope every orchestrator-made commit is created under, with the
message read and the bound, message-only replacement of the docs commit the
documenting stage publishes, lives in ``commits``; the
preconditions a squash is
planned from, the commit count among them and the decision they come to --
collapse a history, rewrite one commit's subject onto the pull request's
reference, or leave the branch alone -- live in ``planning``; the reset,
commit, force-push, and rollback that spend that plan live in ``rewrite``;
what a squash an earlier tick did not finish is owed lives in ``resume``;
which of the four places a refusal left the branch in lives in ``standing``;
the record every one of them hands back lives in ``models``; and ``squash``
composes them into the entry point stage handlers call. Callers import the
owner they need directly, so this initializer binds nothing and importing
``probes`` never drags the rewrite path in.

``resume`` is the owner no fresh squash runs through. A rewrite destroys the
evidence of what it was about -- a subject rewrite of one commit as completely
as a collapse of several -- so the terms go onto the pinned comment before the
reset and that record is what a later tick reads back -- told apart from a
branch with nothing left to rewrite, proved against the objects it names, and
either finished through the same leased publication the interrupted tick owed
or left exactly where it was found. It reaches the size gate through ``rewrite``'s own
call-time hop rather than a second one, and so does ``standing`` for the record
a refusal is classified against, which is why the workflow layer above is named
in one place here.

No facade of this domain's own sits beside the package, and nothing above it
republishes these names either, so each answers on the owner that defines it
and a test intercepting one targets that owner -- ``probes`` for base sync's
divergence check and for the ahead/behind and fork-point reads the
documenting, conflicts, and validating stages take, ``titles`` for the
first-commit subject behind a fresh dev PR and the two helpers that PR falls
back to, ``commits`` for the message the documenting stage reads and the
amendment it makes, and ``squash`` for validating's squash.
``orchestrator.branch_publication`` names only the logger ``rewrite`` reports
on -- an operator's filter prefix rather than a module path.
"""
