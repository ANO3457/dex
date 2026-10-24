**`transform plan` shows how the project already decides.** For each upstream
column a planned model filters, branches on or aggregates, the declaration draft
now carries `precedent`: what the project's other models reading the same relation
do with that column, grouped by the predicate, `CASE` condition or aggregation they
write, with counts and model names ("4 models exclude `('cancelled', 'returned')`,
1 keeps every status"). Column identity follows aliases and CTEs, so a column of
the same name on another relation is not counted, and conflicting precedent stays
visible. A reader dex cannot read statically, or a `ref()` it cannot resolve, makes
the answer `incomplete` with the reason, in the vocabulary `transform references`
uses. The same answer is available before any SQL is written from
`transform references <model.column> --usage`. A plan also warns when a filter
compares a column to a literal its complete cached value domain never holds,
naming any value that matches it ignoring case and whitespace; it never refuses,
and stays silent on a capped domain or a PII-flagged column. All of it reads the
repository and the cache only, so it is free on every connector.
