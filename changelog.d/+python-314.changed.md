**Dependency bounds are explicit where a major would break dex.** The `[duckdb]`
extra is now `duckdb>=1.5,<3`, and the Snowflake connector is held below 5,
matching dbt-snowflake. sqlglot stays below 31, and motley-slayer stays at
exactly 1.2.0. In the lock, sqlglot moves to 30.24, DuckDB to 2.0.0, the
Snowflake connector to 4.8, and the Databricks SDK and SQL connector to 0.117 and
4.4. Other drivers get patch and minor refreshes, while pandas and pyarrow stay on
their current majors. A weekly canary runs the suite against the newest DuckDB
and sqlglot on every supported Python, so lifting a ceiling is a decision taken
on evidence.
