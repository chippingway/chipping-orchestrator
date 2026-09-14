# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Enter the recovery an interrupted auto-rebase is owed, from its legacy call.

The refresh reaches an interrupted rebase through this owner and nothing else,
and what it enters is the record-based route `replay_recovery` coordinates:
the label, the unmoved head, and the published head are asked in that order,
and a checkout the pull request is not standing on is classified off the pair
of heads the attempt recorded and how far the transfer beside them got. The
legacy keyword signature is bound here into the recovery context, the attempt
record included, since that record is what the route decides on.
"""
from __future__ import annotations

import inspect
from typing import Any

from orchestrator.git.base_sync import replay_recovery as _replay_recovery
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _PendingRewrite,
)

_RECOVERY_SIGNATURE = inspect.Signature((
    inspect.Parameter("gh", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("spec", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("issue", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("state", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("worktree", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("pr_number", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter("label", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter(
        "pending_pre_rebase_sha",
        inspect.Parameter.KEYWORD_ONLY,
    ),
    inspect.Parameter(
        "pending_rewrite",
        inspect.Parameter.KEYWORD_ONLY,
        default=_PendingRewrite(),
    ),
    inspect.Parameter("behind", inspect.Parameter.KEYWORD_ONLY, default=0),
    inspect.Parameter(
        "unparking_consumed_max",
        inspect.Parameter.KEYWORD_ONLY,
        default=None,
    ),
))


def _recover_pending_auto_base_rebase_context(
    context: _AutoRebaseRecoveryContext,
) -> bool:
    """Route an interrupted auto-rebase on the record it left."""
    return _replay_recovery._recover_vouched_replay_context(context)


def _recover_pending_auto_base_rebase(
    *args: Any,
    **kwargs: Any,
) -> bool:
    """Finalize a clean auto-base-rebase interrupted by a prior crash.

    The pinned pre-rebase SHA distinguishes an unchanged worktree, an
    already-published rewrite, an ahead-only rewrite that still needs a
    push, and a branch that diverged through an out-of-band update. Returns
    False only when HEAD still equals the anchor and the normal rebase flow
    should continue on the same tick.
    """
    bound_fields = _RECOVERY_SIGNATURE.bind(*args, **kwargs)
    bound_fields.apply_defaults()
    context = _AutoRebaseRecoveryContext(**bound_fields.arguments)
    return _recover_pending_auto_base_rebase_context(context)


_recover_pending_auto_base_rebase.__signature__ = _RECOVERY_SIGNATURE
