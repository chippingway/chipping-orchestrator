# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Analytics recording owners.

Home of the append side of the analytics sink. The owners divide by what a
record costs to produce: the sink append and the three producer-facing
recorders that reach it directly (``events``), the typed requests and keyword
signatures a call is bound through (``models``), and the four steps a finished
agent run is summarized by -- usage and cost (``usage``), the opt-in skill
evidence (``skills``), the out-of-band Codex capabilities either of those
falls back to (``catalog``), and the order they are composed and written in,
under the recorder that enters it (``agent_exit``). The record envelope, the
JSONL line, and both sinks' locking are the ``sink`` owner's, one directory up,
because the trajectory writers satisfy the same envelope and take the same
locking.

This initializer re-exports the narrow public surface (``__all__``): the six
recorders a producer calls -- the envelope builder and the append beneath
them, plus one each for a stage entered, a stage evaluated, a repo's skill
catalog scanned, and a tracked agent run finished. Each is bound here once, at
import, to the object its owner defines rather than a wrapper around it: the
append and the three direct recorders report ``events``, the sequenced one
``agent_exit``, and the envelope ``sink``, which ``events`` republishes because
that is the import site a producer already names. Everything else --
the typed requests, the parse steps, the JSONL append's arguments -- is
reached on its owner, so this package carries no private re-exports.

Where the sink is written, and whether it is written at all, is answered by
the ``config`` owner beside this package rather than here: the read path and
the sync ask the same owner, and a knob has one home. It is read off the
``settings`` holder inside the call, so importing a recorder costs nothing but
the recorders.

One finished run's second record -- the opt-in trajectory -- belongs to the
``trajectories`` package beside this one, and ``agent_exit`` calls its
``persistence`` owner directly rather than reaching the sink back through it,
so the two records stay independent all the way down. The dependency runs one
way: nothing under ``trajectories`` names these recorders, because the
envelope it builds and the channel it logs a failure on both come off ``sink``
above both packages.

This is the one analytics path the orchestrator process itself runs, and it
runs fail-open inside a tracked agent run, so it stays free of the query,
sync, and page graphs above it.
"""
from orchestrator.observability.analytics.recording import agent_exit as _agent_exit, events as _events

__all__ = (
    "append_record",
    "build_record",
    "record_agent_exit",
    "record_repo_skill_catalog",
    "record_stage_enter",
    "record_stage_evaluation",
)

append_record = _events.append_record
build_record = _events.build_record
record_agent_exit = _agent_exit.record_agent_exit
record_repo_skill_catalog = _events.record_repo_skill_catalog
record_stage_enter = _events.record_stage_enter
record_stage_evaluation = _events.record_stage_evaluation
