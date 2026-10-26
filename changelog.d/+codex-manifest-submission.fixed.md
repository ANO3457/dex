**The Codex manifest is ready for the OpenAI plugin directory.** It no longer
declares an empty `interface.screenshots`, which a skills-only upload refuses,
and its long description says the engine ships inside the plugin, with uv
downloading only its Python dependencies, rather than that the first command
downloads the engine from PyPI.
