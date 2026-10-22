**`.dex/` state names the engine that wrote it, and a second engine is named.**
The plugin built its bundled engine as version `0.0.0`, so `cache.json` and
`snapshot.json` recorded `tool_version: 0.0.0`; they now record the release the
plugin ships. When the project pins a different `exmergo-dex-core` in `uv.lock`
or `pyproject.toml`, every envelope carries one warning naming both versions,
and reading a cache or drift baseline written by another release warns too.
