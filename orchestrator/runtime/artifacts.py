# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When this process reclaims the artifacts of the issues it has finished.

The pass itself belongs to `git/worktrees/`: which issues a host still holds
something for, whether each has really ended, and the commit-pinned teardown
that spends one of those readings. This owner decides only whether that pass
may run now and what it is allowed to see while it does; how often a polling
run owes itself one is `artifact_schedule`'s.

It runs between polling passes rather than inside a tick, and that is the whole
reason this module exists. A tick is per-repository, concurrent with the other
repositories' ticks, and full of workers it has just handed to the scheduler;
the thing being reclaimed is one host's disk and one remote's refs, shared by
every repository on it. Nothing inside a tick can say the host is quiet,
because a tick is what makes it busy.

So the pass runs under a scheduler barrier: admission is closed for counted
workers and tracked claims alike, the work already admitted is waited out
within a finite bound, and only a host that went quiet is acted on. Anything
else -- the bound expiring, a shutdown starting, the barrier declining to be
taken at all -- defers the whole pass, which costs one finished issue's
checkout until the next scheduled attempt and nothing else: the next interval
with no window set, or fifteen elapsed minutes later inside a window that is
still open. Admission always reopens, because the hold
is given back around the body whatever the body did. The pass keeps its own
per-candidate claim check underneath all of that: this barrier is what makes
the answer worth having, and that check is what makes a wrong answer harmless.

A hold is a snapshot, and a signal can land the line after it was granted, so
the grant is not the last word: whether this process may still act is asked
again before every candidate, from the run's own stop flag and from the
scheduler that granted the hold. A pass interrupted between two candidates
leaves the rest where they are.

What the barrier cannot say anything about is another PROCESS, since its
counters and claims are this one's own. That is `exclusion`'s: the host is
claimed exclusively for as long as any pass acts, by the one-shot mode on the
way in and by a polling run handing its own presence over. A pass refused the
host does nothing, and a poller that wants the host back waits -- which is why
this module bounds how long a pass may hold it, and gives it back at a
candidate boundary with whatever is left over owed to the next pass.

The two are nested in the one order that is safe, and this module is where that
order lives. The barrier is OUTSIDE: a polling run's presence is what keeps
every other process off these artifacts, so it may only be handed over from a
process that has already gone quiet, and it has to be back before admission
reopens. Dropping it first would publish the host while this run still had a
worker mid-agent-run -- and a process that took it then would sweep with its
own empty scheduler as its only evidence, which is exactly the reading nothing
here may act on.

A polling run asks that schedule's gate twice: between polling passes whether
a turn is owed, and again from inside both holds whether the turn may still
start. The second ask is there for a local window, since draining and taking
the host both spend wall-clock time the window may not have had -- a pass on
one may only START inside it, and spends it as the last thing before its first
reading. Nothing is persisted, so a restart may spend one extra pass -- which
is a pass that reads the host again and reports whatever is already gone as
done.

What a pass DID is reported here and in `artifact_records` beside it, and
nowhere else: one log line per candidate and the tally over them, then one
bounded record per candidate on the analytics sink. Both are taken from the
answers the pass has already produced, so neither can reach a decision, and the
records are handed over per candidate so a refused sink costs one line rather
than the rest of them.
"""
from __future__ import annotations

import collections
import logging
import time

from orchestrator import config
from orchestrator.git.worktrees import discovery, maintenance
from orchestrator.git.worktrees.candidates import MaintenanceCandidate
from orchestrator.git.worktrees.maintenance_results import MaintenanceOutcome, MaintenanceResult
from orchestrator.runtime import artifact_records, artifact_schedule
from orchestrator.runtime.startup import RepoClients
from orchestrator.runtime.state import RuntimeState
from orchestrator.scheduler.service import IssueScheduler

# The channel is the worktree-lifecycle one the pass under this owner reports
# on, rather than the polling process's own: why a pass did not run is a fact
# about the artifacts, and an operator filtering for what happened to them
# would otherwise be told about every teardown and never about the day the
# host was too busy to attempt one.
log = logging.getLogger("orchestrator.worktree_lifecycle")

# How long the barrier may wait for the host to go quiet before the pass is
# given up on for this turn. Bounded well short of the work it might be
# waiting on: an in-flight agent run is capped by `AGENT_TIMEOUT` rather than
# by anything this wait could outlast, and every second of it is a second in
# which no new issue may be admitted. What it is sized for is a handler already
# on its way out -- a label write mid-flight, a GitHub call being retried --
# and not for the agent behind it, which is a host this pass simply leaves for
# a later turn.
_QUIESCENCE_TIMEOUT_SECONDS = 30.0

# How long one pass may go on spending candidates before it gives this host
# back. It is the bound the other side of `exclusion` rests on: a polling
# process that wants the host waits without a deadline, because waiting is the
# only safe answer for it, and what makes that wait finite is this. Sized for a
# pass over a host holding a handful of finished issues, and generous about
# each one: a candidate is a few local git commands, a GitHub read or two, and
# a remote listing. Whatever the pass does not reach is owed to the next
# scheduled pass -- the next interval with no window set, or the next night's
# window, since a pass that started has spent its own -- which costs one
# checkout until then and nothing else.
#
# The clock starts when the pass starts working, so the one host scan in front
# of the candidates spends it too, and it is read at candidate boundaries: the
# host is held for this plus the candidate in hand. The barrier's own wait is
# outside it entirely, since a run that cannot go quiet never takes the host.
_HOST_HOLD_BUDGET_SECONDS = 120.0

_DEFERRED_LOG = (
    "artifact maintenance deferred: this host could not be proved quiet "
    "within %.0fs, so nothing was touched"
)

_UNCLAIMED_LOG = (
    "artifact maintenance deferred: this host is not this process's to take"
)

_CONTENDED_LOG = (
    "artifact maintenance deferred: another orchestrator process took this "
    "host while this one was going quiet"
)

_OVERRAN_LOG = (
    "artifact maintenance has held this host for %.0fs; giving it back with "
    "the rest of the candidates owed to the next pass"
)


class _Continuing:
    """Whether this pass may still act, asked before it acts on anything.

    Three readings, and each is a reason to stop that arrives while the pass is
    already running. Two of them say a stop has begun HERE: the run's own flag,
    which the signal handler sets before anything else, and the scheduler's
    close, which is what the granted hold rested on -- a hold whose scheduler
    has since closed is one nobody would be given now. The third is this pass's
    own share of the host running out, which is what a process waiting for the
    host is owed.

    Asked this often because every one of those answers changes under the pass
    rather than between passes. A signal that arrived a moment after a
    repository's turn began would otherwise be noticed only when the next
    repository came round, and every candidate of that repository would have
    been spent by then.
    """

    def __init__(
        self, state: RuntimeState, scheduler: IssueScheduler,
    ) -> None:
        self._state = state
        self._scheduler = scheduler
        self._started = time.monotonic()

    def __call__(self) -> bool:
        if not self._state.running or self._scheduler.is_closed():
            return False
        held_for = time.monotonic() - self._started
        if held_for < _HOST_HOLD_BUDGET_SECONDS:
            return True
        log.info(_OVERRAN_LOG, held_for)
        return False


def _grouped_candidates(
    clients: RepoClients,
) -> dict[config.RepoSpec, list[MaintenanceCandidate]]:
    """Discover every candidate on this host, split by the repository it is of.

    The discovery is taken over every configured spec at once, because
    attribution is a question about all of them together -- which of them share
    a clone, which of them derive one checkout directory. The pass is then run
    one repository at a time, because the client it asks about an issue's
    ending is authenticated against one repository, and asking it about
    another's issue number would answer about whichever issue carries that
    number there.

    A repository the discovery will not answer for is said once, here: every
    later reading about it goes to the same remote that would not say, so
    reporting its local half alone would read as a repository with nothing
    left.
    """
    scan = discovery._maintenance_candidates(
        [spec for spec, _client in clients],
    )
    if scan.refused:
        log.info(
            "artifact maintenance will not answer for %s this pass",
            ", ".join(scan.refused),
        )
    grouped: dict[config.RepoSpec, list[MaintenanceCandidate]] = (
        collections.defaultdict(list)
    )
    for candidate in scan.candidates:
        grouped[candidate.artifacts.spec].append(candidate)
    return grouped


def _maintained(
    state: RuntimeState,
    clients: RepoClients,
    scheduler: IssueScheduler,
) -> tuple[MaintenanceResult, ...]:
    """Run the pass over every configured repository, and answer with the lot.

    Both guards handed down are the live process's own readings: whether
    anything is running for one issue, and whether this pass may still act at
    all. The first is deliberate redundancy under a hold that already emptied
    the scheduler; the second is what makes the hold's answer keep meaning
    something as the pass spends it.

    A repository whose turn comes after a stop is skipped rather than started,
    and the pass under it stops between candidates for the same reason.
    Whatever it had not reached stays exactly where it is, and the next run's
    discovery finds it again.
    """
    going = _Continuing(state, scheduler)
    grouped = _grouped_candidates(clients)
    answers: list[MaintenanceResult] = []
    for spec, github_client in clients:
        if not going():
            log.info(
                "artifact maintenance stopping before repo=%s: shutdown requested",
                spec.slug,
            )
            break
        answers.extend(maintenance._maintained_candidates(
            github_client,
            grouped.get(spec, ()),
            claimed=scheduler.is_active,
            going=going,
        ))
    return tuple(answers)


def _log_answers(answers: tuple[MaintenanceResult, ...]) -> None:
    """Report every candidate the pass decided about, and the tally over them.

    One line per candidate, retained ones included: a candidate this pass keeps
    for the same reason every time is the one an operator has to settle by
    hand, and it is invisible in a count. Once per pass that starts -- once an
    interval with no window set, or once a night inside one -- so the volume
    is the number of finished issues a host is still holding artifacts for.
    """
    if not answers:
        log.info("artifact maintenance found no candidate to consider")
        return
    counted = collections.Counter(answer.outcome for answer in answers)
    for answer in answers:
        reported = answer.candidate.artifacts
        about = f" ({answer.subject})" if answer.subject else ""
        log.info(
            "issue=#%d repo=%s artifacts %s: %s%s",
            reported.issue_number, reported.spec.slug,
            answer.outcome, answer.reason, about,
        )
    log.info(
        "artifact maintenance over %d candidate(s): "
        "cleaned=%d retained=%d failed=%d",
        len(answers),
        counted[MaintenanceOutcome.CLEANED],
        counted[MaintenanceOutcome.RETAINED],
        counted[MaintenanceOutcome.FAILED],
    )


def run_maintenance_pass(
    state: RuntimeState,
    clients: RepoClients,
    scheduler: IssueScheduler,
    *,
    gate: artifact_schedule.DueGate | None = None,
) -> None:
    """Reclaim what the finished issues of every configured repository hold.

    Four gates, and the order between the middle two is the whole safety
    argument of running this beside a live process.

    Whether this run holds a claim on the host at all comes first and costs
    nothing: a run that took none is one nothing may be reclaimed by, and it
    does not so much as drain its own scheduler to find that out.

    Then the barrier over this process's own workers, and only inside it the
    exclusive hold on the host. That way round because a polling run's presence
    is what keeps every other process off these artifacts: handing it over from
    a process that has NOT gone quiet publishes the host while a worker is
    still mid-agent-run, and whatever takes it then sweeps with its own empty
    scheduler as its only evidence. Inside the barrier the handover is safe in
    both directions -- there is nothing of this run's left to race, and
    admission stays closed until the presence is back, however long the
    process that took it in between holds it.

    Last, inside both, the `gate` a scheduled pass was handed its turn by:
    whether that turn may still start, asked once, after every wait this pass
    makes and as the last thing before its first reading, because both holds
    spend time its schedule may not have had. A pass run on demand has no
    gate to ask, since being asked is its schedule.

    Every one of the four defers the whole pass. None of them reads a
    candidate, and none so much as scans.

    Total boundary. A pass is tidiness running beside the work, so a discovery
    that raised, a client that would not answer, or a teardown step nothing
    caught must cost the polling loop around it nothing beyond this line.
    """
    if not clients or not state.running:
        return
    if not state.host_claim.taken:
        log.info(_UNCLAIMED_LOG)
        return
    try:
        with scheduler.maintenance_barrier(
            timeout=_QUIESCENCE_TIMEOUT_SECONDS,
        ) as quiet:
            if not quiet:
                log.info(_DEFERRED_LOG, _QUIESCENCE_TIMEOUT_SECONDS)
                return
            with state.host_claim.exclusive() as sole:
                if not sole:
                    log.info(_CONTENDED_LOG)
                    return
                if gate is not None and not gate.admitted():
                    return
                answers = _maintained(state, clients, scheduler)
                _log_answers(answers)
                artifact_records.record_cleanup_results(answers)
    except Exception:
        log.exception("artifact maintenance raised; nothing further was taken")


def run_maintenance_when_due(
    state: RuntimeState,
    clients: RepoClients,
    scheduler: IssueScheduler,
    gate: artifact_schedule.DueGate,
) -> None:
    """Run a pass between polling passes whenever the gate says one is owed.

    The gate goes down into the pass and is told when the pass is over, which
    is how a window learns whether its turn started or deferred.
    """
    if state.running and gate.due():
        run_maintenance_pass(state, clients, scheduler, gate=gate)
        gate.settle()
