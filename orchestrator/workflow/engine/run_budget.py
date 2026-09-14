# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an agent-run budget transition tells both observability sinks.

The ledger beside this owner records what an issue may spend and what it has
spent; the circuit above it charges a launch, and the command beyond it widens
a ceiling a human decided was too narrow. None of those three can be read back
off an issue afterwards: pinned state carries the counts as they stand right
now, so an operator asking how an issue arrived at them -- which launches were
charged, which was turned away, and when somebody paid for more -- has nothing
to read. This owner is that record.

One event family for all four transitions, because they are one story. A
launch that reserved a run, the same launch reaching a process, the launch
that was refused, and the ceiling a human moved afterwards are the whole
account of one issue's lifetime, and split across four kinds an operator would
have to join four streams to read it. So the family is `agent_run_budget` and
the step is the `phase` on it, which is the same shape the park's own audit
stream beside this one already has.

Both sinks, deliberately. The audit JSONL has to answer offline what the
database answers over the analytics sink -- whether a deployment's ceiling is
turning launches away, how much of a lifetime an ordinary issue actually
spends, and how often a human buys past it -- so one call writes both under
their own envelopes, exactly as the late size gate's records do. Neither write
may change what the workflow does: both sinks already swallow a filesystem
refusal, each write additionally rides its own guard, and a failure on one
side does not skip the other.

Every phase carries the whole reading the transition was made on, rather than
the one field that moved. A record saying a run was charged and nothing else
is one an operator has to join against a setting that may have changed since;
a record carrying the configured ceiling, the allowance actually in force, the
runs spent, and what is left of them is a row that answers on its own. The
allowance and the setting are both reported because they are different facts:
an issue may carry a ceiling of its own -- which is exactly what an operator
grant writes -- and a refusal explained by the deployment's number would name
one this issue was never held to.

What is left of an unlimited allowance is not a number, and this is where that
is said out loud rather than left to a missing field. `remaining` is on every
phase, and under a ceiling that bounds nothing it carries the word rather than
a count: any number written there is one a query could compare against zero
and read as an issue about to stop, and an absent field is one a consumer
cannot tell from a count some writer or replay lost.

A charge is correlated by the charge itself, not by the shape of the launch
that took it. `reservation_id` pairs the bounded head of the circuit's
fingerprint with the count that charge moved, because the fingerprint alone
repeats: it is deliberately stable across ticks so a standing reservation can
be recognized, which means the same shape is charged again every time a launch
that already started comes back. The count goes up once per charge and never
comes down, so the pair names one charge on one issue and names it identically
from both phases of it -- and it names nothing the prompt, the worktree, or
anything else a launch was built out of would give away. It is on the two
phases a reservation exists under and on neither of the others: a refused
launch never took one, and a grant is not a launch at all.

A refusal says which way an allowance ran out, from a closed vocabulary. The
two readings are genuinely different to whoever is looking: an issue that
spent exactly what it was allowed has reached the ordinary end of a lifetime,
while one already past the ceiling in force was carried there by a ceiling
that moved under it -- a narrowed setting, or a deployment that ran with the
limit off. Bounded rather than free text for the reason every field here is:
a sink carries whatever it is handed.

Emission is tied to the DURABLE transition and to nothing else, which is what
keeps the stream a count of things that happened. A charge is recorded after
the write that takes it lands, so a launch honoring a reservation an earlier
tick left standing reports only the start it actually paid for; a park is
recorded by the tick that takes it, so the ticks that go on meeting it say
nothing; and a grant is recorded after the write that widens the ceiling, so a
command re-read because a previous tick died between its receipt and its write
reports the one extension that became durable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.workflow.engine.run_ledger import AgentRunLedger
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")

# The one family every agent-run budget transition is written under. A wire
# string on both sinks, so an operator's filter and a database column key off
# it.
AGENT_RUN_BUDGET_EVENT = "agent_run_budget"

# How much of a launch fingerprint a reservation id carries. Long enough that
# two launch shapes on one issue cannot collide in practice, short enough to
# stay a correlation label rather than a second identity of its own.
FINGERPRINT_HEAD_LENGTH = 12

# What `remaining` says under an allowance that bounds nothing. A word rather
# than a number, because every number a reader could be handed there is one
# they could compare against zero -- and rather than an absent field, because
# a record missing the count is one a consumer cannot tell from a writer that
# dropped it.
REMAINING_UNLIMITED = "unlimited"


class BudgetPhase(StrEnum):
    """Which durable step of an issue's agent-run budget one record is.

    Four rather than two, because a charge and the spawn it paid for are not
    the same event to anybody counting them: the window between them is where
    a tick can die, and an issue whose runs were all reserved and never
    started is a crash loop rather than a workload. The other two are the ends
    of the lifetime -- the launch the ceiling turned away, and the human who
    decided the ceiling was wrong.
    """

    RESERVED = "reserved"
    STARTED = "started"
    EXHAUSTED = "exhausted"
    EXTENDED = "extended"


class ExhaustionReason(StrEnum):
    """Which way the allowance a refused launch met had run out.

    The park has one reason of its own -- a lifetime is spent once -- so the
    thing that tells two refusals apart is the arithmetic behind them. An
    issue standing exactly at its ceiling got there by running; one already
    past it got there because the ceiling moved, and an operator reading a
    park they did not expect needs to be able to tell which.
    """

    ALLOWANCE_SPENT = "allowance_spent"
    ALLOWANCE_EXCEEDED = "allowance_exceeded"


@dataclass(frozen=True)
class AgentRunLaunch:
    """The launch a charge is taken for, as a record may name it.

    The fingerprint is what the ledger charges under, so it is what correlates
    two ticks of one launch; the stage and the role are what an operator reads
    a launch BY, and they are the same two the `agent_spawn` pair records, so
    a budget record and the spawn beside it agree on where a run happened
    without either re-reading the label.
    """

    fingerprint: str
    stage: str
    agent_role: str


def _emit_charge(
    gh: GitHubClient,
    issue: Issue,
    phase: BudgetPhase,
    ledger: AgentRunLedger,
    launch: AgentRunLaunch,
) -> None:
    """Record one durable phase of the charge a launch took.

    Both phases are the same record under a different `phase`, because they
    describe the same launch against the same counts: what separates them is
    only how far it got, and a reader counting reservations against starts is
    exactly the reader this pair exists for.
    """
    _emit(gh, issue.number, launch.stage, {
        **_ledger_fields(phase, ledger),
        "agent_role": launch.agent_role,
        "reservation_id": _reservation_id(launch, ledger),
    })


def _emit_exhaustion(
    gh: GitHubClient,
    issue: Issue,
    ledger: AgentRunLedger,
    launch: AgentRunLaunch,
) -> None:
    """Record the launch a spent lifetime allowance turned away.

    The reading is the one the refusal was actually made on rather than one
    taken again here, so the record and the sentence the park says to the
    thread quote the same numbers.

    No `reservation_id`: a refused launch never took a charge, and a record
    naming one would correlate against a reservation nothing wrote. The stage
    and the role are still here -- they are what an operator needs to see
    which work the ceiling is stopping.
    """
    _emit(gh, issue.number, launch.stage, {
        **_ledger_fields(BudgetPhase.EXHAUSTED, ledger),
        "agent_role": launch.agent_role,
        "reason": _exhaustion_reason(ledger),
    })


def _emit_extension(
    gh: GitHubClient, issue: Issue, ledger: AgentRunLedger,
) -> None:
    """Record the wider ceiling a trusted operator command just bought.

    The stage is read off the label the issue is wearing rather than named by
    a caller, because a grant has no launch to take one from. What it says is
    where the issue was standing when a human answered its park, which is the
    whole of what an extension can say about where it happened.

    No role and no reservation, though. The ledger is spent by every role at
    every stage, so there is no one role a human bought runs for -- and a
    grant is not a launch, so there is no charge for a correlation to name.
    """
    _emit(
        gh,
        issue.number,
        _label_stage(gh, issue),
        _ledger_fields(BudgetPhase.EXTENDED, ledger),
    )


def _label_stage(gh: GitHubClient, issue: Issue) -> str | None:
    """Where the issue is standing, or nothing where that could not be read.

    The one field on this stream that costs a request to build, and so the one
    that can fail before either write is attempted. It is asked on the far
    side of a durable grant -- the park is already down and the tick is on its
    way to the stage its label names -- so an exception out of here would not
    merely cost the record, it would break a tick that had already changed
    the issue. That is the failure the guards around the two writes exist to
    prevent, and a read on the way to them has to ride one too.

    A failed read costs the stage and not the record. `stage` is optional in
    both envelopes and a phase with no stage is still countable, while a
    transition nothing recorded is one an operator can never count -- and this
    one has already happened.
    """
    try:
        return stage_name(gh.workflow_label(issue))
    except Exception:
        log.exception(
            "issue=#%s: the stage an agent-run budget extension happened at "
            "could not be read; recording the transition without one",
            getattr(issue, "number", "?"),
        )
        return None


def _ledger_fields(
    phase: BudgetPhase, ledger: AgentRunLedger,
) -> dict[str, Any]:
    """The whole budget reading one transition was taken on.

    Every phase carries all of it. A record that reported only the field that
    moved would be one an operator has to join against a setting that may have
    changed since, and the join is not available offline -- which is the whole
    reason the audit copy exists.

    `remaining` is on every record too, including the ones an unlimited
    allowance leaves no count for -- what it carries there is the word rather
    than a number or nothing at all.
    """
    return {
        "phase": phase,
        "configured": ledger.configured,
        "allowance": ledger.allowance,
        "used": ledger.used,
        "remaining": _remaining(ledger),
    }


def _remaining(ledger: AgentRunLedger) -> int | str:
    """What is left of the allowance, said out loud on every record.

    An unlimited ceiling has no count left under it, and the two ways of
    reporting that as a number both mislead: zero reads as an issue that has
    stopped, and any positive figure reads as one about to. Dropping the field
    instead is worse still -- a consumer cannot tell a record that means
    "unbounded" from one a writer, an envelope, or a replay lost the count
    from, and the whole point of the audit copy is answering offline.

    So the field is always there and the unbounded case spells itself.
    `remaining` is therefore an integer or `REMAINING_UNLIMITED`, and a query
    that casts it filters or coalesces that word rather than assuming a
    number.
    """
    if ledger.remaining is None:
        return REMAINING_UNLIMITED
    return ledger.remaining


def _reservation_id(launch: AgentRunLaunch, ledger: AgentRunLedger) -> str:
    """The one charge this record is about, as a single joinable label.

    The launch shape alone cannot be it. A fingerprint is deliberately stable
    across ticks -- that is exactly what lets a reservation an earlier tick
    left standing be recognized and reused -- so the same shape is charged
    again every time a launch that already reached `started` comes back, and
    two unrelated charges would carry one id.

    What tells them apart is the count the charge moved. It goes up by one per
    charge and never comes down, so it is the charge's own sequence number on
    this issue: `<launch>-<used>` names one charge, names it the same from
    both phases of it -- the count does not move between them, and a reused
    reservation reports the count its own charge wrote -- and never names two.
    With the envelope's repo and issue around it, that is a key a consumer can
    join `reserved` to `started` on.
    """
    head = launch.fingerprint[:FINGERPRINT_HEAD_LENGTH]
    return f"{head}-{ledger.used}"


def _exhaustion_reason(ledger: AgentRunLedger) -> ExhaustionReason:
    """Which of the two ways this allowance ran out.

    Past the ceiling rather than at it is a reading nothing about this issue's
    own runs explains: the count only ever goes up and the allowance is read
    live, so an issue above its ceiling is one the ceiling came down on.
    """
    if ledger.used > ledger.allowance:
        return ExhaustionReason.ALLOWANCE_EXCEEDED
    return ExhaustionReason.ALLOWANCE_SPENT


def _emit(
    gh: GitHubClient,
    issue_number: int,
    stage: str | None,
    payload: dict[str, Any],
) -> None:
    """Write one budget record to both sinks, under their own envelopes.

    Two independent writes rather than one, and neither is allowed to skip the
    other: they are separate observability surfaces, and one being unavailable
    is not a reason to lose the other. Each rides its own guard, so a client
    or a sink that raises costs the record and nothing else -- the transition
    it describes is already durable on the issue.
    """
    _emit_audit(gh, issue_number, stage, payload)
    _emit_analytics(gh, issue_number, stage, payload)


def _emit_audit(
    gh: GitHubClient,
    issue_number: int,
    stage: str | None,
    payload: dict[str, Any],
) -> None:
    try:
        gh.emit_event(
            AGENT_RUN_BUDGET_EVENT,
            issue_number=issue_number,
            stage=stage,
            **payload,
        )
    except Exception:
        log.exception(
            "issue=#%s: agent-run budget audit emission failed; continuing",
            issue_number,
        )


def _emit_analytics(
    gh: GitHubClient,
    issue_number: int,
    stage: str | None,
    payload: dict[str, Any],
) -> None:
    try:
        _recording_events.append_record(
            _recording_events.build_record(
                repo=getattr(gh, "_repo_slug", None) or "",
                issue=issue_number,
                event=AGENT_RUN_BUDGET_EVENT,
                stage=stage,
                **payload,
            ),
        )
    except Exception:
        log.exception(
            "issue=#%s: agent-run budget analytics record failed; continuing",
            issue_number,
        )
