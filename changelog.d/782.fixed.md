**`maintain grain` says a lost key fans out joins only when a join uses it.**
Every `key_lost_uniqueness` and `declared_grain_not_unique` detail ended with
"joins on it will fan out", including on keys that no relationship joins on.
The clause now appears only when a known relationship, verified or not, matches
on that key or combination, and the finding lists those relationships in
`data.joins`, in the shape `fully_null_column` uses. A key no relationship uses
ends with "no known join uses it" and has no `data.joins`. Severity is unchanged.
