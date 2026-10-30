# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Analytics synchronization owners.

Home of the ingestion that fills the operator's Postgres target from the
project-local JSONL: what one replay is asked for and counted by, the
translation between a record and a row, the deduplicating insert, the database
lifecycle around it, and the command an operator starts the whole thing with.

The owners split by what each half is answerable to. ``columns`` owns the
inventory the record shape and the table shape meet on -- what a record must
carry, what has a column of its own, which of those columns hold JSON, and
which are derived from its usage evidence instead.
``records`` owns what one record hashes to, pinned to the encoding the sink
wrote its line with because that hash is the key the insert deduplicates on,
plus the coercion each required field is either narrowed by or refused for.
``evidence`` owns what an `agent_exit` record's usage evidence fills on its
row beside the fields copied off it -- each cost basis's amount, an estimate's
rate dates, the completeness, and the non-overlapping token total -- read
through the usage parser's own readers rather than re-derived.
``rows`` owns the line itself: the statement a batch is sent under, the
positional tuple built from the same column list in the same order so no
per-row mapping stands between them, and the reason a line that cannot become a
row is skipped for rather than raised on. None of the four names a driver, so
a caller can build or hash a row without Postgres installed.

Above them, ``models`` owns what a replay is counted by and the state its loop
carries, ``ingest`` owns the two dedup filters and the batching between a file
and one open cursor, ``database`` owns the connection those batches ride and
the rollup left refreshed behind them, ``redaction`` owns what the dialled URL
looks like once it reaches a log line, and ``run`` owns the service itself --
what one replay resolves to, the configured states that are a no-op rather than
a failure, and the transaction shape around the ingest. ``cli`` sits on top as
the entry point an operator schedules: the arguments one replay is asked for
through, the UTC-pinned logging it is watched by, and the exit code and stdout
summary it is read back as.

Callers import the owner they need, so this initializer binds nothing: the
sync is its own command run against its own schema, and nothing in the
polling loop should pay for its imports.
"""
