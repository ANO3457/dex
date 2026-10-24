**`transform plan` drafts the measured half of each model's declaration.** For
every model a plan creates, edits or declares, `data.declarations.<model>` carries
`drafted` (the grain, keys and references, PII and NULL facts, running totals,
unit shapes and filtered value domains the `.dex/` cache and the SQL support, each
with its evidence), `declared` (what the model's YAML says once the plan lands)
and `missing` (the intent fields nobody has supplied). Each missing field is a
warning, naming what the SQL already implies where it can ("fct_orders declares
no population rule; its SQL filters on status"). Drafting reads the cache and the
repository only, so it is free on every connector; an unprofiled input is named
with the command that would profile it, a fact the cache cannot support is left
out with the reason, and a PII-flagged column's values are never drafted. A draft
is never written into the project.
