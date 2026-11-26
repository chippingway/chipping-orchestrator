# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Analytics observations an agent reply carries beside its workflow outcome.

Home of the one attachment vocabulary agent prompts teach and the one reader
that types it (``attachments``), the bounds the telemetry copy of any text is
held to (``bounds``), the versioned JSONL payloads observations and their
diagnostics are written as (``records``), and the best-effort recorder whose
single failure boundary covers a reply from its parse through its append
(``recorder``). The task snapshot is the family recorded today: a developer's
short description of its task, bound to the requirements revision its run was
handed and the invocation that returned it.

Nothing here reads or decides workflow state. A producer in the workflow
layer hands the recorder the run it observed and the reply it read, and the
observations land on the analytics sink as records of their own; nothing a
workflow decides reads one back, and a lost observation owes nobody a retry.

Callers import the owner they need, so this initializer binds nothing.
"""
