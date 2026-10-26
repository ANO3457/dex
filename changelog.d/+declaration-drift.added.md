**`maintain` reports a changed declaration as drift, even when the SQL is
untouched.** A declaration records which rows a model keeps, what one row is and
how each measure adds up, so changing one changes what the model's numbers mean.
`maintain snapshot` now fingerprints each model's declaration (its descriptions
and `config.meta.dex`, per model and per column) as one hash per field, and
reports the count as `data.transform_layer.declared_model_count`. `maintain
semantic` and `maintain check` report `declaration_changed`, naming the model,
the column and the field, plus `declaration_added` and `declaration_removed`.
A population, grain, additivity, unit or aggregation change ranks above a
description change. Reflowing a description, reordering a grain or moving the
entry to another file is not a change. The check reads only the repository and
the snapshot, so it is free on every connector. `data.declaration_drift` says
whether it ran. A baseline pinned before this release reports it as unchecked,
with a warning, rather than as clean: re-run `maintain snapshot --project-only`
to baseline declarations without re-measuring the warehouse. `maintain
reconcile` answers these findings with advisories and never rewrites a
declaration.
