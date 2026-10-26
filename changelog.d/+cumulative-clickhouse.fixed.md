`explore profile --check-cumulative` runs on ClickHouse. The detector's probe
used `LAG`, which ClickHouse does not have, so the check failed there; it now
uses `lagInFrame` over an explicit frame, with a NULL default so an entity's
first row is not counted as an observation.
