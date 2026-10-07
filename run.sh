#!/usr/bin/env bash
# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
# Self-restarting orchestrator wrapper. Exits cleanly when the orchestrator
# detects a self-modifying merge so the new code is picked up on next loop.
set -uo pipefail
cd "$(dirname "$0")"

# Ctrl+C / SIGTERM at the wrapper level must not be swallowed by the restart
# loop -- without a trap, a signal that arrives while bash is in `sleep 1` or
# `git pull` just interrupts that command and the loop relaunches the
# orchestrator anyway.
trap 'exit 130' INT
trap 'exit 143' TERM

# Read ORCHESTRATOR_BASE_BRANCH from .env so the wrapper pulls the orchestrator
# repo's own branch (REPO_ROOT) for self-update -- not BASE_BRANCH, which is
# the *target* repo's base branch and may differ (e.g. target=`master` while
# the orchestrator itself ships from `main`).
base_branch="${ORCHESTRATOR_BASE_BRANCH:-}"
if [ -z "$base_branch" ] && [ -f .env ]; then
    base_branch=$(sed -n 's/^[[:space:]]*ORCHESTRATOR_BASE_BRANCH[[:space:]]*=[[:space:]]*//p' .env \
        | head -n1 | tr -d '"' | tr -d "'")
fi
base_branch="${base_branch:-main}"

self_update() {
    # A non-base checkout or a non-fast-forward pull must never stop the wrapper:
    # under a development systemd unit (Restart=always) an exit here degrades
    # into a silent crash loop where the orchestrator never actually runs. Warn
    # loudly and keep the existing working tree -- stale-but-running is strictly
    # better than a restart loop, and the journal warning is the operator's
    # signal to fix the checkout.
    current_branch=$(git branch --show-current 2>/dev/null)
    if [ "$current_branch" != "$base_branch" ]; then
        msg="[$(date -Iseconds)] WARNING: self-update skipped -- running existing code. "
        msg+="Checked-out branch '$current_branch' is not the expected base branch '$base_branch'. "
        msg+="Restore the base checkout to resume self-update."
        echo "$msg" >&2
        return 0
    fi
    git pull --ff-only origin "$base_branch" && return 0
    rc=$?
    msg="[$(date -Iseconds)] WARNING: self-update failed -- running existing code. "
    msg+="'git pull --ff-only origin $base_branch' exited with code $rc. "
    msg+="Resolve the checkout state to resume self-update."
    echo "$msg" >&2
    return 0
}

refresh_dependencies() {
    local dependency_stamp=".venv/.poetry-dependencies"
    local dependency_signature detail msg
    # Only a successful additive install advances the stamp, so failed refreshes
    # retry on each launch and optional groups the operator enabled survive.
    if ! dependency_signature=$(git hash-object -- pyproject.toml poetry.lock 2>/dev/null); then
        detail="Could not fingerprint pyproject.toml and poetry.lock."
    elif [ -f "$dependency_stamp" ] && [ "$(cat "$dependency_stamp")" = "$dependency_signature" ]; then
        return 0
    elif ! command -v poetry >/dev/null 2>&1; then
        detail="The Poetry executable is not on PATH."
    elif ! env -u VIRTUAL_ENV -u CONDA_PREFIX \
        timeout --foreground --kill-after=10s 300s poetry install --no-interaction; then
        detail="'poetry install --no-interaction' failed or timed out (300s limit)."
    elif printf '%s\n' "$dependency_signature" > "$dependency_stamp"; then
        return 0
    else
        detail="Could not record the successful dependency refresh in $dependency_stamp."
    fi
    msg="[$(date -Iseconds)] WARNING: dependency refresh failed -- the environment may be partially updated. "
    msg+="$detail The wrapper will retry before the next launch."
    echo "$msg" >&2
    return 0
}

self_update
while true; do
    refresh_dependencies
    .venv/bin/python -m orchestrator "$@"
    rc=$?
    # 130 = SIGINT, 143 = SIGTERM. The orchestrator exits with these codes
    # when it stops because of an explicit signal, which is the user's "I
    # want this to stop" -- restarting would defeat the Ctrl+C entirely.
    if [ "$rc" -eq 130 ] || [ "$rc" -eq 143 ]; then
        echo "[$(date -Iseconds)] orchestrator exited via signal (code $rc); stopping wrapper."
        exit "$rc"
    fi
    echo "[$(date -Iseconds)] orchestrator exited with code $rc; restarting in 1s..."
    sleep 1
    self_update
done
