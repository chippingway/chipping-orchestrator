# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Module launch form: `python -m orchestrator` mirrors the console script.

Every command is reached the same way through either form; `run.sh` starts the
polling process as `python -m orchestrator run`.
"""
from __future__ import annotations

import sys

from orchestrator.cli import main

if __name__ == "__main__":
    sys.exit(main())
