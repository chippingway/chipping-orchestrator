# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The decomposer's rationale an accepted notice shows, read back as a thread renders it.

Spelled once for the settlement's own cases and for the recoveries that reach
it after a crash, so both hold the notice to the same reading of what a human
is shown.
"""
from __future__ import annotations

import re

from orchestrator.workflow.engine import comments as _comments

# How the accepted notice introduces the decomposer's own argument, and what
# it says where the record holds none a reader can use.
RATIONALE_LABEL = "Decomposer rationale:"
UNRECORDED_RATIONALE = "Decomposer rationale was not recorded."

# The marker every comment this orchestrator posts carries, and so part of the
# body a notice has to fit one comment with.
COMMENT_MARKER = _comments._ORCH_COMMENT_MARKER

_LINE_BREAKS = "\r\n"

# One fenced block as markdown reads it: a run of three or more of one fence
# character opening a line, then everything up to the first line that is that
# run again -- or longer, with nothing but spaces and tabs beside it -- which
# is where markdown closes it, whatever the quote meant.
_FENCED_BLOCK = re.compile(
    r"(?:\A|(?<=\n))(?P<fence>(?P<mark>[`~])(?P=mark){2,})\n"
    r"(?P<shown>.*?)"
    r"(?<=[\r\n])[ \t]*(?P=fence)(?P=mark)*[ \t]*(?=[\r\n]|\Z)",
    re.DOTALL,
)


def shown_rationale(said: str) -> str:
    """What a thread shows quoted under the accepted notice's rationale label.

    Read the way markdown renders it rather than the way the notice was built:
    every fenced block after the label, in order, with the fence lines taken
    away and the line break the last closing fence stands on dropped. A quote
    that closed its own block early, or left a line outside every block, reads
    back as something other than what the record kept. A notice with no label
    shows nothing.
    """
    quoted = said.partition(RATIONALE_LABEL)[2].lstrip(_LINE_BREAKS)
    return "".join(
        block["shown"] for block in _FENCED_BLOCK.finditer(quoted)
    ).removesuffix("\n")
