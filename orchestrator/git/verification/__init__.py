# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Local-verification domain owners.

The `VerifyResult` evidence record, the `VerifyCommandOutcome` each attempted
command adds to its transcript, the context revision minted from a run's
configuration, and the output budget its `output` fields are sized to live in
``models``; the redact-then-truncate pass that fills those fields in
``output``; the HEAD, tree identity, and committed-path probes in ``probes``
and the worktree status reads in ``status``, which together classify what an
agent run left in a worktree; one command's spawn / teardown / drain and the
outcome it earns in ``process``; and the `VERIFY_COMMANDS` sequencing the
validating stage calls, from the commit and tree it verifies to the result it
records, in ``runner``. Every verification name is defined on one
of these owners, and callers import the owner they need directly, so this
initializer binds nothing and importing one owner never drags the others in.

No facade of this domain's own sits beside the package, and nothing above it
republishes these names either, so each answers on the owner that defines it
and a test intercepting one targets that owner -- ``probes`` for the stage
leaves that compare a HEAD watermark, refuse a dirty tree, or ask which paths a
branch's commits change against base, ``runner`` for the validating approval
gate that spends the verify run.
"""
