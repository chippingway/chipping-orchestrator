# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The polling process's own owners, one per thing a run is made of.

``state`` is the mutable state a single run carries -- whether it is still
polling, the signal that stopped it, the scheduler a handler may close, and the
event the drain announces itself on. Every owner here is handed one rather than
reading it back off a module, so two runs in one interpreter never share it and
a test drives the state it created.

``logs`` settles where the process writes, ``startup`` reads the arguments and
builds the collaborators a run is composed from -- in the bootstrapping form a
tick needs and the read-only form a run that will not tick may have -- ``ticks``
drives one pass over the configured repositories, ``loop`` decides how many
passes there are and guarantees the drain around them, ``artifacts`` decides
whether the finished issues' worktrees and branches may be reclaimed now and
holds the scheduler quiet while they are, ``artifact_schedule`` is when a
polling run owes itself that pass -- an interval, or a local window that takes
precedence over it -- ``artifact_records`` is the one bounded record
each of those candidates is reported to the analytics sink as, ``exclusion`` is
how that claim reaches the
processes this one cannot see -- the only coordination here that is not between
threads -- ``self_update`` answers whether the checkout
the process runs from has moved, and ``shutdown`` owns the signal handler, the
watchdog behind it, and the forced exit it ends at.

``orchestrator/cli.py`` is the composition point above all of them: it creates
the state and hands it to each owner in the order a startup depends on. No
owner here names that composition, and this initializer binds nothing, so
naming one owner never costs the rest.
"""
