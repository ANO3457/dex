**`explore semantic query` screens the columns a query reads without naming
them.** The PII gate checked the tokens a caller named in `--group-by` and
`--where` against the profile. Some columns reach the result through a token
that has no column behind it, and those were screened by name only:
`metric_time`, a token carrying a grain suffix, a dimension defined as an
expression (`upper(email)` named `contact_key`), and a SLayer saved measure in a
filter (`revenue > 100` reads `amount`). Now `metric_time` is screened as each
measure's time dimension. A grain-suffixed token is screened as the dimension it
buckets. An expression is screened by every column it reads, and refused when
dex cannot parse it. A saved measure is screened by the columns its formula
reads. A `query` result also names each dimension that only the name heuristic
screened, as `values` already did. The hosted backend cannot resolve
`metric_time`, so it discloses that `metric_time` was screened by name.
