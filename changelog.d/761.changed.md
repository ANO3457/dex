**`transform build` names the incremental lines of its estimate that are upper
bounds.** On BigQuery, an incremental model's batch filter is usually a watermark
computed by a subquery over the model's own relation. A dry run cannot prune
partitions on that bound, and the job does when it runs, so the model's
`per_table_bytes` line priced the whole history while the build billed only the
window. The line is unchanged, since it is still the most the job can bill, but
the confirmation now maps each such node to the column it bounds under
`data.upper_bounds`, and a note and the over-ceiling refusal say how much of the
estimate those lines are, so a build refused on an over-estimate no longer reads
as a genuinely expensive one.
