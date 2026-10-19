**A BigQuery profile note no longer quotes the server's message.** When BigQuery
refused a profiling batch, the `data_quality` note copied the server's error text,
which can quote the value a statement failed on, into the cache and from there
into `explore map`. The note now names BigQuery's structured reason code instead.
