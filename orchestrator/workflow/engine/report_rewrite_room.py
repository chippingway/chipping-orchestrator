# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a rewrite's report debt was refused for nothing but the room on the pinned comment.

`report_rewrite_debt.records_rewrite` answers whether a rewrite is recorded,
and it refuses for two kinds of reason that a writer has to answer
differently. A rewrite the standing claim cannot be carried onto -- a claim
nobody can read, or one about a head somebody else pushed -- is a head nobody
proved this orchestrator's, so the writer hands it on and the reviewer road
holds the report it finds to it. A proved rewrite the comment has no ROOM for
is a debt the writer owes and could not write down, and handing its head on
without it is the very road the debt exists to close, so the writer holds
instead. Every writer that has to tell the two apart -- the conflict stage,
the base refresh, and the workflow finish of a landed base rewrite built to
take that refresh's finish over (`rewrite_finish_debt`), dormant until a route
calls it -- asks here, so the reading cannot come to differ between them.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_rewrite_debt as _rewrite_debt


def outgrows_the_comment(state: PinnedState, rewrite: _rewrite_debt.RewriteDebt) -> bool:
    """Whether the debt owner refused `rewrite` over `state` for nothing but the comment's room.

    Asked once it has refused. Its other refusals are answered here as
    themselves -- a record that would not read back as written, a standing
    claim nobody can read, and one this rewrite cannot extend -- so whatever
    is left is the room the comment has. A refusal this reading does not know
    is answered as room too, which holds the handoff rather than letting a
    proved rewrite through without its debt.
    """
    if _rewrite_debt.RewriteDebt.read(rewrite.recorded()) != rewrite:
        return False
    if not _rewrite_debt.carries_rewrite_debt(state):
        return True
    standing = _rewrite_debt.read_rewrite_debt(state)
    return standing is not None and standing.retargeted(state, rewrite) is not None
