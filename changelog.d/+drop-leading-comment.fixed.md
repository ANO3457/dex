**A removed YAML entry no longer leaves its comment behind, or takes a blank line
that is not its own.** When `maintain reconcile` drops a column from a
declaration, or `transform remove` removes an entry, the full-line comments
written directly above it at the same indent go with it, instead of ending up
above the next entry and describing a column they were never written about. A
comment set apart by a blank line is a header for what follows it and stays. And
when reconcile removes a `not_null` test from a block-style test list, the blank
line after the list now stays, so the separator between two columns survives.
