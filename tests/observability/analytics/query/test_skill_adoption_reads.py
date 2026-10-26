# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How many sessions that could have used a skill actually did."""
from __future__ import annotations

import unittest
from datetime import UTC, datetime

from orchestrator.observability.analytics.query.skill_reads import get_skill_adoption
from tests.observability.analytics.analytics_assertions import assert_column_values, assert_row_fields
from tests.observability.analytics.query.query_fake_driver import (
    FakeConnect,
    FakeConnection,
)
from tests.observability.analytics.query.query_test_support import configured_db_url

_STAGE_ENTER = "stage_enter"

_BASE_SCAN = "FROM analytics_events"

_ROLLUP_SCAN = "FROM analytics_daily_rollup"

_VIEW_SCAN = "FROM analytics_agent_runs"

_EXIT_SCAN = "event = 'agent_exit'"

# The fragment unique to each of the three scans: only the window one reads the
# incidental references, only the history one reads the offered set beside the
# loads, and only the catalog one is pinned to the repository-level record.
_WINDOW_SCAN = "skills_incidental"

_HISTORY_SCAN = "AS skills_available, extras -> 'skills_triggered'"

_CATALOG_SCAN = "event = 'repo_skill_catalog'"

_LEVEL_FIELD = "extras -> 'skill_levels'"

_STAGE_SELECTION = "stage IN"

_UNKNOWN = "unknown"

_CLAUDE = "claude"

_DEVELOPER = "developer"

_REPO = "owner/repo"

_OTHER_REPO = "owner/other"

_DEVELOP = "develop"

_REVIEW = "review"

_DEVELOP_ONLY = (_DEVELOP,)

_PROJECT = "project"

_USER = "user"

_ANCHOR = "anchor"

_SESSION_ONE = "s1"

_DRILL_DOWN_ISSUE = 551

_YEAR = 2026

_WINDOW_START = datetime(_YEAR, 6, 1, tzinfo=UTC)

_WINDOW_END = datetime(_YEAR, 6, 24, tzinfo=UTC)

# The two selections that leave a scan pinned to `agent_exit` nothing to match.
_EXIT_FREE_SELECTIONS = ([_STAGE_ENTER], [])

# One `repo_skill_catalog` scan row is `(repo, offered names, name-to-level
# map)`.
_DEVELOP_CATALOG = ((_REPO, _DEVELOP_ONLY, {_DEVELOP: _PROJECT}),)

# Three catalogs that settle nothing about `develop`: one where this repository
# never offered the name -- and another repository's definition of it is not
# this one's -- one where it offers the name at two levels, and one whose
# record classified nothing, which no current catalog scan writes.
_UNSETTLED_CATALOGS = (
    ("classified nothing", ((_REPO, _DEVELOP_ONLY, None),)),
    (
        "never offered",
        (
            (_REPO, (_REVIEW,), {_REVIEW: _PROJECT}),
            (_OTHER_REPO, _DEVELOP_ONLY, {_DEVELOP: _USER}),
        ),
    ),
    (
        "offered at two levels",
        (
            (_REPO, _DEVELOP_ONLY, {_DEVELOP: _PROJECT}),
            (_REPO, _DEVELOP_ONLY, {_DEVELOP: _USER}),
        ),
    ),
)

# Four resume-anchored sessions as `(anchor, runs, loads)`, chosen so the
# counters a cell carries come out different from one another: a chain of runs
# adopts once, and only the runs that loaded the skill leave a load row.
_SESSION_CHAINS = (
    ("one-load", 3, 1),
    ("two-loads", 3, 2),
    ("quiet-long", 3, 0),
    ("quiet-short", 2, 0),
)

# One entry per run those chains describe: the anchor it belongs to, and
# whether that run loaded the skill.
_CHAIN_RUNS = tuple(
    (anchor, run < loads)
    for anchor, runs, loads in _SESSION_CHAINS
    for run in range(runs)
)

# What the chains add up to on the window side: 3 + 3 + 3 + 2 invocations.
_CHAIN_INVOCATIONS = 11

# The claude cohort one repository reports: 26 sessions were offered `develop`
# with no source directory named for it, and 3 of them loaded it.
_OFFERED_SESSIONS = 26

_ADOPTING_SESSIONS = 3

# One run per session, the first `_ADOPTING_SESSIONS` of which loaded the skill.
_BLANK_LEVEL_RUNS = tuple(
    (row_id, row_id <= _ADOPTING_SESSIONS)
    for row_id in range(1, _OFFERED_SESSIONS + 1)
)


def _window_row(**row_fields: object) -> tuple:
    """A reporting-window `agent_exit` scan row (identity + skill names).

    `levels` is the run's recorded name-to-source-level map -- a codex run
    reports one level per offered skill. Omitting it models a run that
    reported none, as a claude run does, whose names arrive unclassified.
    """
    row = [
        row_fields.get("repo", _REPO),
        row_fields.get("role", _DEVELOPER),
        row_fields.get("backend", _CLAUDE),
        row_fields.get("resume"),
        row_fields.get("session"),
        row_fields["row_id"],
        row_fields.get("triggered"),
        row_fields.get("incidental"),
        row_fields.get("levels"),
    ]
    return tuple(row)


def _history_row(**row_fields: object) -> tuple:
    """A before-window-end `agent_exit` scan row (availability + loads).

    Omitting `available` models a run that reported no offered set, whose
    record carries no `skills_available` key at all.
    """
    row = [
        row_fields.get("repo", _REPO),
        row_fields.get("role", _DEVELOPER),
        row_fields.get("backend", _CLAUDE),
        row_fields.get("resume"),
        row_fields.get("session"),
        row_fields["row_id"],
        row_fields.get("available"),
        row_fields.get("triggered"),
        row_fields.get("levels"),
    ]
    return tuple(row)


def _assert_one_cell(
    test_case,
    window: tuple,
    history: tuple,
    catalog: tuple = (),
    **expected_fields: object,
) -> None:
    """Run the read over its scans and check the one cell it answers with."""
    conn = FakeConnection(rows_for={
        _CATALOG_SCAN: catalog,
        _WINDOW_SCAN: window,
        _HISTORY_SCAN: history,
    })
    with configured_db_url():
        rows = get_skill_adoption(connect=conn.as_connect)
    assert_column_values(
        test_case,
        rows,
        {name: [expected] for name, expected in expected_fields.items()},
    )


# Both scans' rows for the declared chains. Every run carries its own
# `session_id` and its chain's `resume_session_id`, so a chain reads as one
# logical session however many runs it holds.
_CHAIN_WINDOW = tuple(
    _window_row(
        row_id=row_id,
        resume=anchor,
        session=f"run-{row_id}",
        triggered=_DEVELOP_ONLY if loaded else None,
    )
    for row_id, (anchor, loaded) in enumerate(_CHAIN_RUNS, start=1)
)

_CHAIN_HISTORY = tuple(
    _history_row(
        row_id=row_id,
        resume=anchor,
        session=f"run-{row_id}",
        available=_DEVELOP_ONLY,
        triggered=_DEVELOP_ONLY if loaded else None,
    )
    for row_id, (anchor, loaded) in enumerate(_CHAIN_RUNS, start=1)
)

# Both scans' rows for the blank-level cohort: nothing on either side names a
# source directory, which is what a claude stream records.
_BLANK_LEVEL_WINDOW = tuple(
    _window_row(
        row_id=row_id,
        session=f"blank-{row_id}",
        triggered=_DEVELOP_ONLY if loaded else None,
    )
    for row_id, loaded in _BLANK_LEVEL_RUNS
)

_BLANK_LEVEL_HISTORY = tuple(
    _history_row(
        row_id=row_id,
        session=f"blank-{row_id}",
        available=_DEVELOP_ONLY,
        triggered=_DEVELOP_ONLY if loaded else None,
    )
    for row_id, loaded in _BLANK_LEVEL_RUNS
)

# One session whose in-window run only resumed the earlier run that loaded the
# skill, so the load reaches the aggregate through the history scan alone.
_PRE_WINDOW_SCANS = (
    (_window_row(row_id=2, resume="sess-A", session="sess-B"),),
    (
        _history_row(
            row_id=1,
            session="sess-A",
            available=_DEVELOP_ONLY,
            triggered=_DEVELOP_ONLY,
        ),
        _history_row(
            row_id=2,
            resume="sess-A",
            session="sess-B",
            available=_DEVELOP_ONLY,
        ),
    ),
)


class SkillAdoptionScanTest(unittest.TestCase):
    """What the read settles before dialing, and what each scan reaches."""

    def test_an_unconfigured_database_answers_empty(self) -> None:
        with configured_db_url(None):
            self.assertEqual(get_skill_adoption(connect=FakeConnect()), [])

    def test_a_selection_without_exits_stops(self) -> None:
        # The two session scans pin `agent_exit` themselves, so a selection
        # those rows fall outside of is answered without opening a socket --
        # the catalog scan they resolve against included.
        for events in _EXIT_FREE_SELECTIONS:
            conn = FakeConnection()
            with self.subTest(events=events):
                with configured_db_url():
                    empty = get_skill_adoption(events=events, connect=conn.as_connect)
                self.assertEqual(empty, [])
                self.assertEqual(conn.executed, [])

    def test_the_history_drops_start_and_stage(self) -> None:
        # A skill loaded in an earlier stage or before the window still means
        # the session adopted it, so the history scan keeps only the end bound
        # -- a later load must not leak backward into this window's answer.
        conn = FakeConnection()
        with configured_db_url():
            get_skill_adoption(
                start=_WINDOW_START,
                end=_WINDOW_END,
                stages=["implementing"],
                connect=conn.as_connect,
            )
        window_sql, window_bindings = conn.executed[1]
        history_sql, history_bindings = conn.executed[2]
        self.assertIn("ts >= %s", window_sql)
        self.assertIn(_STAGE_SELECTION, window_sql)
        self.assertIn(_WINDOW_START, window_bindings)
        self.assertNotIn("ts >= %s", history_sql)
        self.assertNotIn(_STAGE_SELECTION, history_sql)
        self.assertIn("ts < %s", history_sql)
        self.assertIn(_WINDOW_END, history_bindings)
        self.assertNotIn(_WINDOW_START, history_bindings)

    def test_the_session_selection_spares_the_catalog(self) -> None:
        # A catalog record is a repository-level fact -- no issue, no stage,
        # and written whenever the catalog was last scanned -- so pushing the
        # session selection onto it would drop every row and leave the level
        # fill with nothing to read.
        conn = FakeConnection()
        with configured_db_url():
            get_skill_adoption(
                issue=_DRILL_DOWN_ISSUE,
                stages=["implementing"],
                connect=conn.as_connect,
            )
        catalog_sql, catalog_bindings = conn.executed[0]
        window_sql, window_bindings = conn.executed[1]
        self.assertNotIn("issue = %s", catalog_sql)
        self.assertNotIn(_STAGE_SELECTION, catalog_sql)
        self.assertEqual(catalog_bindings, ())
        self.assertIn("issue = %s", window_sql)
        self.assertIn(_STAGE_SELECTION, window_sql)
        self.assertIn(_DRILL_DOWN_ISSUE, window_bindings)

    def test_every_scan_stays_on_the_events_table(self) -> None:
        # The `extras` blob these fields live in is carried by neither the
        # rollup nor the agent-run view, and the repository filter narrows
        # every scan so evidence from elsewhere cannot join the aggregate.
        conn = FakeConnection()
        with configured_db_url():
            get_skill_adoption(repo=_REPO, connect=conn.as_connect)
        for scan_sql, bindings in conn.executed:
            self.assertIn(_BASE_SCAN, scan_sql)
            # Every scan reads the recorded levels beside the names it
            # gathers, since a cell is filed under the two together.
            self.assertIn(_LEVEL_FIELD, scan_sql)
            self.assertIn(_REPO, bindings)
            self.assertNotIn(_ROLLUP_SCAN, scan_sql)
            self.assertNotIn(_VIEW_SCAN, scan_sql)
        # Three scans in the order the read runs them: the catalog one pins
        # its own repository-level record, the two session ones the finished
        # run they each project a different half of.
        self.assertEqual(
            [_EXIT_SCAN in executed_sql for executed_sql, _ in conn.executed],
            [False, True, True],
        )


class SkillAdoptionSessionTest(unittest.TestCase):
    """Which rows are one session, and which are several."""

    def test_a_resumed_chain_is_one_session(self) -> None:
        # Two runs sharing a resume id adopt once between them, while both
        # their window invocations and load rows still count.
        _assert_one_cell(
            self,
            (
                _window_row(row_id=1, resume=_ANCHOR, session="a", triggered=_DEVELOP_ONLY),
                _window_row(row_id=2, resume=_ANCHOR, session="b", triggered=_DEVELOP_ONLY),
            ),
            (
                _history_row(
                    row_id=1,
                    resume=_ANCHOR,
                    session="a",
                    available=_DEVELOP_ONLY,
                    triggered=_DEVELOP_ONLY,
                ),
                _history_row(
                    row_id=2,
                    resume=_ANCHOR,
                    session="b",
                    available=_DEVELOP_ONLY,
                    triggered=_DEVELOP_ONLY,
                ),
            ),
            sessions=1,
            adopted=1,
            invocations=2,
            load_rows=2,
        )

    def test_every_idless_row_is_its_own_session(self) -> None:
        # A row carrying no id falls back to its primary key rather than
        # merging into one anonymous bucket: three sessions, two adopting.
        _assert_one_cell(
            self,
            (
                _window_row(row_id=1, triggered=_DEVELOP_ONLY),
                _window_row(row_id=2, triggered=_DEVELOP_ONLY),
                _window_row(row_id=3),
            ),
            (
                _history_row(row_id=1, available=_DEVELOP_ONLY, triggered=_DEVELOP_ONLY),
                _history_row(row_id=2, available=_DEVELOP_ONLY, triggered=_DEVELOP_ONLY),
                _history_row(row_id=3, available=_DEVELOP_ONLY),
            ),
            sessions=3,
            adopted=2,
            invocations=3,
            load_rows=2,
        )

    def test_a_pre_window_load_counts_as_adoption(self) -> None:
        # The in-window run resumed a session whose earlier run loaded the
        # skill, so the session is adopted even though the window shows no
        # load row of its own.
        _assert_one_cell(
            self,
            *_PRE_WINDOW_SCANS,
            sessions=1,
            adopted=1,
            invocations=1,
            load_rows=0,
        )

    def test_an_unrecorded_cohort_label_reads_unknown(self) -> None:
        _assert_one_cell(
            self,
            (
                _window_row(
                    row_id=1,
                    role=None,
                    backend=None,
                    session=_SESSION_ONE,
                    triggered=_DEVELOP_ONLY,
                ),
            ),
            (
                _history_row(
                    row_id=1,
                    role=None,
                    backend=None,
                    session=_SESSION_ONE,
                    available=_DEVELOP_ONLY,
                    triggered=_DEVELOP_ONLY,
                ),
            ),
            agent_role=_UNKNOWN,
            backend=_UNKNOWN,
        )


class SkillAdoptionDenominatorTest(unittest.TestCase):
    """Which sessions count as offered a skill, and which definition of it."""

    def test_a_name_at_two_levels_stays_two_cells(self) -> None:
        # A repository's own `develop` and a global one of that name are two
        # definitions, so the session offered each is counted against the
        # level it was offered at rather than into one blended ratio.
        conn = FakeConnection(rows_for={
            _WINDOW_SCAN: (
                _window_row(
                    row_id=1,
                    session="project-side",
                    triggered=_DEVELOP_ONLY,
                    levels={_DEVELOP: _PROJECT},
                ),
                _window_row(
                    row_id=2,
                    session="user-side",
                    triggered=_DEVELOP_ONLY,
                    levels={_DEVELOP: _USER},
                ),
            ),
            _HISTORY_SCAN: (
                _history_row(
                    row_id=1,
                    session="project-side",
                    available=_DEVELOP_ONLY,
                    triggered=_DEVELOP_ONLY,
                    levels={_DEVELOP: _PROJECT},
                ),
                _history_row(
                    row_id=2,
                    session="user-side",
                    available=_DEVELOP_ONLY,
                    triggered=_DEVELOP_ONLY,
                    levels={_DEVELOP: _USER},
                ),
            ),
        })
        with configured_db_url():
            rows = get_skill_adoption(connect=conn.as_connect)
        by_level = {row.level: row for row in rows}
        self.assertEqual(sorted(by_level), [_PROJECT, _USER])
        for level, row in by_level.items():
            with self.subTest(level=level):
                assert_row_fields(
                    self,
                    row,
                    {"skill": _DEVELOP, "sessions": 1, "adopted": 1, "load_rows": 1},
                )

    def test_an_unclassified_session_reads_unknown(self) -> None:
        # A session that recorded no levels -- a claude run, whose stream
        # names no source directory -- and whose repository offers no catalog
        # to fill them from files its offer and its load under the same
        # `unknown`, so the load still counts as adoption of what it was
        # offered.
        _assert_one_cell(
            self,
            (_window_row(row_id=1, session=_SESSION_ONE, triggered=_DEVELOP_ONLY),),
            (
                _history_row(
                    row_id=1,
                    session=_SESSION_ONE,
                    available=_DEVELOP_ONLY,
                    triggered=_DEVELOP_ONLY,
                ),
            ),
            level=_UNKNOWN,
            sessions=1,
            adopted=1,
        )

    def test_a_load_is_never_its_own_offer(self) -> None:
        # A session none of whose rows reported an offered set has unknown
        # availability, so its load joins no denominator -- not even of the
        # skill it loaded -- while staying a visible diagnostic beside the
        # session that was offered the skill.
        _assert_one_cell(
            self,
            (
                _window_row(row_id=1, session="unreported", triggered=_DEVELOP_ONLY),
                _window_row(row_id=2, session="offered", triggered=_DEVELOP_ONLY),
            ),
            (
                _history_row(row_id=1, session="unreported", triggered=_DEVELOP_ONLY),
                _history_row(
                    row_id=2,
                    session="offered",
                    available=_DEVELOP_ONLY,
                    triggered=_DEVELOP_ONLY,
                ),
            ),
            sessions=1,
            adopted=1,
            invocations=2,
            load_rows=2,
        )

    def test_unknown_availability_has_no_rate(self) -> None:
        # A window whose sessions only ever loaded the skill reports the loads
        # and nothing it could divide them by, rather than a 100% adoption.
        _assert_one_cell(
            self,
            (_window_row(row_id=1, session=_SESSION_ONE, triggered=_DEVELOP_ONLY),),
            (_history_row(row_id=1, session=_SESSION_ONE, triggered=_DEVELOP_ONLY),),
            skill=_DEVELOP,
            sessions=0,
            adopted=0,
            load_rows=1,
            adoption_rate=float(0),
        )

    def test_the_four_counters_stay_apart(self) -> None:
        # Sessions offered, sessions adopting, window invocations, and load
        # rows each answer a different question, so a cohort of chained runs
        # has to report four different numbers rather than one restated.
        _assert_one_cell(
            self,
            _CHAIN_WINDOW,
            _CHAIN_HISTORY,
            repo=_REPO,
            skill=_DEVELOP,
            agent_role=_DEVELOPER,
            backend=_CLAUDE,
            sessions=4,
            adopted=2,
            invocations=_CHAIN_INVOCATIONS,
            load_rows=3,
            adoption_rate=2 / 4,
        )

    def test_an_incidental_stays_a_diagnostic(self) -> None:
        # A path-only mention never becomes availability or adoption, but its
        # own cell stays visible against the cohort's run count -- which is
        # how a skill nobody was offered still shows up as noticed.
        conn = FakeConnection(rows_for={
            _WINDOW_SCAN: (
                _window_row(
                    row_id=1,
                    session=_SESSION_ONE,
                    triggered=_DEVELOP_ONLY,
                    incidental=(_REVIEW,),
                ),
            ),
            _HISTORY_SCAN: (
                _history_row(
                    row_id=1,
                    session=_SESSION_ONE,
                    available=_DEVELOP_ONLY,
                    triggered=_DEVELOP_ONLY,
                ),
            ),
        })
        with configured_db_url():
            rows = get_skill_adoption(connect=conn.as_connect)
        by_skill = {row.skill: row for row in rows}
        assert_row_fields(
            self,
            by_skill[_DEVELOP],
            {"sessions": 1, "adopted": 1, "load_rows": 1, "incidental": 0},
        )
        assert_row_fields(
            self,
            by_skill[_REVIEW],
            {"sessions": 0, "adopted": 0, "invocations": 1, "incidental": 1},
        )


class SkillAdoptionProvenanceTest(unittest.TestCase):
    """Which level a session that named none is counted at, and which not."""

    def test_one_offered_level_fills_a_blank_cohort(self) -> None:
        # A claude stream names no source directory, so a session's offer and
        # its load both arrive unclassified and would report as a
        # `develop / unknown` cell of their own. The repository offers
        # `develop` at exactly one level, so the whole cohort reads as that
        # one cell -- 3 adopting of 26 available -- with no duplicate beside
        # it, which the single-column expectations below pin.
        _assert_one_cell(
            self,
            _BLANK_LEVEL_WINDOW,
            _BLANK_LEVEL_HISTORY,
            catalog=_DEVELOP_CATALOG,
            skill=_DEVELOP,
            level=_PROJECT,
            sessions=_OFFERED_SESSIONS,
            adopted=_ADOPTING_SESSIONS,
            invocations=_OFFERED_SESSIONS,
            load_rows=_ADOPTING_SESSIONS,
            adoption_rate=_ADOPTING_SESSIONS / _OFFERED_SESSIONS,
        )

    def test_every_evidence_category_is_filled(self) -> None:
        # The window load, the incidental reference beside it, and the
        # session's historical offer and load all take the same fill: filling
        # the loads and leaving the offers alone would strand the session
        # outside the denominator it belongs in, and sparing the incidental
        # would leave a noticed skill in an `unknown` row of its own.
        conn = FakeConnection(rows_for={
            _CATALOG_SCAN: (
                (_REPO, (_DEVELOP, _REVIEW), dict.fromkeys((_DEVELOP, _REVIEW), _PROJECT)),
            ),
            _WINDOW_SCAN: (
                _window_row(
                    row_id=1,
                    session=_SESSION_ONE,
                    triggered=_DEVELOP_ONLY,
                    incidental=(_REVIEW,),
                ),
            ),
            _HISTORY_SCAN: (
                _history_row(
                    row_id=1,
                    session=_SESSION_ONE,
                    available=_DEVELOP_ONLY,
                    triggered=_DEVELOP_ONLY,
                ),
            ),
        })
        with configured_db_url():
            rows = get_skill_adoption(connect=conn.as_connect)
        cells = {
            (row.skill, row.level): (row.sessions, row.adopted, row.incidental)
            for row in rows
        }
        self.assertEqual(cells, {
            (_DEVELOP, _PROJECT): (1, 1, 0),
            (_REVIEW, _PROJECT): (0, 0, 1),
        })

    def test_a_history_only_load_is_filled_too(self) -> None:
        # Evidence the window scan never sees takes the same fill, so a
        # session whose earlier run loaded the skill is adopted in the cell
        # its offer landed in rather than in an `unknown` one beside it.
        _assert_one_cell(
            self,
            *_PRE_WINDOW_SCANS,
            catalog=_DEVELOP_CATALOG,
            level=_PROJECT,
            sessions=1,
            adopted=1,
            load_rows=0,
        )

    def test_a_recorded_level_outranks_the_catalog(self) -> None:
        # What the session itself observed is never overwritten, so a globally
        # installed `develop` its rows named `user` is counted there even
        # where the repository checks in a `develop` of its own.
        _assert_one_cell(
            self,
            (
                _window_row(
                    row_id=1,
                    session=_SESSION_ONE,
                    triggered=_DEVELOP_ONLY,
                    levels={_DEVELOP: _USER},
                ),
            ),
            (
                _history_row(
                    row_id=1,
                    session=_SESSION_ONE,
                    available=_DEVELOP_ONLY,
                    triggered=_DEVELOP_ONLY,
                    levels={_DEVELOP: _USER},
                ),
            ),
            catalog=_DEVELOP_CATALOG,
            level=_USER,
            sessions=1,
            adopted=1,
        )

    def test_an_unsettled_catalog_stays_unknown(self) -> None:
        # A name this repository never offered has no definition to file the
        # session under, and the level another repository classified it at is
        # not one either; a name offered at two levels is a choice between
        # definitions rather than a fallback; and a record that classified
        # nothing names no level at all. Each keeps the one spelling an
        # operator can look up, and the offer and the load keep meeting there.
        for catalog_case, catalog in _UNSETTLED_CATALOGS:
            with self.subTest(catalog=catalog_case):
                _assert_one_cell(
                    self,
                    (
                        _window_row(
                            row_id=1,
                            session=_SESSION_ONE,
                            triggered=_DEVELOP_ONLY,
                        ),
                    ),
                    (
                        _history_row(
                            row_id=1,
                            session=_SESSION_ONE,
                            available=_DEVELOP_ONLY,
                            triggered=_DEVELOP_ONLY,
                        ),
                    ),
                    catalog=catalog,
                    skill=_DEVELOP,
                    level=_UNKNOWN,
                    sessions=1,
                    adopted=1,
                )


if __name__ == "__main__":
    unittest.main()
