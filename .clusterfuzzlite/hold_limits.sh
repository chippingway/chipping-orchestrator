#!/bin/bash -eu
# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
#
# Holds every run of a packaged target to the libFuzzer limits its options
# file sets. ClusterFuzzLite passes the `[libfuzzer]` settings of
# `<target>.options` when it fuzzes or reproduces, but its corpus pruning starts
# the merge with none, which would leave inputs without the size cap, the
# memory limit, and the per-input timeout the targets are held to.
#
# `compile_python_fuzzer` writes each target's wrapper to end in
# `$this_dir/<target>.pkg $@`. This writes the limits between the two, so they
# reach every run, and a flag the runner passes still comes after them and wins
# for that run. A wrapper ending any other way fails the build rather than
# shipping a target without its limits.
#
# Usage: hold_limits.sh <target>.options <packaged wrapper>

options=$1
wrapper=$2
package="$(basename "$wrapper").pkg"
run_line="\$this_dir/$package \$@"

limits=$(awk -F ' = ' '/^[a-z_]+ = [0-9]+$/ { printf "-%s=%s ", $1, $2 }' "$options")
if [[ -z "$limits" ]]; then
  echo "hold_limits.sh: $options sets no limits" >&2
  exit 1
fi
script=$(<"$wrapper")
if [[ "$script" != *"$run_line" ]]; then
  echo "hold_limits.sh: $wrapper does not end in $run_line" >&2
  exit 1
fi
printf '%s\n' "${script%"$run_line"}\$this_dir/$package $limits\$@" > "$wrapper"
