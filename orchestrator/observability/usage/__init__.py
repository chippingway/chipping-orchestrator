# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The package API one finished agent run is metered through.

Home of the provider payloads a run is metered from. The owners divide by what
a payload has to be turned into: the JSONL vocabulary and the resilient line
decoder every provider reads through (``protocol``, ``event_stream``); the
price tables and the nested model-name lookup an estimate needs (``prices``,
``model_names``); the per-provider frame decoding and run summary the token
counts come from (``claude_rows``, ``claude_summary``, ``codex_rows``,
``codex_summary``, ``agy_events``, ``agy_summary``); the shell scanning and
command classification a codex skill reference is inferred from (``shell_segments``, ``skill_commands``,
``skills_claude``, ``skills_codex``); and the records and per-provider
reconstruction one timeline is rebuilt into (``trajectory_models``,
``trajectory_claude_blocks``, ``trajectory_claude_stream``,
``trajectory_claude_turns``, ``trajectory_codex``,
``trajectory_codex_items``, ``trajectory_codex_payloads``, ``trajectory_agy``).

This initializer re-exports the narrow public surface (``__all__``): the nine
parsers a caller dispatches through -- dispatch plus the Codex and Claude
parsers for token and cost (``metrics``), skill evidence (``skills``), and the ordered timeline
(``trajectory``) -- plus the six result types they hand back: ``UsageMetrics``
and ``SkillTriggers`` beside the parsers that fill them, and the
``AgentTrajectory`` / ``TrajectoryStep`` / ``SourceItem`` / ``TurnUsage``
quartet on ``trajectory_models``. Each is bound here once, at import, to the
owner's own object rather than a wrapper around it; that binding does not
follow a later patch, so a test intercepting a parser targets the module its
caller imported. Everything else -- the price tables, the protocol keys, the
per-provider decoders -- is reached on its owner, so nothing private is
published here.

The parser is what a tracked run folds its per-issue counters from, so no owner
here may reach the workflow that calls it: the dependency runs the other way,
and a parser is fed a payload rather than an issue.
"""
from orchestrator.observability.usage import (
    metrics as _metrics,
    skills as _skills,
    trajectory as _trajectory,
    trajectory_models as _records,
)

__all__ = (
    "AgentTrajectory",
    "SkillTriggers",
    "SourceItem",
    "TrajectoryStep",
    "TurnUsage",
    "UsageMetrics",
    "parse_agent_skills",
    "parse_agent_trajectory",
    "parse_agent_usage",
    "parse_claude_skills",
    "parse_claude_trajectory",
    "parse_claude_usage",
    "parse_codex_skills",
    "parse_codex_trajectory",
    "parse_codex_usage",
)

UsageMetrics = _metrics.UsageMetrics
parse_agent_usage = _metrics.parse_agent_usage
parse_claude_usage = _metrics.parse_claude_usage
parse_codex_usage = _metrics.parse_codex_usage

SkillTriggers = _skills.SkillTriggers
parse_agent_skills = _skills.parse_agent_skills
parse_claude_skills = _skills.parse_claude_skills
parse_codex_skills = _skills.parse_codex_skills

AgentTrajectory = _records.AgentTrajectory
SourceItem = _records.SourceItem
TrajectoryStep = _records.TrajectoryStep
TurnUsage = _records.TurnUsage
parse_agent_trajectory = _trajectory.parse_agent_trajectory
parse_claude_trajectory = _trajectory.parse_claude_trajectory
parse_codex_trajectory = _trajectory.parse_codex_trajectory
