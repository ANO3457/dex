**`explore --use-project` reads a model's declaration back.** `explore profile`
and `explore map` carry each declared model's declaration as `declaration` on the
relation it builds: its grain, its population rule, and each declared column's
role, unit, additivity and `references`. The declared grain is reported as
`grain`, while `candidate_keys` stays measured and `grain_status` says whether
measurement proves, contradicts or cannot speak to it. A column's `references`
becomes a declared join with `declared_by` naming the declaration; when a
`relationships` test states the same join it stays one edge with both sources.
The declaration is read from the repository on every run and never cached, so a
removed declaration clears on the next run. Declared columns are capped like
profiled ones and the cut is counted. Population values are withheld in
values-free mode and for a filter on a column flagged as personal data. Without
`--use-project` nothing changes.
