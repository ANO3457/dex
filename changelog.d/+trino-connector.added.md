**Trino is a connector: self-hosted Trino, Starburst Enterprise and Trino on
EMR.** Install `exmergo-dex-core[trino]` and set `connector: trino`. The whole
explore, transform and maintain loop runs against `catalog.schema.table`
relations, always written in full, since dex connects with no session catalog.
Scans are priced in cluster-seconds from a free `EXPLAIN (TYPE IO)` and capped
server-side with `query_max_run_time` and `query_max_scan_physical_bytes`, on
dex's own queries and on dbt builds through the rendered profile. Connections
come from `TRINO_URL`, the `TRINO_*` environment, committed config, or a dbt
profile, with password or JWT auth over HTTPS. Starburst Galaxy is accepted in
config and refused until its uptime billing is modeled. Setup, the cost model
and an access-control rule that makes the dex identity read-only are in
`references/trino.md`.
