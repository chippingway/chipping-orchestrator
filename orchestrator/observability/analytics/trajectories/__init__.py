# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Trajectory sink owners.

Home of the opt-in, default-off per-run reasoning sink. The owners divide by
what one record passes through on its way to disk: the caps it is measured
against and the two models it is charged as (``models``), the redaction and
head/tail truncation every free-text field is put through (``sanitize``), the
shape those fields are assembled into and the order the variable arrays are
drawn from the budget in (``serialize``), what the request usage field charges
the budget and keeps of it (``requests``), what a Codex launch looks like to
the sink, observed by the tracked spawn before the process starts
(``codex_launch``), the bounded lookup and read of a Codex run's native
session log its request collection is handed (``codex_sessions``), the gate,
the parse, the guarded request collection, the Codex backfill, and the
fail-open guard around the whole write (``persistence``), and the bare append a
caller outside a tracked run reaches (``api``). The
lock that append and the by-age prune both take is minted by the ``sink``
owner above this package, once per process, so the two writers of one file
cannot end up on separate objects.

Callers import the owner they need, so this initializer binds nothing: the
`agent_exit` recorder reaches ``persistence``, and the tracked spawn's exit
reporting ``codex_launch``. The
write is entered from inside a tracked agent run, so it stays free of the
query and viewer graphs that later read the sink back. Every owner here is
also free of the recording package that composes it -- an ``agent_exit``
reaches this write, not the reverse -- so the record envelope and the JSONL
line come off ``sink`` rather than back through those recorders, and every
knob comes off the ``settings`` holder inside the call.
"""
