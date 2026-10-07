# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The gated publication a landed recovery's settlement still reaches from this layer.

The ordinary publication of a clean rebase is the workflow's
(`workflow/engine/rewrite_publication.py`): it reads the candidate, enters the
size gate and the transfer permit on it before any push, publishes exactly
that candidate, and hands what landed to the shared finish; so does the
retry of a replay a crash kept off the pull request
(`workflow/engine/rewrite_retry.py`). What stays here is the bridge the one
recovery road left in this package still crosses to the same gate -- the
leased no-op that settles a landing whose receipt never went down
(`landed_settlement`) -- handed the gate's own call and the subject
constructor beside it, so that settlement is measured, pinned, and settled
exactly as the publication is.

Both sit in the workflow layer above this package, so they are bound where
they are used rather than at module load: binding them here would make every
git-side import pay for the stage tree they pull in, and the workflow imports
this package back.
"""
from __future__ import annotations


def _gated_publication():
    """The size gate a recovery's settlement passes, imported where it is used.

    The leased no-op that settles a landing is a push onto a pull request the
    remote already carries, and every such push goes through the one gate, so
    the receipt, the debt it pays, and the rotation it carries are settled
    exactly as any publication's are.
    """
    from orchestrator.workflow.stages.implementing import late_push
    return late_push


def _gate_records():
    """The subject constructor for one gated publication.

    The gate's own record owner, reached the same way and for the same
    reason: what a recovery hands the gate is a subject built from the
    context it already holds, and building one costs the same upward hop the
    call does.
    """
    from orchestrator.workflow.stages.implementing import late_records
    return late_records
