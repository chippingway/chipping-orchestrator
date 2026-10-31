# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared JSONL vocabulary and types for usage parsing."""

from __future__ import annotations

TYPE = "type"
MESSAGE = "message"
USAGE = "usage"
ID = "id"
MODEL = "model"
INPUT = "input"
OUTPUT = "output"
INPUT_TOKENS = "input_tokens"
OUTPUT_TOKENS = "output_tokens"
CACHED = "cached"
CACHED_TOKENS = "cached_tokens"
CACHE_READ_TOKENS = "cache_read_tokens"
CACHE_WRITE_TOKENS = "cache_write_tokens"
CACHE_READ = "cache_read"
CACHE_WRITE_FIVE_MIN = "cache_write_5m"
CACHE_WRITE_ONE_HOUR = "cache_write_1h"
# Cache writes a usage block reports no lifetime for; no rate prices them.
CACHE_WRITE_UNKNOWN_LIFETIME = "cache_write_unknown_lifetime"
CACHE_WRITE_THIRTY_MIN = "cache_write_30m"
CACHE_WRITE_TWELVE_HOUR = "cache_write_12h"
TOTAL_TOKEN_USAGE = "total_token_usage"
PAYLOAD = "payload"
INFO_KEY = "info"
ITEM_KEY = "item"
RESULT_KEY = "result"
ASSISTANT = "assistant"
UNKNOWN = "unknown"
CLAUDE = "claude"
CODEX = "codex"
AGY = "agy"
TOKENS_PER_MILLION = 1_000_000

TokenBucket = dict[str, int]
RateMap = dict[str, float]
CodexUsageEvent = tuple[str, TokenBucket]
ModelPath = tuple[str, ...]
