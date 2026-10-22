**On DuckDB, `transform test --mutate` now runs the downstream tests by
default.** A defect that a test on a model downstream catches moves from
`survived` to `caught_downstream`. `score` is unchanged; `--no-downstream`
restores the previous selection exactly. Every connector's `data.counts` now
carries `caught_downstream`, zero when the downstream tests did not run.
