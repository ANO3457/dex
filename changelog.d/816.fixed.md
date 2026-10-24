**`transform plan --scaffold` names the source's database on Snowflake,
Databricks and BigQuery.** The scaffolded source declared only a schema, so dbt
resolved it in the dev target's database, catalog or project, and a model over
a source that lives elsewhere (`SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.CUSTOMER` with a
different `dev_database`) failed to build. New sources now carry `database:`,
as they already did on Trino. The source keeps its schema name, so existing
`source()` calls still resolve. DuckDB, Postgres and Redshift are unchanged:
one connection is one database there.
