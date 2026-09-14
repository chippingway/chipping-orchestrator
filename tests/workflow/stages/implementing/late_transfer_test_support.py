# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one rewrite the transfer's tests grant, refuse, or settle a permit for.

A squash-on-approval of the exact commit an adjudication accepted, described
once: the pinned comment that records the verdict, the evidence the squash
hands in, the publication the gate froze, and the world the two readings the
permit spends -- the checkout and the two fingerprints -- answer in. A case
about one refusal seeds exactly that one and leaves the rest ordinary.

The far end of the same rewrite is seeded from here too, because it is the
same world one write on: `granted` is the comment a permit's own write leaves
-- the permission and the debt the push it licenses still owes -- and
`open_pull_request` is the remote the push is made onto, standing either where
the permit was granted or already on the commit it licensed.
"""
from __future__ import annotations

from orchestrator.workflow.late_split import (
    rewrite_values as _rewrite_values,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_parks as _parks,
)
from tests.workflow.stages.implementing import late_transfer_payloads as _transfer_payloads


def rewrite(**overrides) -> _rewrite_values.LateRewrite:
    """The evidence the squash hands in, with any one term replaced."""
    return _rewrite_values.LateRewrite(**{
        "kind": _rewrite_values.LateRewriteKind.SQUASH,
        "from_sha": _transfer_payloads.ACCEPTED_SHA,
        "from_base_sha": _transfer_payloads.MERGE_BASE_SHA,
        "to_sha": _transfer_payloads.REWRITTEN_SHA,
        "to_base_sha": _transfer_payloads.MERGE_BASE_SHA,
        "pr_number": _transfer_payloads.PR_NUMBER,
        "source_stage": _transfer_payloads.SOURCE_STAGE,
        "lease": _transfer_payloads.LEASED_SHA,
        **overrides,
    })


def entry(**overrides) -> _late_gate_models._PublicationEntry:
    """The publication the gate froze before the rewrite was measured."""
    return _late_gate_models._PublicationEntry(**{
        "stage": _transfer_payloads.SOURCE_STAGE,
        "pr_number": _transfer_payloads.PR_NUMBER,
        "published_sha": _transfer_payloads.LEASED_SHA,
        **overrides,
    })


def spent(state) -> None:
    """The comment a settled transfer leaves, through the write that makes it.

    Three fields, because that is what "spent" means on the comment: the
    exemption and the identity beside it describe the pair the rewrite
    produced, and the phase says the move is done. Written through the record
    owner rather than spelled here, so a case about what a reader does past
    the receipt is seeded with exactly what the receipt leaves -- the proof
    the settlement kept for its own report included.
    """
    _rewrites.record_rewrite_publication(
        state, _rewrite_values.LateRewriteProof.PUSHED,
    )


def gate(github, issue, state, **overrides) -> _late_gate_models._Gate:
    """The subject one gate call taken past publication is about."""
    return _late_gate_models._Gate(**{
        "gh": github,
        "spec": _transfer_payloads.SPEC,
        "issue": issue,
        "state": state,
        "worktree": _transfer_payloads.WORKTREE,
        "reconciling": True,
        "candidate": _transfer_payloads.REWRITTEN_SHA,
        "entry": entry(),
        "rewrite": rewrite(),
        **overrides,
    })


def granted(state, **overrides) -> _rewrite_values.LateRewrite:
    """The comment a permit's own write leaves, and the rewrite it is for.

    Both halves, because the grant writes both: the permission that says what
    the push may carry over, and the debt that says the push is owed at all.
    A case seeding one without the other would be seeding a comment no grant
    ever produced.
    """
    permitted = rewrite(**overrides)
    _rewrites.record_rewrite_authorization(state, permitted, _transfer_payloads.ACCEPTED_DIGEST)
    _parks._approve(
        state, permitted.to_sha, permitted.lease,
        _parks.LateApprovalBasis.UNMEASURED,
    )
    return permitted
