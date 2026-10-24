**`transform plan` warns when an edit contradicts what the model declares.** On a
model that already exists and carries a declaration, the plan now names each
declared rule the edit breaks: a population filter whose predicate is removed or
changed, a changed `GROUP BY` or a dropped grain column, a dropped declared column
(naming what it was declared as), and a `SUM` of a column the upstream model
declares `semi_additive` or `non_additive`, or an `AVG` of a declared ratio. Each
warning names the rule, the changed SQL, the side that looks stale, and both fixes:
update the declaration in the same plan when the change is the job, or restore the
SQL. A change made to both sides that agrees is silent, a declaration-only change is
never blamed on the SQL, a reformat or alias rename is silent, and a predicate dex
cannot read (a macro, a function around the column) is reported as unchecked rather
than removed. The same findings are listed under
`data.declarations.<model>.contradictions`. A contradicted population cites the row
delta row attribution measured: free on DuckDB, and named without measuring on a
billed connector unless `--attribute-rows` is passed. Warnings only; nothing refuses
a plan or blocks apply.
