# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The refusal raised where something meant to act on a pinned record admission refuses.

The whole-state writer (`pinned_state.GitHubStateMixin.write_pinned_state`)
never writes over such a record, creates one beside it, or stamps it as
current, and it raises this rather than answering quietly: a caller told
nothing would go on to whatever the write was for -- a notice, a relabel, an
agent launch -- over a record nobody can read, and a human's edit since the
caller's own reading is enough to leave one. A stage handler's own reading is
held to the same admission and raises it too, so a dispatch catches the one
class around the handler and abandons the handler there.

Kept apart from the writer's owner so the workflow layer, which raises and
catches it as well, names it where it is defined.
"""
from __future__ import annotations


class RecordRefused(RuntimeError):
    """A pinned record admission refuses was met by something meant to act on it.

    Raised by the whole-state writer, with nothing written, and by a stage
    handler's admitted reading. The refusal has already been said in a local
    line by the time it is raised, and it is never posted on the issue.
    """
