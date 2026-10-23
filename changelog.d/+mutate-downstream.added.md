**`transform test --mutate` counts the tests downstream of the model.** With
`--downstream`, the tests of the models that read the mutated one run against
each mutant too. Those models are routed through as ephemeral in the throwaway
copy, so nothing is materialized. A defect only those tests catch is reported as
`caught_downstream`, with the tests in `caught_downstream_by`. `score` still
counts it as a miss for the model's own suite, and the new
`score_with_downstream` counts it as caught. `data.downstream` names the routed
models, the tests that ran, the ones left out and why. On metered connectors it
is opt-in and priced into the same single estimate.
