# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Validate rewrite endpoints, kind, stage, and the publication entered by this call.

The recorded PR, frozen PR, and lease must name the same publication.
A remote already on the rewrite is admitted only when an outstanding
permission accounts for that exact rewritten commit.
"""
from __future__ import annotations

from orchestrator.workflow.late_split import (
    formats as _formats,
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_transfer_reading as _late_transfer_reading,
    state as _state,
)

# Why a rewrite may not carry the exemption over. Each is worded for the log
# line an operator reads when a change a human already ruled on is about to be
# measured again, because what they have to reconcile differs by which of them
# failed.
_UNKNOWN_KIND = "`{kind}` is not a rewrite kind this build authorizes"

_FOREIGN_STAGE = "a `{kind}` rewrite is not one `{stage}` makes"

_UNNAMEABLE_REWRITE = "it cannot name both ends of both contributions"

_UNNAMEABLE_PUBLICATION = (
    "it names no pull request or no head to lease a push against"
)

_UNENTERED_PUBLICATION = (
    "this call was not entered on a publication, so nothing read the pull "
    "request the rewrite claims to be against"
)

_FOREIGN_PUBLICATION = (
    "the rewrite was made against pull request #{claimed} from `{stage}` and "
    "this call was entered on #{entered} from `{frozen}`"
)

_REPLACED_PUBLICATION = (
    "the rewrite was made against pull request #{claimed} and this issue now "
    "records {recorded}"
)

_MOVED_REMOTE = (
    "the force-push is leased against `{lease}` and pull request #{number} "
    "stands at `{standing}`"
)


def _unusable_evidence(
    gate: _late_gate_models._Gate, rewrite: _rewrite_values.LateRewrite,
) -> str:
    """Why this evidence names no rewrite at all, or "".

    The kind is bounded because what a member licenses is a commit the
    orchestrator produced itself, out of commits it can name both ends of; a
    spelling this build does not authorize describes a rewrite nothing here
    made. The STAGE beside it is held to that kind rather than merely to being
    a stage a publication is entered from: the two are one claim about which
    rewrite this workflow made and where, so a `conflict_rebase` offered from
    `validating` or a `squash` from `resolving_conflict` describes a rewrite
    that stage does not make -- and checked a field at a time each half passes
    while the pair is evidence nothing here produced. Every other field is
    held to the shape it claims for the reason each pinned end is: an
    abbreviation is not a commit and a value that cannot name a pull request
    is not one, so a permit granted over either would rest on evidence no
    later reader could check.
    """
    if rewrite.kind not in _rewrite_values.LateRewriteKind:
        return _UNKNOWN_KIND.format(kind=rewrite.kind)
    if not _rewrite_values.entered_from(rewrite.kind, rewrite.source_stage):
        return _FOREIGN_STAGE.format(
            kind=rewrite.kind, stage=rewrite.source_stage,
        )
    named = (
        rewrite.from_sha, rewrite.from_base_sha,
        rewrite.to_sha, rewrite.to_base_sha,
    )
    if not all(
        _formats.is_hex_of(end, _formats.COMMIT_LENGTHS) for end in named
    ):
        return _UNNAMEABLE_REWRITE
    pinned = (
        _formats.whole_number(rewrite.pr_number) and rewrite.pr_number > 0
        and _formats.is_hex_of(rewrite.lease, _formats.COMMIT_LENGTHS)
    )
    return "" if pinned else _UNNAMEABLE_PUBLICATION


def _disagreeing_publication(
    gate: _late_gate_models._Gate, rewrite: _rewrite_values.LateRewrite,
) -> str:
    """Why the rewrite is not against the publication this call froze, or "".

    The entry is this call's own fresh reading of that pull request, taken
    before any effect and refused unless it came back open and standing on the
    head the caller established -- so a rewrite whose every term matches it is
    one made against a pull request confirmed open and unmoved this tick. Read
    a second time here, the answer could only be a later one than the head the
    force-push is already leased against.

    The pull request the ISSUE records is asked beside it, because the entry
    proves the pull request was read and not that it is still the one this
    issue's work belongs to: a repointed `pr_number` describes a publication
    the rewrite was never made against.
    """
    entry = gate.entry
    if entry is None or not entry.is_frozen:
        return _UNENTERED_PUBLICATION
    claimed = (rewrite.pr_number, rewrite.source_stage)
    if claimed != (entry.pr_number, entry.stage):
        return _FOREIGN_PUBLICATION.format(
            claimed=rewrite.pr_number, stage=rewrite.source_stage,
            entered=entry.pr_number, frozen=entry.stage,
        )
    if not _standing_where_the_permit_left_it(gate, rewrite):
        return _MOVED_REMOTE.format(
            lease=rewrite.lease, number=entry.pr_number,
            standing=entry.published_sha,
        )
    recorded = gate.state.get(_state._PR_NUMBER)
    if recorded != rewrite.pr_number:
        return _REPLACED_PUBLICATION.format(
            claimed=rewrite.pr_number, recorded=recorded,
        )
    return ""


def _standing_where_the_permit_left_it(
    gate: _late_gate_models._Gate, rewrite: _rewrite_values.LateRewrite,
) -> bool:
    """Whether the remote is a head this permit accounts for.

    Two heads do, and the second is what makes a lost receipt recoverable.
    The LEASE is the ordinary one: the pull request is where the rewrite was
    made against it and the push has not gone out.

    The REWRITTEN commit is the other, and only while the permission is still
    outstanding. A pull request standing there is this permit's own push
    having landed -- nothing else force-pushes that object under that lease --
    and what is missing is the receipt behind it. Refused as a moved remote,
    the recovery would remeasure a squash the pull request already carries and
    route an oversized one straight back into adjudication with the work
    already published. Admitted, the permit re-proves everything else and the
    republication is the leased no-op it should be, which is what lets the
    receipt behind it settle the debt the grant made durable.

    Phase-aware, because that is the whole of what makes it safe: a spent
    permission accounts for no outstanding push, so past the receipt this head
    is an ordinary moved remote again.
    """
    entry = gate.entry
    if entry.published_sha == rewrite.lease:
        return True
    if entry.published_sha != rewrite.to_sha:
        return False
    return _late_transfer_reading._outstanding_rewrite(gate.state, rewrite.to_sha) is not None
