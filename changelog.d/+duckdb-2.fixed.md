**DuckDB 2.0 is supported.** DuckDB 2.0 removed `fetchone()` from relations, so
every DuckDB project's `connect test` failed with `reason: internal`. The
capabilities check now reads the engine version through a cursor. The `[duckdb]`
extra admits DuckDB 1.5 through 2.x (`duckdb>=1.5,<3`), and the whole suite,
dbt-duckdb builds included, passes on 2.0 under Python 3.11 to 3.14. A database
file that DuckDB 2.0 creates, such as a new `dex demo` warehouse, uses a storage
format DuckDB 1.x cannot open. A file DuckDB 1.x created keeps its format when
dex reads it and when dbt builds into it on 2.0.
