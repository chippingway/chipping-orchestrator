# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The push a caller may hand a gated publication in place of the branch push.

Every gated push onto a pull request the remote already carries is made by
`late_push`, and every one but the base-sync auto rebase's goes through the
branch transport there. That one is the git owner's publication of the exact
candidate it read (`git/base_sync/rewrite_transport.py`), and it reads the
checkout and the remote again before it pushes -- requests a pull request
merged or closed in, or a poll latching a close, can overtake. So a transport
is two steps (`Transport`): the reading, and the push. `late_push` asks
whether the publication ended between them, whatever the reading answered, so
the barrier is the last thing asked before anything is sent, as it is for the
branch push, and an ending is held for its cleanup even where the reading
refused the push; the measurement
before the reading and the proof and settlement after the push stay
`late_push`'s whichever transport carried it.
"""
from __future__ import annotations

from typing import Protocol

from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_publication as _late_publication,
)


class Transport(Protocol):
    """How a gated publication's push is made, read for first and then sent.

    Both steps are handed the gate, the branch, and the answer the gate gave.
    `reads` takes whatever the push is decided on and answers whether it may
    go out; False refuses it with nothing sent, and -- unless the publication
    ended meanwhile, which holds it -- the caller parks for it as for any push
    that did not land. `pushes` makes the push and answers
    whether the branch now carries the commit the gate's answer names.
    """

    def reads(
        self,
        gate: _late_gate_models._Gate,
        branch: str,
        published: _late_publication._PublishedCandidate,
    ) -> bool:
        """Take the reading the push is decided on; whether it may go out."""

    def pushes(
        self,
        gate: _late_gate_models._Gate,
        branch: str,
        published: _late_publication._PublishedCandidate,
    ) -> bool:
        """Make the push; whether the branch now carries the commit."""
