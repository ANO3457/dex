**ClickHouse statement refusals use the shared warehouse error type.** Server
errors outside the existing named connection and budget refusals now raise
`WarehouseQueryError`, retaining the server code and query stage with a bounded
diagnostic. A refused grain measurement no longer aborts verification of the
other models, and values-free mode reports `warehouse_refused` while withholding
the server's message.
