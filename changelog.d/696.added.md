**`explore semantic query` and `values` run on a SLayer layer.** Under
`semantic.vendor: slayer` both commands used to refuse. They now answer locally:
SLayer renders the SQL as a dry run, and dex runs it through the same PII gate,
relation check, cost confirmation and result cap as a local dbt layer, so results
report `execution: dex`. SLayer never opens a datasource, reads a credential or
touches the warehouse. A query takes saved measures named `model.measure` from
one model, groups by that model's own columns (`orders.status`), buckets its
default time dimension with `--grain`, and filters with `--where` in SLayer's own
syntax (`status = 'paid'`). `values` reads a column's domain on its own model, or
the values present for one metric with `--metric`. DuckDB, BigQuery, Snowflake,
Postgres and Redshift are supported; Databricks and ClickHouse are refused with
the reason, because SLayer's SQL for them would return wrong numbers or need a
live server.
