# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Immutable lifetime run-ledger snapshots and the phase of a standing reservation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RunPhase(StrEnum):
    """How far the launch currently holding a charge has got.

    Two phases rather than one flag, because the window between them is the
    one the charge exists for. A slot charged and not yet spawned and a spawn
    that is actually running cost the issue the same run, but they are not the
    same thing to anybody reading the issue afterwards: only one of them ever
    reached an agent.
    """

    RESERVED = "reserved"
    STARTED = "started"


@dataclass(frozen=True)
class AgentRunLedger:
    """One issue's whole agent-run accounting, as a tick reads it.

    `configured` is what the setting says right now and `allowance` is what
    this issue is actually held to; they differ only where the issue carries
    an allowance of its own. Both are reported because a reader explaining a
    refusal owes a human the number it was made on, and the two answer
    different questions -- what the deployment allows, and what this issue
    was allowed.
    """

    configured: int
    allowance: int
    used: int
    reservation: RunPhase | None
    fingerprint: str | None = None

    @property
    def unlimited(self) -> bool:
        """Whether the allowance in force bounds nothing at all."""
        return self.allowance <= 0

    @property
    def spent(self) -> bool:
        """Whether the allowance in force has nothing left to give.

        An unlimited allowance is never this, however much the issue has run:
        the count under it is a total somebody may want later, not a number
        anything is measured against.
        """
        return self.remaining == 0

    @property
    def remaining(self) -> int | None:
        """How many runs are left under the allowance, if it bounds any.

        None where the allowance is unlimited: there is no number of runs left
        under a ceiling there is none of, and answering with one would be a
        remaining count a reader could compare against zero and refuse on.

        Floored at zero rather than reported negative. A count past the
        allowance is an ordinary reading -- an issue that spent runs under a
        wider ceiling, or under none -- and what it has left is nothing.
        """
        if self.unlimited:
            return None
        return max(self.allowance - self.used, 0)

    def pending_for(self, fingerprint: str) -> bool:
        """Whether a charge is standing, unspawned, for exactly this launch.

        Both halves, because either alone answers a different question. A
        charge in any other phase is one whose launch reached a process, and
        what happened to that process is not something a later tick can read
        off the issue -- so it is spent and this launch pays again. A charge
        recorded for some other launch was taken by a road that is not this
        one, and reusing it would spend a run this launch never paid for.
        """
        return (
            self.reservation is RunPhase.RESERVED
            and self.fingerprint == fingerprint
        )
