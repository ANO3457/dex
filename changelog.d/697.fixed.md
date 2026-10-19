**`transform build --verify` settles as one calibration point.** A build's dbt
settlement row was written with a `null` `reservation_id`, while the folded
`--verify` count statements settled through the cost gate under the gate's
`reservation_id`. Both rows carried the combined build-plus-verification
estimate, so `settled_ratios` treated one verified build as two separate
runs (each dividing only its own half of the actual spend by the whole
estimate) and pulled over-ceiling calibration hints down and reached the
3-run sample threshold early. `transform build` now stamps its dbt settlement
row with the gate's `reservation_id` when a gate exists (`null` only when the
build settled with no gate), so the dbt row and verification rows join into a
single billed-over-estimated ratio.
