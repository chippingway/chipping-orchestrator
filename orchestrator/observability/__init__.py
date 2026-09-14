# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Observation-only domain owners.

Home of the four surfaces that watch a run without steering it: the
project-local analytics sink and everything downstream of it (``analytics``),
the provider-payload parser that turns one finished agent run into tokens and
cost (``usage``), the Streamlit page rendered over the operator's Postgres
target (``dashboard``), and the file-backed trajectory viewer beside it
(``trajectory_viewer``). Each arrives under its own subpackage, and all four
are here whole -- every knob, recorder, prune, read, replay, trajectory write,
panel, chart, theme value, record model, filter, and markup builder is reached
on an owner beneath this tree and nowhere else. Nothing of either page is left
beside it: both ``streamlit run`` targets under ``apps`` compose these owners
directly, so there is no flat module for a caller to reach one through.

Callers import the owner they need, so an initializer here binds nothing
unless the surface it fronts is what a caller asks for by name -- ``usage``
re-exports its parsers and their result types under an ``__all__`` and
``analytics.recording`` the recorders a producer appends through, and every
other initializer stays a marker. Nothing under the tree carries an export
manifest or a resolver hook: a re-export is the owner's own object, bound once
at import rather than resolved per lookup, so the module defining a name stays
where a reader finds it and where a patch has to land.
Two constraints hold for every owner that lands here. Nothing observed is on
the workflow's decision path, so no owner may import the workflow engine, a
stage, or an application entrypoint: the dependency runs one way, and the
pages compose these owners rather than the reverse. And Streamlit and Plotly
live in an optional dependency group, so an owner reaches them inside the
function that renders with them rather than at module scope -- importing
anything here has to work in the default install, which has neither.
"""
