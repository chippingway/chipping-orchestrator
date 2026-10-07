# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a recovery's park notices name the commits they are about.

Every park a crash recovery takes tells a human which heads it found -- the
checkout, the remote, the anchor -- and they are named the same way in each,
so an operator reading two notices on one thread can tell whether they are
about the same commit. What a finished recovery says on the pull request, and
the `base_rebased` event it files, are the workflow finish's own
(`workflow/engine/rewrite_finish_notices.py`), whichever road reached it.
"""
from __future__ import annotations

# How much of an object id a human reads in a park message: enough to name the
# commit in a thread, and short enough to stay readable in a sentence.
_SHORT_SHA = 8


def _short(sha: str) -> str:
    """One commit as an operator reads it in a park message or a log line."""
    return (sha or "")[:_SHORT_SHA]
