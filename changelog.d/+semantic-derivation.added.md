**`transform plan` derives a declared mart's semantic model.** When a plan creates,
edits or declares a model under `transform.marts_paths` (a new `.dex/config.yml`
setting, default `[models/marts]`) and the model carries a declaration, the
engine derives the MetricFlow semantic model the declaration states and reports
it as `data.semantic_proposal`. A single-column grain becomes the primary entity,
foreign keys become entities (reusing the name the referenced model's semantic
model already gives the column), dimension and time columns become dimensions,
measures keep their declared aggregation, and a `semi_additive` measure carries
`non_additive_dimension` on the default time dimension. A composite grain, an
aggregation with no MetricFlow equivalent and a name already declared are named
rather than guessed around, and metrics are never derived. Where the project
already has a dbt semantic layer and a time spine, the derivation is added to the
same plan. Where it does not, nothing is added and the proposal is ready for
`semantic plan --definitions-file`. Every derivation passes MetricFlow's schemas,
the metric-input check and dbt's parse of a throwaway copy of the project before
it is offered, and that parse runs even under `semantic plan --no-parse`.
