**Reading a SLayer layer no longer changes the SQL dex generates.** Importing
SLayer adds its reserved words to sqlglot's quoting rules for every dialect, for
the rest of the process. After any command read a SLayer model, the SQL dex
regenerates itself (the query firewall's row cap, `transform test --mutate`, row
attribution in `transform plan`) quoted those words too. On Snowflake,
`SELECT values FROM t` became `SELECT "values" FROM t`, which names a different,
case-sensitive column. dex now puts sqlglot's own rules back after SLayer
loads, and applies SLayer's only while SLayer renders a query or computes schema
drift. SLayer's own SQL still quotes them.
