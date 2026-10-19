**Values-free mode: explore a warehouse with no table value in any result.** A
host whose model may see no cell value selects it with `--values-free`, pins it
for every command with `DEX_RESULT_MODE=values_free`, or builds
`DexEngine(result_mode="values_free")`, which pins the engine so a call asking
for full results is refused. `.dex/config.yml` never selects it. In the mode
`explore profile` withholds `min_value`, `max_value` (numeric ones too) and
`value_domain`; `explore query` accepts only statements whose every output column
is an allowlisted aggregate (`COUNT`, `COUNT(DISTINCT ...)`, `SUM`, `AVG`, the
`STDDEV` and `VARIANCE` family, and the like) returning one row, and refuses
column-keyed `GROUP BY`, `MIN`/`MAX` and other value-returning aggregates,
`DISTINCT`, `LIMIT`, `ORDER BY` and windows with a stable code and no cell; an
error carries a code instead of a warehouse's words; commands not reviewed for the
mode refuse; and every envelope says `data.result_mode: "values_free"`. A
conformance suite ships in the package (`exmergo_dex_core.values_free_conformance`,
extra `[values-free-conformance]`) so a host can check the release it pins. The
mode does not stop membership probing (`count(*) where email = '...'`), a count of
one identifying a row, or an aggregate over a single row returning that row's
value; a host bounds those with a cost ceiling and a query budget.
