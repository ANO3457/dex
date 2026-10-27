**`explore semantic query --local` runs on Postgres.** Every local metric query on
the Postgres connector failed before rendering, because Dex looked MetricFlow's
Postgres renderer up under a class name MetricFlow does not use. A test now
builds the renderer for every connector local metric queries support, so a
misspelling fails in the suite rather than on a user's first query.
