# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a completed reviewer run may declare about verification.

A reviewer closes on a `VERDICT:` line about the diff. What it says about
verification is a separate declaration with markers of its own, so neither
reading can stand in for the other. A declaration takes one of two forms. A
RUN block names the commit it verified and the exact commands the reviewer ran
in this run, each with the exit status it observed and whatever output it
quoted, between an opening and a closing marker line, because only an explicit
close shows the list was not cut short. A REUSED line names the revision of the
current workflow verification evidence the reviewer inspected instead of
running anything itself.

The reviewer is the only witness to either. The orchestrator never observed
those commands run, so an accepted declaration carries every fact exactly as
the reviewer wrote it, labeled reviewer-reported and bound to the reviewer run
and the commit it was handed -- nothing is counted, normalized, or inferred
from it.

Everything else a run can end in is a refusal. Five are the run itself falling
short and are decided before its message is read, three are about the message
of a run that completed. The spellings live here, apart from the parser, so a
prompt that teaches them names the same source the parser reads.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

_VERIFICATION_MARKER_PREFIX = "VERIFICATION:"
_VERIFICATION_RUN_MARKER = f"{_VERIFICATION_MARKER_PREFIX} RUN"
_VERIFICATION_END_MARKER = f"{_VERIFICATION_MARKER_PREFIX} END"
_VERIFICATION_REUSED_MARKER = f"{_VERIFICATION_MARKER_PREFIX} REUSED"
_COMMAND_PREFIX = "COMMAND:"
_EXIT_PREFIX = "EXIT:"
_REVISION_PREFIX = "sha256:"
_REVIEWER_REPORTED = "reviewer_reported"


class _VerificationRefusal(StrEnum):
    """Why a reviewer run earns no verification evidence.

    The first five are the run not completing, in the order they are asked:
    never started, killed by the shutdown sweep, timed out, refused by its
    provider, exited nonzero. Whatever such a run's last message says, it is
    not a declaration anybody finished.

    The last three are the last message of a run that DID complete. `MISSING`
    is a reply that never declared anything. `MALFORMED` is one that reached
    for the contract and missed: a block left open or truncated, one listing
    no command, a command without exactly one exit status, a commit or
    revision out of shape, two declarations or two forms at once, a marker
    line that may render as code, or a verdict inside the block. `STALE` is a
    well-formed declaration about something other than what the reviewer was
    handed: another commit, or evidence that is not the current revision.
    """

    NOT_INVOKED = "not_invoked"
    INTERRUPTED = "interrupted"
    TIMED_OUT = "timed_out"
    PROVIDER_FAILURE = "provider_failure"
    NONZERO_EXIT = "nonzero_exit"
    MISSING = "missing"
    MALFORMED = "malformed"
    STALE = "stale"


@dataclass(frozen=True)
class _VerificationSubject:
    """What the reviewer was handed, which a declaration has to be about.

    `commit` is the full object id of the head under review. `evidence_revision`
    is the lowercase SHA-256 hex digest of the current workflow verification
    evidence the reviewer was shown, or None when there is none to reuse.
    """

    commit: str
    evidence_revision: str | None = None


@dataclass(frozen=True)
class _ReviewerSource:
    """The reviewer run that reported a declaration -- all that vouches for it.

    `session_id` is that run's session, or None when its backend reported
    none; `commit` is the head it was handed.
    """

    session_id: str | None
    commit: str

    @property
    def provenance(self) -> str:
        """The facts were reported by the reviewer, never observed here."""
        return _REVIEWER_REPORTED


@dataclass(frozen=True)
class _ReportedCommand:
    """One command the reviewer says it ran, verbatim.

    `command` is the text as written, `exit_status` the status the reviewer
    stated, and `output` the lines it quoted beneath them, or empty when it
    quoted none.
    """

    command: str
    exit_status: int
    output: str


@dataclass(frozen=True)
class _FreshVerification:
    """Commands the reviewer ran on the reviewed commit, in the order listed.

    Rerunning a command is listed twice, not merged; which exit statuses make
    the run acceptable is the caller's to decide.
    """

    source: _ReviewerSource
    commands: tuple[_ReportedCommand, ...]


@dataclass(frozen=True)
class _ReusedVerification:
    """The current workflow evidence revision the reviewer says it inspected.

    Accepting it proves only that the reviewer named the revision it was shown;
    what that evidence covers is the evidence's own record.
    """

    source: _ReviewerSource
    evidence_revision: str


_VerificationOutcome = _FreshVerification | _ReusedVerification | _VerificationRefusal
