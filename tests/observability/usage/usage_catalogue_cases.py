# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The API price catalogue as the provider pages published it when read on 2026-10-29.

Each rate tuple is one row of its provider's pricing table in that page's column order, `None` standing for a dash:
Claude lists base input, 5m cache writes, 1h cache writes, cache hits, and output; OpenAI lists input, output, cached
input, 30m write, and 12h write, its older models' table stopping after cached input; Gemini lists input, output
including thinking tokens, and context caching.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from orchestrator.observability.usage import protocol

PageRow = tuple[float | None, ...]
RowCase = tuple[str, PageRow, bool]
TierCase = tuple[str, int, PageRow]
ExpectedRow = tuple[str, protocol.RateMap, bool]

VERIFIED_ON = "2026-10-29"

CLAUDE_COLUMNS = (
    protocol.INPUT,
    protocol.CACHE_WRITE_FIVE_MIN,
    protocol.CACHE_WRITE_ONE_HOUR,
    protocol.CACHE_READ,
    protocol.OUTPUT,
)
OPENAI_COLUMNS = (
    protocol.INPUT,
    protocol.OUTPUT,
    protocol.CACHED,
    protocol.CACHE_WRITE_THIRTY_MIN,
    protocol.CACHE_WRITE_TWELVE_HOUR,
)
GEMINI_COLUMNS = (protocol.INPUT, protocol.OUTPUT, protocol.CACHED)

OPUS_FOUR_EIGHT = "claude-opus-4-8"
HAIKU_THREE_FIVE = "claude-3-5-haiku-20241022"
HAIKU_THREE_FIVE_ALIAS = "claude-3-5-haiku-latest"
GPT_FIVE_ONE_CHAT = "gpt-5.1-chat-latest"
GPT_FIVE_SIX = "gpt-5.6"
GPT_FIVE_SIX_SOL = "gpt-5.6-sol"
GEMINI_FOUR_ARGON = "gemini-4-argon"
GEMINI_PRO_PREVIEW = "gemini-3.1-pro-preview"

# Canonical ID, its page row, and whether production estimates price it.
CLAUDE_ROWS = (
    ("claude-fable-5-1", (10, 12.5, 20, 0.25, 50), True),
    ("claude-fable-5", (10, 12.5, 20, 1, 50), True),
    ("claude-opus-5-5", (4, 5, 8, 0.2, 20), True),
    ("claude-opus-5", (5, 6.25, 10, 0.5, 25), True),
    (OPUS_FOUR_EIGHT, (5, 6.25, 10, 0.5, 25), True),
    ("claude-opus-4-7", (5, 6.25, 10, 0.5, 25), True),
    ("claude-opus-4-6", (5, 6.25, 10, 0.5, 25), True),
    ("claude-opus-4-5-20251101", (5, 6.25, 10, 0.5, 25), True),
    ("claude-opus-4-1-20250805", (15, 18.75, 30, 1.5, 75), True),
    ("claude-opus-4-20250514", (15, 18.75, 30, 1.5, 75), True),
    ("claude-sonnet-5-5", (2, 2.5, 4, 0.1, 10), True),
    ("claude-sonnet-5", (2, 2.5, 4, 0.2, 10), True),
    ("claude-sonnet-4-6", (3, 3.75, 6, 0.3, 15), True),
    ("claude-sonnet-4-5-20250929", (3, 3.75, 6, 0.3, 15), True),
    ("claude-sonnet-4-20250514", (3, 3.75, 6, 0.3, 15), True),
    ("claude-haiku-5-5", (0.1, 0.125, 0.2, 0.01, 0.5), True),
    ("claude-haiku-4-5-20251001", (1, 1.25, 2, 0.1, 5), True),
    (HAIKU_THREE_FIVE, (0.8, 1, 1.6, 0.08, 4), True),
)
OPENAI_ROWS = (
    ("gpt-6-astra", (10, 50, 1, 12.5, 25), True),
    ("gpt-6.1-sol", (2, 10, 0.1, 2.5, 5), True),
    ("gpt-6.1-terra", (1, 5, 0.05, 1.25, 2.5), True),
    ("gpt-6-luna", (0.1, 0.5, 0.01, 0.125, 0.25), True),
    ("gpt-6-sol", (2, 10, 0.2, 2.5, 5), True),
    (GPT_FIVE_SIX_SOL, (4, 20, 0.4, 5, 10), True),
    ("gpt-5.6-terra", (2, 12, 0.2, 2.5, 5), True),
    ("gpt-5.6-luna", (0.2, 1.2, 0.02, 0.25, 0.5), True),
    ("gpt-5.5", (5, 30, 0.5, None, None), True),
    ("gpt-5.5-pro", (30, 180, None, None, None), True),
    ("gpt-5.4", (2.5, 15, 0.25, None, None), True),
    ("gpt-5.4-pro", (30, 180, None, None, None), True),
    ("gpt-5.4-mini", (0.75, 4.5, 0.075), True),
    ("gpt-5.4-nano", (0.2, 1.25, 0.02), True),
    ("gpt-5.3-codex", (1.75, 14, 0.175), True),
    ("gpt-5.3-chat-latest", (1.75, 14, 0.175), True),
    ("gpt-5.2", (1.75, 14, 0.175), True),
    ("gpt-5.2-codex", (1.75, 14, 0.175), True),
    ("gpt-5.2-chat-latest", (1.75, 14, 0.175), True),
    ("gpt-5.2-pro", (21, 168, None), True),
    ("gpt-5.1", (1.25, 10, 0.125), True),
    ("gpt-5.1-codex", (1.25, 10, 0.125), True),
    ("gpt-5.1-codex-max", (1.25, 10, 0.125), True),
    ("gpt-5.1-codex-mini", (0.25, 2, 0.025), True),
    (GPT_FIVE_ONE_CHAT, (1.25, 10, 0.125), True),
    ("gpt-5", (1.25, 10, 0.125), True),
    ("gpt-5-codex", (1.25, 10, 0.125), True),
    ("gpt-5-chat-latest", (1.25, 10, 0.125), True),
    ("gpt-5-pro", (15, 120, None), True),
    ("gpt-5-mini", (0.25, 2, 0.025), True),
    ("gpt-5-nano", (0.05, 0.4, 0.005), True),
    ("codex-mini-latest", (1.5, 6, 0.375), True),
)

# Every other spelling a row answers to -- the documented aliases and the
# published snapshot IDs -- and the canonical ID it resolves to.
CLAUDE_ALIASES = MappingProxyType({
    "claude-opus-4-5": "claude-opus-4-5-20251101",
    "claude-opus-4-1": "claude-opus-4-1-20250805",
    "claude-opus-4-0": "claude-opus-4-20250514",
    "claude-sonnet-4-0": "claude-sonnet-4-20250514",
    "claude-sonnet-4-5": "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5": "claude-haiku-4-5-20251001",
    HAIKU_THREE_FIVE_ALIAS: HAIKU_THREE_FIVE,
})
OPENAI_ALIASES = MappingProxyType({
    GPT_FIVE_SIX: GPT_FIVE_SIX_SOL,
    "gpt-5.5-2026-04-23": "gpt-5.5",
    "gpt-5.5-pro-2026-04-23": "gpt-5.5-pro",
    "gpt-5.4-2026-03-05": "gpt-5.4",
    "gpt-5.4-pro-2026-03-05": "gpt-5.4-pro",
    "gpt-5.4-mini-2026-03-17": "gpt-5.4-mini",
    "gpt-5.4-nano-2026-03-17": "gpt-5.4-nano",
    "gpt-5.2-2025-12-11": "gpt-5.2",
    "gpt-5.2-pro-2025-12-11": "gpt-5.2-pro",
    "gpt-5.1-2025-11-13": "gpt-5.1",
    "gpt-5-2025-08-07": "gpt-5",
    "gpt-5-pro-2025-10-06": "gpt-5-pro",
    "gpt-5-mini-2025-08-07": "gpt-5-mini",
    "gpt-5-nano-2025-08-07": "gpt-5-nano",
})

# Model, the prompt size its request tier starts above, and the tier's page row.
CLAUDE_TIERS = (("claude-haiku-5-5", 100_000, (0.5, 0.625, 1, 0.05, 2.5)),)
OPENAI_TIERS = (
    ("gpt-6-astra", 272_000, (20, 75, 2, 25, 50)),
    ("gpt-6.1-sol", 272_000, (4, 15, 0.2, 5, 10)),
    ("gpt-6.1-terra", 272_000, (2, 7.5, 0.1, 2.5, 5)),
    ("gpt-6-luna", 272_000, (0.2, 0.75, 0.02, 0.25, 0.5)),
    ("gpt-6-sol", 272_000, (4, 15, 0.4, 5, 10)),
    (GPT_FIVE_SIX_SOL, 272_000, (8, 30, 0.8, 10, 20)),
    ("gpt-5.6-terra", 272_000, (4, 18, 0.4, 5, 10)),
    ("gpt-5.6-luna", 272_000, (0.4, 1.8, 0.04, 0.5, 1)),
    ("gpt-5.5", 272_000, (10, 45, 1)),
    ("gpt-5.5-pro", 272_000, (60, 270, None)),
    ("gpt-5.4", 272_000, (5, 22.5, 0.5)),
    ("gpt-5.4-pro", 272_000, (60, 270, None)),
)
GEMINI_TIERS = ((GEMINI_PRO_PREVIEW, 200_000, (4, 18, 0.4)),)

# Model, a usage date, and the page row in effect on it: Gemini 4 Argon's rates
# change on 2026-12-01 and the Flash models' on 2027-01-01.
GEMINI_DATED = (
    (GEMINI_FOUR_ARGON, "2026-11-30", (2, 10, 0.1)),
    (GEMINI_FOUR_ARGON, "2026-12-01", (4, 20, 0.2)),
    ("gemini-3.8-flash", "2026-12-31", (0.75, 3.75, 0.075)),
    ("gemini-3.8-flash", "2027-01-01", (1.5, 7.5, 0.15)),
    ("gemini-3.6-flash", "2026-12-31", (0.75, 3.75, 0.075)),
    ("gemini-3.6-flash", "2027-01-01", (1.5, 7.5, 0.15)),
    (GEMINI_PRO_PREVIEW, "2026-10-29", (2, 12, 0.2)),
)

# Spellings near a row's that resolve nothing: unknown versions, unpublished
# snapshots, arbitrary suffixes and prefixes, partner-platform IDs, models the
# pages no longer price, restricted models with no evidence of an emitted ID,
# and an invented SKU.
CLAUDE_LOOKALIKES = (
    "claude-opus-4-9",
    "claude-opus-6",
    "claude-sonnet-4-7",
    "claude-haiku-4-6",
    "claude-opus-4-7-20260416",
    "claude-opus-4-5-20251102",
    "claude-opus-4-7[1m]",
    "claude-opus-4-7-fast",
    "claude-opus-4-8-v2",
    "anthropic.claude-opus-4-7",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude-haiku-4-5@20251001",
    "claude-opus",
    "opus",
    "CLAUDE-OPUS-4-7",
    " claude-opus-4-7",
    "claude-3-opus-20240229",
    "claude-3-7-sonnet-20250219",
    "claude-3-haiku-20240307",
    "claude-haiku-3-5",
    "claude-mythos-5",
    "claude-mythos-5-1",
    "claude-mythos-preview",
    "",
    protocol.UNKNOWN,
)
OPENAI_LOOKALIKES = (
    "gpt-5.6-pro",
    "gpt-5.6-cyber",
    "gpt-5.5-cyber",
    "gpt-5.7",
    "gpt-6",
    "gpt-6.1",
    "gpt-6.2-sol",
    "gpt-6-terra",
    "gpt-5.6-sol-2026-10-01",
    "gpt-5.5-2026-05-01",
    "gpt-5.55",
    "gpt-5.50",
    "gpt-5.5-mini",
    "gpt-5.3",
    "gpt-5.3-codex-spark",
    "gpt-5.1-codex-maxi",
    "gpt-5.4-chat-latest",
    "chat-latest",
    "GPT-5.5",
    "openai/gpt-5.5",
    "gpt-5.5 ",
)
GEMINI_LOOKALIKES = (
    "gemini-3.7-flash",
    "gemini-4-argon-preview",
    "gemini-3.8-flash-high",
    "gemini-3.1-pro",
    "gemini-4",
    "models/gemini-4-argon",
)


@dataclass(frozen=True)
class ProviderCases:
    """One provider's expected rows: undated ones with their activity, aliases, tiers, and lookalikes."""

    columns: tuple[str, ...]
    rows: tuple[RowCase, ...]
    aliases: Mapping[str, str]
    tiers: tuple[TierCase, ...]
    lookalikes: tuple[str, ...]

    def spellings(self) -> dict[str, str]:
        """Every spelling a listed row answers to, mapped to the row's canonical ID."""
        own = {case[0]: case[0] for case in self.rows}
        return {**own, **self.aliases}

    def is_active(self, model: str) -> bool:
        activity = {case[0]: case[2] for case in self.rows}
        return activity[model]

    def expected_row(self, case: RowCase) -> ExpectedRow:
        """A listed row's canonical ID, the rate map its page row prices with, and its activity."""
        model, page_row, active = case
        return model, page_rates(self.columns, page_row), active

    def expected_tiers(self) -> dict[str, tuple[int, protocol.RateMap]]:
        expected = {}
        for model, above, page_row in self.tiers:
            expected[model] = (above, page_rates(self.columns, page_row))
        return expected


def page_rates(columns: tuple[str, ...], page_row: PageRow) -> protocol.RateMap:
    """The rate map a page row prices with: a dash publishes no rate for its column."""
    published = zip(columns, page_row, strict=False)
    return {column: rate for column, rate in published if rate is not None}


CLAUDE = ProviderCases(CLAUDE_COLUMNS, CLAUDE_ROWS, CLAUDE_ALIASES, CLAUDE_TIERS, CLAUDE_LOOKALIKES)
OPENAI = ProviderCases(OPENAI_COLUMNS, OPENAI_ROWS, OPENAI_ALIASES, OPENAI_TIERS, OPENAI_LOOKALIKES)
# Every Gemini row but one is dated, so its rows are checked by date in
# `GEMINI_DATED` rather than listed here.
GEMINI = ProviderCases(GEMINI_COLUMNS, (), MappingProxyType({}), GEMINI_TIERS, GEMINI_LOOKALIKES)
