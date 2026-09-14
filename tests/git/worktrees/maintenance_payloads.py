# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recorded names, file contents, and ref targets for real maintenance scenarios."""
from __future__ import annotations

PR_NUMBER = 42
WARNING = "WARNING"
INFO_LEVEL = "INFO"
LOOSE_FILE = "left-behind.txt"
LOOSE_CONTENT = "an agent's unfinished work\n"
IGNORE_FILE = ".gitignore"
HIDDEN_FILE = "secrets.env"
HIDDEN_CONTENT = "TOKEN=an operator's own\n"
IMPLEMENTING_LABEL = "workflow:implementing"
OTHER_ISSUE_NUMBER = 315
# The classification a stop is driven through, named on its own owner.
_CLASSIFY_ATTR = "_classify_artifacts"
# Where an operator puts a worktree to look at a finished branch.
INSPECTED_DIR = "inspected"
OBJECT_ID_LENGTH = 40
# The teardown step several cases install a refusal on.
REMOTE_DELETE = "_delete_remote_branch_at"
# A commit no artifact of this issue is standing on: what a proof taken a
# moment before the mutation is worth once somebody has pushed.
OTHER_SHA = "b" * OBJECT_ID_LENGTH
