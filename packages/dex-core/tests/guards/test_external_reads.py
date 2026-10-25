"""GHSA-f3jf: the query firewall reaches nothing the cache did not profile.

Two holes, closed together. A function that reads a file, a URL or another
database passed the shape check, because the shape check judged statements and
not calls. And a subquery outside the projection (WHERE, EXISTS, IN, a join's ON)
was never resolved against the cache, so a table nobody profiled could be read as
a filter. Pure static analysis over a hand-built cache, like the decision matrix.
"""

from __future__ import annotations

import pytest

from exmergo_dex_core.cache import ColumnProfile, Dataset, DexCache, PIIFlag
from exmergo_dex_core.config import QueryLimits
from exmergo_dex_core.guards.execution import guarded_statement_verdict
from exmergo_dex_core.guards.query_firewall import QueryRefusedError, inspect_query
from exmergo_dex_core.guards.sql_guard import (
    NotSelectOnlyError,
    RefusalReason,
    assert_select_only,
)

LIMITS = QueryLimits()


@pytest.fixture
def cache() -> DexCache:
    return DexCache(
        datasets=[
            Dataset(
                identifier="db.main.T",
                columns=[
                    ColumnProfile(name="ID", data_type="INTEGER"),
                    ColumnProfile(
                        name="EMAIL",
                        data_type="VARCHAR",
                        pii=PIIFlag(category="email", confidence=0.95),
                    ),
                ],
            ),
            Dataset(
                identifier="db.main.U",
                columns=[ColumnProfile(name="UID", data_type="INTEGER")],
            ),
            Dataset(identifier="db.main.UNPROFILED"),
        ]
    )


def _refusal(sql: str, cache: DexCache, dialect: str = "duckdb") -> str:
    with pytest.raises(QueryRefusedError) as excinfo:
        inspect_query(sql, cache, LIMITS, dialect=dialect)
    return str(excinfo.value)


# --- the advisory's table, row by row -------------------------------------------


@pytest.mark.parametrize(
    ("dialect", "sql", "named"),
    [
        (
            "postgres",
            "SELECT pg_read_file('/etc/passwd') AS x FROM db.main.T",
            "pg_read_file",
        ),
        (
            "duckdb",
            "SELECT ID FROM db.main.T WHERE ID IN (SELECT 1 FROM db.main.NOT_CACHED)",
            "NOT_CACHED",
        ),
        (
            "duckdb",
            "SELECT ID FROM db.main.T WHERE EXISTS "
            "(SELECT 1 FROM read_csv('/etc/passwd'))",
            "read_csv",
        ),
        (
            "clickhouse",
            "SELECT ID FROM db.main.T WHERE ID IN "
            "(SELECT 1 FROM url('http://attacker.example/x','CSV','a Int8'))",
            "url",
        ),
        (
            "clickhouse",
            "SELECT ID FROM db.main.T WHERE ID IN "
            "(SELECT 1 FROM remote('10.0.0.5', system.one))",
            "remote",
        ),
        ("duckdb", "SELECT * FROM read_text('/etc/passwd')", "read_text"),
        ("clickhouse", "SELECT * FROM file('/etc/passwd')", "file"),
    ],
)
def test_every_row_of_the_advisory_is_refused(dialect, sql, named, cache):
    assert named in _refusal(sql, cache, dialect)


def test_the_shape_check_names_the_function_and_the_reason():
    with pytest.raises(NotSelectOnlyError) as excinfo:
        assert_select_only("SELECT pg_read_file('/etc/passwd')", dialect="postgres")
    assert excinfo.value.reason is RefusalReason.UNAPPROVED_FUNCTION
    assert "pg_read_file" in str(excinfo.value)


# --- each denied family, wherever it sits ----------------------------------------

DENIED = [
    ("postgres", "pg_read_binary_file('/etc/passwd')"),
    ("postgres", "pg_stat_file('/etc/passwd')"),
    ("postgres", "pg_ls_dir('/')"),
    ("postgres", "lo_import('/etc/passwd')"),
    ("postgres", "dblink('host=x', 'select 1')"),
    ("postgres", "query_to_xml('select * from secrets', true, true, '')"),
    ("postgres", "set_config('search_path', 'x', false)"),
    ("duckdb", "read_csv_auto('/etc/passwd')"),
    ("duckdb", "read_json('/x.json')"),
    ("duckdb", "read_parquet('s3://bucket/x.parquet')"),
    ("duckdb", "read_blob('/etc/passwd')"),
    ("duckdb", "glob('/home/*')"),
    ("duckdb", "getenv('AWS_SECRET_ACCESS_KEY')"),
    ("duckdb", "query('select * from secrets')"),
    ("duckdb", "postgres_scan('host=x', 'public', 't')"),
    ("duckdb", "sqlite_scan('/x.db', 't')"),
    ("clickhouse", "s3('https://bucket/x.csv')"),
    ("clickhouse", "s3Cluster('c', 'https://bucket/x.csv')"),
    ("clickhouse", "remoteSecure('10.0.0.5', system.one)"),
    ("clickhouse", "hdfs('hdfs://x/y', 'CSV', 'a Int8')"),
    ("clickhouse", "mysql('h:3306', 'db', 't', 'u', 'p')"),
    ("clickhouse", "postgresql('h:5432', 'db', 't', 'u', 'p')"),
    ("clickhouse", "jdbc('jdbc:x', 't')"),
    ("clickhouse", "executable('x.sh', 'CSV', 'a Int8')"),
    ("clickhouse", "merge('db', '^secret')"),
    ("clickhouse", "icebergS3('https://bucket/x')"),
    ("clickhouse", "azureBlobStorage('x', 'c', 'b')"),
    ("bigquery", "EXTERNAL_QUERY('conn', 'select 1')"),
    ("databricks", "read_files('/Volumes/x')"),
    ("databricks", "http_request(conn => 'x', method => 'GET', path => '/')"),
    ("snowflake", "INFER_SCHEMA(LOCATION => '@stage')"),
]


@pytest.mark.parametrize(("dialect", "call"), DENIED)
@pytest.mark.parametrize(
    "template",
    [
        "SELECT {call} AS x FROM db.main.T",
        "SELECT ID FROM db.main.T WHERE ID IN (SELECT {call})",
        "SELECT * FROM {call}",
    ],
    ids=["projection", "where-subquery", "from"],
)
def test_each_external_read_is_refused_wherever_it_sits(dialect, call, template, cache):
    assert "not permitted" in _refusal(template.format(call=call), cache, dialect)


@pytest.mark.parametrize(("dialect", "call"), DENIED)
def test_the_shape_check_refuses_each_one_with_the_function_reason(dialect, call):
    with pytest.raises(NotSelectOnlyError) as excinfo:
        assert_select_only(f"SELECT {call} AS x", dialect=dialect)
    assert excinfo.value.reason is RefusalReason.UNAPPROVED_FUNCTION


@pytest.mark.parametrize(
    ("dialect", "sql"),
    [
        ("duckdb", "SELECT LOWER(CAST(ID AS VARCHAR)), ROUND(1.5) FROM db.main.T"),
        ("duckdb", "SELECT ID, COUNT(*) FROM db.main.T GROUP BY ID"),
        ("clickhouse", "SELECT uniqExact(ID), deltaSum(ID) FROM db.main.T"),
        ("postgres", "SELECT REPLACE('a', 'b', 'c'), LOWER('X')"),
    ],
)
def test_ordinary_functions_are_untouched(dialect, sql, cache):
    inspect_query(sql, cache, LIMITS, dialect=dialect)


def test_a_dbt_model_reading_parquet_is_a_warning_not_a_refusal():
    """A dbt-duckdb model reading a file is ordinary work, run by dbt under the
    user's own profile, so the authoring check says so instead of refusing."""

    from exmergo_dex_core.transform.validate import _assert_query_only

    warnings = _assert_query_only(
        "models/staging/stg_events.sql",
        "select * from read_parquet('data/events/*.parquet')",
        "model",
    )
    assert len(warnings) == 1
    assert "read_parquet" in warnings[0]


def test_a_guarded_build_keeps_its_own_function_policy():
    verdict = guarded_statement_verdict(
        "select * from read_parquet('x.parquet')", node="m", dialect="duckdb"
    )
    assert verdict.allowed


# --- subqueries outside the projection -------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT ID FROM db.main.T WHERE ID = (SELECT MAX(UID) FROM db.main.NOT_CACHED)",
        "SELECT ID FROM db.main.T WHERE EXISTS (SELECT 1 FROM db.main.NOT_CACHED)",
        "SELECT ID FROM db.main.T WHERE ID IN (SELECT 1 FROM db.main.UNPROFILED)",
        "SELECT ID, COUNT(*) FROM db.main.T GROUP BY ID "
        "HAVING COUNT(*) > (SELECT COUNT(*) FROM db.main.NOT_CACHED)",
        "SELECT t.ID FROM db.main.T t JOIN db.main.U u "
        "ON u.UID IN (SELECT 1 FROM db.main.NOT_CACHED)",
        "SELECT ID FROM db.main.T ORDER BY (SELECT MAX(1) FROM db.main.NOT_CACHED)",
        "SELECT ID FROM db.main.T WHERE ID IN "
        "(SELECT UID FROM db.main.U WHERE UID IN (SELECT 1 FROM db.main.NOT_CACHED))",
        "SELECT ID FROM db.main.T WHERE ID IN "
        "(SELECT UID FROM db.main.U UNION SELECT 1 FROM db.main.NOT_CACHED)",
        "SELECT ID FROM db.main.T WHERE ID IN (SELECT 1 FROM '/etc/passwd')",
    ],
)
def test_an_uncached_table_is_refused_in_any_subquery(sql, cache):
    message = _refusal(sql, cache)
    assert "cache" in message or "not profiled" in message


def test_a_subquery_cannot_name_an_unknown_column(cache):
    assert "NOPE" in _refusal(
        "SELECT ID FROM db.main.T WHERE ID IN (SELECT NOPE FROM db.main.U)", cache
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT ID FROM db.main.T t WHERE EXISTS "
        "(SELECT 1 FROM db.main.U u WHERE u.UID = t.ID)",
        "SELECT ID FROM db.main.T t WHERE ID IN (SELECT t.ID FROM db.main.U u)",
        "WITH c AS (SELECT UID AS ID FROM db.main.U) "
        "SELECT ID FROM db.main.T WHERE ID IN (SELECT ID FROM c)",
        "SELECT ID FROM db.main.T WHERE ID IN (SELECT UID FROM db.main.U)",
        "SELECT ID FROM db.main.T WHERE ID IN (SELECT ID FROM db.main.T)",
        # A flagged column used as a filter inside a subquery is a filter, as at
        # the top level: values flow in, none flow out.
        "SELECT ID FROM db.main.T WHERE ID IN "
        "(SELECT ID FROM db.main.T WHERE EMAIL LIKE '%@x.com')",
    ],
)
def test_ordinary_subqueries_still_pass(sql, cache):
    inspected = inspect_query(sql, cache, LIMITS)
    assert "db.main.T" in inspected.tables


def test_subquery_tables_reach_the_relation_check(cache):
    inspected = inspect_query(
        "SELECT ID FROM db.main.T WHERE ID IN (SELECT UID FROM db.main.U)",
        cache,
        LIMITS,
    )
    assert inspected.tables == ["db.main.T", "db.main.U"]
