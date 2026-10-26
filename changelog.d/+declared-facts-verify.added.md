`transform build --verify` and `maintain verify` now check what a model's
declaration says against the relation dbt built. A declared grain is the first
grain source, so a composite grain is checked with no `dbt_utils` test. Three new
findings: `unit_out_of_range` (a `fraction` outside 0 to 1, or a `percent` whose
values all sit within 0 to 1, stating the observed minimum and maximum),
`additivity_contradicted` (a column declared `additive` that the cumulative
detector reads as a running total), and `population_contradicted` (a value a
population filter excludes still present, stated as a count). Every check is an
aggregate-only statement, free on DuckDB and priced into the same single estimate
or offer on a billed connector. `data.suppressed` names `unit`, `additivity` and
`population` whenever one could not run, so a declaration that was not checked
never reads as one that held.
