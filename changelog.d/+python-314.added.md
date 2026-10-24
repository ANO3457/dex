**Python 3.14 is supported.** dex now installs and runs on Python 3.11 through
3.14, and CI tests all four, including every optional extra and fresh wheel
installs. To get there, the dbt stack moves as one tested group: dbt Core 1.12.5
(held below 1.12.6, the ceiling dbt-databricks 1.12.7 sets), dbt-adapters 1.24,
dbt-common 1.38, Mashumaro 3.17, and the 1.12 adapters (dbt-duckdb 1.11,
dbt-snowflake 1.12, dbt-bigquery 1.12, dbt-databricks 1.12.7, dbt-postgres 1.11,
dbt-redshift 1.11, dbt-clickhouse 1.10.3, dbt-trino 1.10.6). The connector extras'
dbt adapter floors rise to those lines, because older adapters pull a dbt Core
that cannot import on 3.14. The `[semantic]` extra moves to MetricFlow 0.213, the
line dbt 1.12 requires, and semantic authoring validates against its schemas.
