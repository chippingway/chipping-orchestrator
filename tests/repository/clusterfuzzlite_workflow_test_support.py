# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ClusterFuzzLite workflows' text, cut into the jobs and steps the checks read.

Nothing in the tree runs these files -- GitHub does -- so the checks hold the
text GitHub receives, read the way the repository's other workflow checks
read theirs: by the indentation each key sits at.
"""
from __future__ import annotations

import re
from itertools import takewhile
from pathlib import Path
from typing import NamedTuple

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_ENCODING = "utf-8"
_JOB = re.compile(r"^ {2}([\w-]+):$", re.MULTILINE)
_STEP_START = "\n      - "
_MINUTES = re.compile(r"^ +timeout-minutes: (\d+)$", re.MULTILINE)
# Where a step's `run: |` lines sit.
_SCRIPT_INDENT = " " * 10


class Fuzzing(NamedTuple):
    """One ClusterFuzzLite workflow: the job and step that run the targets, their mode, and its budgets."""

    workflow: str
    job: str
    run_step: str
    mode: str
    fuzz_seconds: int
    retention_days: int


# Each workflow's file, run job, run step, mode, fuzzing seconds, and the days
# its artifacts are kept.
FUZZING = tuple(map(Fuzzing._make, (
    ("clusterfuzzlite-pr.yml", "fuzz", "Fuzz the change", "code-change", 600, 14),
    ("clusterfuzzlite-batch.yml", "fuzz", "Fuzz the targets", "batch", 3600, 30),
    ("clusterfuzzlite-prune.yml", "prune", "Prune the corpora", "prune", 600, 30),
)))


def workflow_text(name: str) -> str:
    return (WORKFLOW_DIR / name).read_text(encoding=_ENCODING)


def jobs(workflow: str) -> dict[str, str]:
    """Each job's own lines under `jobs:`, by its id, the line naming it aside."""
    pieces = _JOB.split(workflow.partition("\njobs:\n")[2])
    names = pieces[1::2]
    blocks = pieces[2::2]
    by_name = zip(names, blocks, strict=True)
    return dict(by_name)


def job_of(fuzzing: Fuzzing) -> str:
    """The job that runs `fuzzing`'s targets."""
    return jobs(workflow_text(fuzzing.workflow))[fuzzing.job]


def step(job: str, name: str) -> str:
    """The step called `name` in `job`, from its `- name:` line up to the next step."""
    for block in job.split(_STEP_START)[1:]:
        if block.startswith(f"name: {name}\n"):
            return block
    raise LookupError(f"no step is called {name!r}")


def minutes(block: str) -> list[int]:
    """Every `timeout-minutes` in `block`, at whatever level it is declared."""
    return [int(declared) for declared in _MINUTES.findall(block)]


def script(step_block: str) -> str:
    """The shell a `run: |` step hands its runner, as the runner reads it."""
    lines = step_block.partition("run: |\n")[2].splitlines()
    body = takewhile(lambda line: line.startswith(_SCRIPT_INDENT), lines)
    return "".join(f"{line.removeprefix(_SCRIPT_INDENT)}\n" for line in body)
