**Fresh installs trust only the corrected CA bundle.** The engine now requires
`certifi>=2026.10.19`, the first release without the emSign root certificates
that were withdrawn after their private keys were found to be trivially weak.
Every TLS connection dex makes, to a warehouse, the hosted Semantic Layer or the
dbt package hub, trusts that bundle, and a stale one leaves those connections
open to interception. The skill wrappers also warn when the `uv` on `PATH`
is older than 0.13.4, the first release with the corrected roots, and name the
update. If you install dex with pip, use pip 26.2.2 or later.
