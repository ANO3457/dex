**`explore query` refuses time travel.** The query firewall approved a read of a
table's past, such as `FOR VERSION AS OF` on Databricks, `FOR SYSTEM_TIME AS OF`
on BigQuery, or `AT(...)`, `BEFORE(...)` and `CHANGES(...)` on Snowflake, as if it
were a read of the table as it is now, and sent the clause on unchanged. The
exploration cache and its PII verdicts describe the current table, so `SELECT *`
over an older snapshot could return a column that had since been dropped and was
never profiled or flagged. Any table reference that carries a version, a point in
time, or a change stream is now refused before anything reaches the warehouse,
wherever it appears in the statement, including inside a `WHERE` subquery. The
check matches sqlglot's node shape rather than a dialect, so a dialect added
later is covered without a change here. Reading the current table is unaffected.
