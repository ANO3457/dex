**SLayer metric queries answer the same on every Snowflake and Redshift
account.** On Snowflake, `--grain week` and `--grain week_sunday` followed the
account's `WEEK_START`, so an account set to Sunday bucketed `week` from Sunday
and `week_sunday` from Saturday. dex now pins both to the day the grain names,
whatever `WEEK_START` says. On Redshift, a model or column spelt with capitals
(`Orders.Status`) came back under the lowercase name Redshift folds a quoted
identifier to; it now comes back as the model spells it, and two result columns
that differ only in case are refused by name. Postgres now has a live smoke run
of a SLayer query beside BigQuery, Snowflake and Redshift.
